"""Gate G3: run every baseline on the same seeded scenarios and write the comparison table.

    python run_baselines.py                      # all 6 baselines on the 100 eval seeds (config: baselines.eval_seeds)
    python run_baselines.py --seeds 5 --policies B0,B3
Outputs (in ./results/, not committed): baselines_episodes.csv, baselines_summary.md, baselines.png.
Main metric `coverage_full`: mean coverage over the whole 300 s horizon, counting a dead drone as 0 coverage.
That is what makes saving battery matter. Everything is reproducible from config.yaml + the seed list.
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
from baselines import POLICIES, make_policy
from evalstats import mean_ci, paired_diff
from uav_env import UAVEnv

RESULTS = Path(__file__).parent / "results"


def run_episode(env, policy, seed):
    """Play one episode with `policy` on scenario `seed`. Returns one row of metrics."""
    env.reset(seed=seed)
    policy.reset(env)
    cov, fair, outage, rate, reward, done, info = [], [], [], [], 0.0, False, {}
    fair_served, noma_pairs, alpha_low = [], [], []
    while not done:
        _, r, term, trunc, info = env.step(policy.act(env))
        cov.append(info["coverage"]); fair.append(info["fairness"]); outage.append(info["outage_rescue"])
        rate.append(info["sum_rate_mbps"]); fair_served.append(info["fairness_served"])
        noma_pairs.append(info.get("noma_pairs", 0)); alpha_low.append(info.get("alpha_lt_half", 0))
        reward += r
        done = term or trunc
    steps = len(cov)
    return {
        "seed": seed, "mobility": info["mobility"], "n_users": info["n_users"], "steps": steps,
        "survived": bool(steps >= env.T), "coverage_full": float(np.sum(cov) / env.T),
        "coverage_alive": float(np.mean(cov)), "reward_sum": reward, "fairness": float(np.mean(fair)),
        "outage_rescue": float(np.mean(outage)), "battery_left_wh": info["battery_wh"],
        "served_user_s_per_wh": info["served_user_s_per_wh"],
        "sum_rate_mbps": float(np.mean(rate)), "access": info["access"],
        "fairness_served": float(np.mean(fair_served)),
        # noma_opt only (0 otherwise): mean NOMA-mode pairs per step, and the share of them with weak power share < 0.5
        "noma_pairs": float(np.mean(noma_pairs)),
        "alpha_lt_half_share": float(np.sum(alpha_low) / np.sum(noma_pairs)) if np.sum(noma_pairs) > 0 else 0.0,
    }


def _task(args):
    """(name, seed, battery_wh[, access[, env_kwargs]]) -> one episode row. env_kwargs e.g. {"sic_eps": 0.05}."""
    name, seed, battery_wh, *rest = args
    access = rest[0] if rest else None
    kw = rest[1] if len(rest) > 1 else {}
    env = UAVEnv(battery_wh=battery_wh, access=access, **kw)
    return {"policy": name, **kw, **run_episode(env, make_policy(name), seed)}


def fmt(values, k=3):
    """'mean +/- half_width' with k decimals."""
    m, h = mean_ci(values)
    return f"{m:.{k}f} +/- {h:.{k}f}"


def md_table(df):
    """A DataFrame as a markdown table (no tabulate dependency)."""
    head = "| " + " | ".join([df.index.name or ""] + [str(c) for c in df.columns]) + " |"
    rule = "|" + "---|" * (len(df.columns) + 1)
    body = zip(df.index, df.to_numpy(), strict=True)
    rows = ["| " + " | ".join([str(i)] + [f"{v:.3f}" for v in r]) + " |" for i, r in body]
    return "\n".join([head, rule, *rows])


def summarize(df):
    """Markdown table: mean +/- 95% CI per policy, plus paired differences of coverage_full."""
    names = sorted(df.policy.unique())
    n_sc = df.groupby("policy").seed.nunique().min()
    lines = [f"Scenarios per policy: {n_sc}. Values are mean +/- 95% CI over scenarios.", "",
             "| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh "
             "| rescue outage | fairness |",
             "|---|---|---|---|---|---|---|"]
    for n in names:
        d = df[df.policy == n]
        lines.append(f"| {n} | {fmt(d.coverage_full)} | {fmt(d.coverage_alive)} | {d.survived.mean():.0%} | "
                     f"{fmt(d.served_user_s_per_wh, 1)} | {fmt(d.outage_rescue)} | {fmt(d.fairness)} |")
    piv = df.pivot(index="seed", columns="policy", values="coverage_full")
    lines += ["", "Paired difference in coverage_full (row minus column; positive = row is better; "
                  "* = the 95% CI excludes 0):", "", "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for a in names:
        cells = []
        for b in names:
            if a == b:
                cells.append("-")
                continue
            m, h = paired_diff(piv[a], piv[b])
            cells.append(f"{m:+.3f}{'*' if abs(m) > h else ''}")
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    by_mob = df.pivot_table(index="mobility", columns="policy", values="coverage_full", aggfunc="mean").round(3)
    counts = df.drop_duplicates("seed").mobility.value_counts()
    lines += ["", "Mean coverage_full by mobility model (scenario counts: "
              + ", ".join(f"{k} {v}" for k, v in counts.items()) + "):", "", md_table(by_mob)]
    return "\n".join(lines)


def report(df, profile, battery_wh=None):
    """The full summary text: a header naming the settings, then the comparison tables."""
    bat = battery_wh if battery_wh is not None else md.CFG["energy"]["battery_wh"]
    head = (f"Profile: {profile}. Area {md.CFG['area_m']:g} m, max power {md.CFG['uav']['p_max_dbm']:g} dBm, "
            f"battery {bat:g} Wh, horizon {md.CFG['mobility']['episode_steps']} s.")
    return head + "\n\n" + summarize(df)


def default_policies():
    """The pilots run when --policies is not given. The information-ladder pilots B3obs*, the loiter pilots B7, B8 and
    the study pilots B6dep (anticipation) and B6r / B6true / B6meas (model mismatch) run only when named, so the default
    list is the same as before those studies were merged."""
    opt_in = ("B7", "B8", "B6dep", "B6r", "B6true", "B6meas")
    return [p for p in POLICIES if not p.startswith("B3obs") and p not in opt_in]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=None, help="use only the first N eval seeds")
    ap.add_argument("--policies", default=",".join(default_policies()),
                    help="default: B0-B6 and B6fc (the information-ladder pilots B3obs*, the loiter pilots B7, B8 and "
                         "the study pilots B6dep, B6r, B6true, B6meas only when named)")
    ap.add_argument("--battery_wh", type=float, default=None, help="override energy.battery_wh")
    ap.add_argument("--tag", default=None, help="suffix for the output files (default: _<profile>)")
    ap.add_argument("--profile", default="default", help="config profile: default, lowpower, bigarea, hard")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    a = ap.parse_args()
    os.environ["UAV_PROFILE"] = a.profile          # worker processes read this at import
    md.apply_profile(a.profile)
    if a.tag is None:
        a.tag = "" if a.profile == "default" else f"_{a.profile}"
    lo, hi = md.CFG["baselines"]["eval_seeds"]
    seeds = list(range(lo, hi + 1))[: a.seeds]
    tasks = [(n, s, a.battery_wh) for n in a.policies.split(",") for s in seeds]
    print(f"{len(tasks)} episodes ({len(seeds)} scenarios x {len(tasks) // len(seeds)} policies), {a.workers} workers")
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        rows = []
        for i, row in enumerate(pool.map(_task, tasks, chunksize=2), 1):
            rows.append(row)
            if i % 50 == 0:
                print(f"  {i}/{len(tasks)}")
    df = pd.DataFrame(rows)
    RESULTS.mkdir(exist_ok=True)
    df.to_csv(RESULTS / f"baselines_episodes{a.tag}.csv", index=False)
    text = report(df, a.profile, a.battery_wh)
    (RESULTS / f"baselines_summary{a.tag}.md").write_text(text, encoding="utf-8")
    print("\n" + text)

    names = sorted(df.policy.unique())
    fig, ax = plt.subplots(figsize=(6, 4))
    stats = [mean_ci(df[df.policy == n].coverage_full) for n in names]
    ax.bar(names, [s[0] for s in stats], yerr=[s[1] for s in stats], capsize=4)
    ax.set_ylabel("coverage over the 300 s horizon (dead drone = 0)")
    ax.set_title(f"Baselines on {df.seed.nunique()} scenarios (mean, 95% CI)")
    plt.tight_layout(); plt.savefig(RESULTS / f"baselines{a.tag}.png", dpi=110)


if __name__ == "__main__":
    main()
