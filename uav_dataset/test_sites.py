"""Tests for the competing-sites scenarios (D-52), the activity mask, the event_countdown observation and B8.
Run: python -m pytest test_sites.py"""
import numpy as np
import pytest

import make_dataset as md
import oracle as orc
import sites_exp
import uav_env
from baselines import make_policy
from run_baselines import run_episode
from uav_env import UAVEnv

SMALL = {"n_users": 100}
SMALL_GRID = {"grid_n": 4, "altitude_levels_m": [100, 200]}      # a tiny B6 / oracle grid for fast tests


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    md.apply_profile("default")                      # a profile must never leak into other tests


def sites(profile="sites_base", **over):
    md.apply_profile(profile)
    for sec, kv in over.items():
        md.CFG[sec].update(kv)


def all_active(monkeypatch):
    """Force the masked code path with a mask in which everyone is always active."""
    real = md.activity_mask
    monkeypatch.setattr(md, "activity_mask", lambda u, T, dt: np.ones((T + 1, len(u)), bool)
                        if real(u, T, dt) is None else real(u, T, dt))


def rollout(env, seed, actions, groups):
    env.reset(seed=seed)
    out = []
    for a in actions:
        obs, r, term, trunc, info = env.step(a)
        out.append((env.x, env.y, env.h, info["coverage"], info["energy_step_j"], r, info["sum_rate_mbps"],
                    info["outage_rescue"], info["fairness"], info["served"].copy(), obs.copy(),
                    env.observation(groups).copy()))
    ev = env.evaluate([300.0, 700.0], [400.0, 600.0], [100.0, 200.0], env.p_max_w, t=50)
    return out, ev


# ---------------------------------------------------------------- old behaviour is protected
@pytest.mark.parametrize("access", md.ACCESS_SCHEMES)
def test_all_active_mask_reproduces_the_old_run_bit_exact(monkeypatch, access):
    acts = np.random.default_rng(1).uniform(-1, 1, (25, 4))
    groups = uav_env.ALL_GROUPS
    old = rollout(UAVEnv(access=access, scenario_overrides={**SMALL, "mobility": "surge"}), 3, acts, groups)
    all_active(monkeypatch)
    env = UAVEnv(access=access, scenario_overrides={**SMALL, "mobility": "surge"})
    new = rollout(env, 3, acts, groups)
    assert env.active is not None and env.active.all()                 # really the masked path
    for a, b in zip(old[0], new[0], strict=True):
        for x, y in zip(a, b, strict=True):
            assert np.array_equal(x, y)
    assert np.array_equal(old[1], new[1])


def test_all_active_mask_reproduces_b6_bit_exact(monkeypatch):
    md.CFG["uav"]["a_max_mps2"] = 4.0
    base = run_episode(UAVEnv(battery_wh=12.0, scenario_overrides=SMALL), make_policy("B6"), 5)
    all_active(monkeypatch)
    again = run_episode(UAVEnv(battery_wh=12.0, scenario_overrides=SMALL), make_policy("B6"), 5)
    assert base == again


def test_feature_is_off_by_default():
    assert "sites" not in md.CFG["mobility"]["choices"]
    assert "event_countdown" not in uav_env.OBS_GROUPS
    for s in range(5):
        sc = md.make_scenario(s)
        assert "event_t0_s" not in sc and sc["mobility"] != "sites"
        u = md.make_users(s, sc)
        assert "active_from_s" not in u and md.activity_mask(u, 300, 1.0) is None
    env = UAVEnv()
    obs, _ = env.reset(seed=0)
    assert env.active is None and obs.shape == (211,)
    assert env.event_countdown() == 1.0


def test_hard_profile_is_unchanged_by_the_new_section():
    md.apply_profile("hard")
    assert md.CFG["sites"] == md.BASE_CFG["sites"] and "sites" not in md.CFG["mobility"]["choices"]
    assert md.CFG["uav"]["a_max_mps2"] is None and md.CFG["env"]["access"] == "noma"


# ---------------------------------------------------------------- scenario generator
@pytest.mark.parametrize("D", [1000.0, 1500.0, 2000.0])
def test_site_distance_is_D_and_every_site_is_inside_the_map(D):
    sites(sites={"distance_m": D})
    L = md.CFG["area_m"]
    for s in range(15):
        sc = md.make_scenario(s)
        c, r = np.column_stack([sc["site_x"], sc["site_y"]]), np.array(sc["site_radius_m"])
        assert np.hypot(*(c[1] - c[0])) == pytest.approx(D, abs=1e-6)
        assert ((c - r[:, None] >= 0) & (c + r[:, None] <= L)).all()
        if sc["n_sites"] == 3:
            assert min(np.hypot(*(c[2] - c[0])), np.hypot(*(c[2] - c[1]))) >= md.CFG["sites"]["min_separation_m"]
        lo, hi = md.CFG["sites"]["t0_range_s"]
        assert lo <= sc["event_t0_s"] <= hi and 0.5 <= sc["event_share"] <= 0.7 and sc["n_sites"] in (2, 3)


def test_event_draws_are_the_same_in_every_cell_and_seeded():
    keys = ("event_t0_s", "event_share", "n_sites", "site_radius_m", "n_users")
    draws = []
    for cell in sites_exp.CELLS:
        md.apply_profile(cell)
        draws.append([md.make_scenario(s)[k] for s in range(6) for k in keys])
    assert all(d == draws[0] for d in draws)                          # paired cells: same event per seed
    assert len({md.make_scenario(s)["event_t0_s"] for s in range(20)}) > 1


def test_transfer_schedule_follows_the_parameters():
    for tau in (0.0, 60.0, 180.0):
        sites(sites={"tau_s": tau})
        env = UAVEnv(scenario_overrides=SMALL)
        env.reset(seed=2)
        sc, u, A = env.sc, env.users, env.active
        t0, n, m = sc["event_t0_s"], sc["n_users"], md.n_movers(sc)
        assert m == round(sc["event_share"] * n) and len(u) == n + m
        assert (A.sum(axis=1) == n).all()                             # the number of active users never changes
        assert (A[:t0] == A[0]).all() and A[0, :n].all() and not A[0, n:].any()   # nothing changes before t0
        movers = np.flatnonzero(A[0] & ~A[-1])
        assert len(movers) == m and (u.cluster_id.values[movers] == 0).all()     # movers come from site A
        assert (u.cluster_id.values[n:] == 1).all() and A[-1, n:].all()           # their twins appear at site B
        assert sorted(u["class"].values[movers]) == sorted(u["class"].values[n:])  # same demand mix
        for t in (t0, t0 + tau / 2, t0 + tau, 299):
            t = int(t)
            switched = int((~A[t, movers]).sum())
            expect = m if tau == 0 else min(m, int(np.floor((t - t0) * m / tau)) + 1)
            assert switched == expect and int(A[t, n:].sum()) == expect
        again = UAVEnv(scenario_overrides=SMALL)
        again.reset(seed=2)
        assert np.array_equal(again.active, A) and np.array_equal(again.P, env.P)   # seeded


def test_walking_speed_caps_and_users_stay_in_their_site():
    sites()
    env = UAVEnv(scenario_overrides=SMALL)
    for s in range(3):
        env.reset(seed=s)
        speed = np.linalg.norm(env.V, axis=2)
        assert speed.max() <= max(md.CFG["sites"]["burst_speed_mps"]) + 1e-9
        assert np.median(speed[:, env.users.cluster_id.values >= 0]) <= max(md.CFG["sites"]["speed_mps"])
        cid = env.users.cluster_id.values
        c = np.column_stack([env.sc["site_x"], env.sc["site_y"]])
        r = np.array(env.sc["site_radius_m"])
        on = cid >= 0
        d = np.linalg.norm(env.P[:, on] - c[cid[on]][None], axis=2)
        assert (d <= r[cid[on]][None] + 1e-6).all()
        assert (speed[:, ~on] == 0).all()                              # scattered users stand still


# ---------------------------------------------------------------- the mask in the env
@pytest.mark.parametrize("access", md.ACCESS_SCHEMES)
def test_coverage_counts_only_active_users_and_resources_go_only_to_them(access):
    sites(sites={"tau_s": 0.0})
    env = UAVEnv(access=access, scenario_overrides=SMALL)
    env.reset(seed=1)
    t0 = env.sc["event_t0_s"]
    c = np.column_stack([env.sc["site_x"], env.sc["site_y"]])
    for _ in range(t0 + 5):
        _, _, _, _, info = env.step(np.array([0.0, 0.0, 0.0, 1.0]))
    m = env.active_mask()
    assert info["n_active"] == env.sc["n_users"] and not info["served"][~m].any()
    assert info["coverage"] == pytest.approx(info["served"][m].mean())
    # the same as allocating to the active subset alone, with the scenario's fixed total bandwidth
    xy, mr, rs = env.users_now()
    g = md.channel_gain(*xy.T, np.array([env.x]), np.array([env.y]), np.array([env.h]), env.boxes)[0]
    if access in md.QOS_SCHEMES:
        served = md.access_rates(g, env.p_max_w, env.noise_psd, env.sc["bandwidth_hz"], mr, access, eps=env.sic_eps,
                                 rescue=rs, rescue_first=env.rescue_first, return_info=True)[1]["served"]
    else:
        r = md.noma_rates(g, env.p_max_w, env.noise_psd, env.sc["bandwidth_hz"], env.sc["pairing"])
        served = r[0 if access == "noma" else 1] >= mr
    assert np.array_equal(served, info["served"][m])
    # moving the INACTIVE users right under candidate drones changes nothing
    X, Y, H = c[:, 0], c[:, 1], np.full(len(c), 100.0)
    before = env.evaluate(X, Y, H, env.p_max_w)
    for t in (5, t0 + 5):
        env.P[t, ~env.active[t]] = c[0]
    assert np.array_equal(env.evaluate(X, Y, H, env.p_max_w), before)


def test_evaluate_t_respects_the_mask_at_time_t():
    sites(sites={"tau_s": 0.0})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=1)
    t0 = env.sc["event_t0_s"]
    c = np.column_stack([env.sc["site_x"], env.sc["site_y"]])
    X, Y, H = c[:2, 0], c[:2, 1], np.full(2, 100.0)
    for t in (0, t0 - 1, t0, 299):
        xy, mr, rs = env.users_now(t)
        assert len(mr) == env.sc["n_users"]
        g = md.channel_gain(*xy.T, X, Y, H, env.boxes)
        want = md.access_rates(g, env.p_max_w, env.noise_psd, env.sc["bandwidth_hz"], mr, env.access,
                               eps=env.sic_eps, rescue=rs, rescue_first=env.rescue_first,
                               return_info=True)[1]["served"].mean(axis=1)
        assert np.array_equal(env.evaluate(X, Y, H, env.p_max_w, t=t), want)
    before, after = env.evaluate(X, Y, H, env.p_max_w, t=t0 - 1), env.evaluate(X, Y, H, env.p_max_w, t=t0)
    assert before[0] > after[0] and after[1] > before[1]               # demand left A and arrived at B


def test_maps_count_only_active_users():
    sites(sites={"tau_s": 0.0})
    env = UAVEnv(obs_groups=("heat_all_u",), scenario_overrides=SMALL)
    env.reset(seed=1)
    env.t = 299
    shares = env.observation(("heat_all_u",)) ** 2
    assert shares.sum() == pytest.approx(1.0, abs=1e-5)                # shares of the ACTIVE users only
    xy, _, _ = env.users_now()
    assert np.allclose(shares, env._shares(xy, env.grid), atol=1e-6)
    assert env.privileged_state()["priv_maps"].shape[0] == len(uav_env.PRIV_CHANNELS)


def test_event_countdown_is_off_by_default_and_correct_when_on():
    sites(sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    obs, _ = env.reset(seed=1)
    assert obs.shape == (211,)                                         # not in the default observation
    groups = ("pos", "event_countdown")
    t0, T = env.sc["event_t0_s"], env.T
    assert env.observation(groups)[-1] == pytest.approx(t0 / T)
    for _ in range(10):
        env.step(np.zeros(4))
    assert env.observation(groups)[-1] == pytest.approx((t0 - 10) / T)
    env.t = t0 + 1
    assert env.observation(groups)[-1] == 0.0
    sites(sites={"announced": False})
    env = UAVEnv(scenario_overrides=SMALL, obs_groups=groups)
    obs, _ = env.reset(seed=1)
    assert obs.shape == (4,) and obs[-1] == 1.0                        # unannounced: 1 (no announced event)
    assert UAVEnv.obs_dim(uav_env.OBS_GROUPS, 10) == 211


def test_mask_aware_heuristics_run_on_sites():
    sites(baselines=SMALL_GRID)
    env = UAVEnv(scenario_overrides=SMALL)
    for name in ("B1", "B2", "B3obsU", "B6", "B8"):
        env.reset(seed=2)
        pol = make_policy(name)
        pol.reset(env)
        for _ in range(12):
            _, _, _, _, info = env.step(pol.act(env))
        assert 0.0 <= info["coverage"] <= 1.0


# ---------------------------------------------------------------- B8
def test_b8_equals_b6_with_an_ample_battery():
    md.CFG["uav"]["a_max_mps2"] = 4.0
    a = run_episode(UAVEnv(battery_wh=100.0, scenario_overrides=SMALL), make_policy("B6"), 5)
    b = run_episode(UAVEnv(battery_wh=100.0, scenario_overrides=SMALL), make_policy("B8"), 5)
    assert a == b


def test_b8_survives_whenever_b7_does():
    md.CFG["uav"]["a_max_mps2"] = 4.0
    res = {p: run_episode(UAVEnv(battery_wh=13.0, scenario_overrides=SMALL), make_policy(p), 5)
           for p in ("B6", "B7", "B8")}
    assert not res["B6"]["survived"] and res["B7"]["survived"]          # the battery binds for hovering only
    assert res["B8"]["survived"]
    assert res["B8"]["coverage_full"] >= res["B6"]["coverage_full"]


def test_b8_circles_only_when_hovering_would_not_last():
    md.CFG["uav"]["a_max_mps2"] = 4.0
    env = UAVEnv(battery_wh=13.0, scenario_overrides=SMALL)
    env.reset(seed=5)
    pol = make_policy("B8")
    pol.reset(env)
    modes = []
    for _ in range(env.T):
        a = pol.act(env)
        need = (env.T - env.t) * md.energy_step_j(0.0, 0.0, env.p_max_w * pol.power)
        modes.append((pol.circling, env.energy_left_j < need, env.t % md.CFG["baselines"]["replan_every_steps"] == 0))
        if env.step(a)[2]:
            break
    for circ, short, decision in modes:
        if short:
            assert circ                                               # never hovers when hovering would not last
        elif decision:
            assert not circ                                           # back to hovering at the next decision


# ---------------------------------------------------------------- oracle on a sites profile
def test_oracle_runs_on_a_sites_profile_and_the_tensor_backed_replay_is_exact():
    sites(sites={"tau_s": 0.0}, baselines=SMALL_GRID)
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=3)
    nodes = orc.oracle_nodes(env)
    cov = sites_exp.shared_tensor(env, nodes)
    assert np.array_equal(cov, orc.coverage_tensor(env, nodes, cache=False))
    S = orc.segment_scores(cov)
    v, at, target, hops = orc.dp_plan(S, orc.hop_graph(nodes, len(nodes) - 1), len(nodes) - 1)
    assert S.max(axis=1).mean() >= v / S.shape[0] - 1e-12
    c, steps = orc.episode_coverage(env, orc.PlanPolicy(nodes, target, "dp"), 3)
    assert c.shape == (env.T,) and steps == env.T
    plain = {p: orc.episode_coverage(env, make_policy(p), 3)[0] for p in ("B6", "B7", "B8")}
    sites_exp.tensor_backed(env, nodes, cov)
    for p, want in plain.items():
        assert np.array_equal(orc.episode_coverage(env, make_policy(p), 3)[0], want), p


def test_shared_tensor_reuses_rows_only_when_the_inputs_match():
    sites(baselines=SMALL_GRID)
    sites_exp._ROWS.clear()
    covs = {}
    for tau in (0.0, 60.0):
        md.CFG["sites"]["tau_s"] = tau
        env = UAVEnv(scenario_overrides=SMALL)
        env.reset(seed=3)
        nodes = orc.oracle_nodes(env)
        covs[tau] = sites_exp.shared_tensor(env, nodes)
        assert np.array_equal(covs[tau], orc.coverage_tensor(env, nodes, cache=False))
    t = orc.sample_times(env)
    t0 = env.sc["event_t0_s"]
    assert np.array_equal(covs[0.0][t < t0], covs[60.0][t < t0])
    assert not np.array_equal(covs[0.0][(t >= t0) & (t < t0 + 60)], covs[60.0][(t >= t0) & (t < t0 + 60)])
    sites_exp._ROWS.clear()
