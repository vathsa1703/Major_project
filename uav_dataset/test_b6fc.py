"""Tests for B6fc, the forecasting greedy pilot (D-52 phase 3), and the phase 4 runner.
Run: python -m pytest test_b6fc.py"""
import copy

import numpy as np
import pandas as pd
import pytest

import baselines as bl
import make_dataset as md
import oracle as orc
import sites_exp
from baselines import flight_steps, go_to, make_policy
from run_baselines import run_episode
from uav_env import UAVEnv

SMALL = {"n_users": 100}
SMALL_GRID = {"grid_n": 4, "altitude_levels_m": [100, 200]}


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    bl.FC_MEMO = None
    md.apply_profile("default")


def profile(name, **over):
    md.apply_profile(name)
    for sec, kv in over.items():
        md.CFG[sec].update(kv)


def actions(env, pol, seed, n=None, setup=None):
    """Actions of one episode (or its first n steps). setup(env) runs right after reset."""
    env.reset(seed=seed)
    if setup:
        setup(env)
    pol.reset(env)
    out = []
    for _ in range(n or env.T):
        a = pol.act(env)
        out.append(a)
        if any(env.step(a)[2:4]):
            break
    return np.array(out)


# ---------------------------------------------------------------- flight time
@pytest.mark.parametrize("a_max", [None, 4.0])
def test_flight_steps_equal_a_real_go_to_flight(a_max):
    profile("sites_base", uav={"a_max_mps2": a_max})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=1)
    for _ in range(6):                                   # start from a moving drone
        env.step(np.array([0.7, -0.4, 0.3, 1.0]))
    X, Y, H = np.array([300.0, 1500.0, env.x, 1990.0]), np.array([400.0, 200.0, env.y, 1990.0]), \
        np.array([50.0, 300.0, env.h, 150.0])
    got = flight_steps(env, X, Y, H, env.T - env.t)
    for i in range(len(X)):
        e = copy.deepcopy(env)
        k = 0
        while not (np.hypot(X[i] - e.x, Y[i] - e.y) <= 0.5 and abs(H[i] - e.h) <= 0.5):
            e.step(go_to(e, X[i], Y[i], H[i], 1.0))
            k += 1
        assert got[i] == k
    assert np.isinf(flight_steps(env, X[:1], Y[:1], H[:1], 3)[0])     # too far for 3 steps


# ---------------------------------------------------------------- physics path
def test_evaluate_users_is_evaluate_for_the_users_at_t():
    profile("sites_base")
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=2)
    X, Y, H = np.array([300.0, 900.0]), np.array([400.0, 1100.0]), np.array([100.0, 200.0])
    for t in (0, 150, 299):
        assert np.array_equal(env.evaluate(X, Y, H, env.p_max_w, t=t),
                              env.evaluate_users(*env.users_now(t), X, Y, H, env.p_max_w, t))


# ---------------------------------------------------------------- B6fc == B6 without anything to forecast
@pytest.mark.parametrize("a_max", [None, 4.0])
def test_b6fc_is_b6_when_crowds_are_still_and_there_is_no_event(a_max):
    profile("rl_static", baselines=SMALL_GRID, uav={"a_max_mps2": a_max})
    for seed in (1, 4):
        a = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6"), seed)
        b = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6fc"), seed)
        assert a == b


def test_b6fc_is_b6_with_still_crowds_and_an_unannounced_event():
    # unannounced: nothing to forecast but walking, and nobody walks, so every forecast is the present
    profile("sites_base", baselines=SMALL_GRID, sites={"speed_mps": [0.0, 0.0], "burst_prob": 0.0})
    env = UAVEnv(scenario_overrides=SMALL)
    assert np.array_equal(actions(env, make_policy("B6"), 3), actions(env, make_policy("B6fc"), 3))


# ---------------------------------------------------------------- information
@pytest.mark.parametrize("announced", [False, True])
def test_b6fc_never_reads_the_future(announced):
    profile("sites_base", baselines=SMALL_GRID, sites={"announced": announced, "tau_s": 60.0})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=1)
    pol = make_policy("B6fc")
    pol.reset(env)
    t0 = env.sc["event_t0_s"]
    checks = {10 * (t0 // 10) - 20, 10 * (t0 // 10) + 10}                     # decisions before and during the move
    rng = np.random.default_rng(0)
    seen = 0
    while env.t < max(checks) + 1:
        if env.t in checks:
            e, p = copy.deepcopy(env), copy.deepcopy(pol)
            e.P[e.t + 1:] = rng.uniform(0, e.L, e.P[e.t + 1:].shape)          # scramble every future position
            e.V[e.t + 1:] = 0.0
            e.active[e.t + 1:] = rng.uniform(size=e.active[e.t + 1:].shape) < 0.5   # and every future mask
            a_true, a_fake = pol.act(env), p.act(e)
            assert np.array_equal(a_true, a_fake) and pol.target == p.target
            env.step(a_true)
            seen += 1
            continue
        env.step(pol.act(env))
    assert seen == 2


def test_announcement_changes_behaviour_only_when_announced():
    profile("sites_d20_t0", baselines=SMALL_GRID)

    def fake_news(env):                                  # different announcement contents (not the env's physics)
        env.sc.update(event_t0_s=61, event_share=0.99, site_x=env.sc["site_x"][::-1], site_y=env.sc["site_y"][::-1])

    env = UAVEnv(scenario_overrides=SMALL)
    differs = 0
    for seed in (1, 2, 3):
        md.CFG["sites"]["announced"] = False
        u = actions(env, make_policy("B6fc"), seed)
        assert np.array_equal(u, actions(env, make_policy("B6fc"), seed, setup=fake_news))     # never read
        md.CFG["sites"]["announced"] = True
        a = actions(env, make_policy("B6fc"), seed)
        differs += not np.array_equal(a, u)
    assert differs >= 1                                  # the announcement is used when there is one
    profile("hard", baselines=SMALL_GRID)                # no event at all: the flag cannot matter
    env = UAVEnv(scenario_overrides=SMALL)
    plain = actions(env, make_policy("B6fc"), 2, 40)
    assert np.array_equal(plain, actions(env, make_policy("B6fc"), 2, 40,
                                         setup=lambda e: e.sc.update(announced=True)))


def test_announced_forecast_follows_the_announced_schedule():
    profile("sites_base", sites={"announced": True, "tau_s": 60.0})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=2)
    pol = make_policy("B6fc")
    pol.reset(env)
    s = pol.snapshot(env)
    t0, tau = env.sc["event_t0_s"], env.sc["tau_s"]
    true_switched = (env.active[0] & ~env.active).sum(axis=1)                # test-only use of the true mask
    for t in (0, t0 - 1, t0, t0 + 17, t0 + int(tau) - 1, t0 + int(tau), 299):
        assert pol.switched(s, t) == true_switched[t]
    xy_u = pol.forecast(env, s, t0 - 1)[0]
    plain = {k: v for k, v in s.items() if k not in ("t0", "tau", "m", "inA", "dest")}
    assert np.array_equal(xy_u, pol.forecast(env, plain, t0 - 1)[0])       # before t0: velocity forecast only
    after, before = pol.forecast(env, s, t0 + int(tau))[0], pol.forecast(env, plain, t0 + int(tau))[0]
    moved = np.flatnonzero(np.any(after != before, axis=1))
    cB, rB = np.array([env.sc["site_x"][1], env.sc["site_y"][1]]), env.sc["site_radius_m"][1]
    assert len(moved) == min(md.n_movers(env.sc), len(s["inA"]))
    assert (np.hypot(*(after[moved] - cB).T) <= rB + 1e-9).all()           # they are forecast at B
    assert len(after) == len(s["xy"])                                     # the crowd size stays the same


# ---------------------------------------------------------------- determinism, valid actions, memo
def test_b6fc_is_deterministic_and_its_actions_are_valid():
    profile("sites_d15_t60", baselines=SMALL_GRID, sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    a, b = actions(env, make_policy("B6fc"), 4), actions(env, make_policy("B6fc"), 4)
    assert np.array_equal(a, b) and len(a) == env.T
    assert np.isfinite(a).all() and (np.abs(a) <= 1.0).all()


def test_forecast_memo_gives_the_same_flight():
    profile("sites_d15_t60", baselines=SMALL_GRID, sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    plain = actions(env, make_policy("B6fc"), 5)
    bl.FC_MEMO = {}
    first = actions(env, make_policy("B6fc"), 5)
    assert len(bl.FC_MEMO) > 0
    again = actions(env, make_policy("B6fc"), 5)                             # now served from the memo
    assert np.array_equal(plain, first) and np.array_equal(plain, again)


def test_screening_keeps_the_rule_when_it_keeps_everything_and_b6_when_nothing_moves():
    profile("sites_d15_t60", baselines=SMALL_GRID, sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    full = actions(env, make_policy("B6fc"), 5)
    md.CFG["b6fc"]["screen_top"] = 10_000                                     # >= every candidate: no screening
    assert np.array_equal(full, actions(env, make_policy("B6fc"), 5))
    md.CFG["b6fc"]["screen_top"] = 3                                          # tiny: it still runs
    a = actions(env, make_policy("B6fc"), 5)
    assert np.isfinite(a).all() and len(a) == env.T
    profile("rl_static", baselines=SMALL_GRID, b6fc={"screen_top": 3})
    assert run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6"), 1) == \
        run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6fc"), 1)


# ---------------------------------------------------------------- phase 4 runner
def test_confirm_one_runs_and_restores_the_flag(monkeypatch):
    real = md.apply_profile

    def small(name):
        real(name)
        if name and name != "default":
            md.CFG["baselines"].update(SMALL_GRID)
            md.CFG["n_users_choices"] = [100]
    monkeypatch.setattr(md, "apply_profile", small)
    bl.FC_MEMO = {}
    row = sites_exp.confirm_one("sites_d15_t0", 1000, (16.0, 13.0))
    for p in (*sites_exp.PILOTS, "dp"):
        assert 0.0 <= row[p] <= 1.0 and 0.0 <= row[p + "_13wh"] <= 1.0
    assert row["B6fc_u_13wh"] <= row["B6fc_u"] + 1e-12
    assert md.CFG["sites"]["announced"] == md.BASE_CFG["sites"]["announced"]
    assert row["teleport"] >= row["dp_model"] - 1e-12
    assert not set(orc.PLANS) & set(sites_exp.PILOTS)
    assert np.isnan(sites_exp.confirm_one("sites_d15_t0", 1000, (16.0,))["B6_13wh"])   # same columns, NaN = not run


def test_append_keeps_the_header_order(tmp_path):
    csv = tmp_path / "x.csv"
    sites_exp.append(csv, [dict(a=1, b=2, c=3)])
    sites_exp.append(csv, [dict(c=6, a=4)])                                   # fewer columns, other order
    d = pd.read_csv(csv)
    assert list(d.a) == [1, 4] and list(d.c) == [3, 6] and np.isnan(d.b[1])
    with pytest.raises(AssertionError):
        sites_exp.append(csv, [dict(a=1, z=0)])


def test_shards_are_disjoint_cover_the_remaining_seeds_and_keep_seeds_whole():
    seeds = list(range(1000, 1012))
    done = {(c, 1000) for c in sites_exp.CELLS} | {(sites_exp.CELLS[0], 1001)}
    shards = sites_exp.shard_seeds(seeds, 3, done)
    flat = [s for sh in shards for s in sh]
    assert sorted(flat) == list(range(1001, 1012)) and len(flat) == len(set(flat))
    assert shards == sites_exp.shard_seeds(seeds, 3, done)                 # deterministic


def test_merge_checks_gaps_and_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(sites_exp, "OUT", tmp_path)
    cells = sites_exp.CELLS

    def rows(seeds, v=0.5):
        return [{"cell": c, "seed": s, "B6": v, "B6_13wh": v if c == cells[0] else np.nan, "secs_total": 1.0}
                for s in seeds for c in cells]
    sites_exp.append(tmp_path / "confirm_episodes.csv", rows([1]))
    sites_exp.append(tmp_path / "confirm_episodes_shard0.csv", rows([2]))
    sites_exp.append(tmp_path / "confirm_episodes_shard1.csv", rows([2, 3]))       # seed 2 twice, the same numbers
    sites_exp.merge([1, 2, 3], cells[:1])
    d = pd.read_csv(tmp_path / "confirm_episodes.csv")
    assert len(d) == 3 * len(cells) and (tmp_path / "confirm_episodes_premerge.csv").exists()
    with pytest.raises(AssertionError):
        sites_exp.merge([1, 2, 3, 4], cells[:1])                                  # seed 4 missing
    sites_exp.append(tmp_path / "confirm_episodes_shard2.csv", rows([3], v=0.6))  # a disagreeing duplicate
    with pytest.raises(AssertionError):
        sites_exp.merge([1, 2, 3], cells[:1])
