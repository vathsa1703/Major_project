"""Hypothesis H3 inside the game: the same pilots on the same scenarios, once with NOMA and once with OMA.

    python noma_vs_oma.py                                  # default scenarios, 16 Wh (everyone survives), 100 scenarios
    python noma_vs_oma.py --profile hard --seeds 50
    python noma_vs_oma.py --profile lowpower               # 20 dBm instead of 30

NOMA: users are paired (strongest with weakest), each pair shares one frequency slice; the weak user gets 80% of
the pair's power and the strong user removes the weak user's message first (SIC). OMA: every user gets its own slice
(FDMA). Both use the same total bandwidth and the same total power, so the comparison is fair. Each pilot makes its
decisions under the scheme being tested (the search pilots evaluate candidate spots with it).

Output: a table (mean +/- 95% CI, paired NOMA minus OMA per scenario) and a bar chart in results/.
"""
import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import make_dataset as md
from evalstats import mean_ci, paired_diff
from run_baselines import _task

RESULTS = Path(__file__).parent / "results"
METRICS = [("coverage_full", "coverage", 3), ("sum_rate_mbps", "total speed (Mbps)", 1), ("fairness", "fairness", 3),
           ("outage_rescue", "rescue outage", 3)]


def run(policies, seeds, battery_wh=None, workers=4):
    tasks = [(p, s, battery_wh, acc) for acc in ("noma", "oma") for p in policies for s in seeds]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return pd.DataFrame(list(pool.map(_task, tasks, chunksize=2)))


def table(df):
    """One row per pilot: NOMA, OMA and the paired NOMA - OMA difference for each metric."""
    lines = ["| Pilot | " + " | ".join(f"{label}: NOMA / OMA / NOMA-OMA" for _, label, _ in METRICS) + " |",
             "|---|" + "---|" * len(METRICS)]
    for p in sorted(df.policy.unique()):
        cells = []
        for col, _, k in METRICS:
            piv = df[df.policy == p].pivot(index="seed", columns="access", values=col)
            (n, _), (o, _) = mean_ci(piv["noma"]), mean_ci(piv["oma"])
            d, h = paired_diff(piv["noma"], piv["oma"])
            cells.append(f"{n:.{k}f} / {o:.{k}f} / {d:+.{k}f}{'*' if abs(d) > h else ''} (+/-{h:.{k}f})")
        lines.append(f"| {p} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def chart(df, title, path):
    pilots = sorted(df.policy.unique())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (col, label, _) in zip(axes, METRICS[:2], strict=True):
        for i, acc in enumerate(("noma", "oma")):
            stats = [mean_ci(df[(df.policy == p) & (df.access == acc)][col]) for p in pilots]
            ax.bar(np.arange(len(pilots)) + (i - 0.5) * 0.38, [s[0] for s in stats], 0.38, yerr=[s[1] for s in stats],
                   capsize=3, label=acc.upper())
        ax.set_xticks(range(len(pilots)))
        ax.set_xticklabels(pilots)
        ax.set_title(label)
        ax.legend()
    fig.suptitle(title, fontsize=10)
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="default")
    ap.add_argument("--policies", default="B0,B1,B2,B3")
    ap.add_argument("--seeds", type=int, default=None, help="first N scenarios of baselines.eval_seeds")
    ap.add_argument("--battery_wh", type=float, default=16.0, help="16 Wh by default so every pilot survives 300 s")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    a = ap.parse_args()
    os.environ["UAV_PROFILE"] = a.profile
    md.apply_profile(a.profile)
    lo, hi = md.CFG["baselines"]["eval_seeds"]
    seeds = list(range(lo, hi + 1))[: a.seeds]
    df = run(a.policies.split(","), seeds, a.battery_wh, a.workers)
    tag = f"{a.profile}_{md.CFG['uav']['p_max_dbm']:g}dBm"
    head = (f"NOMA vs OMA (H3). Profile {a.profile}, {len(seeds)} scenarios, "
            f"{md.CFG['uav']['p_max_dbm']:g} dBm, battery "
            f"{a.battery_wh:g} Wh. Values: NOMA / OMA / paired NOMA - OMA (95% CI); * = the CI excludes 0.")
    text = head + "\n\n" + table(df)
    RESULTS.mkdir(exist_ok=True)
    df.to_csv(RESULTS / f"noma_vs_oma_{tag}.csv", index=False)
    (RESULTS / f"noma_vs_oma_{tag}.md").write_text(text, encoding="utf-8")
    chart(df, head.split(". Values")[0], RESULTS / f"noma_vs_oma_{tag}.png")
    print(text)


if __name__ == "__main__":
    main()
