"""Model mismatch, AI evaluation (draft pre-registration docs/prereg/model_mismatch.md; run only after the GO).

    python mismatch_eval.py run --cell mm_bl25 --models results/kaggle/mm_bl25/models --out results/mismatch/ai/mm_bl25
    python mismatch_eval.py run --cell mm_bl25 --models ... --out ... --draw 1    # perturbation RE-DRAWN (memorisation)
    python mismatch_eval.py combine --out results/mismatch/ai mm_bl25 mm_h4 mm_none  # Holm over cells -> summary.md

Per cell and draw: the bar pilots B6, B6meas, B3 (level-1 bar = per-scenario best of the three), B6true (upper bound)
and every agent (<models>/<name>/model.zip) with the cell's access scheme (noma_opt) and with oma_opt (NOMA vs OMA under
the identical perturbation draw: the draw depends only on (seed, stream, draw), never on the access scheme).
Resumable: rows already in <out>/episodes_draw<d>.csv are not run again. At most `--workers` processes (laptop: 2).
"""
import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

import make_dataset as md
from evalstats import holm, paired_diff, paired_p
from mismatch_exp import CachedEnv, parse_seeds
from run_baselines import run_episode
from uav_env import UAVEnv

BAR = ("B6", "B6meas", "B3")
UPPER = "B6true"


def _task(job):
    cell, draw, name, path, seed, access = job
    md.apply_profile(cell)
    md.CFG["mismatch"]["draw"] = draw
    if path is None:
        from baselines import make_policy
        pol, env = make_policy(name), CachedEnv()
    else:
        from rl_utils import load_policy
        pol, env = load_policy(path), UAVEnv(access=access)
    row = run_episode(env, pol, seed)
    return {"policy": name + ("|oma" if access == "oma_opt" else ""), "cell": cell, "draw": draw, **row}


def cmd_run(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    csv = out / f"episodes_draw{a.draw}.csv"
    have = pd.read_csv(csv) if csv.exists() else pd.DataFrame(columns=["policy", "seed"])
    done = set(zip(have["policy"], have["seed"], strict=True))
    md.apply_profile(a.cell)
    seeds = parse_seeds(a.seeds) if a.seeds else md.seeds(a.split)
    models = {p.parent.name: str(p) for p in sorted(Path(a.models).glob("*/model.zip"))}
    jobs = [(a.cell, a.draw, n, None, s, None) for n in (*BAR, UPPER) for s in seeds if (n, s) not in done]
    jobs += [(a.cell, a.draw, n, p, s, None) for n, p in models.items() for s in seeds if (n, s) not in done]
    if not a.no_oma:
        jobs += [(a.cell, a.draw, n, p, s, "oma_opt") for n, p in models.items() for s in seeds
                 if (n + "|oma", s) not in done]
    print(f"{len(jobs)} episodes, {a.workers} workers", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for r in pool.map(_task, jobs, chunksize=1):
            pd.DataFrame([r]).to_csv(csv, mode="a", header=not csv.exists(), index=False)


def fmt(mci, k=3):
    m, h = mci
    return f"{m:+.{k}f} [{m - h:+.{k}f}, {m + h:+.{k}f}]"


def cell_stats(csv):
    """Per-cell numbers: the bar, the 3-seed agent mean per scenario, paired difference + p-value, share of room."""
    df = pd.read_csv(csv)
    piv = df.pivot_table(index="seed", columns="policy", values="coverage_full")
    agents = sorted(c for c in piv.columns if c not in (*BAR, UPPER) and not c.endswith("|oma"))
    bar = piv[list(BAR)].max(axis=1)
    ai = piv[agents].mean(axis=1)                             # 3-seed mean per scenario
    d = paired_diff(ai, bar)
    room = piv[UPPER].mean() - bar.mean()
    share = (ai.mean() - bar.mean()) / room if room > 0 else float("nan")
    oma = [c + "|oma" for c in agents if c + "|oma" in piv]
    noma_oma = paired_diff(piv[agents].mean(axis=1), piv[oma].mean(axis=1)) if oma else (float("nan"), 0.0)
    per_seed = {c: paired_diff(piv[c], bar) for c in agents}
    return dict(n=len(piv), bar=bar.mean(), ai=ai.mean(), upper=piv[UPPER].mean(), diff=d, p=paired_p(ai, bar),
                share=share, noma_oma=noma_oma, per_seed=per_seed, b6=piv["B6"].mean(),
                ai_b6=paired_diff(ai, piv["B6"]), pilots={n: piv[n].mean() for n in BAR})


def cmd_combine(a):
    out = Path(a.out)
    stats = {c: cell_stats(out / c / "episodes_draw0.csv") for c in a.cells}
    adj = dict(zip(stats, holm([s["p"] for s in stats.values()]), strict=True))
    lines = ["# Model mismatch: AI vs the level-1 bar (draw 0 = the pre-registered evaluation)", "",
             "| cell | n | bar (best of B6, B6meas, B3) | AI 3-seed mean | AI - bar [95% CI] | Holm p | pass | "
             "B6true | share of room captured | AI - B6 | NOMA - OMA (AI) |", "|" + "---|" * 11]
    for c, s in stats.items():
        ok = s["diff"][0] > 0 and adj[c] < 0.05 and c != "mm_none"
        lines.append(f"| {c} | {s['n']} | {s['bar']:.4f} | {s['ai']:.4f} | {fmt(s['diff'])} | {adj[c]:.4f} | "
                     f"{'PASS' if ok else 'no'} | {s['upper']:.4f} | {s['share']:+.2f} | {fmt(s['ai_b6'])} | "
                     f"{fmt(s['noma_oma'])} |")
    lines += ["", "Per training seed (agent - bar):", ""]
    for c, s in stats.items():
        lines.append(f"- {c}: " + "; ".join(f"{k} {fmt(v)}" for k, v in s["per_seed"].items()))
    redraw = [c for c in a.cells if (out / c / "episodes_draw1.csv").exists()]
    if redraw:
        lines += ["", "## Re-drawn perturbation (draw 1, same scenarios; memorisation check)", "",
                  "| cell | bar | AI | AI - bar [95% CI] | share of room |", "|---|---|---|---|---|"]
        for c in redraw:
            s = cell_stats(out / c / "episodes_draw1.csv")
            lines.append(f"| {c} | {s['bar']:.4f} | {s['ai']:.4f} | {fmt(s['diff'])} | {s['share']:+.2f} |")
    if "mm_none" in stats:
        s = stats["mm_none"]
        lines += ["", f"Negative control mm_none: AI - B6 = {fmt(s['ai_b6'])} (the AI must NOT beat B6 here)."]
    text = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "combine"])
    ap.add_argument("cells", nargs="*")
    ap.add_argument("--cell")
    ap.add_argument("--models")
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="val", choices=["val", "test"])
    ap.add_argument("--seeds", default=None, help="lo-hi instead of the split (smoke tests)")
    ap.add_argument("--draw", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no_oma", action="store_true")
    a = ap.parse_args()
    if a.cmd == "run":
        cmd_run(a)
    else:
        cmd_combine(a)


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
