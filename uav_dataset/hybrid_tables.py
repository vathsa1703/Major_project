"""Precompute the hybrid timing AI's B6 tables and B-targets (hybrid.scenario_data) for a pool of scenarios.

    python hybrid_tables.py build --profile sites_d20_t0_ann --seeds 10000-10299 --shard 0/4
    python hybrid_tables.py bundle --profile sites_d20_t0_ann --seeds 10000-10299 --out bundle_t0.npz
    python hybrid_tables.py build --profile sites_d20_t0_ann --seeds 100-119 --access oma_opt     # eval, OMA
build writes one cached .npz per scenario (results/hybrid_cache/, or --cache_dir), skipping the ones that exist;
bundle packs them into one file (seeds, tables (S, 30, 980), targets (S, 3)) for training.
"""
import argparse
import os
import time

import numpy as np

import make_dataset as md


def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        seeds += list(range(int(lo), int(hi or lo) + 1))
    return seeds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "bundle"])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--access", default=None)
    ap.add_argument("--shard", default="0/1", help="i/n: this process builds every n-th seed starting at i")
    ap.add_argument("--cache_dir", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    os.environ["UAV_PROFILE"] = a.profile
    md.apply_profile(a.profile)
    import hybrid
    from uav_env import UAVEnv
    env = UAVEnv(access=a.access)
    seeds = parse_seeds(a.seeds)
    if a.cmd == "build":
        i, n = (int(v) for v in a.shard.split("/"))
        mine = seeds[i::n]
        t0 = time.time()
        for c, s in enumerate(mine, 1):
            env.reset(seed=s)
            hybrid.scenario_data(env, cache=True, cache_dir=a.cache_dir)
            print(f"  {c}/{len(mine)} seed {s} n_users {env.sc['n_users']}  {time.time() - t0:.0f}s", flush=True)
        return
    tables, targets = [], []
    for s in seeds:
        env.reset(seed=s)
        assert hybrid.cache_path(env, a.cache_dir).exists(), f"seed {s} has no table yet (run build first)"
        t, g = hybrid.scenario_data(env, cache=True, cache_dir=a.cache_dir)
        tables.append(t)
        targets.append(g)
    np.savez_compressed(a.out, seeds=np.array(seeds), tables=np.stack(tables), targets=np.stack(targets))
    print(f"bundle {a.out}: {len(seeds)} scenarios, tables {np.stack(tables).shape}")


if __name__ == "__main__":
    main()
