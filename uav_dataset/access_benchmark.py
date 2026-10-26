"""One-snapshot benchmark of the access schemes (book 14.6 step 2): for each scenario, the best spot on B3's grid
under each scheme (fixed altitude, full power, the crowd at t = 0), and the coverage there.

    python access_benchmark.py                                   # profile rl_static, val seeds 100-119, 150 m
    python access_benchmark.py --profile hard --split val --h 150

Variants: oma, oma_opt, noma, noma_opt (sic_eps 0) and noma_opt (sic_eps 0.05). For noma_opt it also reports, at
its best spot, the share of pairs that use NOMA (the rest use OMA inside the pair), how often the weak user's power
share alpha is below 0.5, and how many users the full linear scan would add over the binary search.
Output: results/access_benchmark_<profile>.md / .csv (not committed).
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import make_dataset as md
from baselines import _grid
from evalstats import holm, mean_ci, paired_diff, paired_p
from uav_env import UAVEnv

RESULTS = Path(__file__).parent / "results"
VARIANTS = [("oma", 0.0), ("oma_opt", 0.0), ("noma", 0.0), ("noma_opt", 0.0), ("noma_opt", 0.05)]


def label(scheme, eps):
    return scheme + (f"[eps={eps:g}]" if eps else "")


def one(seed, h):
    env = UAVEnv()
    env.reset(seed=seed)
    X, Y = _grid(env)
    H = np.full(len(X), float(h))
    ux, uy = env.user_xy().T
    G = md.channel_gain(ux, uy, X, Y, H, env.links)
    B, R, p = env.sc["bandwidth_hz"], env.min_rate, env.p_max_w
    row = dict(seed=seed, n_users=env.sc["n_users"])
    for scheme, eps in VARIANTS:
        rates, info = md.access_rates(G, p, env.noise_psd, B, R, scheme, env.sc["pairing"],
                                      np.random.default_rng([seed, 0]), eps=eps, return_info=True)
        cov = info["served"].mean(axis=1)
        j = int(np.argmax(cov))
        lab = label(scheme, eps)
        row[f"cov_{lab}"] = cov[j]
        row[f"rate_{lab}"] = rates[j].sum() / 1e6
        if scheme == "noma_opt":
            row[f"pairs_{lab}"] = int(info["pairs"][j])
            row[f"noma_share_{lab}"] = info["noma_pairs"][j] / max(1, info["pairs"][j])
            row[f"alpha_lt_half_{lab}"] = info["alpha_lt_half"][j] / max(1, info["noma_pairs"][j])
            lin = md.access_rates(G[j], p, env.noise_psd, B, R, scheme, eps=eps, return_info=True, search="linear")
            row[f"scan_gain_{lab}"] = (lin[1]["served"].sum() - info["served"][j].sum()) / env.sc["n_users"]
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="rl_static")
    ap.add_argument("--split", default="val")
    ap.add_argument("--h", type=float, default=150.0)
    a = ap.parse_args()
    md.apply_profile(a.profile)
    df = pd.DataFrame([one(s, a.h) for s in md.seeds(a.split)])
    labs = [label(s, e) for s, e in VARIANTS]
    lines = [f"Access schemes, one snapshot (t = 0). Profile {a.profile}, {a.split} seeds "
             f"({len(df)} scenarios), altitude {a.h:g} m, {md.CFG['uav']['p_max_dbm']:g} dBm, best spot on B3's "
             f"{md.CFG['baselines']['grid_n']} x {md.CFG['baselines']['grid_n']} grid for each scheme. "
             "Mean +/- 95% CI over scenarios.", "",
             "| Scheme | coverage at its best spot | total speed there (Mbps) |", "|---|---|---|"]
    for lab in labs:
        (c, ch), (r, rh) = mean_ci(df[f"cov_{lab}"]), mean_ci(df[f"rate_{lab}"])
        lines.append(f"| {lab} | {c:.3f} +/- {ch:.3f} | {r:.1f} +/- {rh:.1f} |")
    comps = [("noma_opt", "oma_opt"), ("noma_opt[eps=0.05]", "oma_opt"), ("noma_opt", "noma"), ("oma_opt", "oma"),
             ("noma", "oma"), ("noma_opt[eps=0.05]", "noma_opt")]
    ps = holm([paired_p(df[f"cov_{x}"], df[f"cov_{y}"]) for x, y in comps])
    lines += ["", "Paired coverage differences (Holm over these 6; * = adjusted p < 0.05):", "",
              "| Comparison | coverage difference (95% CI) | Holm p |", "|---|---|---|"]
    for (x, y), p in zip(comps, ps, strict=True):
        d, h = paired_diff(df[f"cov_{x}"], df[f"cov_{y}"])
        lines.append(f"| {x} - {y} | {d:+.3f}{'*' if p < 0.05 else ''} (+/-{h:.3f}) | {p:.2g} |")
    lines += ["", "noma_opt at its best spot (mean over scenarios; min - max):", "",
              "| Variant | pairs | share of pairs using NOMA | share of NOMA pairs with alpha < 0.5 | "
              "users the full scan adds (share of N) |", "|---|---|---|---|---|"]
    for lab in ("noma_opt", "noma_opt[eps=0.05]"):
        cells = []
        for col, k in (("pairs", 0), ("noma_share", 3), ("alpha_lt_half", 3), ("scan_gain", 4)):
            v = df[f"{col}_{lab}"]
            cells.append(f"{v.mean():.{k}f} ({v.min():.{k}f} - {v.max():.{k}f})")
        lines.append(f"| {lab} | " + " | ".join(cells) + " |")
    text = "\n".join(lines)
    RESULTS.mkdir(exist_ok=True)
    df.to_csv(RESULTS / f"access_benchmark_{a.profile}.csv", index=False)
    (RESULTS / f"access_benchmark_{a.profile}.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
