"""G5 evaluation (pre-registered rules, book D-55): trained agents vs the best simple pilot per scenario,
on one sites cell.

    python g5_eval.py --profile sites_d20_t0_ann --models results/kaggle/r1_t0/models --out results/g5/r1_t0

Writes <out>/episodes.csv (one row per pilot x seed; also each agent with access oma_opt for the NOMA-vs-OMA report) and
<out>/summary.md. The bar is, per scenario, the best of B6, B7, B8 and B6fc (B6fc uses the announcement when the profile
announces the event). Resumable: rows already in episodes.csv are not run again.
"""
import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

import make_dataset as md
from evalstats import paired_diff
from rl_utils import load_policy
from run_baselines import _task, run_episode
from uav_env import UAVEnv

BAR = ("B6", "B7", "B8", "B6fc")


def fmt(mci):
    m, h = mci
    return f"{m:+.3f} +/- {h:.3f}{'*' if abs(m) > h else ''}"


def _agent_task(args):
    name, path, seed, access = args
    md.apply_profile(os.environ["UAV_PROFILE"])
    pol = load_policy(path)
    return {"policy": name, **run_episode(UAVEnv(access=access), pol, seed)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--models", required=True, help="folder with <name>/model.zip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="val", choices=["val", "test"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--seeds", type=int, default=None, help="first N seeds only (smoke test)")
    ap.add_argument("--no_oma", action="store_true", help="skip the agents' OMA runs")
    a = ap.parse_args()
    os.environ["UAV_PROFILE"] = a.profile
    md.apply_profile(a.profile)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    csv = out / "episodes.csv"
    have = pd.read_csv(csv) if csv.exists() else pd.DataFrame(columns=["policy", "seed"])
    done = set(zip(have["policy"], have["seed"], strict=True))
    seeds = md.seeds(a.split)[: a.seeds]
    models = {p.parent.name: p for p in sorted(Path(a.models).glob("*/model.zip"))}
    jobs_b = [(n, s, None) for n in BAR for s in seeds if (n, s) not in done]
    jobs_a = [(n, str(p), s, None) for n, p in models.items() for s in seeds if (n, s) not in done]
    if not a.no_oma:
        jobs_a += [(n + "|oma", str(p), s, "oma_opt") for n, p in models.items() for s in seeds
                   if (n + "|oma", s) not in done]
    rows = []
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for r in pool.map(_task, jobs_b, chunksize=1):
            rows.append(r)
            pd.DataFrame([r]).to_csv(csv, mode="a", header=not csv.exists(), index=False)
        for r in pool.map(_agent_task, jobs_a, chunksize=1):
            rows.append(r)
            pd.DataFrame([r]).to_csv(csv, mode="a", header=not csv.exists(), index=False)
    df = pd.read_csv(csv)
    piv = df.pivot_table(index="seed", columns="policy", values="coverage_full")
    bar = piv[list(BAR)].max(axis=1)
    lines = [f"G5 evaluation. Profile {a.profile}, split {a.split} ({len(piv)} scenarios). Bar = per-scenario best of "
             f"{', '.join(BAR)} (mean {bar.mean():.3f}; per pilot " +
             ", ".join(f"{n} {piv[n].mean():.3f}" for n in BAR) + ").", "",
             "| agent | coverage (NOMA) | agent - bar (95% CI) | agent - B6 | coverage with OMA | NOMA - OMA |",
             "|---|---|---|---|---|---|"]
    for n in models:
        if n not in piv:
            continue
        d_bar, d_b6 = paired_diff(piv[n], bar), paired_diff(piv[n], piv["B6"])
        oma = piv.get(n + "|oma")
        o = (f"{oma.mean():.3f} | {fmt(paired_diff(piv[n], oma))}" if oma is not None else "- | -")
        lines.append(f"| {n} | {piv[n].mean():.3f} | {fmt(d_bar)} | {fmt(d_b6)} | {o} |")
    text = "\n".join(lines)
    (out / "summary.md").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
