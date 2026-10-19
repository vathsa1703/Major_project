"""RL helpers: curriculum control wrapper, env factory, and policy adapters that plug into run_baselines.run_episode.

Curriculum (the plan's order): `xy` = the agent only moves horizontally (altitude fixed at the start height, full
power) -> `xyz` = + altitude -> `xyzp` = + transmit power. Each step must work before the next one is switched on.
"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces

import make_dataset as md
from uav_env import UAVEnv

CONTROLS = {"xy": 2, "xyz": 3, "xyzp": 4}


def expand_action(a, controls):
    """Agent action (2, 3 or 4 numbers) -> the env's 4 numbers [vx, vy, vz, power]. Unused controls are held:
    vz = 0 (keep altitude) and power = +1 (full power)."""
    a = np.asarray(a, dtype=np.float64).ravel()
    k = CONTROLS[controls]
    assert len(a) == k, f"controls={controls!r} needs {k} numbers, got {len(a)}"
    full = np.array([0.0, 0.0, 0.0, 1.0])
    full[:k] = a
    return full


class ControlWrapper(gym.ActionWrapper):
    """Shrinks the action space to the controls switched on in the current curriculum step."""

    def __init__(self, env, controls):
        super().__init__(env)
        self.controls = controls
        self.action_space = spaces.Box(-1.0, 1.0, shape=(CONTROLS[controls],), dtype=np.float32)

    def action(self, action):
        return expand_action(action, self.controls)


def make_env(controls="xy", reward=None, scenario_seeds=None, battery_wh=None):
    """A training/eval env. Call AFTER md.apply_profile(...): the env reads the config when it is created."""
    return ControlWrapper(UAVEnv(reward=reward, battery_wh=battery_wh, scenario_seeds=scenario_seeds), controls)


def train_seeds():
    return md.seeds("train")


# ---------------------------------------------------------------- adapters for run_baselines.run_episode
class RLPolicy:
    """A trained SB3 model as a policy: act(env) -> 4-number action."""

    name = "PPO"

    def __init__(self, model, controls):
        self.model, self.controls = model, controls

    def reset(self, env):
        pass

    def act(self, env):
        action, _ = self.model.predict(env.observation(), deterministic=True)
        return expand_action(action, self.controls)


class RandomPolicy:
    """Uniformly random actions in the same control space as the agent (the floor an agent must beat)."""

    name = "Random"

    def __init__(self, controls="xy"):
        self.controls = controls

    def reset(self, env):
        self.rng = np.random.default_rng([env.scenario_seed, 99])

    def act(self, env):
        return expand_action(self.rng.uniform(-1, 1, CONTROLS[self.controls]), self.controls)
