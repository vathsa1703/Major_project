"""Contribution 2: how much user-location information does a placement planner need? (pre-registered:
docs/prereg/value_of_info.md). B6 and B3 plan on a belief built from phone GPS reports (baselines.ReportsView: a share f
of the phones reports, with GPS error sigma, every `age` seconds) and are compared, scenario by scenario, with the same
planner on the true users. The drone always serves the TRUE users.

    python voi_exp.py run --profiles hard --workers 2                       # resumable; appends to <out>/episodes.csv
    python voi_exp.py run --profiles sites_d20_t60_ann --part 0/2 --workers 4   # half of the tasks (Kaggle)
    python voi_exp.py analyse                                               # tables + plots from every episodes*.csv
Outputs in results/voi/ (not committed): episodes*.csv, summary.md, voi_ratio_vs_f.png, voi_sigma_age.png.
"""
import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import make_dataset as md
from baselines import make_policy
from evalstats import paired_diff
from run_baselines import run_episode
from uav_env import UAVEnv

OUT = Path(__file__).parent / "results" / "voi"
PROFILES = ("hard", "sites_d20_t60_ann")
PLANNERS = ("B6", "B3")                          # B6 primary, B3 secondary (pre-registered)
SEEDS = list(range(100, 120)) + list(range(1000, 1010))     # val 100-119 + 1000-1009 (30 scenarios)
F_GRID = (0.05, 0.1, 0.2, 0.5, 1.0)
TARGET = 0.98                                    # pre-registered: >= 98% of full-information coverage
N_BOOT, BOOT_SEED = 10000, 0


def configs(planner):
    """(f, sigma_m, age_s) of every pre-registered configuration of a planner (the reference is separate)."""
    out = [(f, 10.0, 0) for f in F_GRID]
    if planner == "B6":
        out += [(f, 50.0, 0) for f in F_GRID]
    else:
        out += [(0.2, 50.0, 0)]
    return out + [(0.2, 0.0, 0), (0.2, 10.0, 30), (0.2, 10.0, 60)]


def pilot(planner, f, sigma, age):
    return planner if f is None else f"{planner}rep:f={f:g},sigma={sigma:g},age={age:g}"


def all_tasks(profiles):
    """(profile, planner, f, sigma, age, seed); f None = the full-information reference (the planner itself)."""
    out = []
    for prof in profiles:
        for pl in PLANNERS:
            for cfg in [(None, None, None)] + configs(pl):
                out += [(prof, pl, *cfg, s) for s in SEEDS]
    return out


def _task(task):
    prof, pl, f, sigma, age, seed = task
    md.apply_profile(prof)
    t0 = time.time()
    row = run_episode(UAVEnv(), make_policy(pilot(pl, f, sigma, age)), seed)
    return {"profile": prof, "planner": pl, "ref": f is None, "f": f, "sigma_m": sigma, "age_s": age,
            "pilot": pilot(pl, f, sigma, age), "time_s": round(time.time() - t0, 2), **row}


def run(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    csv = out / f"episodes{a.tag}.csv"
    tasks = all_tasks(a.profiles.split(","))
    i, n = (int(x) for x in a.part.split("/"))
    tasks = tasks[i::n]
    if csv.exists():
        have = pd.read_csv(csv)
        done = set(zip(have.profile, have.pilot, have.seed, strict=True))
        tasks = [t for t in tasks if (t[0], pilot(*t[1:5]), t[5]) not in done]
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"{len(tasks)} episodes to run, {a.workers} workers -> {csv}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for k, r in enumerate(pool.map(_task, tasks, chunksize=1), 1):
            pd.DataFrame([r]).to_csv(csv, mode="a", header=not csv.exists(), index=False)
            if k % 20 == 0 or k == len(tasks):
                print(f"  {k}/{len(tasks)}  {(time.time() - t0) / 60:.1f} min", flush=True)


# ---------------------------------------------------------------- analysis
def load(folder):
    df = pd.concat([pd.read_csv(p) for p in sorted(Path(folder).glob("episodes*.csv"))], ignore_index=True)
    return df.drop_duplicates(["profile", "pilot", "seed"], keep="first")


def ratio_ci(c, r, idx):
    """Coverage ratio mean(c) / mean(r) (paired by scenario) and its bootstrap draws over the resampled scenarios."""
    return c.mean() / r.mean(), c[idx].mean(axis=1) / r[idx].mean(axis=1)


def f_star(R):
    """Smallest grid f whose ratio and every larger f's ratio reach TARGET; inf if none. R: (..., len(F_GRID))."""
    ok = np.asarray(R) >= TARGET
    tail = np.flip(np.logical_and.accumulate(np.flip(ok, -1), -1), -1)      # ok at this f and all larger
    fs = np.array(F_GRID)
    first = np.argmax(tail, axis=-1)
    return np.where(tail.any(axis=-1), fs[first], np.inf)


def fmt_f(x):
    return "not reached" if not np.isfinite(x) else f"{x:g}"


def analyse(a):
    df = load(a.out)
    rng = np.random.default_rng(BOOT_SEED)
    lines, rows, fstar = [], [], []
    for prof in [p for p in PROFILES if p in set(df.profile)]:
        for pl in PLANNERS:
            d = df[(df.profile == prof) & (df.planner == pl)]
            if d.empty:
                continue
            piv = d.pivot(index="seed", columns="pilot", values="coverage_full")
            ref = piv[pl].dropna()
            seeds = ref.index.values
            idx = rng.integers(0, len(seeds), size=(N_BOOT, len(seeds)))
            r = ref.values
            boot = {}
            for f, s, ag in configs(pl):
                name = pilot(pl, f, s, ag)
                if name not in piv or piv.loc[seeds, name].isna().any():
                    continue
                c = piv.loc[seeds, name].values
                R, Rb = ratio_ci(c, r, idx)
                boot[(f, s, ag)] = Rb
                lo, hi = np.percentile(Rb, [2.5, 97.5])
                dm, dh = paired_diff(c, r)
                nrep = (d[d.pilot == name].set_index("seed").loc[seeds, "n_users"] * f).mean()
                rows.append(dict(profile=prof, planner=pl, f=f, sigma_m=s, age_s=ag, n=len(seeds), coverage=c.mean(),
                                 coverage_full_info=r.mean(), ratio=R, ratio_lo=lo, ratio_hi=hi, diff=dm, diff_hw=dh,
                                 mean_reporters=nrep, reach=bool(R >= TARGET), lo_reach=bool(lo >= TARGET),
                                 time_s=d[d.pilot == name].time_s.mean()))
            for s in (10.0, 50.0):
                keys = [(f, s, 0) for f in F_GRID]
                if not all(k in boot for k in keys):
                    continue
                R = np.array([next(x["ratio"] for x in rows if x["profile"] == prof and x["planner"] == pl
                                   and (x["f"], x["sigma_m"], x["age_s"]) == k) for k in keys])
                Rb = np.column_stack([boot[k] for k in keys])
                lo_all = np.percentile(Rb, 2.5, axis=0)
                fb = f_star(Rb)
                q = np.quantile(fb, [0.025, 0.975], method="inverted_cdf")
                fstar.append(dict(profile=prof, planner=pl, sigma_m=s, f_star=float(f_star(R)), ci_lo=float(q[0]),
                                  ci_hi=float(q[1]), p_not_reached=float(np.mean(~np.isfinite(fb))),
                                  f_star_conservative=float(f_star(lo_all)),
                                  ref_mean=r.mean(), ref_time_s=d[d.pilot == pl].time_s.mean()))
    T, F = pd.DataFrame(rows), pd.DataFrame(fstar)
    T.to_csv(Path(a.out) / "table_ratios.csv", index=False)
    F.to_csv(Path(a.out) / "table_fstar.csv", index=False)

    lines += ["# Value of information: results", "",
              f"Scenarios per configuration: {int(T.n.min()) if len(T) else 0} (seeds 100-119 and 1000-1009), paired "
              f"with the same planner on the true users. Ratio = mean coverage / mean full-information coverage; "
              f"95% CI by paired bootstrap over scenarios ({N_BOOT} resamples, seed {BOOT_SEED}). diff = coverage "
              f"minus full information, mean +/- 95% CI (normal approximation). Target {TARGET:.0%}.", "",
              "## Table 1. Coverage ratio per configuration", "",
              "| profile | planner | f | sigma (m) | age (s) | mean reporters | coverage | full info | ratio [95% CI] "
              "| diff | reaches 98% (point / CI low) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, x in T.iterrows():
        lines.append(f"| {x.profile} | {x.planner} | {x.f:g} | {x.sigma_m:g} | {x.age_s:g} | {x.mean_reporters:.0f} | "
                     f"{x.coverage:.3f} | {x.coverage_full_info:.3f} | {x.ratio:.3f} "
                     f"[{x.ratio_lo:.3f}, {x.ratio_hi:.3f}] | {x['diff']:+.3f} +/- {x.diff_hw:.3f} | "
                     f"{'yes' if x.reach else 'no'} / {'yes' if x.lo_reach else 'no'} |")
    lines += ["", "## Table 2. f* = smallest report share reaching 98% (age 0)", "",
              "f* = smallest grid f whose ratio and every larger f's ratio are >= 0.98 (point estimates). "
              "95% interval = percentile interval of f* recomputed in every bootstrap resample. "
              "Conservative f* = the same rule on the lower CI bounds.", "",
              "| profile | planner | sigma (m) | f* | 95% interval | share of resamples not reaching 98% | "
              "conservative f* | full-info coverage |", "|---|---|---|---|---|---|---|---|"]
    for _, x in F.iterrows():
        lines.append(f"| {x.profile} | {x.planner} | {x.sigma_m:g} | {fmt_f(x.f_star)} | [{fmt_f(x.ci_lo)}, "
                     f"{fmt_f(x.ci_hi)}] | {x.p_not_reached:.3f} | {fmt_f(x.f_star_conservative)} | {x.ref_mean:.3f} |")
    # pre-registered pass rule (B6, sigma 10 and 50, both profiles)
    prim = F[F.planner == "B6"]
    verdicts = []
    for _, x in prim.iterrows():
        ok = np.isfinite(x.f_star) and np.isfinite(x.ci_hi) and x.ci_hi < 1.0
        verdicts.append(ok)
        lines.append("")
        verdict = "identifiable and < 1" if ok else "NOT (identifiable and < 1)"
        lines.append(f"- B6, {x.profile}, sigma {x.sigma_m:g} m: f* {fmt_f(x.f_star)}, 95% interval "
                     f"[{fmt_f(x.ci_lo)}, {fmt_f(x.ci_hi)}] -> {verdict}")
    complete = len(prim) == 2 * len(PROFILES)
    overall = ("PASS" if all(verdicts) else "FAIL") if complete else "INCOMPLETE"
    lines += ["", f"**Pre-registered criterion** (B6, both profiles, sigma 10 and 50 m: f* identifiable and its 95% "
                  f"interval entirely below 1): {overall}"]
    # exploratory: by crowd size
    ex = []
    for prof in [p for p in PROFILES if p in set(df.profile)]:
        d = df[(df.profile == prof) & (df.planner == "B6")]
        if d.empty:
            continue
        piv = d.pivot(index="seed", columns="pilot", values="coverage_full")
        nu = d.drop_duplicates("seed").set_index("seed").n_users
        for n_u in sorted(nu.unique()):
            sd = nu.index[nu == n_u]
            cells = []
            for f in F_GRID:
                name = pilot("B6", f, 10.0, 0)
                cells.append(f"{piv.loc[sd, name].mean() / piv.loc[sd, 'B6'].mean():.3f}" if name in piv else "-")
            ex.append(f"| {prof} | {n_u} | {len(sd)} | " + " | ".join(cells) + " |")
    lines += ["", "## Table 3 (exploratory, not pre-registered). B6 ratio by crowd size (sigma 10 m, age 0)", "",
              "Few scenarios per row: no CIs, read as a trend only. Reporters = f x crowd size.", "",
              "| profile | users | scenarios | " + " | ".join(f"f={f:g}" for f in F_GRID) + " |",
              "|---|---|---|" + "---|" * len(F_GRID), *ex]
    text = "\n".join(lines) + "\n"
    (Path(a.out) / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    plots(T, Path(a.out))


# ---------------------------------------------------------------- plots
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
# colour, line, marker, x dodge (a factor: the f axis is logarithmic)
SERIES = {"B6 sigma 10 m": ("#2a78d6", "-", "o", 0.96), "B6 sigma 50 m": ("#2a78d6", "--", "s", 1.0),
          "B3 sigma 10 m": ("#eb6834", "-", "^", 1.04)}


def _axes_style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelcolor=INK2)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def plots(T, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    profs = [p for p in PROFILES if p in set(T.profile)]
    fig, axes = plt.subplots(1, len(profs), figsize=(5.2 * len(profs), 4.2), sharey=True, squeeze=False)
    for ax, prof in zip(axes[0], profs, strict=True):
        for label, (col, ls, mk, dodge) in SERIES.items():
            pl, s = label.split()[0], float(label.split()[2])
            d = T[(T.profile == prof) & (T.planner == pl) & (T.sigma_m == s) & (T.age_s == 0)
                  & T.f.isin(F_GRID)].sort_values("f")
            if len(d) < 2:
                continue
            ax.errorbar(d.f * dodge, d.ratio, yerr=[d.ratio - d.ratio_lo, d.ratio_hi - d.ratio], color=col, ls=ls,
                        marker=mk, ms=6, lw=2, capsize=3, label=label)
        ax.axhline(TARGET, color=INK2, lw=1, ls=":", label="98% of full information")
        ax.axhline(1.0, color=GRID, lw=1)
        ax.set_xscale("log")
        ax.set_xticks(F_GRID)
        ax.set_xticklabels([f"{f:g}" for f in F_GRID])
        ax.set_xlabel("share of phones that report their GPS position (f)", color=INK)
        ax.set_title(prof, color=INK, fontsize=11)
        _axes_style(ax)
    axes[0][0].set_ylabel("coverage / full-information coverage", color=INK)
    axes[0][0].legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right")
    fig.suptitle("How many phones must report? (age 0; mean and 95% CI over 30 scenarios)", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "voi_ratio_vs_f.png", dpi=130)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2), sharey=True)
    combos = [(p, pl) for p in profs for pl in PLANNERS]
    cols = {("hard", "B6"): ("#2a78d6", "-"), ("hard", "B3"): ("#2a78d6", "--"),
            ("sites_d20_t60_ann", "B6"): ("#eb6834", "-"), ("sites_d20_t60_ann", "B3"): ("#eb6834", "--")}
    for ax, (key, vals, xlabel) in zip(axes, [("sigma_m", (0.0, 10.0, 50.0), "GPS error sigma (m), f 0.2, age 0"),
                                              ("age_s", (0, 30, 60), "report interval (s), f 0.2, sigma 10 m")],
                                       strict=True):
        for k, (prof, pl) in enumerate(combos):
            other = ("age_s", 0) if key == "sigma_m" else ("sigma_m", 10.0)
            d = T[(T.profile == prof) & (T.planner == pl) & (T.f == 0.2) & (T[other[0]] == other[1])
                  & T[key].isin(vals)].sort_values(key)
            if len(d) < 2:
                continue
            x = np.arange(len(d)) + (k - 1.5) * 0.06
            col, ls = cols[(prof, pl)]
            ax.errorbar(x, d.ratio, yerr=[d.ratio - d.ratio_lo, d.ratio_hi - d.ratio], color=col, ls=ls,
                        marker="o" if pl == "B6" else "^",
                        ms=6, lw=2, capsize=3, label=f"{pl}, {prof}")
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels([f"{v:g}" for v in vals])
        ax.set_xlabel(xlabel, color=INK)
        ax.axhline(TARGET, color=INK2, lw=1, ls=":")
        ax.axhline(1.0, color=GRID, lw=1)
        _axes_style(ax)
    axes[0].set_ylabel("coverage / full-information coverage", color=INK)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=INK, loc="lower left")
    fig.suptitle("Sensitivity to GPS error and report age (20% of phones report; mean and 95% CI)", color=INK,
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "voi_sigma_age.png", dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "analyse"])
    ap.add_argument("--profiles", default=",".join(PROFILES))
    ap.add_argument("--part", default="0/1", help="i/n: run every n-th task starting at i (to split across machines)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--tag", default="", help="suffix of the episodes file (episodes<tag>.csv)")
    ap.add_argument("--limit", type=int, default=None, help="run at most this many tasks (smoke test)")
    a = ap.parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    run(a) if a.mode == "run" else analyse(a)


if __name__ == "__main__":
    main()
