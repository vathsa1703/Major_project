"""Compare a trained agent with Random and the baselines on the SAME scenarios of a split (paired).

    python rl_eval.py --model results/rl/<name>/model.zip --split val
    python rl_eval.py --policies B0,B2,B3,Random --split val      # no model: baselines and random only
Splits: train (0-99), val (100-119), test (120-139). Look at test only once, at the very end.
Metric: coverage_full (mean coverage over the whole horizon, a dead drone counts 0), mean +/- 95% CI,
and paired differences.
"""
import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

import make_dataset as md
from baselines import POLICIES
from rl_utils import CONTROLS, RandomPolicy, RLPolicy, expand_action  # noqa: F401  (expand_action re-exported)
from run_baselines import _task, run_episode, summarize
from uav_env import UAVEnv

HERE = Path(__file__).parent


def evaluate(names, seeds, model_path=None, controls="xy", workers=4, battery_wh=None):
    """Rows (one per policy x seed). Baselines run in parallel processes; Random and PPO run here."""
    rows = []
    base = [n for n in names if n in POLICIES]
    if base:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows += list(pool.map(_task, [(n, s, battery_wh) for n in base for s in seeds], chunksize=2))
    for n in names:
        if n == "Random":
            pol = RandomPolicy(controls)
        elif n == "PPO":
            from stable_baselines3 import PPO
            pol = RLPolicy(PPO.load(model_path, device="cpu"), controls)
        else:
            continue
        rows += [{"policy": n, **run_episode(UAVEnv(battery_wh=battery_wh), pol, s)} for s in seeds]
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="path to model.zip (adds the PPO row)")
    ap.add_argument("--policies", default="Random,B0,B1,B2,B3,B5")
    ap.add_argument("--split", default="val", choices=["train", "val", "test"])
    ap.add_argument("--profile", default=md.CFG["rl"]["profile"])
    ap.add_argument("--controls", default=md.CFG["rl"]["controls"], choices=list(CONTROLS))
    ap.add_argument("--seeds", type=int, default=None, help="use only the first N seeds of the split")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--out", default=None, help="markdown file to write")
    a = ap.parse_args()
    os.environ["UAV_PROFILE"] = a.profile
    md.apply_profile(a.profile)
    names = a.policies.split(",") + (["PPO"] if a.model else [])
    seeds = md.seeds(a.split)[: a.seeds]
    df = evaluate(names, seeds, a.model, a.controls, a.workers)
    head = (f"Split: {a.split} ({len(seeds)} scenarios, seeds {seeds[0]}-{seeds[-1]}). Profile: {a.profile}. "
            f"Controls: {a.controls}. Area {md.CFG['area_m']:g} m, {md.CFG['uav']['p_max_dbm']:g} dBm, "
            f"battery {md.CFG['energy']['battery_wh']:g} Wh.")
    text = head + "\n\n" + summarize(df)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    df.to_csv(HERE / "results" / f"eval_{a.split}_{a.profile}.csv", index=False)


if __name__ == "__main__":
    main()
