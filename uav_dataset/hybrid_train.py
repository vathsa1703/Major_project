"""Train the hybrid timing AI (hybrid.py): PPO with a Discrete(2) head (follow B6 / leave for the B-target) on a FIXED
pool of precomputed scenarios (hybrid_tables.py bundle). All settings: config.yaml `hybrid:` (flags only override).

    python hybrid_train.py --profile sites_d20_t0_ann --bundle bundle_t0.npz --seed 0 --name hyb_t0_s0
    python hybrid_train.py --profile sites_d20_t0_ann --bundle bundle_t0.npz --timesteps 2000 --name smoke
Outputs: results/hybrid_rl/<name>/model.zip + config.json (+ checkpoints/ for crash recovery; the FINAL model is the
one evaluated, pre-registered). No validation scenario is played during training (no model selection on val).
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv, VecMonitor, VecNormalize

import make_dataset as md

HERE = Path(__file__).parent


class TrainLog(BaseCallback):
    """After every rollout: mean coverage per decision and the share of LEAVE actions in the rollout."""

    def __init__(self):
        super().__init__()
        self.cov, self.leave, self.t0 = [], [], time.time()

    def _on_step(self):
        for info in self.locals["infos"]:
            self.cov.append(info["coverage"])
            self.leave.append(info["hybrid_action"])
        return True

    def _on_rollout_end(self):
        if self.cov:
            c, lv = float(np.mean(self.cov)), float(np.mean(self.leave))
            self.logger.record("hybrid/coverage", c)
            self.logger.record("hybrid/leave_share", lv)
            print(f"{self.num_timesteps} decisions  {time.time() - self.t0:.0f}s  coverage {c:.3f}  leave {lv:.2f}",
                  flush=True)
        self.cov, self.leave = [], []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--bundle", required=True, help="hybrid_tables.py bundle of the training pool")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timesteps", type=int, default=None)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out_dir", default=str(HERE / "results" / "hybrid_rl"))
    ap.add_argument("--torch_threads", type=int, default=1)
    ap.add_argument("--pool", default=None, help="lo-hi: override the pool (smoke tests only)")
    a = ap.parse_args()
    md.apply_profile(a.profile)
    import hybrid
    from rl_net import DictMapExtractor
    h = dict(md.CFG["hybrid"])
    total = a.timesteps or int(h["timesteps"])
    lo, hi = a.pool.split("-") if a.pool else h["train_seeds"]
    pool = list(range(int(lo), int(hi) + 1))
    held_out = set(md.seeds("val")) | set(md.seeds("test"))
    assert held_out.isdisjoint(pool), "the training pool must not contain validation or test seeds"
    data = hybrid.load_bundle(a.bundle)
    missing = sorted(set(pool) - set(data))
    assert not missing, f"the bundle lacks {len(missing)} pool seeds, e.g. {missing[:5]}"
    torch.set_num_threads(a.torch_threads)
    out = Path(a.out_dir) / a.name
    out.mkdir(parents=True, exist_ok=True)
    cfg = dict(h, profile=a.profile, seed=a.seed, timesteps=total, bundle=Path(a.bundle).name,
               hold_steps=hybrid.every(), algo="PPO", kind="hybrid_timing")
    (out / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    venv = DummyVecEnv([lambda: hybrid.HybridTimingEnv(scenario_seeds=pool, data=data) for _ in range(h["n_envs"])])
    venv = VecNormalize(VecMonitor(venv), norm_obs=False, norm_reward=True, gamma=h["gamma"])
    kw = {"features_extractor_class": DictMapExtractor, "features_extractor_kwargs": {"use_priv": False},
          "normalize_images": False, "net_arch": list(h["net_arch"])}
    model = PPO("MultiInputPolicy", venv, learning_rate=h["learning_rate"], n_steps=h["n_steps"],
                batch_size=h["batch_size"], n_epochs=h["n_epochs"], gamma=h["gamma"], gae_lambda=h["gae_lambda"],
                clip_range=h["clip_range"], ent_coef=h["ent_coef"], policy_kwargs=kw, seed=a.seed, device="cpu",
                verbose=0)
    cbs = [TrainLog(), CheckpointCallback(max(int(h["checkpoint_every"]) // h["n_envs"], 1), str(out / "checkpoints"))]
    t0 = time.time()
    model.learn(total_timesteps=total, callback=cbs, progress_bar=False)
    model.save(out / "model")
    took = time.time() - t0
    print(f"done in {took:.0f}s ({total / took:.1f} decisions/s) -> {out / 'model.zip'}", flush=True)


if __name__ == "__main__":
    main()
