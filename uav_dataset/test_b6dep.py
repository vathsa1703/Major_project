"""Tests for B6dep, the departure-time planner (anticipation rule).
Run: python -m pytest test_b6dep.py"""
import copy

import numpy as np
import pytest

import baselines as bl
import make_dataset as md
import oracle as orc
from baselines import B6GridAltitude, fly_two_legs, go_to, make_policy
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


def actions(env, pol, seed, n=None):
    env.reset(seed=seed)
    pol.reset(env)
    out = []
    for _ in range(n or env.T):
        a = pol.act(env)
        out.append(a)
        if any(env.step(a)[2:4]):
            break
    return np.array(out)


# ---------------------------------------------------------------- planned flights = real flights
@pytest.mark.parametrize("a_max", [None, 4.0])
def test_fly_two_legs_equals_a_real_two_leg_go_to_flight(a_max):
    profile("sites_base", uav={"a_max_mps2": a_max})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=1)
    for _ in range(5):                                   # start from a moving drone
        env.step(np.array([0.6, -0.5, 0.2, 1.0]))
    first = np.array([[300.0, 400.0, 100.0]] * 3)
    second = np.array([[1700.0, 1500.0, 300.0], [1990.0, 10.0, 50.0], [0.0, 0.0, 0.0]])
    dep = np.array([0.0, 37.0, np.inf])
    n = 160
    pos = fly_two_legs(env, first, second, dep, n)
    assert pos.shape == (n + 1, 3, 3)
    for p in range(3):
        e = copy.deepcopy(env)
        for k in range(n + 1):
            assert np.allclose(pos[k, p], [e.x, e.y, e.h], rtol=0, atol=1e-9)
            tgt = first[p] if k < dep[p] else second[p]
            e.step(go_to(e, *tgt, 1.0))


# ---------------------------------------------------------------- B6dep == B6 when there is nothing announced
def test_b6dep_is_b6_without_an_event():
    profile("hard", baselines=SMALL_GRID, uav={"a_max_mps2": 4.0})
    for seed in (1, 4):
        a = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6"), seed)
        b = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6dep"), seed)
        assert a == b


def test_b6dep_is_b6_when_the_event_is_not_announced():
    profile("sites_d20_t60", baselines=SMALL_GRID, sites={"announced": False})
    env = UAVEnv(scenario_overrides=SMALL)
    assert np.array_equal(actions(env, make_policy("B6"), 2), actions(env, make_policy("B6dep"), 2))


def test_b6dep_is_b6_after_the_announced_move_is_over():
    profile("sites_d15_t60", baselines=SMALL_GRID, sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=3)
    pol = make_policy("B6dep")
    pol.reset(env)
    t_end = env.sc["event_t0_s"] + env.sc["tau_s"]
    checked = 0
    while env.t < env.T:
        if env.t % 10 == 0 and env.t * env.dt >= t_end:
            ref = make_policy("B6")
            ref.reset(env)
            B6GridAltitude.plan(ref, env)
            a = pol.act(env)
            assert pol.target == ref.target
            checked += 1
            env.step(a)
            continue
        env.step(pol.act(env))
    assert checked >= 10


# ---------------------------------------------------------------- information
def test_b6dep_never_reads_the_future():
    profile("sites_d20_t60", baselines=SMALL_GRID, sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=1)
    pol = make_policy("B6dep")
    pol.reset(env)
    t0 = env.sc["event_t0_s"]
    checks = {10 * (t0 // 10) - 30, 10 * (t0 // 10) - 10, 10 * (t0 // 10) + 20}      # before and during the move
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
    assert seen == 3


def test_extrapolation_is_capped():
    profile("sites_d15_t60", sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=2)
    for _ in range(3):
        env.step(np.zeros(4))
    pol = make_policy("B6dep")
    pol.reset(env)
    s = pol.snapshot(env)
    plain = {k: v for k, v in s.items() if k not in ("t0", "tau", "m", "inA", "dest")}   # walking only
    cap = int(md.CFG["b6dep"]["extrap_cap_s"])
    at_cap = pol.forecast(env, plain, env.t + cap)[0]
    assert np.array_equal(at_cap, pol.forecast(env, plain, env.t + cap + 50)[0])
    fc = make_policy("B6fc")
    fc.reset(env)
    assert np.array_equal(at_cap, fc.forecast(env, plain, env.t + cap)[0])          # same forecast up to the cap


# ---------------------------------------------------------------- determinism, valid actions
def test_b6dep_is_deterministic_and_its_actions_are_valid():
    profile("sites_d15_t0", baselines=SMALL_GRID, sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    a, b = actions(env, make_policy("B6dep"), 4), actions(env, make_policy("B6dep"), 4)
    assert np.array_equal(a, b) and len(a) == env.T
    assert np.isfinite(a).all() and (np.abs(a) <= 1.0).all()


# ---------------------------------------------------------------- it fixes B6fc's early departure
def test_b6dep_beats_b6fc_where_b6fc_leaves_too_early():
    """Design seed 1 of sites_d20_t60 (100 users, announced, full B6 grid): B6fc scores the far site over its own
    window after arrival, leaves too early and loses to plain B6; B6dep must do at least as well as B6fc."""
    profile("sites_d20_t60", sites={"announced": True})
    env = UAVEnv(scenario_overrides=SMALL)
    cov = {p: orc.episode_coverage(env, make_policy(p), 1)[0].mean() for p in ("B6", "B6fc", "B6dep")}
    assert cov["B6fc"] < cov["B6"]                         # the situation the test is about
    assert cov["B6dep"] >= cov["B6fc"]
    assert cov["B6dep"] >= cov["B6"] - 1e-12               # here it also does not lose to B6
