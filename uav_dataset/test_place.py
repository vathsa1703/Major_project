"""Tests for the real-place case study (Kathmandu, Bagmati floods): OSM processing, local metres, the height-aware
line-of-sight test, the reconstructed crowd and the place profile. No network access: everything runs from the
committed processed map places/kathmandu_bagmati.json. Run: python -m pytest test_place.py"""
import copy
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

import make_dataset as md
import osm_place as op
import place
from baselines import make_policy
from run_baselines import run_episode
from uav_env import UAVEnv

PROFILE = "place_kathmandu_bagmati"


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    # apply_profile only overwrites keys, so keys a test added to a profile would survive the reset: restore them too
    md.CFG["profiles"] = copy.deepcopy(md.BASE_CFG["profiles"])
    md.apply_profile("default")                      # a profile must never leak into other tests


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("tests must not touch the network")
    monkeypatch.setattr(op.urllib.request, "urlopen", refuse)


# ---------------------------------------------------------------- coordinates
def test_local_metres_box_corners_centre_and_round_trip():
    lat_c, lon_c, L = 27.69, 85.307, 2000.0
    s, w, n, e = op.bbox_from_centre(lat_c, lon_c, L)
    assert op.to_local(lat_c, lon_c, lat_c, lon_c, L) == pytest.approx((L / 2, L / 2))
    assert op.to_local(s, w, lat_c, lon_c, L) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert op.to_local(n, e, lat_c, lon_c, L) == pytest.approx((L, L), abs=1e-6)
    x, y = op.to_local(27.6931, 85.3012, lat_c, lon_c, L)
    assert op.to_latlon(x, y, lat_c, lon_c, L) == pytest.approx((27.6931, 85.3012), abs=1e-12)
    # 0.001 degree of latitude = 111.19 m on the mean sphere; of longitude: x cos(lat)
    k = math.pi / 180 * op.R_EARTH_M
    assert op.to_local(lat_c + 0.001, lon_c, lat_c, lon_c, L)[1] - L / 2 == pytest.approx(0.001 * k)
    assert op.to_local(lat_c, lon_c + 0.001, lat_c, lon_c, L)[0] - L / 2 == pytest.approx(
        0.001 * k * math.cos(math.radians(lat_c)))


# ---------------------------------------------------------------- OSM processing
def _raw():
    lat_c, lon_c, L = 27.69, 85.307, 2000.0

    def ll(x, y):
        la, lo = op.to_latlon(x, y, lat_c, lon_c, L)
        return {"lat": la, "lon": lo}
    sq = [ll(100, 100), ll(120, 100), ll(120, 120), ll(100, 120), ll(100, 100)]
    return {"elements": [
        {"type": "way", "id": 2, "tags": {"building": "yes", "building:levels": "4"}, "geometry": sq},
        {"type": "way", "id": 1, "tags": {"building": "yes", "height": "12 m"},
         "geometry": [ll(500, 500), ll(530, 500), ll(530, 520), ll(500, 500)]},
        {"type": "way", "id": 3, "tags": {"building": "house"}, "geometry": [ll(3000, 3000), ll(3010, 3000),
                                                                            ll(3010, 3010)]},     # outside the box
        {"type": "relation", "id": 9, "tags": {"building": "yes"}, "members": [
            {"type": "way", "role": "outer", "geometry": [ll(700, 700), ll(760, 700), ll(760, 760), ll(700, 760)]},
            {"type": "way", "role": "inner", "geometry": [ll(720, 720), ll(730, 720), ll(730, 730)]}]},
        {"type": "way", "id": 5, "tags": {"waterway": "river", "name": "Bagmati River"},
         "geometry": [ll(0, 1000), ll(2000, 1000)]},
        {"type": "node", "id": 7, "lat": ll(300, 1500)["lat"], "lon": ll(300, 1500)["lon"],
         "tags": {"amenity": "school", "name": "A School"}},
        {"type": "node", "id": 8, "lat": ll(300, 1500)["lat"], "lon": ll(300, 1500)["lon"],
         "tags": {"amenity": "bank"}}]}


def _pc():
    return {"name": "test", "title": "t", "centre_deg": [27.69, 85.307], "side_m": 2000.0, "levels_m": 3.0,
            "bbox_deg": op.bbox_from_centre(27.69, 85.307, 2000.0)}


def test_process_parses_heights_relations_rivers_shelters_and_is_deterministic():
    raw = _raw()
    p = op.process(raw, _pc())
    b = {x["id"]: x for x in p["buildings"]}
    assert set(b) == {"w1", "w2", "r9"}                         # w3 lies outside the box; the inner ring is dropped
    assert (b["w2"]["h"], b["w2"]["src"]) == (12.0, "levels")    # 4 levels x 3 m
    assert (b["w1"]["h"], b["w1"]["src"]) == (12.0, "height")    # "12 m"
    assert b["r9"]["h"] is None and b["r9"]["src"] == "none"
    assert b["w2"]["xy"] == [[100.0, 100.0], [120.0, 100.0], [120.0, 120.0], [100.0, 120.0]]   # closing vertex dropped
    assert p["rivers"][0]["name"] == "Bagmati River" and p["rivers"][0]["xy"][1] == [2000.0, 1000.0]
    assert [(s["kind"], s["x"], s["y"]) for s in p["shelters"]] == [("school", 300.0, 1500.0)]
    shuffled = copy.deepcopy(raw)
    shuffled["elements"].reverse()
    assert json.dumps(op.process(shuffled, _pc()), sort_keys=True) == json.dumps(p, sort_keys=True)


def test_parse_height_rules():
    assert op.parse_height({"height": "7.5"}, 3.0) == (7.5, "height")
    assert op.parse_height({"height": "x", "building:levels": "2"}, 3.0) == (6.0, "levels")
    assert op.parse_height({"building:levels": "3;4"}, 3.0) == (9.0, "levels")
    assert op.parse_height({}, 3.0) == (None, "none")


def test_committed_place_file_gives_the_same_city_every_time():
    md.apply_profile(PROFILE)
    raw = place.load_place("kathmandu_bagmati")
    assert raw["credit"].startswith("Map data (c) OpenStreetMap contributors")
    assert len(raw["buildings"]) == 12061 and len(raw["shelters"]) == 147
    a = place.Scene("kathmandu_bagmati")
    b = place.Scene("kathmandu_bagmati")
    assert a.fingerprint() == b.fingerprint() == "8cca866ac4209c08989791a07477c595915bd8b3"
    assert np.array_equal(a.dist, b.dist)
    assert a.hmax <= md.CFG["place"]["max_plausible_height_m"]
    assert (a.height_src == 2).sum() == 1                        # the one 25-storey tag is treated as an error


def test_fill_heights_empirical_and_uniform():
    c = dict(md.BASE_CFG["place"])
    bs = [{"h": 6.0}, {"h": None}, {"h": 99.0}, {"h": None}]
    h, src = place.fill_heights(bs, {**c, "min_tagged": 1, "max_plausible_height_m": 45})
    assert list(src) == [0, 1, 2, 1] and h[0] == 6.0 and np.all(h[1:] == 6.0)     # the only plausible tag
    h, _ = place.fill_heights(bs, {**c, "min_tagged": 5})
    lo, hi = c["default_height_range_m"]
    assert np.all((h[1:] >= lo) & (h[1:] <= hi))


# ---------------------------------------------------------------- height-aware line of sight
def toy_scene(height, x0=100, x1=120):
    """A 400 x 400 m map with 1 m cells and one wall of the given height between x0 and x1 (full y range)."""
    grid = np.zeros((400, 400), np.float32)
    grid[x0:x1, :] = height
    return SimpleNamespace(grid=grid, n=400, cell=1.0, hmax=float(grid.max()))


def test_link_over_a_low_building_is_clear_under_a_tall_one_blocked():
    ux, uy, uz = np.array([90.0]), np.array([200.0]), np.array([1.5])
    X, Y, H = np.array([200.0]), np.array([200.0]), np.array([50.0])
    # the ray rises 48.5 m over 110 m: 5.9 m above the ground at the near wall (x = 100), 14.7 m at x = 120
    assert place.ray_clear(toy_scene(3.0), ux, uy, uz, X, Y, H)[0, 0]
    assert not place.ray_clear(toy_scene(10.0), ux, uy, uz, X, Y, H)[0, 0]
    assert not place.ray_clear(toy_scene(40.0), ux, uy, uz, X, Y, H)[0, 0]
    # the same 10 m wall is cleared from higher up (300 m: 28.6 m above the wall at x = 100)
    assert place.ray_clear(toy_scene(10.0), ux, uy, uz, X, Y, np.array([300.0]))[0, 0]
    # a drone straight above the user is always seen; a drone on the user's side of the wall too
    assert place.ray_clear(toy_scene(40.0), ux, uy, uz, np.array([90.0]), np.array([200.0]), H)[0, 0]
    assert place.ray_clear(toy_scene(40.0), ux, uy, uz, np.array([60.0]), np.array([150.0]), H)[0, 0]
    # a user on the roof of the wall (z = roof + 1.5) sees over its own building
    assert place.ray_clear(toy_scene(10.0), np.array([110.0]), uy, np.array([11.5]), X, Y, H)[0, 0]


def test_ray_clear_matches_a_brute_force_reference():
    rng = np.random.default_rng(0)
    grid = (rng.uniform(size=(400, 400)) < 0.02).astype(np.float32) * rng.uniform(3, 30, size=(400, 400)).astype(
        np.float32)
    S = SimpleNamespace(grid=grid, n=400, cell=1.0, hmax=float(grid.max()))
    ux, uy = rng.uniform(0, 400, 30), rng.uniform(0, 400, 30)
    uz = np.full(30, 1.5)
    X, Y, H = rng.uniform(0, 400, 25), rng.uniform(0, 400, 25), rng.uniform(50, 300, 25)
    got = place.ray_clear(S, ux, uy, uz, X, Y, H)
    ref = np.ones_like(got)
    for p in range(25):
        for u in range(30):
            dh = math.hypot(X[p] - ux[u], Y[p] - uy[u])
            k = 1
            while k * S.cell < dh + S.cell and ref[p, u]:
                s = min(k * S.cell, dh)
                x, y = ux[u] + (X[p] - ux[u]) / dh * s, uy[u] + (Y[p] - uy[u]) / dh * s
                z = uz[u] + (H[p] - uz[u]) / dh * s
                i, j = min(int(x), 399), min(int(y), 399)
                if grid[i, j] > z:
                    ref[p, u] = False
                k += 1
    assert np.array_equal(got, ref)


def test_geometric_los_replaces_al_hourani_with_eta_los_or_eta_nlos():
    md.apply_profile(PROFILE)
    links = SimpleNamespace(user_z=lambda ux, uy: np.full(len(ux), 1.5),
                            los_clear=lambda ux, uy, X, Y, H: np.array([[True, False]]))
    ux, uy = np.array([0.0, 0.0]), np.array([0.0, 0.0])
    g = md.channel_gain(ux, uy, np.array([30.0]), np.array([40.0]), np.array([101.5]), links)[0]
    a = md.CFG["a2g"]
    assert 10 * np.log10(g[0] / g[1]) == pytest.approx(a["eta_nlos_db"] - a["eta_los_db"])
    d = math.sqrt(30**2 + 40**2 + 100**2)
    fspl = 20 * math.log10(4 * math.pi * md.CFG["fc_hz"] * d / md.C)
    assert -10 * np.log10(g[0]) == pytest.approx(fspl + a["eta_los_db"])
    md.CFG["place"]["los_model"] = "statistical"                  # sensitivity: Al-Hourani + excess on blocked rays
    g2 = md.channel_gain(ux, uy, np.array([30.0]), np.array([40.0]), np.array([101.5]), links)[0]
    assert 10 * np.log10(g2[0] / g2[1]) == pytest.approx(md.CFG["obstacles"]["excess_loss_db"])


def test_place_links_cache_equals_direct_computation():
    md.apply_profile(PROFILE)
    sc = md.make_scenario(3)
    u = md.make_users(3, sc)
    L = place.links_for(3, u)
    X, Y, H = np.array([500.0, 1500.0, 900.0]), np.array([800.0, 1200.0, 1000.0]), np.array([50.0, 150.0, 300.0])
    act = u.index.values[::3]
    ux, uy = u.x.values[act], u.y.values[act]
    direct = place.ray_clear(L.S, ux, uy, L.user_z(ux, uy), X, Y, H)
    assert np.array_equal(L.los_clear(ux, uy, X, Y, H), direct)
    assert np.array_equal(L.los_clear(ux, uy, X, Y, H), direct)             # from the cache
    assert L.hits >= 3
    fx = ux + 0.25                                                            # not pool users: computed directly
    assert np.array_equal(L.los_clear(fx, uy, X, Y, H), place.ray_clear(L.S, fx, uy, L.user_z(fx, uy), X, Y, H))


# ---------------------------------------------------------------- the reconstructed crowd
def test_place_crowd_follows_the_assumptions():
    md.apply_profile(PROFILE)
    S = place.scene()
    c = md.CFG["place"]
    for seed in (0, 5):
        sc = md.make_scenario(seed)
        u = md.make_users(seed, sc)
        assert sc["mobility"] == "place" and sc["n_obstacles"] == 0
        n = sc["n_users"]
        g = u.group.values
        assert (g[:n] != "evacuee").all() and (g[n:] == "evacuee").all()
        h = S.height_at(u.x.values, u.y.values)
        d = S.dist_at(u.x.values, u.y.values)
        st = g == "stranded"
        assert st.sum() == sc["n_stranded"] and (h[st] > 0).all()            # on roofs ...
        assert np.allclose(u.z_m[st], h[st] + c["user_height_m"])
        bid = S.bid[S.cell_of(u.x.values[st], u.y.values[st])]
        assert (S.b_dist[bid] <= c["flood_band_m"]).all()                     # ... of buildings in the flood band
        assert (h[~st] == 0).all() and (d[~st] > c["flood_band_m"]).all()     # everyone else on open, dry ground
        rescue_share = (u["class"][st] == "rescue").mean()
        assert rescue_share > (u["class"][(g != "stranded") & (g != "evacuee")] == "rescue").mean()
        act = md.activity_mask(u, 300, 1.0)
        assert (act.sum(axis=1) == n).all()                                   # the number counted never changes
        m = int(round(sc["event_share"] * sc["n_stranded"]))
        assert (~act[-1, :n]).sum() == m and act[-1, n:].all() and not act[0, n:].any()
        assert sorted(u["class"].values[n:]) == sorted(u["class"].values[:n][~act[-1, :n]])   # twins keep class
        assert (g[:n][~act[-1, :n]] == "stranded").all()                     # only stranded people are evacuated
    a, b = md.make_users(5, md.make_scenario(5)), md.make_users(5, md.make_scenario(5))
    assert a.equals(b)                                                         # deterministic


# ---------------------------------------------------------------- the profile runs every pilot
@pytest.mark.parametrize("access", ["noma_opt", "oma_opt"])
def test_place_profile_runs_every_pilot(access):
    md.apply_profile(PROFILE)
    md.CFG["mobility"]["episode_steps"] = 30                    # short episodes for the test
    md.CFG["place"].update(t0_range_s=[5, 8], tau_s=10)          # the evacuation happens inside them
    md.CFG["baselines"].update(grid_n=4, altitude_levels_m=[100, 200])
    covs = {}
    for p in ("B0", "B2", "B3", "B6", "B7", "B8", "B6fc"):
        r = run_episode(UAVEnv(access=access), make_policy(p), 1)
        assert r["steps"] == 30 and 0.0 <= r["coverage_full"] <= 1.0
        covs[p] = r["coverage_full"]
    assert covs["B8"] == covs["B6"]                               # ample battery: B8 hovers like B6


def test_place_scenario_refuses_overrides():
    md.apply_profile(PROFILE)
    with pytest.raises(ValueError):
        UAVEnv(scenario_overrides={"n_users": 100}).reset(seed=0)


def test_payload3d_is_compact_and_complete():
    md.apply_profile(PROFILE)
    S = place.scene()
    p = place.payload3d(S)
    assert p["n_buildings"] == len(S.buildings) and p["n_drawn"] >= 0.99 * len(S.buildings)
    assert all(len(b) % 2 == 1 and len(b) >= 7 for b in p["polys"])
    assert p["rivers"] and p["band"] and "OpenStreetMap" in p["credit"]
    assert len(json.dumps(p, separators=(",", ":"))) < 1_500_000
    assert place.payload3d(S, max_polys=100)["n_drawn"] == 100


def test_dashboard_shows_the_place_in_2d_and_3d(monkeypatch):
    import dashboard_core as dc
    prof = md.BASE_CFG["profiles"][PROFILE]
    monkeypatch.setitem(prof["mobility"], "episode_steps", 12)              # short episodes for the test
    monkeypatch.setitem(prof, "baselines", {**prof["baselines"], "grid_n": 4, "altitude_levels_m": [100, 200]})
    dc.clear_caches()
    s = dc.Settings(profile=PROFILE, seed=2, access="noma_opt")
    assert "OpenStreetMap" in dc.describe(dc.build_scenario(s)) and "not real data" in dc.describe(dc.build_scenario(s))
    ep = dc.run_pilot(s, "B6")
    fig = dc.render_frame(ep, 5)
    assert len(fig.axes[0].collections) >= 2                                  # footprints + people
    data = dc.flight3d(s, "B0")
    p = data["place"]
    assert p["polys"] and p["rivers"] and "OpenStreetMap" in p["credit"]
    z = np.array(data["users"]["z"])
    assert len(z) == data["users"]["n_drawn"] and (z > 0).any() and (z == 0).any()   # roofs and ground
    page = dc.viewer3d_html(data)
    assert "ShapeUtils.triangulateShape" in page and "__FLIGHT_JSON__" not in page
    dc.clear_caches()


# ---------------------------------------------------------------- old profiles are untouched
def test_synthetic_scenarios_still_use_the_rectangles():
    md.apply_profile("hard")
    env = UAVEnv()
    env.reset(seed=7)
    assert isinstance(env.links, np.ndarray) and env.links is env.boxes and len(env.boxes) >= 3
    assert "place" not in env.sc and "group" not in env.users
