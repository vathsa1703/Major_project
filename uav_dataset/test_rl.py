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


# ---------------------------------------------------------------- observation groups (what the agent sees)
def test_default_observation_is_unchanged_and_explicit_all_groups_is_identical():
    from uav_env import OBS_GROUPS
    env = UAVEnv()
    env.reset(seed=4)
    assert env.observation_space.shape == (211,)
    assert np.array_equal(env.observation(), env.observation(OBS_GROUPS))


def test_a_smaller_observation_drops_only_the_named_groups_and_keeps_the_rest_in_order():
    full = UAVEnv()
    lean = UAVEnv(obs_groups=("pos", "heat_all", "heat_rescue"))
    full.reset(seed=4)
    lean.reset(seed=4)
    assert lean.observation_space.shape == (3 + 200,)
    o_full, o_lean = full.observation(), lean.observation()
    assert np.array_equal(o_lean[:3], o_full[:3])                 # position
    assert np.array_equal(o_lean[3:], o_full[11:])                # the two maps
    # a trained policy can ask a full env for just the subset it knows
    assert np.array_equal(full.observation(("pos", "heat_all", "heat_rescue")), o_lean)


def test_unknown_observation_group_is_refused_and_dimensions_match_the_space():
    with pytest.raises(AssertionError):
        UAVEnv(obs_groups=("pos", "the_answer"))
    for groups in (("pos",), ("pos", "vel", "battery"), ("heat_all",), ("pos", "prev", "heat_all", "heat_rescue")):
        env = UAVEnv(obs_groups=groups)
        obs, _ = env.reset(seed=2)
        assert obs.shape == env.observation_space.shape == (UAVEnv.obs_dim(groups, env.grid),)
        assert env.observation_space.contains(obs)


def test_rl_policy_asks_the_env_for_its_own_observation_groups():
    from rl_utils import RLPolicy

    class SeesWhatItAsksFor:
        def __init__(self):
            self.shapes = []

        def predict(self, obs, deterministic=True):
            self.shapes.append(obs.shape)
            return np.array([0.0, 0.0], dtype=np.float32), None

    env = UAVEnv(battery_wh=1000.0)                                # the env itself shows all 211 numbers
    env.reset(seed=4)
    m = SeesWhatItAsksFor()
    pol = RLPolicy(m, "goto", hold=10, obs_groups=("pos", "heat_all", "heat_rescue"))
    pol.reset(env)
    env.step(pol.act(env))
    assert m.shapes == [(203,)]


# ---------------------------------------------------------------- settings saved next to a model
def test_model_settings_are_found_next_to_the_model_or_one_folder_up(tmp_path):
    import json

    from rl_utils import model_settings
    run = tmp_path / "run1"
    (run / "checkpoints").mkdir(parents=True)
    (run / "config.json").write_text(json.dumps({"controls": "goto", "hold_steps": 10}), encoding="utf-8")
    assert model_settings(run / "model.zip") == {"controls": "goto", "hold_steps": 10}
    assert model_settings(run / "checkpoints" / "rl_model_1000_steps.zip")["hold_steps"] == 10
    assert model_settings(tmp_path / "nowhere" / "model.zip") == {}


def test_old_models_without_hold_in_their_settings_default_to_deciding_every_second(tmp_path):
    import json

    from view_run import build_policy
    pytest.importorskip("stable_baselines3")
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    venv = DummyVecEnv([lambda: make_env("xy", "v1", scenario_seeds=[1, 2])])
    PPO("MlpPolicy", venv, n_steps=32, batch_size=32, n_epochs=1, device="cpu", seed=0).save(tmp_path / "model")
    old_config = {"controls": "xy"}                                  # an old model: no hold key
    (tmp_path / "config.json").write_text(json.dumps(old_config), encoding="utf-8")
    pol = build_policy("ppo", str(tmp_path / "model.zip"))
    assert pol.controls == "xy" and pol.hold == 1 and pol.obs_groups is None


# ---------------------------------------------------------------- Track 2: opt-in observation extras, Dict obs, priv
NEW_GROUPS = ("pos", "vel", "battery", "time", "prev", "crowd_n", "history", "heat_all_u", "heat_rescue_u")


def test_default_observation_still_equals_the_old_formula():
    env = UAVEnv()
    env.reset(seed=7)
    for a in np.random.default_rng(2).uniform(-1, 1, (3, 4)):
        env.step(a)
    xy, L, u = env.user_xy(), env.L, env.uav

    def capped(p):
        h, _, _ = np.histogram2d(p[:, 0], p[:, 1], bins=env.grid, range=[[0, L], [0, L]])
        return np.minimum(1.0, h.ravel() / len(p) * 10.0)
    old = np.concatenate([[env.x / L, env.y / L, (env.h - u["h_min_m"]) / (u["h_max_m"] - u["h_min_m"])],
                          [env.vx / u["v_max_mps"], env.vy / u["v_max_mps"], env.vz / u["vz_max_mps"]],
                          [env.energy_left_j / env.battery_j], [env.t / env.T],
                          [env.prev["coverage"], env.prev["throughput"], env.prev["fairness"]],
                          capped(xy), capped(xy[env.rescue])])
    obs = env.observation()
    assert obs.dtype == np.float32 and obs.shape == (211,)
    assert np.array_equal(obs, np.clip(old, -1, 1).astype(np.float32))


def test_uncapped_map_is_in_range_never_saturates_and_keeps_the_true_shares():
    md.apply_profile("rl_static")
    saturated_somewhere = False
    for seed in range(100, 108):
        env = UAVEnv(obs_groups=("heat_all", "heat_all_u"))
        env.reset(seed=seed)
        o = env.observation()
        g2 = env.grid**2
        capped, unc = o[:g2], o[g2:]
        saturated_somewhere |= bool((capped >= 1.0).sum() > 1)
        assert unc.min() >= 0 and unc.max() < 1.0                         # several cells occupied -> never 1
        assert float((unc.astype(float) ** 2).sum()) == pytest.approx(1.0, abs=1e-5)   # shares add up to 1
        full = capped >= 1.0                       # cells the capped map cannot tell apart, the uncapped one can
        if full.sum() > 1:
            assert len(np.unique(unc[full])) > 1
    assert saturated_somewhere                                             # the cap really did hide something


def test_crowd_n_is_monotone_in_the_number_of_users_and_spans_0_to_1():
    vals = []
    for n in (100, 300, 600, 1000):
        env = UAVEnv(obs_groups=("crowd_n",), scenario_overrides={"n_users": n})
        env.reset(seed=3)
        vals.append(float(env.observation()[0]))
    assert vals[0] == pytest.approx(0.0) and vals[-1] == pytest.approx(1.0)
    assert all(a < b for a, b in zip(vals, vals[1:], strict=False))
    env = UAVEnv(obs_groups=("crowd_n",), scenario_overrides={"n_users": 4000})
    env.reset(seed=3)
    assert env.observation()[0] == 1.0                                     # outside the range: clipped


def test_history_holds_own_position_and_coverage_at_decision_times():
    from rl_utils import HoldWrapper
    env = HoldWrapper(ControlWrapper(UAVEnv(battery_wh=1000.0, obs_groups=("history",), history_every=10), "goto"),
                      10)
    obs, _ = env.reset(seed=3)
    e = env.unwrapped
    assert obs.shape == (12,) and np.allclose(obs, np.tile([0.5, 0.5, 0.0], 4))     # before the start: the start
    rec = {0: (0.5, 0.5, 0.0)}
    for k in range(1, 4):
        obs, *_, info = env.step(np.array([0.6, -0.3], dtype=np.float32))
        rec[10 * k] = (info["x"] / e.L, info["y"] / e.L, info["coverage"])
    want = np.array([rec[0], rec[10], rec[20], rec[30]], dtype=np.float32).ravel()
    assert np.allclose(obs, want, atol=1e-6)
    assert rec[30][2] > 0 and rec[30][:2] != rec[10][:2]                   # it measured something and moved
    # a policy asking a plain env (no wrapper) for the same groups at a 10 s rhythm sees the same numbers
    assert np.allclose(e.observation(("history",), history_every=10), want, atol=1e-6)


def test_dict_observation_has_maps_and_scalars_and_passes_the_checker():
    env = UAVEnv(obs_groups=NEW_GROUPS, obs_mode="dict")
    obs, _ = env.reset(seed=4)
    assert set(obs) == {"maps", "scalars"}
    assert obs["maps"].shape == (2, env.grid, env.grid) and obs["scalars"].shape == (3 + 3 + 1 + 1 + 3 + 1 + 12,)
    assert env.observation_space.contains(obs)
    box = UAVEnv(obs_groups=("heat_all_u", "heat_rescue_u"))             # same maps as box mode, in (C, x, y) form
    box.reset(seed=4)
    assert np.allclose(obs["maps"].ravel(), box.observation())
    check_env(env, skip_render_check=True)
    check_env(make_env("goto", hold=10, obs_groups=NEW_GROUPS, obs_mode="dict", privileged=True).unwrapped,
              skip_render_check=True)


def test_privileged_state_exists_only_when_asked_and_only_in_dict_mode():
    plain = UAVEnv(obs_groups=NEW_GROUPS, obs_mode="dict")
    priv = UAVEnv(obs_groups=NEW_GROUPS, obs_mode="dict", privileged=True)
    assert "priv_maps" not in plain.observation_space.spaces and "priv_maps" in priv.observation_space.spaces
    o_plain, _ = plain.reset(seed=5)
    o_priv, _ = priv.reset(seed=5)
    assert not any(k.startswith("priv") for k in o_plain)
    assert np.array_equal(o_plain["maps"], o_priv["maps"]) and np.array_equal(o_plain["scalars"], o_priv["scalars"])
    assert priv.observation(privileged=False).keys() == o_plain.keys()       # a policy can ask without priv
    with pytest.raises(AssertionError):
        UAVEnv(privileged=True)                                               # box mode: refused


def test_privileged_maps_are_the_raw_true_state():
    md.apply_profile("rl_static")
    env = UAVEnv(obs_groups=NEW_GROUPS, obs_mode="dict", privileged=True)
    obs, _ = env.reset(seed=104)
    p = env.priv_grid
    pm = obs["priv_maps"].astype(float) / 255
    assert obs["priv_maps"].dtype == np.uint8 and pm.shape == (4, p, p)
    xy = env.user_xy()
    h, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=p, range=[[0, env.L], [0, env.L]])
    assert np.allclose(pm[0], np.sqrt(h / len(xy)), atol=1 / 255)             # density, uncapped
    assert len(env.boxes) > 0 and pm[2].max() > 0.5 and pm[2].min() == 0     # obstacle occupancy
    area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in env.boxes) / env.L**2
    assert 0.5 * area < pm[2].mean() <= area + 0.005                          # overlapping buildings count once
    assert 0 < pm[3].max() <= 1 and (pm[3][h == 0] == 0).all()                 # demand only where people are
    assert obs["priv_n"][0] == pytest.approx(env.crowd_n())


def test_fresh_training_pool_is_disjoint_from_validation_and_test():
    from rl_utils import train_seeds, training_pool
    assert training_pool(None) == train_seeds()
    pool = training_pool([10000, 19999])
    assert len(pool) == 10000 and pool[0] == 10000
    assert set(pool).isdisjoint(md.seeds("val")) and set(pool).isdisjoint(md.seeds("test"))
    with pytest.raises(AssertionError):
        training_pool([0, 150])                                               # contains val and test seeds


def test_rl_policy_in_dict_mode_never_asks_the_env_for_the_privileged_state():
    from rl_utils import RLPolicy

    class Model:
        observation_space = UAVEnv.dict_space(NEW_GROUPS, md.CFG["env"]["grid"], privileged=True)
        seen = []

        def predict(self, obs, deterministic=True):
            Model.seen.append(obs)
            return np.array([0.0, 0.0], dtype=np.float32), None

    env = UAVEnv(battery_wh=1000.0)

    def forbidden():
        raise AssertionError("the acting policy asked for the privileged state")
    env.privileged_state = forbidden
    env.reset(seed=4)
    pol = RLPolicy(Model(), "goto", hold=10, obs_groups=NEW_GROUPS, obs_mode="dict")
    pol.reset(env)
    for _ in range(12):
        env.step(pol.act(env))
    assert len(Model.seen) == 2
    for o in Model.seen:
        assert Model.observation_space.contains(o)
        assert not o["priv_maps"].any() and not o["priv_n"].any()            # zeros, never the true state
