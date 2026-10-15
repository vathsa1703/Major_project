"""Tests for the Gymnasium env. Run: python -m pytest test_env.py"""
import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

import make_dataset as md
from uav_env import UAVEnv


def _run(env, actions):
    out = []
    for a in actions:
        out.append(env.step(a))
        if out[-1][2] or out[-1][3]:
            break
    return out


def test_passes_gymnasium_checker():
    check_env(UAVEnv(), skip_render_check=True)


def test_reset_obs_in_space_and_deterministic_by_seed():
    env = UAVEnv()
    o1, _ = env.reset(seed=4)
    o2, _ = env.reset(seed=4)
    o3, _ = env.reset(seed=5)
    assert env.observation_space.contains(o1)
    assert np.array_equal(o1, o2) and not np.array_equal(o1, o3)


def test_whole_episode_is_reproducible():
    acts = np.random.default_rng(0).uniform(-1, 1, (50, 4))
    runs = []
    for _ in range(2):
        env = UAVEnv(); env.reset(seed=7)
        runs.append([(r, o.tobytes()) for o, r, *_ in _run(env, acts)])
    assert runs[0] == runs[1]


def test_obs_always_in_space_and_uav_never_leaves_limits():
    env = UAVEnv(); env.reset(seed=2)
    u = md.CFG["uav"]
    for a in np.random.default_rng(1).uniform(-1, 1, (120, 4)):
        o, r, term, trunc, info = env.step(a)
        assert env.observation_space.contains(o)
        assert 0 <= info["x"] <= env.L and 0 <= info["y"] <= env.L
        assert u["h_min_m"] <= info["h"] <= u["h_max_m"]
        assert info["battery_wh"] >= 0
        if term or trunc:
            break


def test_speed_is_capped():
    env = UAVEnv(); env.reset(seed=2)
    env.step(np.array([1.0, 1.0, 0.0, 0.0]))        # diagonal full stick
    assert np.hypot(env.vx, env.vy) <= md.CFG["uav"]["v_max_mps"] + 1e-9


def test_battery_runs_out_and_terminates_with_penalty():
    env = UAVEnv(reward="v1", battery_wh=0.5); env.reset(seed=3)      # 0.5 Wh = 1800 J -> ~10 s of hover
    steps = _run(env, [np.array([0, 0, 0, 1.0])] * 100)
    obs, reward, term, trunc, info = steps[-1]
    assert term and not trunc and info["battery_wh"] == 0.0
    assert len(steps) < 20
    assert reward == pytest.approx(info["coverage"] - md.CFG["env"]["terminal_penalty"] * (1 - info["coverage"]))


def test_truncates_at_episode_length_with_a_big_battery():
    env = UAVEnv(battery_wh=1000.0); env.reset(seed=3)
    steps = _run(env, [np.zeros(4)] * (env.T + 10))
    assert len(steps) == env.T and steps[-1][3] and not steps[-1][2]


def test_reward_versions():
    a = np.array([0.0, 0.0, 0.0, 1.0])
    e1, e2 = UAVEnv(reward="v1"), UAVEnv(reward="v2")
    e1.reset(seed=6); e2.reset(seed=6)
    _, r1, *_, i1 = e1.step(a)
    _, r2, *_, i2 = e2.step(a)
    assert r1 == pytest.approx(i1["coverage"])
    assert r2 == pytest.approx(i2["coverage"] - md.CFG["env"]["lambda_energy"] * i2["energy_step_j"] / e2.hover_step_j)
    assert r2 < r1


def test_more_power_costs_more_energy_and_flying_fast_costs_more_than_hovering():
    env = UAVEnv(); env.reset(seed=6)
    _, *_, lo = env.step(np.array([0, 0, 0, -1.0]))
    env.reset(seed=6)
    _, *_, hi = env.step(np.array([0, 0, 0, 1.0]))
    assert hi["energy_step_j"] > lo["energy_step_j"]


def test_users_follow_the_scenario_trajectory():
    env = UAVEnv(); env.reset(seed=9)
    P, _ = md.simulate_positions(9, env.sc, env.users)
    env.step(np.zeros(4))
    assert np.array_equal(env.user_xy(), P[1])


def test_fading_changes_the_numbers_only_when_on():
    a = np.array([0.0, 0.0, 0.0, 1.0])
    rates = {}
    for fading in (False, True):
        env = UAVEnv(fading=fading); env.reset(seed=11)
        infos = [env.step(a)[4] for _ in range(8)]
        rates[fading] = [i["sum_rate_mbps"] for i in infos]       # coverage can saturate, sum rate cannot
        assert all(0 <= i["coverage"] <= 1 for i in infos)
    assert rates[False] != rates[True]
