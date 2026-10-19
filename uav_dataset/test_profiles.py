"""Tests for config profiles (lowpower, bigarea, hard). Run: python -m pytest test_profiles.py"""
import copy

import numpy as np
import pytest

import make_dataset as md
from uav_env import UAVEnv


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    md.apply_profile("default")                      # a profile must never leak into other tests


def test_default_profile_equals_the_base_config():
    md.apply_profile("hard")
    md.apply_profile("default")
    base = copy.deepcopy(md.BASE_CFG)
    for key in base:
        if key != "active_profile":
            assert md.CFG[key] == base[key], key
    assert md.CFG["active_profile"] == "default"


def test_hard_profile_overrides_only_what_it_names():
    md.apply_profile("hard")
    assert md.CFG["area_m"] == 2000 and md.CFG["uav"]["p_max_dbm"] == 20
    assert md.CFG["energy"]["battery_wh"] == 16 and md.CFG["obstacles"]["n_range"] == [3, 8]
    assert "random_waypoint" not in md.CFG["mobility"]["choices"]
    # untouched values keep their base value, even inside a dict that was partly overridden
    assert md.CFG["uav"]["v_max_mps"] == md.BASE_CFG["uav"]["v_max_mps"]
    assert md.CFG["energy"]["P0_w"] == md.BASE_CFG["energy"]["P0_w"]


def test_profiles_edit_nested_dicts_in_place_so_other_modules_see_them():
    held = md.CFG["baselines"]                       # a module-level reference, as baselines.py keeps
    md.apply_profile("hard")
    assert held["grid_n"] == 14
    md.apply_profile("default")
    assert held["grid_n"] == md.BASE_CFG["baselines"]["grid_n"]


def test_unknown_profile_is_an_error():
    with pytest.raises(KeyError):
        md.apply_profile("does_not_exist")


@pytest.mark.parametrize("name", ["lowpower", "bigarea", "hard"])
def test_env_runs_under_each_profile_with_valid_limits(name):
    md.apply_profile(name)
    env = UAVEnv()
    obs, _ = env.reset(seed=5)
    assert env.observation_space.contains(obs)
    assert env.L == md.CFG["area_m"]
    assert env.p_max_w == pytest.approx(10 ** ((md.CFG["uav"]["p_max_dbm"] - 30) / 10))
    for a in np.random.default_rng(0).uniform(-1, 1, (15, 4)):
        obs, r, term, trunc, info = env.step(a)
        assert 0 <= info["x"] <= env.L and 0 <= info["y"] <= env.L and env.observation_space.contains(obs)


def test_scenarios_follow_the_profile():
    md.apply_profile("hard")
    sc = [md.make_scenario(s) for s in range(40)]
    assert all(3 <= c["n_obstacles"] <= 8 for c in sc)
    assert all(c["mobility"] != "random_waypoint" for c in sc)
    users = md.make_users(0, sc[0])
    assert users.x.between(0, 2000).all() and users.x.max() > 1000     # the crowd really uses the bigger map


def test_lower_power_lowers_coverage_for_the_same_drone():
    cov = {}
    for name in ("default", "lowpower"):
        md.apply_profile(name)
        env = UAVEnv(battery_wh=1000.0)
        env.reset(seed=2)
        cov[name] = float(np.mean([env.step(np.array([0.0, 0.0, 0.0, 1.0]))[4]["coverage"] for _ in range(10)]))
    assert cov["lowpower"] < cov["default"]
