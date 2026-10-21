"""Train a PPO or SAC agent on the UAV env. All settings are in config.yaml under `rl:` (flags only override them).

    python rl_train.py                                   # curriculum step 1: profile rl_static, move only, 300k steps
    python rl_train.py --timesteps 20000 --name smoke
Track 2 (Dict observation: uncapped maps, crowd size, own history; fresh scenarios; gamma 0.95):
    python rl_train.py --algo PPO --obs_mode dict --train_seeds 10000-19999 --gamma 0.95 --name e0_ppo
                       --obs pos,vel,battery,time,prev,crowd_n,history,heat_all_u,heat_rescue_u
    python rl_train.py --algo SAC --obs_mode dict --privileged ...   # SAC with an asymmetric (critic-only priv) critic
Training scenarios are drawn ONLY from the training seeds (0-99). Validation seeds (100-119) are for choosing a model,
test seeds (120-139) for the final report. Outputs: results/rl/<name>/model.zip, config.json, tb/ (TensorBoard logs).
Each reward part is logged separately (reward/coverage, reward/energy, reward/terminal) to spot reward hacking.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO, SAC
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv, VecMonitor, VecNormalize

import make_dataset as md
from rl_net import AsymSACPolicy, CnnMapExtractor, DictMapExtractor
from rl_utils import CONTROLS, make_env, training_pool

HERE = Path(__file__).parent


class StdAnnealCallback(BaseCallback):
    """Shrinks the exploration noise on a straight line from `start` to `end` over the whole training run.

    The noise is the random wobble added to every action while the agent learns. In this task an action is a spot on a
    2 km map, so a noise of 0.33 means about +-330 m, more than the width of a crowd, which hides the effect of the
    agent's own choice from the learning signal. Annealing lets it explore widely at first and refine at the end.
    It gives the agent no information about the task; it only changes how much it experiments."""

    def __init__(self, start, end, total_timesteps):
        super().__init__()
        self.start, self.end, self.total = start, end, total_timesteps
        self.history = []

    def _set(self):
        progress = min(self.num_timesteps / self.total, 1.0)
        std = self.start + (self.end - self.start) * progress
        self.model.policy.log_std.data.fill_(float(np.log(std)))
        self.history.append((self.num_timesteps, std))

    def _on_training_start(self):
        self.model.policy.log_std.requires_grad_(False)       # the schedule decides it, not the optimiser
        self._set()

    def _on_rollout_start(self):
        self._set()

    def _on_step(self):
        return True


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

    def __init__(self, every, seeds, controls, hold=1, obs_groups=None, obs_mode="box"):
        super().__init__()
        self.every, self.seeds, self.controls, self.hold, self.last = every, seeds, controls, hold, 0
        self.obs_groups, self.obs_mode = obs_groups, obs_mode
        self.history = []

    def _on_step(self):
        if self.num_timesteps - self.last >= self.every:
            self.last = self.num_timesteps
            from rl_utils import RLPolicy
            from run_baselines import run_episode
            from uav_env import UAVEnv
            pol = RLPolicy(self.model, self.controls, self.hold, self.obs_groups, self.obs_mode)
            cov = float(np.mean([run_episode(UAVEnv(), pol, s)["coverage_full"] for s in self.seeds]))
            self.history.append((self.num_timesteps, cov))
            self.logger.record("val/coverage_full", cov)
            print(f"VAL @ {self.num_timesteps} steps: coverage_full {cov:.3f} on {len(self.seeds)} val scenarios",
                  flush=True)
        return True


def build(cfg, profile):
    md.apply_profile(profile)
    pool = training_pool(cfg.get("train_seed_range"))
    venv = DummyVecEnv([lambda: make_env(cfg["controls"], cfg["reward"], scenario_seeds=pool,
                                         hold=cfg["hold_steps"], obs_groups=cfg["obs_groups"],
                                         obs_mode=cfg.get("obs_mode", "box"), privileged=cfg.get("privileged", False))
                        for _ in range(cfg["n_envs"])])
    venv = VecMonitor(venv)
    # reward scaling only: observations are already in [-1, 1], so a saved model needs no extra statistics
    return VecNormalize(venv, norm_obs=False, norm_reward=True, gamma=cfg["gamma"]) if cfg["norm_reward"] else venv


def policy_kwargs(cfg):
    """The network: a plain MLP on the observation, the CNN that reads the two maps as a picture (box observation),
    or the Dict-observation CNN (obs_mode dict). For SAC with privileged=True the critic's extractor also reads the
    critic-only true state; the actor's never does (rl_net.AsymSACPolicy)."""
    algo = cfg.get("algo", "PPO")
    if cfg.get("obs_mode", "box") == "dict":
        kw = {"features_extractor_class": DictMapExtractor, "features_extractor_kwargs": {"use_priv": False},
              "normalize_images": False}
        if algo == "SAC":
            kw["net_arch"] = list(cfg["sac"]["net_arch"])
            if cfg.get("privileged"):
                kw["critic_features_extractor_kwargs"] = {"use_priv": True}
        else:
            kw.update(net_arch=list(cfg["net_arch"]), log_std_init=cfg["log_std_init"])
        return kw
    assert not cfg.get("privileged"), "the privileged critic needs obs_mode dict"
    if algo == "SAC":
        kw = {"net_arch": list(cfg["sac"]["net_arch"])}
    else:
        kw = {"net_arch": list(cfg["net_arch"]), "log_std_init": cfg["log_std_init"]}
    if cfg["policy"] == "cnn":
        kw.update(features_extractor_class=CnnMapExtractor,
                  features_extractor_kwargs={"grid": md.CFG["env"]["grid"]})
    return kw


def make_model(cfg, venv, out):
    """PPO (as before) or SAC with separate actor / critic extractors (asymmetric when privileged)."""
    common = dict(seed=cfg["seed"], gamma=cfg["gamma"], policy_kwargs=policy_kwargs(cfg),
                  tensorboard_log=str(out / "tb"), device="cpu", verbose=1)
    if cfg.get("algo", "PPO") == "SAC":
        s = cfg["sac"]
        return SAC(AsymSACPolicy, venv, learning_rate=s["learning_rate"], buffer_size=s["buffer_size"],
                   learning_starts=s["learning_starts"], batch_size=s["batch_size"], tau=s["tau"],
                   train_freq=s["train_freq"], gradient_steps=s["gradient_steps"], ent_coef=s["ent_coef"], **common)
    assert not cfg.get("privileged"), "the asymmetric (privileged) critic is implemented for SAC only"
    policy = "MultiInputPolicy" if cfg.get("obs_mode", "box") == "dict" else "MlpPolicy"
    return PPO(policy, venv, learning_rate=cfg["learning_rate"], n_steps=cfg["n_steps"], batch_size=cfg["batch_size"],
               n_epochs=cfg["n_epochs"], gae_lambda=cfg["gae_lambda"], clip_range=cfg["clip_range"],
               ent_coef=cfg["ent_coef"], **common)


def main():
    cfg = dict(md.CFG["rl"])
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", default=cfg["algo"], choices=["PPO", "SAC"])
    ap.add_argument("--profile", default=cfg["profile"])
    ap.add_argument("--controls", default=cfg["controls"], choices=list(CONTROLS))
    ap.add_argument("--reward", default=cfg["reward"], choices=["v1", "v2"])
    ap.add_argument("--timesteps", type=int, default=cfg["total_timesteps"])
    ap.add_argument("--seed", type=int, default=cfg["seed"])
    ap.add_argument("--name", default=None)
    ap.add_argument("--log_std_init", type=float, default=cfg["log_std_init"])
    ap.add_argument("--hold", type=int, default=cfg["hold_steps"], help="seconds each decision is held")
    ap.add_argument("--policy", default=cfg["policy"], choices=["mlp", "cnn"],
                    help="how the agent reads the observation (box mode; dict mode always uses its CNN)")
    ap.add_argument("--obs", default=",".join(cfg["obs_groups"]), help="comma list of observation groups to use")
    ap.add_argument("--obs_mode", default=cfg["obs_mode"], choices=["box", "dict"])
    ap.add_argument("--privileged", action="store_true", help="SAC: asymmetric critic that also sees the true state")
    ap.add_argument("--gamma", type=float, default=cfg["gamma"])
    ap.add_argument("--n_envs", type=int, default=cfg["n_envs"])
    ap.add_argument("--train_seeds", default=None,
                    help="lo-hi: train on fresh procedural scenarios lo..hi (default: config train_seed_range)")
    ap.add_argument("--std_end", type=float, default=cfg["std_end"],
                    help="if set, anneal the exploration noise from exp(log_std_init) down to this value")
    ap.add_argument("--no_norm_reward", action="store_true")
    a = ap.parse_args()
    seed_range = [int(v) for v in a.train_seeds.split("-")] if a.train_seeds else cfg["train_seed_range"]
    cfg.update(algo=a.algo, profile=a.profile, controls=a.controls, reward=a.reward, total_timesteps=a.timesteps,
               seed=a.seed, log_std_init=a.log_std_init, hold_steps=a.hold, policy=a.policy,
               obs_groups=a.obs.split(","), obs_mode=a.obs_mode, privileged=a.privileged or cfg["privileged"],
               gamma=a.gamma, n_envs=a.n_envs, train_seed_range=seed_range, std_end=a.std_end,
               norm_reward=cfg["norm_reward"] and not a.no_norm_reward)
    assert not (cfg["std_end"] and cfg["algo"] == "SAC"), "std_end (noise annealing) is for PPO only"
    torch.set_num_threads(cfg["torch_threads"])
    name = a.name or f"{cfg['profile']}_{cfg['controls']}_{cfg['reward']}_s{cfg['seed']}"
    out = HERE / cfg["out_dir"] / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    venv = build(cfg, cfg["profile"])
    model = make_model(cfg, venv, out)
    val_cb = ValScoreCallback(max(cfg["val_eval_every_steps"] // cfg["n_envs"], 1) * cfg["n_envs"],
                              md.seeds("val")[: cfg["val_eval_scenarios"]], cfg["controls"], cfg["hold_steps"],
                              cfg["obs_groups"], cfg["obs_mode"])
    anneal = ([StdAnnealCallback(float(np.exp(cfg["log_std_init"])), cfg["std_end"], cfg["total_timesteps"])]
              if cfg["std_end"] else [])
    callbacks = [RewardPartsCallback(), val_cb, *anneal,
                 CheckpointCallback(max(cfg["checkpoint_every_steps"] // cfg["n_envs"], 1), str(out / "checkpoints"))]
    t0 = time.time()
    model.learn(total_timesteps=cfg["total_timesteps"], callback=callbacks, progress_bar=False)
    model.save(out / "model")
    took = time.time() - t0
    print(f"done in {took:.0f}s ({cfg['total_timesteps'] / took:.1f} decisions/s) -> {out / 'model.zip'}", flush=True)


if __name__ == "__main__":
    main()
