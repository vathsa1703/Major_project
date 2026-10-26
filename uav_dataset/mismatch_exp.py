"""Model mismatch: is there room for a learner when the true channel differs from the planners' textbook model?

    python mismatch_exp.py tune                       # B6meas settings on DESIGN seeds 10000-10009 (never val)
    python mismatch_exp.py room --shard 0/2           # (and 1/2 in a second process) the room test on val seeds 100-119
    python mismatch_exp.py confirm --shard 0/2        # exploratory cells (mm_h8, mm_combo) on fresh seeds 1000-1019
    python mismatch_exp.py report                     # -> results/mismatch/room.md
    python mismatch_exp.py room --cells mm_bl25 --policies B6,B6meas --seeds 100-101   # smoke test

Room test (no AI): per cell (config profiles mm_*; `rl_static` with the owner's G5 settings, one perturbation type per
cell) and val scenario, the pilots B6 (nominal), B6r (nominal + off-grid refinement), B6meas (nominal proposal +
measured search; level-1 information), B3 (nominal, fixed altitude) and B6true (true channel + refinement; upper bound).
Room = B6true - per-scenario best of (B6, B6meas) [and of (B6, B6meas, B3), the AI's bar], paired 95% CI.
Pre-registered room pass (reviewer amendment 7): mean >= 0.02 AND the 95% CI lower bound > 0.
Every finished episode is appended to a CSV (one per shard), so an interrupted run resumes.

Speed: still crowds (mobility `static`, no activity mask, a QoS-aware scheme or extreme pairing) make env.evaluate a
pure function of the candidate within an episode, so CachedEnv memoises it per candidate (exactly the same numbers;
test in test_mismatch.py). Any other scenario falls back to the plain evaluate.
"""
import argparse
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

import make_dataset as md
from baselines import make_policy
from evalstats import paired_diff
from run_baselines import run_episode
from uav_env import UAVEnv

OUT = Path(__file__).parent / "results" / "mismatch"
CELLS = ["mm_none", "mm_s4_c25", "mm_s4_c50", "mm_s4_c150", "mm_s8_c25", "mm_s8_c50", "mm_s8_c150", "mm_bl25",
         "mm_h2", "mm_h4"]
EXPLORATORY = ["mm_h8", "mm_combo"]        # added AFTER the room test (no cell passed); never in the pass family
TYPES = {"mm_none": "none (negative control)", "mm_bl25": "building loss 25 dB (planner 15)",
         "mm_h2": "2 hidden buildings", "mm_h4": "4 hidden buildings", "mm_h8": "EXPLORATORY: 8 hidden buildings",
         "mm_combo": "EXPLORATORY: shadowing 8 dB / 150 m + loss 25 dB + 4 hidden"}
POLICIES = ("B6", "B6r", "B6meas", "B3", "B6true")
VAL = "100-119"
DESIGN = "10000-10009"
CONFIRM = "1000-1019"                         # fresh seeds (never train / val / test) for the exploratory cells
TUNE_CELLS = ["mm_none", "mm_bl25", "mm_s8_c50", "mm_h4"]
TUNE_GRID = [dict(k=k, dwell_s=d, alt_probes=a, steps_m=st) for k in (3, 5) for d in (2, 10) for a in (False, True)
             for st in ([100, 50, 25], [50, 25])]
ROOM_PASS = 0.02


def cell_label(c):
    if c in TYPES:
        return TYPES[c]
    s, corr = c.split("_")[1:]
    return f"shadowing sigma {s[1:]} dB, corr {corr[1:]} m"


class CachedEnv(UAVEnv):
    """UAVEnv whose evaluate is memoised per candidate (x, y, h, power, model) within an episode, ONLY for still crowds
    without an activity mask and with a scheme that does not draw random pairs (then the users, their rates and the
    gains are the same at every t, and every candidate's coverage is computed independently of the others)."""

    def reset(self, seed=None, options=None):
        self._ecache = {}
        return super().reset(seed=seed, options=options)

    def _cacheable(self):
        return (self.sc["mobility"] == "static" and self.active is None
                and (self.access in md.QOS_SCHEMES or self.sc["pairing"] == "extreme"))

    def evaluate_users(self, xy, min_rate, rescue, X, Y, H, p_w, t, model="nominal"):
        if not self._cacheable():
            return super().evaluate_users(xy, min_rate, rescue, X, Y, H, p_w, t, model=model)
        X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
        keys = [(model, float(p_w), x, y, h) for x, y, h in zip(X.tolist(), Y.tolist(), H.tolist(), strict=True)]
        miss = [i for i, k in enumerate(keys) if k not in self._ecache]
        if miss:
            vals = super().evaluate_users(xy, min_rate, rescue, X[miss], Y[miss], H[miss], p_w, t, model=model)
            for i, v in zip(miss, vals, strict=True):
                self._ecache[keys[i]] = float(v)
        return np.array([self._ecache[k] for k in keys])


def parse_seeds(s):
    lo, hi = (int(v) for v in s.split("-"))
    return list(range(lo, hi + 1))


def b6meas_variant(v):
    st = "-".join(str(int(s)) for s in (v.get("steps_m") or md.CFG["refine"]["steps_m"]))
    return f"k{v['k']}_d{v['dwell_s']}_alt{int(v['alt_probes'])}_s{st}"


def run_one(cell, pol, seed, b6meas=None, draw=0):
    md.apply_profile(cell)
    if b6meas:
        md.CFG["b6meas"].update(b6meas)
    md.CFG["mismatch"]["draw"] = draw
    t0 = time.time()
    p = make_policy(pol)
    row = run_episode(CachedEnv(), p, seed)
    row.update(cell=cell, policy=pol, draw=draw, secs=round(time.time() - t0, 2),
               variant=b6meas_variant(md.CFG["b6meas"]) if pol == "B6meas" else "")
    nan = float("nan")
    row.update(meas_points=-1, final_x=nan, final_y=nan, final_h=nan, final_measured=nan, t_commit=-1)
    if pol == "B6meas":
        row.update(meas_points=len(p.log), final_x=p.center[0], final_y=p.center[1], final_h=p.center[2],
                   final_measured=p.center_val, t_commit=p.t_commit if p.t_commit is not None else -1)
    md.apply_profile("default")
    return row


def append(csv, row):
    df = pd.DataFrame([row])
    if csv.exists():
        head = list(pd.read_csv(csv, nrows=0).columns)
        assert not set(df.columns) - set(head), f"new columns {set(df.columns) - set(head)} for {csv.name}"
        df = df.reindex(columns=head)
    df.to_csv(csv, mode="a", header=not csv.exists(), index=False)


def run_jobs(jobs, csv, shard):
    k, n = (int(v) for v in shard.split("/"))
    jobs = jobs[k::n]
    done = set()
    if csv.exists():
        old = pd.read_csv(csv, keep_default_na=False)
        done = set(zip(old.cell, old.policy, old.seed, old.variant.astype(str), strict=True))
    todo = [j for j in jobs if (j[0], j[1], j[2], j[4]) not in done]
    print(f"{len(todo)} of {len(jobs)} episodes to run (shard {shard})", flush=True)
    t0 = time.time()
    for i, (cell, pol, seed, var, _tag) in enumerate(todo, 1):
        append(csv, run_one(cell, pol, seed, var))
        if i % 10 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}  {(time.time() - t0) / 60:.1f} min", flush=True)


def frozen_b6meas():
    """The frozen B6meas setting = config `b6meas:` (the tuned values are written there after `tune`)."""
    md.apply_profile("default")
    return {k: md.CFG["b6meas"][k] for k in ("k", "dwell_s", "alt_probes", "steps_m")}


def cmd_room(a, prefix="room"):
    OUT.mkdir(parents=True, exist_ok=True)
    seeds, cells, pols = parse_seeds(a.seeds), a.cells.split(","), a.policies.split(",")
    var = frozen_b6meas()
    jobs = [(c, p, s, None, b6meas_variant(var) if p == "B6meas" else "") for c in cells for s in seeds for p in pols]
    run_jobs(jobs, OUT / f"{prefix}_episodes_{a.shard.replace('/', 'of')}.csv", a.shard)


def cmd_tune(a):
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = parse_seeds(a.seeds or DESIGN)
    jobs = [(c, "B6meas", s, v, b6meas_variant(v)) for v in TUNE_GRID for c in TUNE_CELLS for s in seeds]
    jobs += [(c, "B6", s, None, "") for c in TUNE_CELLS for s in seeds]
    run_jobs(jobs, OUT / f"tune_episodes_{a.shard.replace('/', 'of')}.csv", a.shard)


def load(prefix):
    fs = sorted(OUT.glob(f"{prefix}_episodes_*.csv"))
    df = pd.concat([pd.read_csv(f, keep_default_na=False) for f in fs], ignore_index=True)
    dup = df.duplicated(["cell", "policy", "seed", "variant", "draw"])
    assert not dup.any(), f"duplicate episodes in {prefix}"
    return df


def ci(m, h, k=3):
    return f"{m:+.{k}f} [{m - h:+.{k}f}, {m + h:+.{k}f}]"


def cmd_report(a):
    lines = ["# Model mismatch: room test (no AI)", ""]
    tune_txt = []
    if list(OUT.glob("tune_episodes_*.csv")):
        t = load("tune")
        m = t[t.policy == "B6meas"].groupby("variant").coverage_full.mean().sort_values(ascending=False)
        b6 = t[t.policy == "B6"].coverage_full.mean()
        per = t[t.policy == "B6meas"].pivot_table(index="variant", columns="cell", values="coverage_full")
        tune_txt = [f"## B6meas tuning (design seeds {DESIGN}, cells {', '.join(TUNE_CELLS)}; never val)", "",
                    f"Mean coverage_full over the {t.seed.nunique()} design seeds x {len(TUNE_CELLS)} cells; "
                    f"B6 on the same: {b6:.4f}. Chosen = the best mean, frozen in config `b6meas:` = "
                    f"{b6meas_variant(frozen_b6meas())}.", "",
                    "| variant | mean | " + " | ".join(per.columns) + " |", "|---|---|" + "---|" * len(per.columns)]
        for v in m.index:
            tune_txt.append(f"| {v} | {m[v]:.4f} | " + " | ".join(f"{per.loc[v, c]:.4f}" for c in per.columns) + " |")
        tune_txt.append("")
    df = load("room")
    n_sc = df.groupby("cell").seed.nunique()
    lines += [f"Profile family `mm_*`: `rl_static` scenarios (2 km map, 20 dBm, 3-8 known buildings, still crowds, "
              f"16 Wh) with the owner's G5 settings (noma_opt, sic_eps 0.05, rescue_first, a_max 4 m/s^2). Val seeds "
              f"{VAL} ({n_sc.min()}-{n_sc.max()} scenarios per cell). coverage_full = mean coverage over 300 s. "
              f"All pilots fly the same env.step (the TRUE world); B6, B6r, B6meas and B3 plan with the NOMINAL "
              f"model, B6true with the true one.", "",
              "Room = B6true - per-scenario best of (B6, B6meas); AI bar = per-scenario best of (B6, B6meas, B3). "
              f"Pre-registered room pass: mean >= {ROOM_PASS} AND 95% CI lower bound > 0. [a, b] = paired 95% CI.", "",
              f"## Val seeds {VAL}", ""] + room_tables(df)
    if list(OUT.glob("confirm_episodes_*.csv")):
        lines += [f"## Confirmation of the exploratory cells on FRESH seeds {CONFIRM} (run after the val result; the "
                  f"room criterion applied unchanged)", ""] + room_tables(load("confirm"), confirm=True)
    secs = df.groupby("policy").secs.mean()
    lines += ["Run time per episode (s, mean): " + ", ".join(f"{k} {v:.1f}" for k, v in secs.items()), ""]
    text = "\n".join(lines + tune_txt)
    (OUT / "room.md").write_text(text, encoding="utf-8")
    print(text)


def room_tables(df, confirm=False):
    piv = df.pivot_table(index=["cell", "seed"], columns="policy", values="coverage_full")
    lines = ["Mean coverage_full per pilot:", "",
             "| cell | perturbation | " + " | ".join(POLICIES) + " |", "|---|---|" + "---|" * len(POLICIES)]
    for c in CELLS + EXPLORATORY:
        if c not in piv.index.get_level_values(0):
            continue
        p = piv.loc[c]
        lines.append(f"| {c} | {cell_label(c)} | " + " | ".join(
            f"{p[q].mean():.4f}" if q in p else "-" for q in POLICIES) + " |")
    lines += ["", "Room (paired over scenarios):", "",
              "| cell | room = B6true - best(B6, B6meas) | pass | B6true - AI bar (incl. B3) | B6true - B6 | "
              "B6r - B6 (resolution) | B6true - B6r (knowing the channel) | B6meas - B6 |",
              "|---|---|---|---|---|---|---|---|"]
    for c in CELLS + EXPLORATORY:
        if c not in piv.index.get_level_values(0):
            continue
        p = piv.loc[c].dropna()
        best = p[["B6", "B6meas"]].max(axis=1)
        bar = p[["B6", "B6meas", "B3"]].max(axis=1)
        r = paired_diff(p.B6true, best)
        ok = r[0] >= ROOM_PASS and r[0] - r[1] > 0
        verdict = ("PASS" if ok else "no") + (" (exploratory)" if c in EXPLORATORY and not confirm else "")
        lines.append(f"| {c} | {ci(*r)} | {verdict} | {ci(*paired_diff(p.B6true, bar))} | "
                     f"{ci(*paired_diff(p.B6true, p.B6))} | {ci(*paired_diff(p.B6r, p.B6))} | "
                     f"{ci(*paired_diff(p.B6true, p.B6r))} | {ci(*paired_diff(p.B6meas, p.B6))} |")
    return lines + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["room", "confirm", "tune", "report"])
    ap.add_argument("--cells", default=",".join(CELLS))
    ap.add_argument("--policies", default=",".join(POLICIES))
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--shard", default="0/1")
    a = ap.parse_args()
    if a.cmd == "room":
        a.seeds = a.seeds or VAL
        cmd_room(a)
    elif a.cmd == "confirm":
        a.seeds = a.seeds or CONFIRM
        a.cells = ",".join(EXPLORATORY) if a.cells == ",".join(CELLS) else a.cells
        cmd_room(a, prefix="confirm")
    elif a.cmd == "tune":
        cmd_tune(a)
    else:
        cmd_report(a)


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
