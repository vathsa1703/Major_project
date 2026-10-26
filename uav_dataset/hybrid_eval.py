"""Evaluate the hybrid timing AI (pre-registered: docs/prereg/hybrid_timing.md) on one announced sites cell.

    python hybrid_eval.py --profile sites_d20_t0_ann --models results/hybrid_rl/t0 --out results/hybrid/t0
                          [--bar_from ../results/g5/r1_t0/episodes.csv] [--workers 2]
    python hybrid_eval.py --report --out results/hybrid        # both cells -> results/hybrid/summary.md (Holm)

Per val scenario (100-119):
  prep      oracle coverage tensor (cached in results/oracle_cache/), the clairvoyant dp plan replayed through env.step
            (row 'dp'), and the hybrid's B6 table = the tensor at the decision times (saved to results/hybrid_cache/)
  prep_oma  the B6 table with access oma_opt (for the agents' OMA runs)
  B6never   the hybrid pilot that never leaves: must equal B6 exactly (checked in the report)
  ceiling   DIAGNOSTIC only: the best fixed departure time per scenario (follow B6 until d, then leave; d = 0..29 or
            never), chosen with hindsight = the most the hybrid's two actions could give with perfect timing
  bar       B6, B7, B8, B6fc (+ B6dep if baselines has it when this runs: decided in the pre-registration). Rows can be
            copied from an earlier G5 run with --bar_from (same profile, same code); missing ones are run.
  agents    every <models>/<name>/model.zip, with the cell's access (NOMA) and with access oma_opt (name|oma).
Writes <out>/episodes.csv (resumable: finished rows are not run again).
"""
import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import baselines as bl
import make_dataset as md
from evalstats import holm, mean_ci, paired_diff, paired_p
from run_baselines import _task, run_episode

BAR = ("B6", "B7", "B8", "B6fc") + (("B6dep",) if "B6dep" in bl.POLICIES else ())
CELLS = {"t0": "sites_d20_t0_ann", "t60": "sites_d20_t60_ann"}
HERE = Path(__file__).parent


def _setup():
    md.apply_profile(os.environ["UAV_PROFILE"])


def _prep(seed):
    """Oracle tensor -> hybrid table (saved to the hybrid cache) + the clairvoyant dp replay row."""
    _setup()
    import hybrid
    import oracle as orc
    from uav_env import UAVEnv
    env = UAVEnv()
    env.reset(seed=seed)
    nodes = orc.oracle_nodes(env)
    cov = orc.coverage_tensor(env, nodes)
    path = hybrid.cache_path(env)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, table=orc.frozen_scores(cov)[:, :-1], target=hybrid.b_target(env))
    graph = orc.hop_graph(nodes, len(nodes) - 1)
    _, _, target, _ = orc.dp_plan(orc.segment_scores(cov), graph, len(nodes) - 1)
    return {"policy": "dp", **run_episode(UAVEnv(), orc.PlanPolicy(nodes, target, "dp"), seed)}


def _prep_oma(seed):
    _setup()
    import hybrid
    from uav_env import UAVEnv
    env = UAVEnv(access="oma_opt")
    env.reset(seed=seed)
    hybrid.scenario_data(env)
    return None


def _schedule(args):
    name, seed = args
    _setup()
    import hybrid
    from uav_env import UAVEnv
    if name == "B6never":
        return {"policy": name, **run_episode(UAVEnv(), hybrid.ScheduleHybrid(None), seed)}
    best = None                                            # ceiling: every fixed departure, keep the best
    for d in [None, *range(md.CFG["mobility"]["episode_steps"] // hybrid.every())]:
        r = run_episode(UAVEnv(), hybrid.ScheduleHybrid(d), seed)
        if best is None or r["coverage_full"] > best["coverage_full"]:
            best = dict(r, leave_at=-1 if d is None else d)
    return {"policy": "ceiling", **best}


def _agent(args):
    name, path, seed, access = args
    _setup()
    from stable_baselines3 import PPO

    import hybrid
    from uav_env import UAVEnv
    pol = hybrid.HybridPolicy(PPO.load(path, device="cpu"))
    row = run_episode(UAVEnv(access=access), pol, seed)
    acts = np.array(pol.pilot.actions)
    first = int(np.argmax(acts == 1)) if (acts == 1).any() else -1
    return {"policy": name, **row, "leave_share": float(acts.mean()), "first_leave": first,
            "actions": "".join(map(str, acts))}


def append(csv, rows):
    rows = [r for r in rows if r is not None]
    if not rows:
        return
    df = pd.DataFrame(rows)
    if csv.exists():
        head = list(pd.read_csv(csv, nrows=0).columns)
        cols = head + [c for c in df.columns if c not in head]
        if cols != head:                                   # new columns: rewrite with the wider header
            old = pd.read_csv(csv).reindex(columns=cols)
            old.to_csv(csv, index=False)
        df.reindex(columns=cols).to_csv(csv, mode="a", header=False, index=False)
    else:
        df.to_csv(csv, index=False)


def run_cell(a):
    os.environ["UAV_PROFILE"] = a.profile
    md.apply_profile(a.profile)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    csv = out / "episodes.csv"
    have = pd.read_csv(csv) if csv.exists() else pd.DataFrame(columns=["policy", "seed"])
    done = set(zip(have["policy"], have["seed"], strict=True))
    seeds = md.seeds("val")[: a.seeds]
    if a.bar_from:
        old = pd.read_csv(a.bar_from)
        old = old[old.policy.isin(BAR) & old.seed.isin(seeds)]
        old = old[[(p, s) not in done for p, s in zip(old.policy, old.seed, strict=True)]]
        append(csv, old.to_dict("records"))
        done |= set(zip(old.policy, old.seed, strict=True))
    models = {p.parent.name: p for p in sorted(Path(a.models).glob("*/model.zip"))} if a.models else {}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        def run(fn, jobs, key):
            for job, r in zip(jobs, pool.map(fn, jobs, chunksize=1), strict=True):
                append(csv, [r])
                print(f"  {key(job)} done", flush=True)
        run(_prep, [s for s in seeds if ("dp", s) not in done], lambda s: f"prep {s}")
        if not a.no_oma:                                   # cached per scenario: a rerun only loads the tables
            run(_prep_oma, list(seeds), lambda s: f"prep_oma {s}")
        run(_schedule, [(n, s) for n in ("B6never", "ceiling") for s in seeds if (n, s) not in done],
            lambda j: f"{j[0]} {j[1]}")
        run(_task, [(n, s, None) for n in BAR for s in seeds if (n, s) not in done], lambda j: f"{j[0]} {j[1]}")
        jobs = [(n, str(p), s, None) for n, p in models.items() for s in seeds if (n, s) not in done]
        if not a.no_oma:
            jobs += [(n + "|oma", str(p), s, "oma_opt") for n, p in models.items() for s in seeds
                     if (n + "|oma", s) not in done]
        run(_agent, jobs, lambda j: f"{j[0]} {j[2]}")
    print(cell_summary(pd.read_csv(csv), a.profile)[0])


# ---------------------------------------------------------------- report
def fmt(mci):
    m, h = mci
    return f"{m:+.3f} +/- {h:.3f}{'*' if abs(m) > h else ''}"


def cell_summary(df, profile):
    """Markdown for one cell, and the numbers the pass mark needs (mean agent - bar per scenario, p)."""
    piv = df.pivot_table(index="seed", columns="policy", values="coverage_full")
    bar_names = [n for n in BAR if n in piv]
    bar = piv[bar_names].max(axis=1)
    agents = sorted(c for c in piv.columns if "|" not in c and c not in (*BAR, "dp", "B6never", "ceiling"))
    L = [f"### {profile} (val, {len(piv)} scenarios)", "",
         f"Bar = per-scenario best of {', '.join(bar_names)}: mean {bar.mean():.3f} (" +
         ", ".join(f"{n} {piv[n].mean():.3f}" for n in bar_names) + ")."]
    if "dp" in piv:
        L.append(f"Clairvoyant dp (replayed): {piv['dp'].mean():.3f}; room over the bar "
                 f"{fmt(paired_diff(piv['dp'], bar))}.")
    if "B6never" in piv and "B6" in piv:
        same = bool(np.array_equal(piv["B6never"].to_numpy(), piv["B6"].to_numpy()))
        L.append(f"Check: hybrid pilot that never leaves == B6 on every scenario: {same}.")
    if "ceiling" in piv:
        c = piv["ceiling"]
        L.append(f"Diagnostic (hindsight, not flyable): best fixed departure per scenario {c.mean():.3f}; "
                 f"vs bar {fmt(paired_diff(c, bar))}; vs B6 {fmt(paired_diff(c, piv['B6']))}.")
    L += ["", "| agent | coverage (NOMA) | agent - bar (95% CI) | agent - B6 | leave share | first leave (decision) "
              "| coverage with OMA | NOMA - OMA |", "|---|---|---|---|---|---|---|---|"]
    extra = df.drop_duplicates(["policy", "seed"]).set_index(["policy", "seed"])
    for n in agents:
        oma = piv.get(n + "|oma")
        o = f"{oma.mean():.3f} | {fmt(paired_diff(piv[n], oma))}" if oma is not None else "- | -"
        lv = extra.loc[n]["leave_share"].mean() if "leave_share" in extra else np.nan
        fl = extra.loc[n]["first_leave"]
        fl_txt = f"{fl[fl >= 0].mean():.1f} (never on {(fl < 0).sum()})" if len(fl) else "-"
        L.append(f"| {n} | {piv[n].mean():.3f} | {fmt(paired_diff(piv[n], bar))} | "
                 f"{fmt(paired_diff(piv[n], piv['B6']))} | {lv:.2f} | {fl_txt} | {o} |")
    res = {}
    if agents:
        mean_agent = piv[agents].mean(axis=1)                 # per scenario: mean over the training seeds
        d, h = paired_diff(mean_agent, bar)
        p = paired_p(mean_agent, bar)
        res = dict(diff=d, ci=h, p=p, n_agents=len(agents))
        L += ["", f"**{len(agents)}-seed mean** (per scenario, mean over the agents): {mean_agent.mean():.3f}; "
                  f"vs bar {d:+.3f} +/- {h:.3f} (p = {p:.3g}); vs B6 {fmt(paired_diff(mean_agent, piv['B6']))}."]
        if "dp" in piv:
            room = piv["dp"].mean() - bar.mean()
            res["room_share"] = (mean_agent.mean() - bar.mean()) / room if room > 0 else np.nan
            L.append(f"Share of the clairvoyant room captured: (agent - bar) / (dp - bar) = "
                     f"{mean_agent.mean() - bar.mean():+.3f} / {room:+.3f} = {res['room_share']:+.0%}.")
        omas = [n + "|oma" for n in agents if n + "|oma" in piv]
        if omas:
            mo = piv[omas].mean(axis=1)
            L.append(f"NOMA vs OMA (same agents, access oma_opt): {mean_agent.mean():.3f} vs {mo.mean():.3f}, "
                     f"NOMA - OMA {fmt(paired_diff(mean_agent, mo))}.")
        m, h = mean_ci(piv[agents].mean(axis=0))
        L += ["", "Per training seed (NOMA): " + ", ".join(f"{n} {piv[n].mean():.3f}" for n in agents) + "; "
              f"over training seeds {m:.3f} +/- {h:.3f} (mean +/- 95% CI)."]
    return "\n".join(L), res


def report(out):
    out = Path(out)
    parts, res = [], {}
    for tag, prof in CELLS.items():
        csv = out / tag / "episodes.csv"
        if csv.exists():
            text, r = cell_summary(pd.read_csv(csv), prof)
            parts.append(text)
            if r:
                res[prof] = r
    lines = ["## Hybrid timing AI: G5 evaluation (pre-registered, docs/prereg/hybrid_timing.md)", "",
             "HYBRID: B6 chooses WHERE, the PPO timing policy chooses only WHEN to leave for the announced "
             "destination.",
             "All numbers: mean coverage over 300 s, replayed through env.step. Paired differences with 95% CI "
             "(* = CI excludes 0).", ""]
    lines += sum([[p, ""] for p in parts], [])
    if res:
        names = list(res)
        adj = holm([res[n]["p"] for n in names])
        lines += ["### Pre-registered pass mark", "",
                  "Pass = in at least one cell the seed mean (Round A: 3 seeds) beats the bar: mean paired "
                  "difference > 0 and Holm-adjusted p < 0.05 over the 2 cells.", "",
                  "| cell | agent - bar | p | Holm p | passes |", "|---|---|---|---|---|"]
        ok = []
        for n, p in zip(names, adj, strict=True):
            r = res[n]
            passed = bool(r["diff"] > 0 and p < 0.05)
            ok.append(passed)
            lines.append(f"| {n} | {r['diff']:+.3f} +/- {r['ci']:.3f} | {r['p']:.3g} | {p:.3g} | {passed} |")
        lines += ["", f"**Verdict: {'PASS' if any(ok) else 'NOT MET'}** "
                      f"({sum(ok)} of {len(ok)} cells pass; {len(names)} cells evaluated)."]
    text = "\n".join(lines)
    (out / "summary.md").write_text(text + "\n", encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--models", default=None, help="folder with <name>/model.zip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bar_from", default=None, help="episodes.csv of an earlier run on the same profile")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seeds", type=int, default=None, help="first N val seeds only (smoke test)")
    ap.add_argument("--no_oma", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.report:
        report(a.out)
    else:
        run_cell(a)


if __name__ == "__main__":
    main()
