"""Tests that need PyTorch + Stable-Baselines3 (the CNN that reads the maps). Run: python -m pytest test_rl_net.py"""
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("stable_baselines3")

import numpy as np  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.vec_env import DummyVecEnv  # noqa: E402

import make_dataset as md  # noqa: E402
from rl_net import CnnMapExtractor  # noqa: E402
from rl_utils import make_env  # noqa: E402
from uav_env import UAVEnv  # noqa: E402


def _space(groups):
    return UAVEnv(obs_groups=groups).observation_space


def test_cnn_extractor_output_size_with_and_without_scalar_inputs():
    full = CnnMapExtractor(_space(None), grid=10)
    maps_only = CnnMapExtractor(_space(("heat_all", "heat_rescue")), grid=10)
    assert full.features_dim == 128 + 32 and maps_only.features_dim == 128
    assert full(torch.zeros(5, 211)).shape == (5, 160) and maps_only(torch.zeros(5, 200)).shape == (5, 128)


def test_cnn_extractor_is_reproducible_and_sees_where_the_crowd_is():
    torch.manual_seed(0)
    a = CnnMapExtractor(_space(None), grid=10)
    torch.manual_seed(0)
    b = CnnMapExtractor(_space(None), grid=10)
    left, right = torch.zeros(1, 211), torch.zeros(1, 211)
    left[0, 11 + 0] = 1.0                      # a crowd in the first cell of the map
    right[0, 11 + 99] = 1.0                    # the same crowd in the last cell
    assert torch.equal(a(left), b(left))
    assert not torch.allclose(a(left), a(right))        # position matters to the network


def test_cnn_extractor_needs_both_maps():
    with pytest.raises(AssertionError):
        CnnMapExtractor(_space(("pos", "heat_all")), grid=10)


def test_ppo_with_the_cnn_and_a_lean_observation_trains_and_acts(tmp_path):
    groups = ("pos", "heat_all", "heat_rescue")
    venv = DummyVecEnv([lambda: make_env("goto", "v1", scenario_seeds=md.seeds("train")[:3], hold=10, obs_groups=groups)
                        for _ in range(2)])
    model = PPO("MlpPolicy", venv, n_steps=16, batch_size=32, n_epochs=1, seed=0, device="cpu",
                policy_kwargs={"net_arch": [32], "features_extractor_class": CnnMapExtractor,
                               "features_extractor_kwargs": {"grid": 10}})
    model.learn(total_timesteps=64)
    obs = venv.reset()
    assert obs.shape == (2, 203)
    action, _ = model.predict(obs, deterministic=True)
    assert action.shape == (2, 2) and np.all(np.abs(action) <= 1)


def test_std_anneal_shrinks_the_noise_on_a_straight_line_and_freezes_the_optimiser_out(tmp_path):
    from rl_train import StdAnnealCallback
    venv = DummyVecEnv([lambda: make_env("goto", "v1", scenario_seeds=md.seeds("train")[:3], hold=10)])
    model = PPO("MlpPolicy", venv, n_steps=16, batch_size=16, n_epochs=1, seed=0, device="cpu",
                policy_kwargs={"log_std_init": np.log(0.4)})
    cb = StdAnnealCallback(0.4, 0.05, 160)
    model.learn(total_timesteps=160, callback=cb)
    steps = [s for _, s in cb.history]
    assert steps[0] == pytest.approx(0.4) and steps[-1] < 0.12           # starts at the start value, ends near the end
    assert all(a >= b for a, b in zip(steps, steps[1:], strict=False))   # never goes back up
    assert not model.policy.log_std.requires_grad
    assert float(model.policy.log_std.exp().mean()) == pytest.approx(steps[-1], rel=1e-3)


# ---------------------------------------------------------------- Track 2: Dict observations, asymmetric SAC critic
NEW_GROUPS = ("pos", "vel", "battery", "time", "prev", "crowd_n", "history", "heat_all_u", "heat_rescue_u")


def _dict_env(privileged, seeds=(10000, 10001, 10002)):
    return make_env("goto", "v1", scenario_seeds=list(seeds), hold=10, obs_groups=NEW_GROUPS, obs_mode="dict",
                    privileged=privileged)


def _batch(space, n=3, seed=0):
    """A random batch of observations from a Dict space, as torch tensors."""
    space.seed(seed)
    obs = [space.sample() for _ in range(n)]
    return {k: torch.as_tensor(np.stack([o[k] for o in obs])) for k in space.spaces}


def test_dict_extractor_sizes_and_cheaper_cnn():
    from rl_net import DictMapExtractor
    space = _dict_env(True).observation_space
    actor = DictMapExtractor(space)
    critic = DictMapExtractor(space, use_priv=True)
    assert actor.features_dim == 128 + 32 and critic.features_dim == 128 + 32 + 128 + 1
    lin = [m for m in actor.map_net if isinstance(m, torch.nn.Linear)][0]
    assert lin.in_features == 32 * 5 * 5                       # 4x smaller than CnnMapExtractor's 32 x 10 x 10
    b = _batch(space)
    assert actor(b).shape == (3, 160) and critic(b).shape == (3, 289)
    with pytest.raises(AssertionError):
        DictMapExtractor(_dict_env(False).observation_space, use_priv=True)    # no priv in the env: refused


def _perturb_priv(b):
    out = dict(b)
    out["priv_maps"] = torch.randint(0, 256, b["priv_maps"].shape, dtype=b["priv_maps"].dtype)
    out["priv_n"] = torch.rand(b["priv_n"].shape)
    return out


def _asym_sac(privileged=True):
    from stable_baselines3 import SAC

    from rl_net import AsymSACPolicy, DictMapExtractor
    venv = DummyVecEnv([lambda: _dict_env(privileged) for _ in range(2)])
    kw = {"features_extractor_class": DictMapExtractor, "features_extractor_kwargs": {"use_priv": False},
          "normalize_images": False, "net_arch": [32, 32]}
    if privileged:
        kw["critic_features_extractor_kwargs"] = {"use_priv": True}
    return SAC(AsymSACPolicy, venv, buffer_size=500, learning_starts=16, batch_size=16, seed=0, device="cpu",
               policy_kwargs=kw)


def test_actor_output_is_unchanged_when_only_the_privileged_input_changes():
    """THE D-24 test: the flying policy (actor) cannot react to the critic-only true state."""
    model = _asym_sac(privileged=True)
    pol = model.policy
    assert pol.critic.features_extractor.use_priv and pol.critic_target.features_extractor.use_priv
    assert not pol.actor.features_extractor.use_priv
    assert pol.actor.features_extractor is not pol.critic.features_extractor
    b = _batch(pol.observation_space, n=4)
    bp = _perturb_priv(b)
    with torch.no_grad():
        assert torch.equal(pol.actor(b, deterministic=True), pol.actor(bp, deterministic=True))
        mean, log_std, _ = pol.actor.get_action_dist_params(b)
        mean2, log_std2, _ = pol.actor.get_action_dist_params(bp)
        assert torch.equal(mean, mean2) and torch.equal(log_std, log_std2)
        act = pol.actor(b, deterministic=True)
        q, qp = pol.critic(b, act), pol.critic(bp, act)
    assert not torch.allclose(q[0], qp[0])                       # the critic does read it


def test_actor_output_unchanged_by_priv_after_training_too(tmp_path):
    model = _asym_sac(privileged=True)
    model.learn(total_timesteps=48)
    pol = model.policy
    b = _batch(pol.observation_space, n=4, seed=3)
    with torch.no_grad():
        assert torch.equal(pol.actor(b, deterministic=True), pol.actor(_perturb_priv(b), deterministic=True))
    # the actor's own parameters contain nothing that reads priv
    assert not any("priv" in n for n, _ in pol.actor.named_parameters())
    assert any("priv" in n for n, _ in pol.critic.named_parameters())


def _save_with_settings(model, tmp_path, **settings):
    import json
    model.save(tmp_path / "model")
    cfg = {"controls": "goto", "hold_steps": 10, "obs_groups": list(NEW_GROUPS), "obs_mode": "dict", **settings}
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(tmp_path / "model.zip")


def test_sac_asymmetric_trains_saves_loads_and_flies_without_priv(tmp_path):
    from rl_eval import evaluate
    from rl_utils import load_policy
    model = _asym_sac(privileged=True)
    model.learn(total_timesteps=48)
    path = _save_with_settings(model, tmp_path, algo="SAC", privileged=True)
    pol = load_policy(path)
    assert pol.name == "SAC" and pol.obs_mode == "dict" and pol.hold == 10
    loaded = pol.model.policy
    assert loaded.critic.features_extractor.use_priv and not loaded.actor.features_extractor.use_priv
    env = UAVEnv(battery_wh=1000.0)
    env.reset(seed=3)
    a = pol.act(env)
    assert a.shape == (4,) and a[2] == 0.0 and a[3] == 1.0
    # same action as the in-memory model on the same (priv-free) observation
    obs = pol.observation(env)
    assert np.allclose(model.predict(obs, deterministic=True)[0], pol.model.predict(obs, deterministic=True)[0])
    df = evaluate(["SAC"], md.seeds("val")[:1], path, battery_wh=1000.0)
    assert list(df.policy) == ["SAC"] and df.survived.all()


def test_sac_symmetric_and_ppo_dict_train_and_act(tmp_path):
    from rl_net import DictMapExtractor
    from rl_utils import load_policy
    sym = _asym_sac(privileged=False)
    assert not sym.policy.critic.features_extractor.use_priv
    sym.learn(total_timesteps=32)
    venv = DummyVecEnv([lambda: _dict_env(False) for _ in range(2)])
    ppo = PPO("MultiInputPolicy", venv, n_steps=16, batch_size=32, n_epochs=1, seed=0, device="cpu",
              policy_kwargs={"net_arch": [32], "features_extractor_class": DictMapExtractor,
                             "features_extractor_kwargs": {"use_priv": False}, "normalize_images": False})
    ppo.learn(total_timesteps=64)
    pol = load_policy(_save_with_settings(ppo, tmp_path, algo="PPO"))
    env = UAVEnv(battery_wh=1000.0)
    env.reset(seed=3)
    assert pol.name == "PPO" and pol.act(env).shape == (4,)


def test_rl_train_builds_every_track2_learner(tmp_path):
    """rl_train's own builders (config -> env -> model) for E0 (PPO), E2 (SAC) and E3 (SAC + privileged critic)."""
    import rl_train
    base = dict(md.CFG["rl"])
    try:
        _build_all(rl_train, base, tmp_path)
    finally:
        md.apply_profile("default")


def _build_all(rl_train, base, tmp_path):
    for algo, privileged in (("PPO", False), ("SAC", False), ("SAC", True)):
        cfg = {**base, "algo": algo, "obs_mode": "dict", "privileged": privileged, "obs_groups": list(NEW_GROUPS),
               "gamma": 0.95, "n_envs": 2, "train_seed_range": [10000, 19999], "n_steps": 16, "batch_size": 16,
               "sac": {**base["sac"], "buffer_size": 200, "learning_starts": 8, "batch_size": 8}}
        venv = rl_train.build(cfg, "rl_static")
        model = rl_train.make_model(cfg, venv, tmp_path / algo)
        model.learn(total_timesteps=32)
        assert model.gamma == 0.95 and venv.gamma == 0.95
        pool = venv.venv.envs[0].unwrapped.scenario_pool
        assert min(pool) == 10000 and len(pool) == 10000
        if algo == "SAC":
            assert model.policy.critic.features_extractor.use_priv == privileged
            assert not model.policy.actor.features_extractor.use_priv
