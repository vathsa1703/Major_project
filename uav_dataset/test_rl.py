"""Tests for the RL pieces: control wrapper, scenario pool, static crowd, reward parts, training smoke test.
Run: python -m pytest test_rl.py"""
import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

import make_dataset as md
from rl_utils import CONTROLS, ControlWrapper, RandomPolicy, expand_action, make_env
from uav_env import UAVEnv


@pytest.fixture(autouse=True)
def back_to_default():
    md.apply_profile("default")
    yield
    md.apply_profile("default")


# ---------------------------------------------------------------- curriculum controls
def test_expand_action_holds_the_unused_controls():
    assert expand_action([0.3, -0.4], "xy").tolist() == [0.3, -0.4, 0.0, 1.0]       # keep altitude, full power
    assert expand_action([0.3, -0.4, 0.5], "xyz").tolist() == [0.3, -0.4, 0.5, 1.0]
    assert expand_action([0.3, -0.4, 0.5, -1.0], "xyzp").tolist() == [0.3, -0.4, 0.5, -1.0]
    with pytest.raises(AssertionError):
        expand_action([0.1, 0.2, 0.3], "xy")


@pytest.mark.parametrize("controls", list(CONTROLS))
def test_wrapper_shrinks_the_action_space_and_passes_the_checker(controls):
    env = make_env(controls)
    assert env.action_space.shape == (CONTROLS[controls],)
    check_env(env, skip_render_check=True)


def test_wrapped_env_in_xy_mode_never_changes_altitude_or_power():
    env = ControlWrapper(UAVEnv(battery_wh=1000.0), "xy")
    env.reset(seed=3)
    for a in np.random.default_rng(0).uniform(-1, 1, (20, 2)):
        _, _, _, _, info = env.step(a)
        assert info["h"] == md.CFG["uav"]["start_h_m"]
        assert info["p_tx_w"] == pytest.approx(env.unwrapped.p_max_w)


# ---------------------------------------------------------------- scenario pool (train seeds only)
def test_scenarios_come_only_from_the_pool_and_are_reproducible():
    pool = [4, 8, 15]
    env = UAVEnv(scenario_seeds=pool)
    env.reset(seed=1)
    drawn = []
    for _ in range(12):
        env.reset()
        drawn.append(env.scenario_seed)
    assert set(drawn) <= set(pool) and len(set(drawn)) > 1
    env2 = UAVEnv(scenario_seeds=pool)
    env2.reset(seed=1)
    again = []
    for _ in range(12):
        env2.reset()
        again.append(env2.scenario_seed)
    assert drawn == again


def test_explicit_scenario_seed_overrides_the_pool():
    env = UAVEnv(scenario_seeds=[1, 2, 3])
    env.reset(options={"scenario_seed": 120})
    assert env.scenario_seed == 120


def test_training_pool_is_the_training_split_and_excludes_val_and_test():
    from rl_utils import train_seeds
    assert set(train_seeds()).isdisjoint(md.seeds("val")) and set(train_seeds()).isdisjoint(md.seeds("test"))


# ---------------------------------------------------------------- static crowd
def test_static_crowd_never_moves():
    sc = {**md.make_scenario(3), "mobility": "static"}
    u = md.make_users(3, sc)
    P, V = md.simulate_positions(3, sc, u)
    assert P.shape[0] == md.CFG["mobility"]["episode_steps"] + 1
    assert (P == P[0]).all() and (V == 0).all()
    assert np.allclose(P[0], u[["x", "y"]].values)


def test_rl_static_profile_makes_every_scenario_static_and_hard():
    md.apply_profile("rl_static")
    assert all(md.make_scenario(s)["mobility"] == "static" for s in range(30))
    assert md.CFG["area_m"] == 2000 and md.CFG["uav"]["p_max_dbm"] == 20 and md.CFG["energy"]["battery_wh"] == 16


# ---------------------------------------------------------------- reward parts
def test_reward_parts_add_up_to_the_reward():
    env = UAVEnv(reward="v2")
    env.reset(seed=4)
    for a in np.random.default_rng(1).uniform(-1, 1, (10, 4)):
        _, r, *_, info = env.step(a)
        assert r == pytest.approx(info["reward_coverage"] + info["reward_energy"] + info["reward_terminal"])
        assert info["reward_energy"] < 0 and info["reward_terminal"] == 0


def test_v1_has_no_energy_part_and_death_adds_the_terminal_part():
    env = UAVEnv(reward="v1", battery_wh=0.3)
    env.reset(seed=4)
    last = None
    for _ in range(40):
        *_, term, trunc, last = (*env.step(np.array([0, 0, 0, 1.0])),)
        if term or trunc:
            break
    assert term and last["reward_energy"] == 0.0 and last["reward_terminal"] < 0


# ---------------------------------------------------------------- adapters
def test_random_policy_is_deterministic_and_stays_in_the_control_space():
    env = UAVEnv(battery_wh=1000.0)
    outs = []
    for _ in range(2):
        env.reset(seed=6)
        pol = RandomPolicy("xy")
        pol.reset(env)
        outs.append([pol.act(env).tolist() for _ in range(5)])
    assert outs[0] == outs[1]
    assert all(a[2] == 0.0 and a[3] == 1.0 and abs(a[0]) <= 1 and abs(a[1]) <= 1 for a in outs[0])


def test_evaluate_runs_random_on_a_split_and_returns_one_row_per_scenario():
    from rl_eval import evaluate
    df = evaluate(["Random"], md.seeds("val")[:2], controls="xy", battery_wh=1000.0)
    assert list(df.policy.unique()) == ["Random"] and len(df) == 2 and df.survived.all()


# ---------------------------------------------------------------- PPO smoke test (needs the RL libraries)
def test_ppo_trains_a_few_steps_and_acts_through_the_adapter(tmp_path):
    pytest.importorskip("stable_baselines3")
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv

    from rl_eval import evaluate
    from rl_train import RewardPartsCallback
    from rl_utils import RLPolicy

    venv = DummyVecEnv([lambda: make_env("xy", "v1", scenario_seeds=md.seeds("train")[:3]) for _ in range(2)])
    model = PPO("MlpPolicy", venv, n_steps=64, batch_size=64, n_epochs=1, seed=0, device="cpu", verbose=0)
    model.learn(total_timesteps=256, callback=RewardPartsCallback())
    path = tmp_path / "m.zip"
    model.save(path)

    env = UAVEnv(battery_wh=1000.0)
    env.reset(seed=3)
    pol = RLPolicy(PPO.load(path, device="cpu"), "xy")
    a = pol.act(env)
    assert a.shape == (4,) and env.action_space.contains(a.astype(np.float32)) and a[2] == 0.0 and a[3] == 1.0

    df = evaluate(["PPO"], md.seeds("val")[:1], str(path), "xy", battery_wh=1000.0)
    assert list(df.policy) == ["PPO"] and df.survived.all()


# ---------------------------------------------------------------- your own scenario + the viewer's pilots
def test_scenario_overrides_replace_only_what_you_name():
    env = UAVEnv(scenario_overrides={"n_users": 500, "n_clusters": 4, "mobility": "surge", "n_obstacles": 6})
    env.reset(seed=11)
    assert env.sc["n_users"] == 500 and len(env.users) == 500 and env.sc["n_clusters"] == 4
    assert env.sc["mobility"] == "surge" and len(env.boxes) == 6
    assert env.sc["bandwidth_hz"] == 500 * md.CFG["bandwidth_per_user_hz"]       # bandwidth follows the user count
    other = md.make_scenario(11)
    assert env.sc["cluster_radius_m"] == other["cluster_radius_m"]      # untouched fields keep the seed's value


def test_overridden_scenario_is_reproducible_and_odd_user_counts_are_refused():
    ov = {"n_users": 300, "mobility": "hotspot_jump"}
    a, b = UAVEnv(scenario_overrides=ov), UAVEnv(scenario_overrides=ov)
    assert np.array_equal(a.reset(seed=2)[0], b.reset(seed=2)[0])
    with pytest.raises(AssertionError):
        UAVEnv(scenario_overrides={"n_users": 301}).reset(seed=2)


def test_viewer_builds_every_kind_of_pilot():
    from baselines import POLICIES
    from view_run import ALIASES, build_policy, run
    for name in list(POLICIES) + ["random", "fixed", "follow"]:
        assert hasattr(build_policy(name), "act")
    assert ALIASES["fixed"] == "B0" and ALIASES["follow"] == "B1"
    with pytest.raises(ValueError):
        build_policy("ppo")                                   # needs a model path
    with pytest.raises(ValueError):
        build_policy("nonsense")
    env, frames = run(3, build_policy("B0"), battery_wh=1000.0, overrides={"n_users": 100})
    assert len(frames) == env.T and frames[0][0].shape == (100, 2)


# ---------------------------------------------------------------- waypoint ("fly to this spot") controls
def _goto_env(controls="goto"):
    env = ControlWrapper(UAVEnv(battery_wh=1000.0), controls)
    env.reset(seed=3)
    return env


def test_waypoint_controls_need_the_env():
    with pytest.raises(AssertionError):
        expand_action([0.0, 0.0], "goto")


def test_goto_maps_the_action_square_onto_the_map():
    env = _goto_env().unwrapped
    L = env.L
    for a, (tx, ty) in (([-1, -1], (0, 0)), ([1, 1], (L, L)), ([0, 0], (L / 2, L / 2))):
        full = expand_action(a, "goto", env)
        want = np.array([tx - env.x, ty - env.y])
        if np.linalg.norm(want) > 1e-9:                       # direction points at the target
            assert np.dot(full[:2], want) > 0 and np.allclose(full[:2] / max(np.linalg.norm(full[:2]), 1e-9),
                                                              want / np.linalg.norm(want))
        assert full[2] == 0.0 and full[3] == 1.0              # altitude held, full power


def test_goto_flies_to_the_target_and_then_stays_there():
    env = _goto_env()
    a = np.array([0.5, -0.5], dtype=np.float32)               # target (0.75 L, 0.25 L)
    target = np.array([0.75, 0.25]) * env.unwrapped.L
    speeds = []
    for _ in range(150):
        *_, info = env.step(a)
        speeds.append(np.hypot(env.unwrapped.vx, env.unwrapped.vy))
    assert np.hypot(info["x"] - target[0], info["y"] - target[1]) < 2.0
    assert max(speeds) <= md.CFG["uav"]["v_max_mps"] + 1e-9
    assert max(speeds[-10:]) < 0.5                            # it has stopped (this is what velocity controls lacked)
    assert info["h"] == md.CFG["uav"]["start_h_m"]


def test_gotoz_and_gotozp_steer_altitude_and_power():
    env = _goto_env("gotoz")
    for _ in range(80):
        *_, info = env.step(np.array([0.0, 0.0, 1.0], dtype=np.float32))
    assert info["h"] == pytest.approx(md.CFG["uav"]["h_max_m"])
    env = _goto_env("gotozp")
    *_, info = env.step(np.array([0.0, 0.0, 0.0, -1.0], dtype=np.float32))
    assert info["p_tx_w"] < env.unwrapped.p_max_w * 0.01


def test_policy_adapters_handle_waypoint_controls():
    env = UAVEnv(battery_wh=1000.0)
    env.reset(seed=5)
    pol = RandomPolicy("goto")
    pol.reset(env)
    a = pol.act(env)
    assert a.shape == (4,) and abs(a[0]) <= 1 and abs(a[1]) <= 1 and a[2] == 0.0 and a[3] == 1.0


# ---------------------------------------------------------------- holding a decision for k seconds
def test_hold_wrapper_repeats_the_choice_and_adds_up_the_rewards():
    from rl_utils import HoldWrapper
    a = np.array([0.4, -0.2], dtype=np.float32)
    held = HoldWrapper(ControlWrapper(UAVEnv(battery_wh=1000.0, reward="v1"), "goto"), 10)
    held.reset(seed=3)
    _, r_held, *_ = held.step(a)
    assert held.unwrapped.t == 10                              # ten simulated seconds in one decision
    ref = ControlWrapper(UAVEnv(battery_wh=1000.0, reward="v1"), "goto")
    ref.reset(seed=3)
    r_ref = sum(ref.step(a)[1] for _ in range(10))
    assert r_held == pytest.approx(r_ref)


def test_hold_wrapper_stops_exactly_at_the_end_of_the_episode():
    from rl_utils import HoldWrapper
    held = HoldWrapper(ControlWrapper(UAVEnv(battery_wh=1000.0), "goto"), 7)    # 300 is not a multiple of 7
    held.reset(seed=3)
    a = np.zeros(2, dtype=np.float32)
    for _ in range(100):
        _, _, term, trunc, _ = held.step(a)
        if term or trunc:
            break
    assert trunc and held.unwrapped.t == held.unwrapped.T == 300


def test_make_env_only_wraps_when_asked_to_hold():
    from rl_utils import HoldWrapper
    assert not isinstance(make_env("goto", hold=1), HoldWrapper)
    assert isinstance(make_env("goto", hold=10), HoldWrapper)
    check_env(make_env("goto", hold=10), skip_render_check=True)


def test_rl_policy_decides_only_every_hold_seconds():
    from rl_utils import RLPolicy

    class CountingModel:
        calls = 0

        def predict(self, obs, deterministic=True):
            CountingModel.calls += 1
            return np.array([0.1, 0.1], dtype=np.float32), None

    env = UAVEnv(battery_wh=1000.0)
    env.reset(seed=4)
    pol = RLPolicy(CountingModel(), "goto", hold=10)
    pol.reset(env)
    for _ in range(25):
        env.step(pol.act(env))
    assert CountingModel.calls == 3                            # seconds 0, 10 and 20
