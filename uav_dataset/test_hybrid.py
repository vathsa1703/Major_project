"""Tests for the hybrid timing AI (hybrid.py, hybrid_tables.py, hybrid_train.py, hybrid_eval.py).
Run: python -m pytest test_hybrid.py"""
import copy
import re
from pathlib import Path

import numpy as np
import pytest

import baselines as bl
import hybrid
import make_dataset as md
import oracle as orc
from baselines import go_to, make_policy
from run_baselines import run_episode
from uav_env import UAVEnv

SMALL = {"n_users": 100}
SMALL_GRID = {"grid_n": 4, "altitude_levels_m": [100, 200]}


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    md.apply_profile("default")


def profile(name="sites_d20_t60_ann", **over):
    md.apply_profile(name)
    md.CFG["baselines"].update(SMALL_GRID)
    for sec, kv in over.items():
        md.CFG[sec].update(kv)


def fresh(seed=3, **kw):
    env = UAVEnv(scenario_overrides=SMALL, **kw)
    env.reset(seed=seed)
    return env


def scramble_future(env, rng):
    """Replace every future position and activity flag (after env.t) with garbage."""
    env.P[env.t + 1:] = rng.uniform(0, env.L, env.P[env.t + 1:].shape)
    env.V[env.t + 1:] = 0.0
    env.active[env.t + 1:] = rng.uniform(size=env.active[env.t + 1:].shape) < 0.5


# ---------------------------------------------------------------- the B6 table equals live B6
def test_table_rows_are_the_oracle_tensor_at_decision_times(tmp_path):
    profile()
    env = fresh()
    table, _ = hybrid.scenario_data(env, cache=False)
    cov = orc.coverage_tensor(env, cache=False)
    assert np.array_equal(table, orc.frozen_scores(cov)[:, :-1])     # oracle's last node = the start spot


@pytest.mark.parametrize("name", ["sites_d20_t0_ann", "sites_d20_t60_ann"])
def test_table_b6_flies_exactly_like_live_b6(tmp_path, name):
    profile(name)
    for seed in (3, 8):
        live = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6"), seed)
        tab = run_episode(UAVEnv(scenario_overrides=SMALL), hybrid.ScheduleHybrid(None, cache_dir=tmp_path), seed)
        assert tab == live                                           # every metric, bit for bit


def test_table_b6_picks_live_b6_targets_at_every_decision(tmp_path):
    profile()
    env = fresh(5)
    table, _ = hybrid.scenario_data(env, cache=False)
    tb, b6 = hybrid.TableB6(table), make_policy("B6")
    tb.reset(env), b6.reset(env)
    rng = np.random.default_rng(1)
    while env.t < env.T:
        if env.t % hybrid.every() == 0:
            tb.plan(env), b6.plan(env)
            assert tb.target == b6.target
        env.step(np.r_[rng.uniform(-1, 1, 3), 1.0])                    # anywhere, so 'stay' and ties are exercised


def test_table_is_cached_and_bundled(tmp_path):
    profile()
    env = fresh()
    t1, g1 = hybrid.scenario_data(env, cache=True, cache_dir=tmp_path)
    assert hybrid.cache_path(env, tmp_path).exists()
    t2, g2 = hybrid.scenario_data(env, cache=True, cache_dir=tmp_path)
    assert np.array_equal(t1, t2) and np.array_equal(g1, g2)
    np.savez_compressed(tmp_path / "b.npz", seeds=np.array([3]), tables=t1[None], targets=g1[None])
    data = hybrid.load_bundle(tmp_path / "b.npz")
    assert list(data) == [3] and np.array_equal(data[3][0], t1)


# ---------------------------------------------------------------- the two actions
def test_follow_maps_to_b6_and_leave_to_the_b_target(tmp_path):
    profile()
    henv = hybrid.HybridTimingEnv(cache_dir=tmp_path, scenario_overrides=SMALL)
    henv.reset(options={"scenario_seed": 3})
    env = henv.env
    b6 = make_policy("B6")
    b6.reset(env)
    b6.plan(env)
    _, _, _, _, info = henv.step(hybrid.FOLLOW)
    assert info["target"] == b6.target and info["hybrid_action"] == 0
    target = tuple(float(v) for v in hybrid.b_target(fresh(3)))
    _, _, _, _, info = henv.step(hybrid.LEAVE)
    assert info["target"] == target
    d0 = np.hypot(env.x - target[0], env.y - target[1])
    henv.step(hybrid.LEAVE)                                            # it keeps flying there
    assert np.hypot(env.x - target[0], env.y - target[1]) < d0 or d0 < 1.0
    b6.plan(env)
    _, _, _, _, info = henv.step(hybrid.FOLLOW)                        # and may go back to following B6
    assert info["target"] == b6.target
    assert henv.action_space.n == 2 and henv.pilot.actions == [0, 1, 1, 0]


def test_flight_uses_go_to_at_b6_power(tmp_path):
    profile()
    env = fresh()
    pol = hybrid.ScheduleHybrid(0, cache_dir=tmp_path)
    pol.reset(env)
    a = pol.act(env)
    assert np.array_equal(a, go_to(env, *hybrid.b_target(fresh()), bl.BCFG["power_frac"]))


def test_reward_is_the_sum_of_the_held_coverage(tmp_path):
    profile()
    henv = hybrid.HybridTimingEnv(cache_dir=tmp_path, scenario_overrides=SMALL)
    henv.reset(options={"scenario_seed": 3})
    ref = fresh(3, reward="v1")
    pol = hybrid.ScheduleHybrid(None, cache_dir=tmp_path)
    pol.reset(ref)
    total = 0.0
    for _ in range(hybrid.every()):
        total += ref.step(pol.act(ref))[1]
    _, r, _, _, _ = henv.step(hybrid.FOLLOW)
    assert r == pytest.approx(total, abs=1e-12)


def test_an_episode_is_30_decisions_and_ends_truncated(tmp_path):
    profile()
    henv = hybrid.HybridTimingEnv(cache_dir=tmp_path, scenario_overrides=SMALL)
    henv.reset(options={"scenario_seed": 3})
    n, done = 0, False
    while not done:
        _, _, term, trunc, _ = henv.step(n % 2)
        n, done = n + 1, term or trunc
    assert n == henv.env.T // hybrid.every() and trunc and not term


def test_b_target_needs_an_announced_event():
    profile("sites_d20_t60")                                             # unannounced
    with pytest.raises(AssertionError):
        hybrid.b_target(fresh())


def test_b_target_is_near_site_b():
    profile()
    for seed in (1, 2, 3, 4):
        env = fresh(seed)
        x, y, _ = hybrid.b_target(env)
        A, B = (np.array([env.sc["site_x"][i], env.sc["site_y"][i]]) for i in (0, 1))
        assert np.linalg.norm([x, y] - B) < np.linalg.norm([x, y] - A)


# ---------------------------------------------------------------- the agent never sees the future
def test_observation_and_b_target_ignore_the_future():
    profile()
    rng = np.random.default_rng(0)
    env = fresh(3)
    fake = copy.deepcopy(env)
    scramble_future(fake, rng)
    assert np.array_equal(hybrid.b_target(env), hybrid.b_target(fake))
    groups = hybrid.obs_groups()
    t0 = env.sc["event_t0_s"]
    for stop in (10 * (t0 // 10) - 20, 10 * (t0 // 10) + 10):          # before and during the move
        while env.t < stop:
            env.step(go_to(env, 900.0, 1100.0, 150.0, 1.0))
        fake = copy.deepcopy(env)
        scramble_future(fake, rng)
        o1 = env.observation(groups, dict_obs=True, history_every=hybrid.every(), privileged=False)
        o2 = fake.observation(groups, dict_obs=True, history_every=hybrid.every(), privileged=False)
        assert o1.keys() == o2.keys() and all(np.array_equal(o1[k], o2[k]) for k in o1)


def test_pilot_reads_only_the_present_row_of_the_table(tmp_path):
    profile()
    env = fresh(5)
    table, target = hybrid.scenario_data(env, cache=False)
    rng = np.random.default_rng(2)
    while env.t < env.T:
        if env.t % hybrid.every() == 0:
            k = env.t // hybrid.every()
            junk = table.copy()
            junk[k + 1:] = rng.uniform(size=junk[k + 1:].shape)          # garbage future rows
            a, b = hybrid.TableB6(table), hybrid.TableB6(junk)
            a.reset(env), b.reset(env)
            a.plan(env), b.plan(env)
            assert a.target == b.target
        env.step(np.array([0.3, -0.2, 0.0, 1.0]))


def test_obs_groups_are_raw_and_hybrid_code_never_imports_the_oracle():
    assert set(hybrid.obs_groups()) <= set(UAVEnv.group_sizes(10))
    assert not any(g.startswith("priv") for g in hybrid.obs_groups())
    here = Path(__file__).parent
    for f in ("hybrid.py", "hybrid_train.py"):
        text = (here / f).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+oracle\b", text, re.M), f"{f} imports the oracle"


def test_training_pool_is_disjoint_from_val_and_test():
    md.apply_profile("sites_d20_t0_ann")
    lo, hi = md.CFG["hybrid"]["train_seeds"]
    assert set(range(lo, hi + 1)).isdisjoint(set(md.seeds("val")) | set(md.seeds("test")))


# ---------------------------------------------------------------- smoke training
def test_ppo_trains_a_few_steps_and_flies_through_the_adapter(tmp_path):
    pytest.importorskip("stable_baselines3")
    from stable_baselines3 import PPO

    from rl_net import DictMapExtractor
    profile()
    env = hybrid.HybridTimingEnv(scenario_seeds=[3, 4], cache_dir=tmp_path, scenario_overrides=SMALL)
    kw = {"features_extractor_class": DictMapExtractor, "features_extractor_kwargs": {"use_priv": False},
          "normalize_images": False, "net_arch": [16, 16]}
    model = PPO("MultiInputPolicy", env, n_steps=32, batch_size=32, n_epochs=1, seed=0, device="cpu", verbose=0,
                policy_kwargs=kw)
    model.learn(64)
    model.save(tmp_path / "m")
    model = PPO.load(tmp_path / "m", device="cpu")
    pol = hybrid.HybridPolicy(model, cache_dir=tmp_path)
    row = run_episode(UAVEnv(scenario_overrides=SMALL), pol, 3)
    assert 0.0 <= row["coverage_full"] <= 1.0 and len(pol.pilot.actions) == 30
    assert set(pol.pilot.actions) <= {0, 1}
