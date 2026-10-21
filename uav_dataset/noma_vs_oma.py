"""Hypothesis H3 inside the game: the same pilots on the same scenarios, once per access scheme.

    python noma_vs_oma.py                                  # default scenarios, 16 Wh (everyone survives), 100 scenarios
    python noma_vs_oma.py --profile hard --seeds 50
    python noma_vs_oma.py --profile lowpower               # 20 dBm instead of 30
    python noma_vs_oma.py --profile hard --schemes noma,oma,oma_opt,noma_opt --policies B0,B2,B3   # four schemes
    python noma_vs_oma.py --profile hard --schemes noma_opt --eps 0.05                             # imperfect SIC
    python noma_vs_oma.py --from_csv a.csv,b.csv --compare "noma_opt[eps=0.05]:noma_opt"           # re-analyse

NOMA: users are paired (strongest with weakest), each pair shares one frequency slice; the weak user gets 80% of
the pair's power and the strong user removes the weak user's message first (SIC). OMA: every user gets its own slice
(FDMA). Both use the same total bandwidth and the same total power, so the comparison is fair. oma_opt / noma_opt are
the QoS-aware versions (make_dataset.access_rates): each admitted user gets just its minimum rate at minimum power,
cheapest users first; noma_opt pairs the admitted users and chooses NOMA or OMA per pair. Each pilot makes its
decisions under the scheme being tested (the search pilots evaluate candidate spots with it).

Output: tables (mean +/- 95% CI; paired differences per scenario with Holm-corrected significance) in results/.
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
from evalstats import holm, mean_ci, paired_diff, paired_p
from run_baselines import _task

RESULTS = Path(__file__).parent / "results"
METRICS = [("coverage_full", "coverage", 3), ("sum_rate_mbps", "total speed (Mbps)", 1), ("fairness", "fairness", 3),
           ("outage_rescue", "rescue outage", 3)]
# the four-scheme tables also report fairness among the SERVED users only
METRICS4 = METRICS[:3] + [("fairness_served", "fairness (served)", 3)] + METRICS[3:]
COMPARISONS = [("noma_opt", "oma_opt"), ("noma_opt", "noma"), ("oma_opt", "oma"), ("noma", "oma")]


def scheme_label(access, env_kw):
    """Name of a run variant: the access scheme, plus any non-default option, e.g. noma_opt[eps=0.05]."""
    opts = []
    if env_kw.get("sic_eps", md.CFG["access"]["sic_eps"]) != md.CFG["access"]["sic_eps"]:
        opts.append(f"eps={env_kw['sic_eps']:g}")
    if env_kw.get("rescue_first", md.CFG["access"]["rescue_first"]) != md.CFG["access"]["rescue_first"]:
        opts.append(f"rescue_first={env_kw['rescue_first']}")
    return access + (f"[{','.join(opts)}]" if opts else "")


def run(policies, seeds, battery_wh=None, workers=4, schemes=("noma", "oma"), env_kw=None):
    env_kw = dict(env_kw or {})
    tasks = [(p, s, battery_wh, acc, env_kw) for acc in schemes for p in policies for s in seeds]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        df = pd.DataFrame(list(pool.map(_task, tasks, chunksize=2)))
    df["scheme"] = [scheme_label(a, env_kw) for a in df.access]
    return df


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


def scheme_table(df, schemes=None):
    """Mean +/- 95% CI per pilot and scheme, for every metric."""
    schemes = schemes or list(dict.fromkeys(df.scheme))
    lines = ["| Pilot | Scheme | " + " | ".join(label for _, label, _ in METRICS4) + " |",
             "|---|---|" + "---|" * len(METRICS4)]
    for p in sorted(df.policy.unique()):
        for s in schemes:
            d = df[(df.policy == p) & (df.scheme == s)]
            if len(d):
                cells = [f"{mean_ci(d[c])[0]:.{k}f} +/- {mean_ci(d[c])[1]:.{k}f}" for c, _, k in METRICS4]
                lines.append(f"| {p} | {s} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def comparison_rows(df, comparisons):
    """Paired differences a - b per pilot, comparison and metric, with p-values and Holm correction over ALL rows."""
    rows = []
    for p in sorted(df.policy.unique()):
        for a, b in comparisons:
            for col, label, k in METRICS4:
                piv = df[df.policy == p].pivot(index="seed", columns="scheme", values=col)
                if a not in piv or b not in piv:
                    continue
                piv = piv[[a, b]].dropna()
                d, h = paired_diff(piv[a], piv[b])
                rows.append(dict(pilot=p, comparison=f"{a} - {b}", metric=label, k=k, diff=d, ci=h, n=len(piv),
                                 p=paired_p(piv[a], piv[b])))
    out = pd.DataFrame(rows)
    if len(out):
        out["p_holm"] = holm(out.p.values)
    return out


def comparison_table(df, comparisons=COMPARISONS):
    """Markdown: one row per pilot and comparison, one column per metric: diff (+/- 95% CI); * = Holm-adjusted
    p < 0.05 across every cell of the table."""
    c = comparison_rows(df, comparisons)
    if not len(c):
        return "(no comparison possible)"
    labels = [label for _, label, _ in METRICS4]
    lines = ["| Pilot | Comparison | " + " | ".join(labels) + " |", "|---|---|" + "---|" * len(labels)]
    for (p, comp), g in c.groupby(["pilot", "comparison"], sort=False):
        cells = []
        for lab in labels:
            r = g[g.metric == lab]
            if not len(r):
                cells.append("-")
                continue
            r = r.iloc[0]
            k = int(r.k)
            cells.append(f"{r['diff']:+.{k}f}{'*' if r.p_holm < 0.05 else ''} (+/-{r.ci:.{k}f})")
        lines.append(f"| {p} | {comp} | " + " | ".join(cells) + " |")
    lines.append(f"\n{len(c)} paired comparisons in this table; * = significant after Holm correction over all of "
                 f"them (normal approximation, two-sided, 0.05).")
    return "\n".join(lines)


def chart(df, title, path, col_name="access"):
    pilots = sorted(df.policy.unique())
    groups = list(dict.fromkeys(df[col_name]))
    w = 0.8 / len(groups)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (col, label, _) in zip(axes, METRICS[:2], strict=True):
        for i, acc in enumerate(groups):
            stats = [mean_ci(df[(df.policy == p) & (df[col_name] == acc)][col]) for p in pilots]
            ax.bar(np.arange(len(pilots)) + (i - (len(groups) - 1) / 2) * w, [s[0] for s in stats], w,
                   yerr=[s[1] for s in stats], capsize=3, label=acc.upper() if col_name == "access" else acc)
        ax.set_xticks(range(len(pilots)))
        ax.set_xticklabels(pilots)
        ax.set_title(label)
        ax.legend(fontsize=7)
    fig.suptitle(title, fontsize=10)
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def parse_comparisons(text):
    return [tuple(c.split(":")) for c in text.split(",")] if text else COMPARISONS


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="default")
    ap.add_argument("--policies", default="B0,B1,B2,B3")
    ap.add_argument("--seeds", type=int, default=None, help="first N scenarios of baselines.eval_seeds")
    ap.add_argument("--battery_wh", type=float, default=16.0, help="16 Wh by default so every pilot survives 300 s")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--schemes", default="noma,oma", help="any of noma, oma, oma_opt, noma_opt")
    ap.add_argument("--eps", type=float, default=None, help="imperfect-SIC residual for noma_opt (config default)")
    ap.add_argument("--rescue_first", action="store_true", help="QoS-aware schemes admit rescue users first")
    ap.add_argument("--tag", default="", help="suffix for the output files")
    ap.add_argument("--from_csv", default=None, help="comma-separated episode CSVs to merge and analyse (no runs)")
    ap.add_argument("--compare", default=None, help='comparisons "a:b,c:d" of scheme labels (default: four H3 ones)')
    a = ap.parse_args()
    os.environ["UAV_PROFILE"] = a.profile
    md.apply_profile(a.profile)
    RESULTS.mkdir(exist_ok=True)
    comparisons = parse_comparisons(a.compare)
    if a.from_csv:
        df = pd.concat([pd.read_csv(f) for f in a.from_csv.split(",")], ignore_index=True)
        text = scheme_table(df) + "\n\n" + comparison_table(df, comparisons)
        (RESULTS / f"h3_analysis{a.tag}.md").write_text(text, encoding="utf-8")
        print(text)
        return
    lo, hi = md.CFG["baselines"]["eval_seeds"]
    seeds = list(range(lo, hi + 1))[: a.seeds]
    schemes = a.schemes.split(",")
    env_kw = {}
    if a.eps is not None:
        env_kw["sic_eps"] = a.eps
    if a.rescue_first:
        env_kw["rescue_first"] = True
    df = run(a.policies.split(","), seeds, a.battery_wh, a.workers, schemes, env_kw)
    tag = f"{a.profile}_{md.CFG['uav']['p_max_dbm']:g}dBm"
    settings = (f"Profile {a.profile}, {len(seeds)} scenarios, {md.CFG['uav']['p_max_dbm']:g} dBm, battery "
                f"{a.battery_wh:g} Wh")
    if sorted(schemes) == ["noma", "oma"] and not env_kw:          # the original two-scheme H3 table
        head = f"NOMA vs OMA (H3). {settings}. Values: NOMA / OMA / paired NOMA - OMA (95% CI); * = the CI excludes 0."
        text = head + "\n\n" + table(df)
        df.to_csv(RESULTS / f"noma_vs_oma_{tag}{a.tag}.csv", index=False)
        (RESULTS / f"noma_vs_oma_{tag}{a.tag}.md").write_text(text, encoding="utf-8")
        chart(df, head.split(". Values")[0], RESULTS / f"noma_vs_oma_{tag}{a.tag}.png")
    else:
        head = (f"Access schemes (H3). {settings}; sic_eps {env_kw.get('sic_eps', md.CFG['access']['sic_eps'])}, "
                f"rescue_first {env_kw.get('rescue_first', md.CFG['access']['rescue_first'])}.")
        text = (head + "\n\nMean +/- 95% CI over scenarios:\n\n" + scheme_table(df)
                + "\n\nPaired differences (row scheme minus column scheme, per scenario), mean (+/- 95% CI):\n\n"
                + comparison_table(df, comparisons))
        df.to_csv(RESULTS / f"h3_schemes_{tag}{a.tag}.csv", index=False)
        (RESULTS / f"h3_schemes_{tag}{a.tag}.md").write_text(text, encoding="utf-8")
        chart(df, head.split(";")[0], RESULTS / f"h3_schemes_{tag}{a.tag}.png", col_name="scheme")
    print(text)


if __name__ == "__main__":
    main()
