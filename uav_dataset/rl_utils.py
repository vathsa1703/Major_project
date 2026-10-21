"""RL helpers: curriculum control wrapper, env factory, and policy adapters that plug into run_baselines.run_episode.

Curriculum (the plan's order): the agent controls only position, then also altitude, then also power.
Two ways to steer, because they are not equally easy to learn:
  xy / xyz / xyzp      = VELOCITY controls: the action is how fast to fly. Hovering needs the agent to output exactly 0.
  goto / gotoz / gotozp = WAYPOINT controls: the action is WHERE to fly (a spot on the map, then also an altitude, then
                          also the power). The drone flies there at full speed and stays when it arrives, so staying
                          over the crowd needs no special effort. (Velocity controls made PPO find the crowd and then
                          drift away: see CLAUDE.md.)
Unused controls are held: altitude at the start height and full power.
"""
import json
from pathlib import Path

import gymnasium as gym
import numpy as np
from gymnasium import spaces

import make_dataset as md
from uav_env import UAVEnv

CONTROLS = {"xy": 2, "xyz": 3, "xyzp": 4, "goto": 2, "gotoz": 3, "gotozp": 4}
WAYPOINT = ("goto", "gotoz", "gotozp")


def expand_action(a, controls, env=None):
    """Agent action (2, 3 or 4 numbers) -> the env's 4 numbers [vx, vy, vz, power].
    Waypoint controls need `env` (to know where the drone is now)."""
    a = np.asarray(a, dtype=np.float64).ravel()
    k = CONTROLS[controls]
    assert len(a) == k, f"controls={controls!r} needs {k} numbers, got {len(a)}"
    full = np.array([0.0, 0.0, 0.0, 1.0])
    if controls not in WAYPOINT:
        full[:k] = a
        return full
    assert env is not None, "waypoint controls need the env"
    e, u = env.unwrapped if hasattr(env, "unwrapped") else env, md.CFG["uav"]
    tx, ty = (a[0] + 1) / 2 * e.L, (a[1] + 1) / 2 * e.L                      # target spot on the map
    d = np.array([tx - e.x, ty - e.y]) / (u["v_max_mps"] * e.dt)
    if np.linalg.norm(d) > 1.0:
        d = d / np.linalg.norm(d)                                           # fly at full speed, never faster
    full[:2] = d
    if k >= 3:                                                              # target altitude
        th = u["h_min_m"] + (a[2] + 1) / 2 * (u["h_max_m"] - u["h_min_m"])
        full[2] = np.clip((th - e.h) / (u["vz_max_mps"] * e.dt), -1.0, 1.0)
    if k >= 4:
        full[3] = a[3]
    return full


class ControlWrapper(gym.ActionWrapper):
    """Shrinks the action space to the controls switched on in the current curriculum step."""

    def __init__(self, env, controls):
        super().__init__(env)
        self.controls = controls
        self.action_space = spaces.Box(-1.0, 1.0, shape=(CONTROLS[controls],), dtype=np.float32)

    def action(self, action):
        return expand_action(action, self.controls, self.env)


class HoldWrapper(gym.Wrapper):
    """The agent decides once every `k` seconds; its choice is held (and re-applied each second) for `k` steps and the
    rewards of those steps are added up. This is the rhythm the baselines use (they re-plan every K = 10 s). It turns a
    300-decision game into a 30-decision game, which is much easier to learn, and stops the second-by-second
    overshoot-and-correct circling seen with k = 1."""

    def __init__(self, env, k):
        super().__init__(env)
        self.k = k

    def step(self, action):
        total = 0.0
        for _ in range(self.k):
            obs, r, terminated, truncated, info = self.env.step(action)
            total += r
            if terminated or truncated:
                break
        return obs, total, terminated, truncated, info


def make_env(controls="xy", reward=None, scenario_seeds=None, battery_wh=None, hold=1, obs_groups=None,
             obs_mode="box", privileged=False):
    """A training/eval env. Call AFTER md.apply_profile(...): the env reads the config when it is created.
    hold = how many seconds the agent's choice is held (1 = it decides every second); it is also the spacing of the
    `history` observation group. obs_mode/privileged: see UAVEnv (privileged = critic-only true state, dict only)."""
    env = ControlWrapper(UAVEnv(reward=reward, battery_wh=battery_wh, scenario_seeds=scenario_seeds,
                                obs_groups=obs_groups, obs_mode=obs_mode, privileged=privileged,
                                history_every=hold), controls)
    return HoldWrapper(env, hold) if hold > 1 else env


def train_seeds():
    return md.seeds("train")


def training_pool(seed_range=None):
    """Scenario seeds the agent trains on. None = the training split (0-99, the old behaviour). [lo, hi] = a pool of
    FRESH procedural scenarios lo..hi (inclusive), which must not overlap the validation or test seeds."""
    if seed_range is None:
        return train_seeds()
    lo, hi = (int(v) for v in seed_range)
    pool = list(range(lo, hi + 1))
    held_out = set(md.seeds("val")) | set(md.seeds("test"))
    assert pool and held_out.isdisjoint(pool), "the training pool must not contain validation or test seeds"
    return pool


# ---------------------------------------------------------------- adapters for run_baselines.run_episode
class RLPolicy:
    """A trained SB3 model as a policy: act(env) -> 4-number action."""

    name = "PPO"

    def __init__(self, model, controls, hold=1, obs_groups=None, obs_mode="box"):
        # controls, hold, obs_groups and obs_mode must match how the model was trained (see model_settings)
        self.model, self.controls, self.hold, self.obs_groups = model, controls, hold, obs_groups
        self.obs_mode = obs_mode or "box"
        self.last = None

    def reset(self, env):
        self.last = None

    def observation(self, env):
        """What the acting policy sees. The env is NEVER asked for the privileged (critic-only) state. If the model
        was trained with an asymmetric critic, its observation space still lists the priv keys; they are filled with
        zeros, which the actor's extractor ignores anyway (it never reads priv keys)."""
        if self.obs_mode != "dict":
            return env.observation(self.obs_groups, history_every=self.hold)
        obs = env.observation(self.obs_groups, dict_obs=True, history_every=self.hold, privileged=False)
        space = getattr(self.model, "observation_space", None)
        for k, sp in getattr(space, "spaces", {}).items():
            if k not in obs:
                assert k.startswith("priv"), f"the env did not produce the observation key {k!r}"
                obs[k] = np.zeros(sp.shape, dtype=sp.dtype)
        return obs

    def act(self, env):
        if self.last is None or env.t % self.hold == 0:                  # decide every `hold` seconds
            self.last, _ = self.model.predict(self.observation(env), deterministic=True)
        return expand_action(self.last, self.controls, env)


def load_policy(model_path, controls=None, hold=None):
    """A trained model (PPO or SAC, read from its saved settings) as an RLPolicy, with its own controls, hold,
    observation groups and observation mode."""
    saved = model_settings(model_path)
    algo = saved.get("algo", "PPO")
    if algo == "SAC":
        from stable_baselines3 import SAC as Algo
    else:
        from stable_baselines3 import PPO as Algo
    pol = RLPolicy(Algo.load(model_path, device="cpu"), controls or saved.get("controls", "xy"),
                   hold or saved.get("hold_steps", 1), saved.get("obs_groups"), saved.get("obs_mode", "box"))
    pol.name = algo
    return pol


class RandomPolicy:
    """Uniformly random actions in the same control space as the agent (the floor an agent must beat)."""

    name = "Random"

    def __init__(self, controls="xy"):
        self.controls = controls

    def reset(self, env):
        self.rng = np.random.default_rng([env.scenario_seed, 99])

    def act(self, env):
        return expand_action(self.rng.uniform(-1, 1, CONTROLS[self.controls]), self.controls, env)


# ---------------------------------------------------------------- settings saved next to every trained model
def model_settings(model_path):
    """The settings a model was trained with (controls, hold_steps, obs_groups, policy), read from the
    config.json that rl_train.py saves next to it. Old models lack some keys; their defaults are the old behaviour
    (hold 1, all groups)."""
    p = Path(model_path).resolve()
    for folder in (p.parent, p.parent.parent):
        cfg = folder / "config.json"
        if cfg.exists():
            return json.loads(cfg.read_text(encoding="utf-8"))
    return {}
