"""Tests for the baselines, the episode runner and the statistics helpers. Run: python -m pytest test_baselines.py"""
import numpy as np
import pytest

import make_dataset as md
from baselines import POLICIES, B3GridSearch, B5EnergyAware, go_to, kmeans, make_policy
from evalstats import mean_ci, paired_diff
from run_baselines import run_episode, summarize
from uav_env import UAVEnv

BCFG = md.CFG["baselines"]


def _env(seed=3, **kw):
    env = UAVEnv(**kw)
    env.reset(seed=seed)
    return env


# ---------------------------------------------------------------- statistics
def test_mean_ci_no_variation_means_no_uncertainty():
    assert mean_ci([10, 10, 10, 10, 10]) == (10.0, 0.0)
    assert mean_ci([4.0]) == (4.0, 0.0)


def test_mean_ci_shrinks_with_more_data():
    rng = np.random.default_rng(0)
    assert mean_ci(rng.normal(size=400))[1] < mean_ci(rng.normal(size=25))[1]


def test_paired_diff_detects_a_consistent_winner_that_unpaired_would_hide():
    easy = np.array([10.0, 50.0, 90.0, 30.0, 70.0])          # scenario difficulty varies a lot
    mean, hw = paired_diff(easy + 5, easy)
    assert mean == pytest.approx(5.0) and hw == 0.0           # always exactly +5
    assert mean_ci(easy + 5)[1] > 10                          # the unpaired CI is far wider than the 5-point gap


# ---------------------------------------------------------------- helpers
def test_go_to_moves_toward_the_target_and_saturates():
    env = _env()
    a = go_to(env, env.x + 1000, env.y, env.h, 1.0)
    assert a[0] == pytest.approx(1.0) and abs(a[1]) < 1e-9 and a[3] == 1.0
    near = go_to(env, env.x + 3, env.y, env.h, 0.5)
    assert 0 < near[0] < 1 and near[3] == 0.0
    assert go_to(env, env.x, env.y, env.h + 1000, 1.0)[2] == 1.0


def test_kmeans_finds_separated_blobs():
    rng = np.random.default_rng(0)
    pts = np.vstack([rng.normal(c, 5, size=(60, 2)) for c in ([100, 100], [800, 200], [400, 900])])
    centres, labels = kmeans(pts, np.ones(len(pts)), 3, 30, np.random.default_rng(1))
    for truth in ([100, 100], [800, 200], [400, 900]):
        assert np.hypot(*(centres - truth).T).min() < 20
    assert len(set(labels)) == 3


def test_kmeans_weights_pull_the_centre():
    pts = np.array([[0.0, 0.0], [100.0, 0.0]])
    centres, _ = kmeans(pts, np.array([1.0, 9.0]), 1, 5, np.random.default_rng(0))
    assert centres[0][0] == pytest.approx(90.0)


def test_env_evaluate_is_pure_and_matches_a_real_step():
    env = _env()
    state = (env.x, env.y, env.h, env.t)
    before = env.rng.bit_generator.state
    cov = env.evaluate([env.x, 100.0], [env.y, 100.0], [env.h, 150.0], env.p_max_w)
    assert (env.x, env.y, env.h, env.t) == state and env.rng.bit_generator.state == before
    assert cov.shape == (2,) and ((0 <= cov) & (cov <= 1)).all()
    env.fading = False
    pred = env.evaluate(env.x, env.y, env.h, env.p_max_w)[0]
    nxt = env.step(np.array([0.0, 0.0, 0.0, 1.0]))[4]["coverage"]
    assert abs(pred - nxt) < 0.1                               # users move one step in between


# ---------------------------------------------------------------- the six policies
@pytest.mark.parametrize("name", list(POLICIES))
def test_every_policy_returns_valid_actions_for_a_whole_episode(name):
    env = _env(battery_wh=1000.0)
    pol = make_policy(name)
    pol.reset(env)
    for _ in range(25):
        a = pol.act(env)
        assert env.action_space.contains(a.astype(np.float32))
        env.step(a)


@pytest.mark.parametrize("name", list(POLICIES))
def test_every_policy_is_deterministic(name):
    rows = [run_episode(UAVEnv(battery_wh=2.0), make_policy(name), 4) for _ in range(2)]
    assert rows[0] == rows[1]


def test_b0_stays_at_the_centre():
    env = _env(battery_wh=1000.0)
    pol = make_policy("B0")
    pol.reset(env)
    for _ in range(20):
        env.step(pol.act(env))
    assert (env.x, env.y) == pytest.approx((env.L / 2, env.L / 2)) and env.h == pytest.approx(BCFG["altitude_m"], abs=5)


def test_b1_moves_toward_the_biggest_cluster():
    env = _env(battery_wh=1000.0)
    cid = env.users["cluster_id"].values
    big = np.bincount(cid[cid >= 0]).argmax()
    target = env.user_xy()[cid == big].mean(axis=0)
    d0 = np.hypot(*(np.array([env.x, env.y]) - target))
    pol = make_policy("B1")
    pol.reset(env)
    for _ in range(5):
        env.step(pol.act(env))
    assert np.hypot(env.x - target[0], env.y - target[1]) < d0


def test_b3_never_picks_a_worse_spot_than_where_it_is():
    env = _env()
    pol = B3GridSearch()
    pol.reset(env)
    pol.plan(env)
    p_w = env.p_max_w
    here = env.evaluate(env.x, env.y, BCFG["altitude_m"], p_w)[0]
    chosen = env.evaluate(pol.target[0], pol.target[1], pol.target[2], p_w)[0]
    assert chosen >= here - 1e-12


def test_b5_stays_put_when_moving_gains_nothing(monkeypatch):
    env = _env()
    pol = B5EnergyAware()
    pol.reset(env)
    monkeypatch.setattr(env, "evaluate", lambda X, Y, H, p: np.full(len(np.atleast_1d(X)), 0.5))   # flat landscape
    pol.plan(env)
    assert pol.target[:2] == (env.x, env.y)


def test_b5_moves_when_the_gain_is_large(monkeypatch):
    env = _env()
    pol = B5EnergyAware()
    pol.reset(env)

    def fake(X, Y, H, p):
        X = np.atleast_1d(X)
        out = np.zeros(len(X))
        out[0] = 0.9                                            # candidate 0 (grid corner) is far better
        return out

    monkeypatch.setattr(env, "evaluate", fake)
    pol.plan(env)
    assert pol.target[:2] == (0.0, 0.0)


def test_b4_is_reproducible_and_stays_in_bounds():
    outs = []
    for _ in range(2):
        env = _env()
        pol = make_policy("B4")
        pol.reset(env)
        pol.plan(env)
        outs.append((pol.target, pol.power))
    assert outs[0] == outs[1]
    (x, y, h), p = outs[0]
    assert 0 <= x <= env.L and 0 <= y <= env.L and env.uav["h_min_m"] <= h <= env.uav["h_max_m"] and 0.05 <= p <= 1.0


# ---------------------------------------------------------------- runner
def test_run_episode_accounts_for_a_dead_drone_as_zero_coverage():
    row = run_episode(UAVEnv(battery_wh=0.5), make_policy("B0"), 3)
    assert row["steps"] < 300 and not row["survived"]
    assert row["coverage_full"] == pytest.approx(row["coverage_alive"] * row["steps"] / 300)
    assert row["battery_left_wh"] == 0.0


def test_run_episode_survives_with_a_big_battery():
    row = run_episode(UAVEnv(battery_wh=1000.0), make_policy("B0"), 3)
    assert row["survived"] and row["steps"] == 300
    assert row["coverage_full"] == pytest.approx(row["coverage_alive"])


def test_summarize_builds_a_table_with_paired_differences():
    import pandas as pd
    rows = [{"policy": p, "seed": s, "mobility": "surge", "coverage_full": c + s * 0.01, "coverage_alive": c,
             "survived": True, "served_user_s_per_wh": 1.0, "outage_rescue": 0.1, "fairness": 0.5}
            for p, c in (("B0", 0.5), ("B1", 0.6)) for s in range(5)]
    text = summarize(pd.DataFrame(rows))
    assert "| B1 |" in text and "+0.100*" in text and "-0.100*" in text
