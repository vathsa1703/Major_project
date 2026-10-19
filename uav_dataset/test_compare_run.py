"""Tests for the pilot-comparison picture. Run: python -m pytest test_compare_run.py"""
import numpy as np
import pytest

import make_dataset as md
from compare_run import compare, draw, summarize_run
from view_run import build_policy, run


@pytest.fixture(autouse=True)
def default_profile():
    md.apply_profile("default")
    yield
    md.apply_profile("default")


def test_compare_runs_every_pilot_on_the_same_scenario(tmp_path):
    res = compare(4, ["B0", "random"], overrides={"n_users": 100, "mobility": "surge"}, battery_wh=1000.0)
    assert list(res) == ["B0", "random"]
    # same scenario: same crowd at the start for every pilot
    assert np.array_equal(res["B0"][1][0][0], res["random"][1][0][0])
    for _, frames, s in res.values():
        assert s["survived"] and s["steps"] == 300 and 0 <= s["coverage_full"] <= 1
        assert len(frames) == 300
    out = tmp_path / "c.png"
    draw(res, 4, "test title", str(out))
    assert out.exists() and out.stat().st_size > 5000


def test_a_dead_drone_counts_as_zero_for_the_rest_of_the_horizon():
    env, frames = run(3, build_policy("B0"), battery_wh=0.5, overrides={"n_users": 100})
    s = summarize_run(env, frames)
    assert not s["survived"] and s["steps"] < env.T and s["battery_left_wh"] == 0.0
    assert s["coverage_full"] == pytest.approx(s["coverage_alive"] * s["steps"] / env.T)
    assert s["coverage_full"] < s["coverage_alive"]


def test_same_pilot_same_scenario_gives_the_same_numbers():
    a = compare(2, ["B1"], overrides={"n_users": 100}, battery_wh=1000.0)["B1"][2]
    b = compare(2, ["B1"], overrides={"n_users": 100}, battery_wh=1000.0)["B1"][2]
    assert a == b
