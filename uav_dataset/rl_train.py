"""Train a PPO agent on the UAV env. All settings are in config.yaml under `rl:` (flags only override them).

    python rl_train.py                                   # curriculum step 1: profile rl_static, move only, 300k steps
    python rl_train.py --timesteps 20000 --name smoke
Training scenarios are drawn ONLY from the training seeds (0-99). Validation seeds (100-119) are for choosing a model,
test seeds (120-139) for the final report. Outputs: results/rl/<name>/model.zip, config.json, tb/ (TensorBoard logs).
Each reward part is logged separately (reward/coverage, reward/energy, reward/terminal) to spot reward hacking.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv, VecMonitor, VecNormalize

import make_dataset as md
from rl_utils import make_env, train_seeds

HERE = Path(__file__).parent


class RewardPartsCallback(BaseCallback):
    """After every rollout, log the mean of each reward part and of coverage over the steps just collected."""

    KEYS = ("reward_coverage", "reward_energy", "reward_terminal")

    def __init__(self):
        super().__init__()
        self.buf = {k: [] for k in self.KEYS}

    def _on_step(self):
        for info in self.locals["infos"]:
            for k in self.KEYS:
                self.buf[k].append(info[k])
        return True

    def _on_rollout_end(self):
        for k, v in self.buf.items():
            if v:
                self.logger.record(f"reward/{k.removeprefix('reward_')}", float(np.mean(v)))
            self.buf[k] = []


class ValScoreCallback(BaseCallback):
    """Every `every` steps, play the first few VALIDATION scenarios with the deterministic policy and print the mean
    coverage over the horizon. Lets us watch real progress (and see over-fitting) during a long run."""

    def __init__(self, every, seeds, controls):
        super().__init__()
        self.every, self.seeds, self.controls, self.last = every, seeds, controls, 0
        self.history = []

    def _on_step(self):
        if self.num_timesteps - self.last >= self.every:
            self.last = self.num_timesteps
            from rl_utils import RLPolicy
            from run_baselines import run_episode
            from uav_env import UAVEnv
            pol = RLPolicy(self.model, self.controls)
            cov = float(np.mean([run_episode(UAVEnv(), pol, s)["coverage_full"] for s in self.seeds]))
            self.history.append((self.num_timesteps, cov))
            self.logger.record("val/coverage_full", cov)
            print(f"VAL @ {self.num_timesteps} steps: coverage_full {cov:.3f} on {len(self.seeds)} val scenarios",
                  flush=True)
        return True


def build(cfg, profile):
    md.apply_profile(profile)
    pool = train_seeds()
    venv = DummyVecEnv([lambda: make_env(cfg["controls"], cfg["reward"], scenario_seeds=pool)
                        for _ in range(cfg["n_envs"])])
    venv = VecMonitor(venv)
    # reward scaling only: observations are already in [-1, 1], so a saved model needs no extra statistics
    return VecNormalize(venv, norm_obs=False, norm_reward=True, gamma=cfg["gamma"]) if cfg["norm_reward"] else venv


def main():
    cfg = dict(md.CFG["rl"])
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=cfg["profile"])
    ap.add_argument("--controls", default=cfg["controls"], choices=["xy", "xyz", "xyzp"])
    ap.add_argument("--reward", default=cfg["reward"], choices=["v1", "v2"])
    ap.add_argument("--timesteps", type=int, default=cfg["total_timesteps"])
    ap.add_argument("--seed", type=int, default=cfg["seed"])
    ap.add_argument("--name", default=None)
    ap.add_argument("--log_std_init", type=float, default=cfg["log_std_init"])
    ap.add_argument("--no_norm_reward", action="store_true")
    a = ap.parse_args()
    cfg.update(profile=a.profile, controls=a.controls, reward=a.reward, total_timesteps=a.timesteps, seed=a.seed,
               log_std_init=a.log_std_init, norm_reward=cfg["norm_reward"] and not a.no_norm_reward)
    name = a.name or f"{cfg['profile']}_{cfg['controls']}_{cfg['reward']}_s{cfg['seed']}"
    out = HERE / cfg["out_dir"] / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    venv = build(cfg, cfg["profile"])
    model = PPO(
        "MlpPolicy", venv, seed=cfg["seed"], learning_rate=cfg["learning_rate"], n_steps=cfg["n_steps"],
        batch_size=cfg["batch_size"], n_epochs=cfg["n_epochs"], gamma=cfg["gamma"], gae_lambda=cfg["gae_lambda"],
        clip_range=cfg["clip_range"], ent_coef=cfg["ent_coef"],
        policy_kwargs={"net_arch": list(cfg["net_arch"]), "log_std_init": cfg["log_std_init"]},
        tensorboard_log=str(out / "tb"), device="cpu", verbose=1)
    val_cb = ValScoreCallback(max(cfg["val_eval_every_steps"] // cfg["n_envs"], 1) * cfg["n_envs"],
                              md.seeds("val")[: cfg["val_eval_scenarios"]], cfg["controls"])
    callbacks = [RewardPartsCallback(), val_cb,
                 CheckpointCallback(max(cfg["checkpoint_every_steps"] // cfg["n_envs"], 1), str(out / "checkpoints"))]
    t0 = time.time()
    model.learn(total_timesteps=cfg["total_timesteps"], callback=callbacks, progress_bar=False)
    model.save(out / "model")
    print(f"done in {time.time() - t0:.0f}s -> {out / 'model.zip'}")


if __name__ == "__main__":
    main()
