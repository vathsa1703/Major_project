"""Tests for the NOMA/OMA switch in the game and the two NOMA tools (H3). Run: python -m pytest test_noma_access.py"""
import numpy as np
import pandas as pd
import pytest

import make_dataset as md
from uav_env import UAVEnv


@pytest.fixture(autouse=True)
def default_profile():
    md.apply_profile("default")
    yield
    md.apply_profile("default")


def _step(access, seed=3):
    env = UAVEnv(access=access, battery_wh=1000.0)
    env.reset(seed=seed)
    return env, env.step(np.array([0.0, 0.0, 0.0, 1.0]))[4]


def test_noma_is_the_default_and_both_schemes_are_always_reported():
    env, info = _step(None)
    assert env.access == "noma" and info["access"] == "noma"
    assert info["coverage"] == info["coverage_noma"]
    for k in ("coverage_oma", "sum_rate_noma_mbps", "sum_rate_oma_mbps"):
        assert k in info


def test_oma_mode_scores_with_oma_and_sees_the_same_world():
    _, n = _step("noma")
    _, o = _step("oma")
    assert o["coverage"] == o["coverage_oma"]
    # same scenario and the same move, so both report the same NOMA and OMA numbers
    assert n["coverage_noma"] == o["coverage_noma"] and n["coverage_oma"] == o["coverage_oma"]


def test_unknown_access_scheme_is_refused():
    with pytest.raises(AssertionError):
        UAVEnv(access="cdma")


def test_evaluate_uses_the_scheme_being_tested():
    spots = (np.array([300.0, 700.0]), np.array([300.0, 500.0]), np.array([150.0, 150.0]))
    envs = {a: UAVEnv(access=a) for a in ("noma", "oma")}
    for e in envs.values():
        e.reset(seed=4)
    got = {a: e.evaluate(*spots, e.p_max_w) for a, e in envs.items()}
    e = envs["oma"]
    ux, uy = e.user_xy().T
    gains = md.channel_gain(ux, uy, *spots, e.boxes)
    want = [(md.noma_rates(g, e.p_max_w, e.noise_psd, e.sc["bandwidth_hz"], e.sc["pairing"])[1] >= e.min_rate).mean()
            for g in gains]
    assert np.allclose(got["oma"], want)
    assert not np.allclose(got["noma"], got["oma"])


def test_noma_gives_more_total_speed_at_full_power():
    _, info = _step("noma", seed=1)
    assert info["sum_rate_noma_mbps"] > info["sum_rate_oma_mbps"]


def test_h3_table_reports_the_paired_difference():
    from noma_vs_oma import table
    rows = [{"policy": "B0", "seed": s, "access": a, "coverage_full": c + 0.01 * s, "sum_rate_mbps": 10.0 + d,
             "fairness": 0.5, "outage_rescue": 0.1}
            for s in range(5) for a, c, d in (("noma", 0.6, 2.0), ("oma", 0.5, 0.0))]
    text = table(pd.DataFrame(rows))
    assert "| B0 |" in text and "+0.100*" in text and "+2.0*" in text


def test_h3_runner_plays_each_pilot_under_both_schemes():
    from noma_vs_oma import run
    df = run(["B0"], [2, 3], battery_wh=1000.0, workers=1)
    assert sorted(df.access.unique()) == ["noma", "oma"] and len(df) == 4 and df.survived.all()


def test_noma_picture_is_consistent(tmp_path):
    from noma_picture import draw, snapshot
    s = snapshot(1)
    n = s["env"].sc["n_users"]
    assert len(s["weak"]) == len(s["strong"]) == n // 2 and len(s["shown"]) <= 60
    assert s["cov_noma"] == pytest.approx(np.isin(s["status"], ["both", "NOMA only"]).mean())
    assert s["cov_oma"] == pytest.approx(np.isin(s["status"], ["both", "OMA only"]).mean())
    out = tmp_path / "p.png"
    draw(s, "t", str(out))
    assert out.stat().st_size > 5000
