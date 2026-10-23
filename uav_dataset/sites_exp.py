"""D-52 scenario redesign, phases 1-2 (pre-registered; do not change the grid, the baselines or the pass mark).

    python sites_exp.py phase1            # B8 on `hard`, 12 and 13 Wh, acceleration limit on (a_max 4), 100 scenarios
    python sites_exp.py headroom --seeds 0-19      # energy-free headroom on the 9 design cells (sites_d*_t* profiles)
    python sites_exp.py confirm           # phase 4: all 9 cells on FRESH seeds 1000-1019, B6, B7, B8, B6fc (unannounced
                                          # and announced), dp, teleport; the phase-2 passing cells also at 13 Wh
    python sites_exp.py confirm --shard 0/3   # (and 1/3, 2/3 in two more processes) the remaining jobs in 3 shards
    python sites_exp.py merge             # shards -> confirm_episodes.csv (checks: no gaps, duplicates agree)
    python sites_exp.py screencheck       # B6fc screened (as in phase 4) vs its full rule, on 4 design scenarios
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

import baselines as bl
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
    """Append rows to a CSV, in the column order of its header (rows with fewer columns get empty cells; a column the
    header does not have is an error, never a silent shift)."""
    df = pd.DataFrame(rows)
    if csv.exists():
        head = list(pd.read_csv(csv, nrows=0).columns)
        extra = set(df.columns) - set(head)
        assert not extra, f"columns not in {csv.name}: {sorted(extra)}"
        df = df.reindex(columns=head)
    df.to_csv(csv, mode="a", header=not csv.exists(), index=False)


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


# ---------------------------------------------------------------- phase 4: confirmation on fresh seeds
CONFIRM_SEEDS = list(range(1000, 1020))      # D-52 phase 4: fresh (design 0-11, val 100-119, test 120-139, RL 10000+)
PHASE2_PASS = [c for c in CELLS if c not in ("sites_d10_t60", "sites_d10_t180")]     # D-53: the 7 that passed
LOW_WH = 13.0                                # pre-registered battery repeat (12-13 Wh)
_LOW = f"_{LOW_WH:g}wh"                      # column suffix of the 13 Wh runs
PILOTS = ("B6", "B7", "B8", "B6fc_u", "B6fc_a")      # B6fc_u / _a: the scenario's event unannounced / announced
SCREEN_TOP = 100                             # b6fc.screen_top for phase 4 (run time; agreement with the full rule in
                                             # the report: `python sites_exp.py screencheck`)


def run_pilot(env, name, seed):
    """Replay one pilot (or B6fc with the announcement flag set for this run); returns per-step coverage, steps."""
    ann = {"B6fc_u": False, "B6fc_a": True}.get(name)
    if ann is not None:
        md.CFG["sites"]["announced"] = ann              # read by make_scenario at env.reset (only feeds B6fc here)
    pol = make_policy("B6fc" if ann is not None else name)
    c, steps = orc.episode_coverage(env, pol, seed)
    if ann is not None:
        assert bool(env.sc["announced"]) == ann
        md.CFG["sites"]["announced"] = md.BASE_CFG["sites"]["announced"]
    return c, steps


def confirm_one(cell, seed, batteries):
    """One fresh scenario of one cell: teleport bound, dp (energy-free plan, replayed with the real battery) and the
    5 simple pilots, at every battery in `batteries`. Returns one row."""
    md.apply_profile(cell)
    md.CFG["b6fc"]["screen_top"] = SCREEN_TOP
    t0 = time.time()
    env = UAVEnv()
    env.reset(seed=seed)
    sc = dict(env.sc)
    nodes = orc.oracle_nodes(env)
    cov = shared_tensor(env, nodes)
    tensor_backed(env, nodes, cov)
    t_tensor = time.time() - t0
    S = orc.segment_scores(cov)
    value, _, target, _ = orc.dp_plan(S, orc.hop_graph(nodes, len(nodes) - 1), len(nodes) - 1)
    row = dict(cell=cell, seed=seed, distance_m=sc["distance_m"], tau_s=sc["tau_s"], n_users=sc["n_users"],
               n_sites=sc["n_sites"], t0_s=sc["event_t0_s"], share=sc["event_share"], access=env.access,
               teleport=float(S.max(axis=1).mean()), dp_model=value / S.shape[0], secs_tensor=t_tensor,
               screen_top=SCREEN_TOP)
    t_ev = int(sc["event_t0_s"])
    wh16 = md.CFG["energy"]["battery_wh"]
    for wh in (wh16, LOW_WH):                         # every row has every column (NaN = not run), in a fixed order
        env.battery_j = wh * 3600.0
        sfx = "" if wh == wh16 else f"_{wh:g}wh"
        for name in (*PILOTS, "dp"):
            if wh not in batteries:
                for k in ("", "_survived", "_pre", "_post"):
                    row[f"{name}{sfx}{k}"] = np.nan
                row[f"secs_{name}{sfx}"] = np.nan
                continue
            t1 = time.time()
            if name == "dp":
                c, steps = orc.episode_coverage(env, orc.PlanPolicy(nodes, target, "dp"), seed)
            else:
                c, steps = run_pilot(env, name, seed)
            row[f"{name}{sfx}"] = float(c.mean())
            row[f"{name}{sfx}_survived"] = bool(steps >= env.T)
            row[f"{name}{sfx}_pre"], row[f"{name}{sfx}_post"] = float(c[:t_ev].mean()), float(c[t_ev:].mean())
            row[f"secs_{name}{sfx}"] = time.time() - t1
    row["secs_total"] = time.time() - t0
    md.apply_profile("default")
    return row


def _done(csv):
    if not csv.exists():
        return set()
    old = pd.read_csv(csv)
    return set(zip(old.cell, old.seed, strict=True))


def shard_seeds(seeds, n_shards, done):
    """Deterministic, disjoint split of the seeds that still have jobs into n_shards lists, balanced by crowd size
    (the run time grows with the number of users): largest crowd first, each to the least-loaded shard (ties: lowest
    shard). A seed is never split, so the tensor rows and forecasts shared between its cells stay in one process."""
    md.apply_profile(CELLS[0])
    size = {s: md.make_scenario(s)["n_users"] for s in seeds}          # the same in every cell (paired cells)
    md.apply_profile("default")
    left = [s for s in seeds if any((c, s) not in done for c in CELLS)]
    shards, load = [[] for _ in range(n_shards)], [0] * n_shards
    for s in sorted(left, key=lambda s: (-size[s], s)):
        k = min(range(n_shards), key=lambda k: (load[k], k))
        shards[k].append(s)
        load[k] += size[s]
    return [sorted(x) for x in shards]


def confirm(seeds, low_cells, shard=None):
    """shard = (k, n): run only shard k of n (shard_seeds over the jobs not yet in confirm_episodes.csv), writing
    confirm_episodes_shard{k}.csv; `merge` combines them. Scheduling only: every row is computed exactly as in one
    process (the shared rows and forecasts are exact reuse of identical inputs, kept within one seed)."""
    OUT.mkdir(parents=True, exist_ok=True)
    main = OUT / "confirm_episodes.csv"
    done = _done(main)
    csv = main
    if shard is not None:
        k, n = shard
        seeds = shard_seeds(seeds, n, done)[k]
        csv = OUT / f"confirm_episodes_shard{k}.csv"
        done |= _done(csv)
    jobs = [(c, s) for s in seeds for c in CELLS if (c, s) not in done]      # seed-major; cells D-major (memo)
    print(f"confirm: {len(jobs)} scenarios to run ({len(CELLS)} cells; {LOW_WH:g} Wh also on {len(low_cells)}), "
          f"1 process{'' if shard is None else f', shard {shard[0]} of {shard[1]}, seeds {seeds}'}", flush=True)
    t0, last = time.time(), None
    for i, (c, s) in enumerate(jobs, 1):
        D = md.BASE_CFG["profiles"][c]["sites"]["distance_m"]
        if (s, D) != last:                     # rows / forecasts are shared only within one seed and one distance
            _ROWS.clear()
            bl.FC_MEMO = {}
            last = (s, D)
        md.apply_profile(c)
        wh16 = md.CFG["energy"]["battery_wh"]
        row = confirm_one(c, s, (wh16, LOW_WH) if c in low_cells else (wh16,))
        append(csv, [row])
        print(f"  {i}/{len(jobs)} {c} seed {s}: " + " ".join(f"{p} {row[p]:.3f}" for p in (*PILOTS, "dp"))
              + f"  {row['secs_total']:.0f}s (total {(time.time() - t0) / 60:.1f} min)", flush=True)
    bl.FC_MEMO = None


def merge(seeds, low_cells):
    """Merge the shard files into confirm_episodes.csv (the old file is kept as confirm_episodes_premerge.csv).
    Duplicated (cell, seed) rows must agree on every result column; every (cell, seed) must be present, with the
    13 Wh columns for the low cells."""
    main = OUT / "confirm_episodes.csv"
    rt = dict(float_precision="round_trip")           # exact floats (the default parser can be 1 ulp off)
    parts = [pd.read_csv(main, **rt)] + [pd.read_csv(f, **rt) for f in sorted(OUT.glob("confirm_episodes_shard*.csv"))]
    cols = list(parts[0].columns)
    df = pd.concat([p.reindex(columns=cols) for p in parts], ignore_index=True)
    res = [c for c in cols if not c.startswith("secs")]
    for _, g in df.groupby(["cell", "seed"]):
        if len(g) > 1:
            a = g[res].iloc[0]
            for i in range(1, len(g)):
                b = g[res].iloc[i]
                same = all((pd.isna(x) and pd.isna(y)) or x == y for x, y in zip(a, b, strict=True))
                assert same, f"different duplicate rows for {g.cell.iloc[0]} seed {g.seed.iloc[0]}"
    df = df.drop_duplicates(["cell", "seed"], keep="first")
    missing = [(c, s) for c in CELLS for s in seeds if not ((df.cell == c) & (df.seed == s)).any()]
    assert not missing, f"missing rows: {missing}"
    for c in low_cells:
        assert df.loc[(df.cell == c) & df.seed.isin(seeds), f"B6{_LOW}"].notna().all(), f"13 Wh missing in {c}"
    main.replace(OUT / "confirm_episodes_premerge.csv")
    df.sort_values(["seed", "cell"]).to_csv(main, index=False)
    print(f"merged {len(parts)} files: {len(df)} rows ({len(CELLS)} cells x {len(seeds)} seeds)")


SCREEN_CASES = [("sites_d15_t0", 11), ("sites_d20_t60", 1), ("sites_d10_t180", 6), ("sites_d15_t60", 9)]   # design
#   seeds (not the fresh ones) with 100-300 users, so the full rule stays affordable


def screencheck():
    """B6fc with the full rule vs with screen_top = SCREEN_TOP, both announcement variants, on SCREEN_CASES: share of
    identical decisions and the coverage of each. Written to screencheck.csv (shown by `report`)."""
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for cell, seed in SCREEN_CASES:
        for ann in (False, True):
            res = {}
            for top in (None, SCREEN_TOP):
                md.apply_profile(cell)
                md.CFG["sites"]["announced"] = ann
                md.CFG["b6fc"]["screen_top"] = top
                env = UAVEnv()
                env.reset(seed=seed)
                pol = make_policy("B6fc")
                pol.reset(env)
                targets, cov, t1, done = [], [], time.time(), False
                while not done:
                    a = pol.act(env)
                    if env.t % orc.decision_steps() == 0:
                        targets.append(pol.target)
                    _, _, term, trunc, info = env.step(a)
                    cov.append(info["coverage"])
                    done = term or trunc
                res[top] = (np.array(targets), float(np.sum(cov) / env.T), time.time() - t1)
            n = min(len(res[None][0]), len(res[SCREEN_TOP][0]))
            same = float((np.abs(res[None][0][:n] - res[SCREEN_TOP][0][:n]).max(axis=1) < 1e-9).mean())
            rows.append(dict(cell=cell, seed=seed, n_users=env.sc["n_users"], announced=ann, full=res[None][1],
                             screened=res[SCREEN_TOP][1], same_decisions=same, secs_full=res[None][2],
                             secs_screened=res[SCREEN_TOP][2]))
            print(rows[-1], flush=True)
    md.apply_profile("default")
    pd.DataFrame(rows).to_csv(OUT / "screencheck.csv", index=False)


def screencheck_table():
    d = pd.read_csv(OUT / "screencheck.csv")
    L = [f"### B6fc screening check (screen_top {SCREEN_TOP} vs the full rule; design seeds, not the fresh ones)", "",
         "| cell | seed | users | announced | full rule | screened | screened - full | same decisions | time full / "
         "screened s |", "|---|---|---|---|---|---|---|---|---|"]
    for r in d.itertuples():
        L.append(f"| {r.cell} | {r.seed} | {r.n_users} | {r.announced} | {r.full:.4f} | {r.screened:.4f} | "
                 f"{r.screened - r.full:+.4f} | {r.same_decisions:.0%} | {r.secs_full:.0f} / {r.secs_screened:.0f} |")
    L += ["", f"Mean screened - full: {(d.screened - d.full).mean():+.4f}; identical decisions "
          f"{d.same_decisions.mean():.0%} on average.", ""]
    return L


def _cell_stats(d, bar_pilots, dp_col="dp", sfx=""):
    """Per cell: means, the best simple pilot by cell mean, paired dp - best (mean, CI, p)."""
    means = {p: d[f"{p}{sfx}"].mean() for p in bar_pilots}
    best = max(bar_pilots, key=lambda p: means[p])
    m, h = paired_diff(d[f"{dp_col}{sfx}"], d[f"{best}{sfx}"])
    return means, best, m, h, paired_p(d[f"{dp_col}{sfx}"], d[f"{best}{sfx}"])


def confirm_table():
    df = pd.read_csv(OUT / "confirm_episodes.csv", float_precision="round_trip")
    v_max = md.BASE_CFG["uav"]["v_max_mps"]
    L = ["## Phase 4: confirmation on fresh scenarios (D-52), seeds "
         f"{df.seed.min()}-{df.seed.max()}", "",
         "Per cell: mean coverage_full (replayed through env.step, 300 s, a_max 4, noma_opt, sic_eps 0.05, rescue "
         "first). B6fc_u = B6fc with the event unannounced (velocity extrapolation only); B6fc_a = announced (also the "
         "announced A -> B schedule). dp = energy-free clairvoyant plan, replayed (the same plan in both variants). "
         "Bars (pre-registered, best by cell mean): unannounced = best of B6, B7, B8, B6fc_u; announced = best of B6, "
         "B7, B8, B6fc_u, B6fc_a. dp - bar paired over the cell's scenarios, mean +/- 95% CI, two-sided p, Holm over "
         f"the 9 cells within each variant. PASS (pre-registered): mean dp - bar >= {PASS_MARK:.2f}.", ""]
    variants = (("unannounced", ("B6", "B7", "B8", "B6fc_u")), ("announced", ("B6", "B7", "B8", "B6fc_u", "B6fc_a")))
    cells = [c for c in CELLS if (df.cell == c).any()]
    L += ["### Means per pilot (16 Wh)", "",
          "| cell | D km | tau s | transit s | n | B6 | B7 | B8 | B6fc_u | B6fc_a | dp | teleport |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cell in cells:
        d = df[df.cell == cell]
        D, tau = d.distance_m.iloc[0], d.tau_s.iloc[0]
        L.append(f"| {cell} | {D / 1000:.1f} | {tau:g} | {D / v_max:.0f} | {len(d)} | "
                 + " | ".join(f"{d[p].mean():.3f}" for p in (*PILOTS, "dp", "teleport")) + " |")
    for vname, bar in variants:
        stats = {c: _cell_stats(df[df.cell == c].sort_values("seed"), bar) for c in cells}
        hp = dict(zip(cells, holm([stats[c][4] for c in cells]), strict=True))
        L += ["", f"### Headroom, {vname} cells (bar = best of {', '.join(bar)})", "",
              "| cell | phase 2 | bar pilot | bar | dp | dp - bar (95% CI) | p | Holm p | dp - bar before / after t0 "
              "| pass (>= 0.02) |", "|---|---|---|---|---|---|---|---|---|---|"]
        for c in cells:
            d = df[df.cell == c]
            means, best, m, h, p = stats[c]
            pre, post = ((d[f"dp_{w}"] - d[f"{best}_{w}"]).mean() for w in ("pre", "post"))
            L.append(f"| {c} | {'pass' if c in PHASE2_PASS else 'fail'} | {best} | {means[best]:.3f} | "
                     f"{d.dp.mean():.3f} | {m:+.3f} +/- {h:.3f} | {p:.2g} | {hp[c]:.2g}{' *' if hp[c] < 0.05 else ''}"
                     f" | {pre:+.3f} / {post:+.3f} | {'PASS' if m >= PASS_MARK else 'no'} |")
    L += ["", "### How much of dp's lead over B6 does B6fc capture? (16 Wh)", "",
          "Share = (B6fc - B6) / (dp - B6), from the cell means; paired B6fc - B6 with 95% CI.", "",
          "| cell | dp - B6 | B6fc_u - B6 (95% CI) | share u | B6fc_a - B6 (95% CI) | share a | B6fc_a - B6fc_u |",
          "|---|---|---|---|---|---|---|"]
    for c in cells:
        d = df[df.cell == c].sort_values("seed")
        lead = (d.dp - d.B6).mean()
        (mu, hu), (ma, ha) = paired_diff(d.B6fc_u, d.B6), paired_diff(d.B6fc_a, d.B6)
        L.append(f"| {c} | {lead:+.3f} | {mu:+.3f} +/- {hu:.3f} | {mu / lead:.0%} | {ma:+.3f} +/- {ha:.3f} | "
                 f"{ma / lead:.0%} | {(d.B6fc_a - d.B6fc_u).mean():+.3f} |")
    low = [c for c in cells if f"B6{_LOW}" in df and df.loc[df.cell == c, f"B6{_LOW}"].notna().all()]
    if low:
        L += ["", f"### Battery repeat at {LOW_WH:g} Wh (pre-registered: passing cells repeated at 12-13 Wh)", "",
              "Same scenarios. dp = the energy-free plan replayed with the small battery: if it dies, the room is only "
              "a LOWER bound (an energy-aware DP was NOT built). Bars as above.", "",
              "| cell | B6 | B7 | B8 | B6fc_u | B6fc_a | dp | dp survived | unann. bar | dp - bar (95% CI) | "
              "ann. bar | dp - bar (95% CI) | pass u / a |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in low:
            d = df[df.cell == c].sort_values("seed")
            cells_txt = []
            passes = []
            for _, bar in variants:
                means, best, m, h, _ = _cell_stats(d, bar, sfx=_LOW)
                cells_txt += [f"{best} {means[best]:.3f}", f"{m:+.3f} +/- {h:.3f}"]
                passes.append("PASS" if m >= PASS_MARK else "no")
            L.append(f"| {c} | " + " | ".join(f"{d[p + _LOW].mean():.3f}" for p in (*PILOTS, "dp"))
                     + f" | {d['dp' + _LOW + '_survived'].mean():.0%} | " + " | ".join(cells_txt)
                     + f" | {' / '.join(passes)} |")
        surv = ", ".join(f"{p} {df[p + _LOW + '_survived'].dropna().mean():.0%}" for p in (*PILOTS, "dp"))
        L += ["", f"Survival at {LOW_WH:g} Wh (share of scenarios lasting 300 s): {surv}."]
    surv16 = ", ".join(f"{p} {df[p + '_survived'].mean():.0%}" for p in (*PILOTS, "dp"))
    L += ["", f"Survival at 16 Wh: {surv16}.",
          f"Run time: {df.secs_total.sum() / 60:.0f} min for {len(df)} scenarios ({df.secs_total.mean():.0f} s each; "
          f"tensor {df.secs_tensor.mean():.0f} s, B6fc_u {df.secs_B6fc_u.mean():.0f} s, "
          f"B6fc_a {df.secs_B6fc_a.mean():.0f} s).", ""]
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
    if (OUT / "confirm_episodes.csv").exists():
        L += confirm_table()
    if (OUT / "screencheck.csv").exists():
        L += screencheck_table()
    if (OUT / "negcontrol.txt").exists():
        L += ["Negative control (hard, old defaults, B6 seed 7): " + (OUT / "negcontrol.txt").read_text().strip()]
    text = "\n".join(L)
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["phase1", "headroom", "confirm", "merge", "screencheck", "negcontrol", "report"])
    ap.add_argument("--seeds", default=None, help="headroom default 0-19; confirm default 1000-1019")
    ap.add_argument("--low-cells", default="phase2", help="confirm: cells repeated at 13 Wh: phase2 (the 7 that "
                    "passed phase 2), none, or a comma list of cell names")
    ap.add_argument("--shard", default=None, help="confirm: k/n = run shard k (0-based) of n in this process")
    a = ap.parse_args()
    if a.cmd == "phase1":
        phase1()
    elif a.cmd == "headroom":
        headroom(orc.parse_seeds(a.seeds or "0-19"))
    elif a.cmd in ("confirm", "merge"):
        low = {"phase2": PHASE2_PASS, "none": []}.get(a.low_cells) or a.low_cells.split(",")
        seeds = orc.parse_seeds(a.seeds or "1000-1019")
        if a.cmd == "merge":
            merge(seeds, low)
        else:
            confirm(seeds, low, tuple(int(x) for x in a.shard.split("/")) if a.shard else None)
    elif a.cmd == "screencheck":
        screencheck()
    elif a.cmd == "negcontrol":
        negcontrol()
    else:
        report()


if __name__ == "__main__":
    sys.exit(main())
