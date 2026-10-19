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
