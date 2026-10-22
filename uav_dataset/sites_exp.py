"""D-52 scenario redesign, phases 1-2 (pre-registered; do not change the grid, the baselines or the pass mark).

    python sites_exp.py phase1            # B8 on `hard`, 12 and 13 Wh, acceleration limit on (a_max 4), 100 scenarios
    python sites_exp.py headroom --seeds 0-19      # energy-free headroom on the 9 design cells (sites_d*_t* profiles)
    python sites_exp.py negcontrol        # today's `hard` with the old defaults: B6 seed 7 must give 0.7206
    python sites_exp.py report            # tables -> results/sites/summary.md
One process, sequential. Every finished episode / scenario is appended to a CSV, so an interrupted run resumes.

Phase 1 (battery-only check). B6 and B7 never look at the battery, so their trajectory until the battery is empty does
not depend on its size: their 12 and 13 Wh numbers come by exact truncation of 16 Wh per-step logs (method and check of
accel_loiter_exp.py; the logs of the plan-step-5 run `hard_on` are read from results/sites/phase1_b67_steps/).
`phase1` also re-runs B6 and B7 for real at 12 and 13 Wh on VERIFY_SEEDS and the report checks that truncation and the
real runs agree exactly. B8 looks at the battery, so it is always run for real.

Phase 2 (headroom, energy-free first). Per cell and scenario: coverage tensor + dp + teleport bound from oracle.py (the
planner ignores energy and the acceleration limit; every reported plan number is a REPLAY through env.step with the
cell's real battery, 16 Wh, and acceleration limit), and B6, B7, B8 replayed the same way. The announced/unannounced
flag only feeds the (off) event_countdown observation, so for the clairvoyant dp and these baselines the 18-cell grid
reduces to 9 cells.
"""
import argparse
import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import make_dataset as md
import oracle as orc
from accel_loiter_exp import truncate
from baselines import make_policy
from evalstats import holm, mean_ci, paired_diff, paired_p
from run_baselines import run_episode
from uav_env import UAVEnv

OUT = Path(__file__).parent / "results" / "sites"
B67_STEPS = OUT / "phase1_b67_steps"
A_ON = 4.0                                   # a_max of D-48 (engineering assumption, sensitivity {2, 4, 8})
P1_SEEDS = list(range(100))                  # hard, baselines.eval_seeds (0-99)
P1_BATTERIES = (12.0, 13.0)
VERIFY_SEEDS = (0, 7, 42)
CELLS = [f"sites_d{d}_t{t}" for d in ("10", "15", "20") for t in (0, 60, 180)]
BASES = ("B6", "B7", "B8")
PASS_MARK = 0.02                             # D-52, pre-registered (same value as oracle.min_gain)


def hard_accel():
    md.apply_profile("hard")
    md.CFG["uav"]["a_max_mps2"] = A_ON


def append(csv, rows):
    pd.DataFrame(rows).to_csv(csv, mode="a", header=not csv.exists(), index=False)


# ---------------------------------------------------------------- phase 1
def phase1():
    OUT.mkdir(parents=True, exist_ok=True)
    csv = OUT / "phase1_episodes.csv"
    done = set()
    if csv.exists():
        old = pd.read_csv(csv)
        done = set(zip(old.policy, old.seed, old.battery_wh, strict=True))
    jobs = [(p, s, b) for p in ("B6", "B7") for s in VERIFY_SEEDS for b in P1_BATTERIES]
    jobs += [("B8", s, b) for s in P1_SEEDS for b in P1_BATTERIES]
    jobs = [j for j in jobs if j not in done]
    print(f"phase 1: {len(jobs)} episodes to run, 1 process", flush=True)
    t0 = time.time()
    for i, (p, s, b) in enumerate(jobs, 1):
        hard_accel()
        t1 = time.time()
        row = run_episode(UAVEnv(battery_wh=b), make_policy(p), s)
        append(csv, [dict(policy=p, battery_wh=b, secs=time.time() - t1, **row)])
        if i % 10 == 0 or i == len(jobs):
            print(f"  {i}/{len(jobs)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    md.apply_profile("default")


def phase1_table():
    df = pd.read_csv(OUT / "phase1_episodes.csv")
    res, L = {}, []
    checks = []
    for p in ("B6", "B7"):
        for b in P1_BATTERIES:
            vals = {s: truncate(dict(np.load(B67_STEPS / f"hard_on__{p}__{s}.npz")), b, 300) for s in P1_SEEDS}
            res[(p, b)] = (pd.Series({s: v[0] for s, v in vals.items()}),
                           pd.Series({s: v[1] for s, v in vals.items()}))
            for s in VERIFY_SEEDS:
                real = df[(df.policy == p) & (df.seed == s) & (df.battery_wh == b)]
                if len(real):
                    # equal up to summation order (np.sum of a list vs of an array slice: last-ulp differences)
                    checks.append(bool(abs(real.coverage_full.iloc[0] - vals[s][0]) < 1e-12
                                       and bool(real.survived.iloc[0]) == vals[s][1]))
    for b in P1_BATTERIES:
        d = df[(df.policy == "B8") & (df.battery_wh == b)].set_index("seed").sort_index()
        res[("B8", b)] = (d.coverage_full, d.survived.astype(bool))
    n8 = min(len(res[("B8", b)][0]) for b in P1_BATTERIES)
    L += [f"## Phase 1: battery-only check on `hard` (100 scenarios, seeds 0-99), acceleration limit on "
          f"(a_max {A_ON:g}),",
          "today's NOMA (env.access noma, as in book 7.10), 300 s; coverage_full (dead drone = 0), mean +/- 95% CI", "",
          f"B8 episodes found: {n8} per battery. B6/B7 by exact truncation of the 16 Wh step logs; truncation = real "
          f"run on {sum(checks)}/{len(checks)} checks (seeds {VERIFY_SEEDS}, both batteries; |diff| < 1e-12).", "",
          "| battery | B6 | B6 survived | B7 | B7 survived | B8 | B8 survived |", "|---|---|---|---|---|---|---|"]
    for b in P1_BATTERIES:
        cells = []
        for p in BASES:
            c, s = res[(p, b)]
            m, h = mean_ci(c)
            cells += [f"{m:.3f} +/- {h:.3f}", f"{s.mean():.0%}"]
        L.append(f"| {b:g} Wh | " + " | ".join(cells) + " |")
    pairs = []
    for b in P1_BATTERIES:
        c = {p: res[(p, b)][0] for p in BASES}
        idx = c["B8"].index
        for a, z in (("B8", "B6"), ("B8", "B7"), ("B7", "B6")):
            pairs.append((f"{a} - {z} at {b:g} Wh", c[a].loc[idx], c[z].loc[idx]))
    ps = [paired_p(a, z) for _, a, z in pairs]
    L += ["", "Paired differences of coverage_full (Holm over the 6 rows):", "",
          "| comparison | mean diff +/- 95% CI | p | Holm p |", "|---|---|---|---|"]
    for (lab, a, z), p, q in zip(pairs, ps, holm(ps), strict=True):
        m, h = paired_diff(a, z)
        L.append(f"| {lab} | {m:+.4f} +/- {h:.4f} | {p:.2g} | {q:.2g}{' *' if q < 0.05 else ''} |")
    t = df[df.policy == "B8"].secs
    L += ["", f"B8 run time: {t.sum() / 60:.0f} min for {len(t)} episodes ({t.mean():.1f} s per episode).", ""]
    return L


# ---------------------------------------------------------------- phase 2
_ROWS = {}          # tensor rows by their exact inputs (shared between the cells of one seed; cleared per seed)


def shared_tensor(env, nodes):
    """oracle.coverage_tensor(env, nodes) without the disk cache, but computing each row once per distinct INPUT: a
    row is env.evaluate(nodes, t) and depends only on the active users' positions, rates and rescue flags at t, the
    obstacles, the nodes and the radio settings. Within one seed these are identical across the tau cells of one D
    before the event (t < t0) and after the move is complete (t >= t0 + tau), so those rows are reused (exact: same
    inputs, same function)."""
    p_w = env.p_max_w * md.CFG["baselines"]["power_frac"]
    rows = []
    for t in orc.sample_times(env):
        xy, mr, rs = env.users_now(t)
        blob = b"".join([np.ascontiguousarray(a).tobytes() for a in (xy, mr, rs, env.boxes, nodes)])
        blob += repr((int(t), p_w, env.access, env.sic_eps, env.rescue_first, env.sc["bandwidth_hz"],
                      env.sc["pairing"], env.scenario_seed)).encode()
        key = hashlib.sha1(blob).hexdigest()
        if key not in _ROWS:
            _ROWS[key] = env.evaluate(nodes[:, 0], nodes[:, 1], nodes[:, 2], p_w, t=t)
        rows.append(_ROWS[key])
    return np.stack(rows)


def tensor_backed(env, nodes, cov):
    """Make env.evaluate answer B6's lattice candidates at the tensor's sample times from the tensor (the same numbers:
    every tensor entry IS env.evaluate at that node and time, and evaluate is row-independent for the QoS schemes and
    for extreme pairing), computing only the extra candidates (B6's 'stay' spot). Anything else -> the real evaluate.
    Used to replay B6, B7, B8 without recomputing the 980-candidate search every 10 s (test_sites checks equality)."""
    plain = env.evaluate
    if not (env.access in md.QOS_SCHEMES or env.sc["pairing"] == "extreme"):
        return plain
    times = {int(t): i for i, t in enumerate(orc.sample_times(env))}
    lat = nodes[:-1]
    n = len(lat)
    p_ref = env.p_max_w * md.CFG["baselines"]["power_frac"]

    def evaluate(X, Y, H, p_w, t=None):
        tt = env.t if t is None else int(t)
        X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
        if (tt in times and p_w == p_ref and len(X) >= n and np.array_equal(X[:n], lat[:, 0])
                and np.array_equal(Y[:n], lat[:, 1]) and np.array_equal(H[:n], lat[:, 2])):
            head = cov[times[tt], :n].copy()
            return np.concatenate([head, plain(X[n:], Y[n:], H[n:], p_w, t=tt)]) if len(X) > n else head
        return plain(X, Y, H, p_w, t=t)

    env.evaluate = evaluate
    return plain


def headroom_one(cell, seed):
    """One scenario of one cell: teleport bound, dp (replayed) and B6, B7, B8 (replayed). Returns one row."""
    md.apply_profile(cell)
    t0 = time.time()
    env = UAVEnv()
    env.reset(seed=seed)
    sc = dict(env.sc)
    nodes = orc.oracle_nodes(env)
    cov = shared_tensor(env, nodes)
    tensor_backed(env, nodes, cov)
    t_tensor = time.time() - t0
    S = orc.segment_scores(cov)
    graph = orc.hop_graph(nodes, len(nodes) - 1)
    value, _, target, _ = orc.dp_plan(S, graph, len(nodes) - 1)
    t_plan = time.time() - t0 - t_tensor
    row = dict(cell=cell, seed=seed, distance_m=sc["distance_m"], tau_s=sc["tau_s"], n_users=sc["n_users"],
               n_sites=sc["n_sites"], t0_s=sc["event_t0_s"], share=sc["event_share"], access=env.access,
               battery_wh=env.battery_j / 3600.0, teleport=float(S.max(axis=1).mean()),
               dp_model=value / S.shape[0])
    pols = [(b, make_policy(b)) for b in BASES] + [("dp", orc.PlanPolicy(nodes, target, "dp"))]
    t_ev = int(sc["event_t0_s"])
    for name, pol in pols:
        c, steps = orc.episode_coverage(env, pol, seed)
        row[name] = float(c.mean())
        row[f"{name}_survived"] = bool(steps >= env.T)
        row[f"{name}_pre"], row[f"{name}_post"] = float(c[:t_ev].mean()), float(c[t_ev:].mean())
    row.update(secs_tensor=t_tensor, secs_plan=t_plan, secs_total=time.time() - t0)
    md.apply_profile("default")
    return row


def headroom(seeds):
    OUT.mkdir(parents=True, exist_ok=True)
    csv = OUT / "headroom_episodes.csv"
    done = set()
    if csv.exists():
        old = pd.read_csv(csv)
        done = set(zip(old.cell, old.seed, strict=True))
    jobs = [(c, s) for s in seeds for c in CELLS if (c, s) not in done]      # seed-major: every cell grows together
    print(f"headroom: {len(jobs)} scenarios to run ({len(CELLS)} cells), 1 process", flush=True)
    t0, last = time.time(), None
    for i, (c, s) in enumerate(jobs, 1):
        if s != last:
            _ROWS.clear()
            last = s
        row = headroom_one(c, s)
        append(csv, [row])
        print(f"  {i}/{len(jobs)} {c} seed {s}: B6 {row['B6']:.3f} B7 {row['B7']:.3f} B8 {row['B8']:.3f} "
              f"dp {row['dp']:.3f} tele {row['teleport']:.3f}  {row['secs_total']:.0f}s "
              f"(total {(time.time() - t0) / 60:.1f} min)", flush=True)


def headroom_table():
    df = pd.read_csv(OUT / "headroom_episodes.csv")
    v_max = md.BASE_CFG["uav"]["v_max_mps"]
    L = ["## Phase 2: energy-free headroom on the competing-sites design grid (D-52)", "",
         "Per cell: mean coverage_full (replayed through env.step, 300 s, 16 Wh, a_max 4, noma_opt, sic_eps 0.05, "
         "rescue first). Best baseline = the best of B6, B7, B8 by the cell mean (pre-registered bar). dp - best: "
         "paired over the cell's scenarios, mean +/- 95% CI. Teleport = tensor-level bound (best node in every 10 s "
         "segment, travel ignored; not flyable). Transit = D / v_max. Pass mark (pre-registered): dp - best >= "
         f"{PASS_MARK:.2f}. Announced/unannounced: identical for dp and these baselines, so 9 cells, not 18.", "",
         "| cell | D km | tau s | transit s | n | B6 | B7 | B8 | best | dp | dp - best (95% CI) | p | teleport | "
         "teleport - best | dp - per-scenario max | dp - best before / after t0 | pass |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cell in CELLS:
        d = df[df.cell == cell].sort_values("seed")
        if not len(d):
            continue
        means = {b: d[b].mean() for b in BASES}
        best = max(BASES, key=lambda b: means[b])
        m, h = paired_diff(d.dp, d[best])
        mx, _ = paired_diff(d.dp, d[list(BASES)].max(axis=1))
        pre, post = ((d[f"dp_{w}"] - d[f"{best}_{w}"]).mean() for w in ("pre", "post"))
        D, tau = d.distance_m.iloc[0], d.tau_s.iloc[0]
        L.append(f"| {cell} | {D / 1000:.1f} | {tau:g} | {D / v_max:.0f} | {len(d)} | "
                 + " | ".join(f"{means[b]:.3f}" for b in BASES)
                 + f" | {best} | {d.dp.mean():.3f} | {m:+.3f} +/- {h:.3f} | {paired_p(d.dp, d[best]):.2g} | "
                 f"{d.teleport.mean():.3f} | {d.teleport.mean() - means[best]:+.3f} | {mx:+.3f} | "
                 f"{pre:+.3f} / {post:+.3f} | {'PASS' if m >= PASS_MARK else 'no'} |")
    L += ["", "Survival (share of scenarios that last 300 s): "
          + ", ".join(f"{b} {df[f'{b}_survived'].mean():.0%}" for b in (*BASES, "dp")) + ".",
          f"Run time: {df.secs_total.sum() / 60:.0f} min for {len(df)} scenarios ({df.secs_total.mean():.0f} s each; "
          f"tensor {df.secs_tensor.mean():.0f} s, dp {df.secs_plan.mean():.0f} s).", ""]
    return L


# ---------------------------------------------------------------- negative control
def negcontrol():
    md.apply_profile("hard")
    row = run_episode(UAVEnv(), make_policy("B6"), 7)
    md.apply_profile("default")
    ok = round(row["coverage_full"], 4) == 0.7206
    print(f"negative control: hard, old defaults, B6 seed 7 coverage_full = {row['coverage_full']:.6f} "
          f"({'equals' if ok else 'DIFFERS FROM'} 0.7206)")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "negcontrol.txt").write_text(f"{row['coverage_full']!r} {ok}\n", encoding="utf-8")


def report():
    L = []
    if (OUT / "phase1_episodes.csv").exists():
        L += phase1_table()
    if (OUT / "headroom_episodes.csv").exists():
        L += headroom_table()
    if (OUT / "negcontrol.txt").exists():
        L += ["Negative control (hard, old defaults, B6 seed 7): " + (OUT / "negcontrol.txt").read_text().strip()]
    text = "\n".join(L)
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["phase1", "headroom", "negcontrol", "report"])
    ap.add_argument("--seeds", default="0-19")
    a = ap.parse_args()
    if a.cmd == "phase1":
        phase1()
    elif a.cmd == "headroom":
        headroom(orc.parse_seeds(a.seeds))
    elif a.cmd == "negcontrol":
        negcontrol()
    else:
        report()


if __name__ == "__main__":
    sys.exit(main())
