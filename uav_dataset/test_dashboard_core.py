"""Tests for the dashboard logic (dashboard_core.py). Fast, and they never import streamlit.
Run: python -m pytest test_dashboard_core.py"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from matplotlib.figure import Figure

import dashboard_core as dc
import make_dataset as md
from baselines import make_policy
from run_baselines import run_episode
from uav_env import UAVEnv

HERE = Path(__file__).parent
SMALL = dict(n_users=100, mobility="surge")       # a small crowd keeps every episode well under a second


@pytest.fixture(autouse=True)
def default_profile():
    md.apply_profile("default")
    dc.clear_caches()
    yield
    md.apply_profile("default")


def test_dashboard_core_does_not_import_streamlit():
    code = "import sys, dashboard_core; assert 'streamlit' not in sys.modules, 'streamlit was imported'"
    r = subprocess.run([sys.executable, "-c", code], cwd=HERE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_scenario_from_settings_is_deterministic_and_respects_overrides():
    s = dc.Settings(profile="hard", seed=7, n_users=200, n_clusters=3, mobility="surge", n_obstacles=4)
    a, b = dc.build_scenario(s), dc.build_scenario(s)
    assert np.array_equal(a["positions"], b["positions"]) and np.array_equal(a["boxes"], b["boxes"])
    assert a["sc"]["n_users"] == 200 and a["sc"]["n_clusters"] == 3 and a["sc"]["mobility"] == "surge"
    assert len(a["boxes"]) == 4 and a["area_m"] == 2000 and a["p_max_dbm"] == 20
    c = dc.build_scenario(dc.Settings(profile="hard", seed=8, n_users=200))
    assert not np.array_equal(a["users_xy"], c["users_xy"])           # another seed is another disaster
    assert md.CFG["active_profile"] == "default"                       # the profile is restored afterwards


def test_invalid_settings_are_rejected():
    for bad in (dict(profile="nope"), dict(access="cdma"), dict(n_users=101), dict(mobility="flying"),
                dict(battery_wh=0)):
        with pytest.raises(AssertionError):
            dc.Settings(**bad)


def test_trace_has_the_columns_and_matches_run_episode():
    s = dc.Settings(seed=4, battery_wh=1000.0, access="noma", **SMALL)
    ep = dc.run_pilot(s, "B2")
    assert list(ep.trace.columns) == dc.TRACE_COLUMNS
    assert len(ep.trace) == ep.steps == 300 and ep.trace.t.tolist() == list(range(1, 301))
    with dc.configured(s):
        ref = run_episode(UAVEnv(access="noma", battery_wh=1000.0, scenario_overrides=s.overrides()),
                          make_policy("B2"), 4)
    assert ep.summary["coverage_full"] == pytest.approx(ref["coverage_full"])
    assert ep.summary["rescue_outage"] == pytest.approx(ref["outage_rescue"])
    assert ep.trace.coverage.mean() == pytest.approx(ref["coverage_alive"])
    assert dc.run_pilot(s, "B2") is ep                                 # cached
    m = dc.metrics_at(ep, 150)
    assert m["t"] == 150 and 0 <= m["coverage"] <= 1 and m["n_users"] == 100


def test_a_dead_drone_shows_in_the_trace():
    ep = dc.run_pilot(dc.Settings(seed=3, battery_wh=0.5, **SMALL), "B0")
    assert ep.steps < 300 and not ep.summary["survived"] and ep.trace.battery_wh.iloc[-1] == 0.0
    assert not dc.metrics_at(ep, ep.steps)["alive"]


def test_frames_render_as_figures():
    for access in ("noma", "noma_opt", "oma"):
        ep = dc.run_pilot(dc.Settings(seed=2, battery_wh=1000.0, access=access, **SMALL), "B3")
        fig = dc.render_frame(ep, 60, show_pairs=True)
        assert isinstance(fig, Figure)
        weak, strong = dc._pairs(ep, 59, 60)
        if access == "oma":
            assert len(weak) == 0
        else:
            assert 0 < len(weak) <= 60 and np.all(weak != strong)
    assert isinstance(dc.render_maps({"a": ep, "b": ep}), Figure)


def test_comparison_returns_one_row_per_pilot_on_the_same_scenario():
    s = dc.Settings(seed=4, battery_wh=1000.0, **SMALL)
    res = dc.compare_pilots(s, ["B0", "random", "B0"])
    assert list(res) == ["B0", "random", "B0 (2)"]
    assert np.array_equal(res["B0"].frames[0][0], res["random"].frames[0][0])
    table = dc.summary_table(res)
    assert len(table) == 3 and table["pilot / scheme"].tolist() == list(res)
    long = dc.long_trace(res, "coverage")
    assert len(long) == 900 and set(long.name) == set(res)


def test_access_comparison_respects_the_scheme():
    s = dc.Settings(seed=6, battery_wh=1000.0, **SMALL)
    res = dc.compare_access(s, "B0", ["noma", "oma", "noma_opt"])
    assert [ep.env.access for ep in res.values()] == ["noma", "oma", "noma_opt"]
    # B0 flies the same path whatever the scheme, so the OMA run must give exactly what the NOMA run reported
    # that fixed OMA would have given at the same positions
    assert np.allclose(res["oma"].trace.coverage, res["noma"].trace.coverage_oma)
    assert np.allclose(res["noma"].trace.coverage, res["noma"].trace.coverage_noma)
    assert res["noma_opt"].summary["coverage_full"] >= res["noma"].summary["coverage_full"] - 1e-9


def test_batch_comparison_gives_a_paired_difference_and_a_verdict():
    s = dc.Settings(seed=10, battery_wh=1000.0, **SMALL)
    bt = dc.batch_compare(s, "B3", "B0", 3)
    assert bt.per_seed["scenario seed"].tolist() == [10, 11, 12]
    assert np.allclose(bt.per_seed["difference (A - B)"], bt.per_seed["B3"] - bt.per_seed["B0"])
    assert bt.diff[0] == pytest.approx(bt.per_seed["difference (A - B)"].mean())
    assert "B3 minus B0" in bt.verdict and "rough" in bt.verdict
    acc = dc.batch_compare(s, "noma_opt", "oma_opt", 2, kind="access", pilot="B0", metric="outage_rescue")
    assert list(acc.per_seed.columns[:2]) == ["scenario seed", "noma_opt"]
    with pytest.raises(AssertionError):
        dc.batch_compare(s, "B3", "B0", dc.MAX_BATCH + 1)


def test_plan_has_its_fields_and_the_battery_advice_is_right():
    small = dict(profile="hard", seed=5, n_users=100)
    low = dc.recommend(dc.Settings(battery_wh=13.0, **small))
    for f in ("x_m", "y_m", "altitude_m", "power_dbm", "coverage", "rescue_served", "centre_coverage",
              "battery_advice", "hover_wh_needed"):
        assert getattr(low, f) is not None
    assert set(low.coverage) == set(md.ACCESS_SCHEMES) and all(0 <= v <= 1 for v in low.coverage.values())
    assert 0 <= low.x_m <= 2000 and 0 <= low.y_m <= 2000
    assert low.altitude_m in md.BASE_CFG["baselines"]["altitude_levels_m"]
    with dc.configured(dc.Settings(**small)):
        hover_w = md.energy_step_j(0.0, 0.0, 0.1)                     # 20 dBm = 0.1 W, full power
    assert low.hover_w == pytest.approx(hover_w)
    assert low.hover_wh_needed == pytest.approx(hover_w * 300 / 3600)  # about 14.5 Wh
    assert not low.battery_ok and "13.0 Wh < 14.5 Wh" in low.battery_advice
    assert f"~{13.0 * 3600 / hover_w:.0f} s" in low.battery_advice and low.cheapest_power_w < hover_w
    high = dc.recommend(dc.Settings(battery_wh=30.0, **small))
    assert high.battery_ok and "30.0 Wh >= 14.5 Wh" in high.battery_advice
    assert (high.x_m, high.y_m, high.altitude_m) == (low.x_m, low.y_m, low.altitude_m)   # the battery does not move it
    assert "Drone deployment plan" in low.markdown() and len(low.table()) > 10
    assert isinstance(dc.render_plan(low), Figure)


def test_plan_coverage_matches_the_env_evaluation():
    s = dc.Settings(seed=1, n_users=100, access="noma_opt")
    p = dc.recommend(s)
    for scheme in ("noma", "oma_opt"):
        with dc.configured(s):
            env = UAVEnv(access=scheme, scenario_overrides=s.overrides())
            env.reset(seed=1)
            assert p.coverage[scheme] == pytest.approx(env.evaluate(p.x_m, p.y_m, p.altitude_m, p.power_w)[0])


def test_battery_advice_text():
    ok, text = dc.battery_advice(20.0, 174.0, 300)
    assert ok and "lasts the whole mission" in text
    ok, text = dc.battery_advice(10.0, 180.0, 300, cheapest=(10.0, 130.0))
    assert not ok and "die at ~200 s" in text and "130 W" in text


def test_works_without_a_models_folder(tmp_path, monkeypatch):
    missing = tmp_path / "nothing_here"
    assert dc.list_models(missing) == {}
    monkeypatch.setenv("UAV_MODELS_DIR", str(missing))
    assert dc.default_models_dir() == missing
    opts = dc.pilot_options()
    assert "B3" in opts and "random" in opts and not any(k.startswith(dc.AI_PREFIX) for k in opts)
    with pytest.raises(ValueError):
        dc.run_pilot(dc.Settings(seed=1, **SMALL), dc.AI_PREFIX + "ghost")


def test_models_are_listed_from_a_folder(tmp_path):
    (tmp_path / "my_ai").mkdir()
    (tmp_path / "my_ai" / "model.zip").write_bytes(b"not really a model")
    (tmp_path / "my_ai" / "config.json").write_text('{"algo": "PPO", "profile": "rl_static", "hold_steps": 10}')
    (tmp_path / "empty_dir").mkdir()
    assert list(dc.list_models(tmp_path)) == ["my_ai"]
    opts = dc.pilot_options(tmp_path)
    assert "rl_static" in opts[dc.AI_PREFIX + "my_ai"]


def test_showcase_material_exists():
    pics, gifs = dc.gallery()
    assert pics and gifs and all(p.exists() for p, _ in pics + gifs)
    assert pics[0][0].name.startswith("1_")                            # numbered book figures first
    assert len(dc.HEADLINES) == 4 and all(h["source"] for h in dc.HEADLINES)
    t = dc.assumptions_table()
    assert t["status / source"].str.contains("engineering assumption").any()


def test_gif_is_made():
    ep = dc.run_pilot(dc.Settings(seed=2, battery_wh=1000.0, **SMALL), "B1")
    gif = dc.make_gif(ep, every=50)
    assert gif[:3] == b"GIF" and len(gif) > 1000
