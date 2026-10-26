"""The anticipation rule (pre-registered: docs/prereg/anticipation_rule.md). When can thinking ahead beat greedy
re-planning for a UAV base station? Headroom h = clairvoyant plan (dp) minus the best simple pilot, predicted from
two numbers of a scenario family: A = (T_tr + 10) / (tau + 10) and M = T_tr / T_episode, with
T_tr = max(0, D - 2 rho) / v_max (time in transit between the two sites' footprints).

    python anticip_exp.py footprint                 # rho per cell (design seeds 0-19, t = 0) -> footprint.csv
    python anticip_exp.py oldcells --shard 0/4      # B6dep (+ B6 check) on the 9 D-52 cells, fresh seeds 1000-1019
    python anticip_exp.py merge old                 # shards -> oldcells_episodes.csv (gaps / duplicates checked)
    python anticip_exp.py fit --confirm <confirm_episodes.csv>   # fit on the 9 cells, predictions for the 8 new ones
    python anticip_exp.py newcells --shard 0/4      # the 8 new cells, seeds 2000-2019 (dp, B6, B6fc u/a, B6dep)
    python anticip_exp.py merge new
    python anticip_exp.py evaluate                  # pre-registered criteria, tables, figure -> results/anticipation/
Every finished scenario is appended to a CSV, so an interrupted run resumes. Shards split the seeds (never a seed),
so rows shared between the cells of one seed (coverage tensor, B6's lattice rows, B6fc forecasts) stay in one process.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import baselines as bl
import make_dataset as md
import oracle as orc
import sites_exp
from baselines import make_policy
from evalstats import paired_diff, paired_p
from uav_env import UAVEnv

OUT = Path(__file__).parent / "results" / "anticipation"
OLD_CELLS = list(sites_exp.CELLS)                     # the 9 D-52 cells (fit set)
OLD_SEEDS = list(range(1000, 1020))                   # their fresh seeds (D-52 phase 4)
NEW_CELLS = ["sites_v8_d15_t60", "sites_v25_d15_t60", "sites_v8_d20_t0", "sites_v25_d20_t0",
             "sites_T600_d20_t0", "sites_T600_d15_t60", "sites_d175_t30", "sites_d125_t120"]   # test set (prereg)
NEW_SEEDS = list(range(2000, 2012))                   # fresh, disjoint from every earlier seed set
                                                      # (12: owner, before any run)
FOOT_SEEDS = list(range(20))                          # design seeds: rho is a property of the physics, not an outcome
DECISION_S = 10.0                                     # the decision period (baselines.replan_every_steps x dt)
PASS_MARK = sites_exp.PASS_MARK                       # 0.02
SCREEN_TOP = sites_exp.SCREEN_TOP                     # B6fc screening, as in D-52 phase 4
OLD_PILOTS = ("B6", "B7", "B8", "B6fc_u", "B6fc_a")   # columns of the phase-4 file
NEW_PILOTS = ("B6", "B6fc_u", "B6fc_a", "B6dep")
BAR_ANN_OLD = (*OLD_PILOTS, "B6dep")                  # announced bar (pre-registered)
BAR_ANN_NEW = NEW_PILOTS
BAR_UNANN_OLD = ("B6", "B7", "B8", "B6fc_u")
BAR_UNANN_NEW = ("B6", "B6fc_u")


# ---------------------------------------------------------------- pilots
ANN = {"B6fc_u": ("B6fc", False), "B6fc_a": ("B6fc", True), "B6dep": ("B6dep", True)}


def run_pilot(env, name, seed):
    """Replay one pilot with this run's announcement flag (B6fc_u / B6fc_a / B6dep announced; the others ignore it).
    Returns per-step coverage and the steps flown."""
    pol_name, ann = ANN.get(name, (name, None))
    if ann is not None:
        md.CFG["sites"]["announced"] = ann
    try:
        c, steps = orc.episode_coverage(env, make_policy(pol_name), seed)
        if ann is not None:
            assert bool(env.sc["announced"]) == ann
    finally:
        md.CFG["sites"]["announced"] = md.BASE_CFG["sites"]["announced"]
    return c, steps


_LAT = {}           # B6 lattice rows by their exact inputs (one seed at a time)


def memo_backed(env):
    """Make env.evaluate answer B6's lattice calls (B6's 980 candidates in oracle_nodes order + extra candidates) from a
    memo of lattice rows keyed by their exact inputs (the active users at t, obstacles, nodes, radio settings), so B6
    and B6dep's own B6 step compute every row once, and the cells of one seed share rows with identical inputs. The
    same numbers as the real evaluate (row-independent for the QoS schemes and extreme pairing; test). Returns the
    real evaluate."""
    plain = env.evaluate
    if not (env.access in md.QOS_SCHEMES or env.sc["pairing"] == "extreme"):
        return plain
    lat = orc.oracle_nodes(env)[:-1]
    n = len(lat)
    p_ref = env.p_max_w * md.CFG["baselines"]["power_frac"]

    def evaluate(X, Y, H, p_w, t=None):
        tt = env.t if t is None else int(t)
        X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
        if (p_w == p_ref and len(X) >= n and np.array_equal(X[:n], lat[:, 0]) and np.array_equal(Y[:n], lat[:, 1])
                and np.array_equal(H[:n], lat[:, 2])):
            xy, mr, rs = env.users_now(tt)
            blob = b"".join(np.ascontiguousarray(a).tobytes() for a in (xy, mr, rs, env.boxes, lat))
            blob += repr((tt, p_w, env.access, env.sic_eps, env.rescue_first, env.sc["bandwidth_hz"],
                          env.sc["pairing"], env.scenario_seed)).encode()
            key = hashlib.sha1(blob).hexdigest()
            if key not in _LAT:
                _LAT[key] = plain(lat[:, 0], lat[:, 1], lat[:, 2], p_w, t=tt)
            head = _LAT[key].copy()
            return np.concatenate([head, plain(X[n:], Y[n:], H[n:], p_w, t=tt)]) if len(X) > n else head
        return plain(X, Y, H, p_w, t=t)

    env.evaluate = evaluate
    return plain


# ---------------------------------------------------------------- footprint radius rho
FOOT_R = np.arange(0.0, 1500.0 + 1e-9, 10.0)          # offsets tried (m)
FOOT_DIRS = 8


def footprint_one(cell, seed):
    """rho for one scenario: the drone over site A's centre at the altitude level (of B6's) that serves the most of
    A's users at t = 0; coverage of A's active users (all active users present, the cell's physics: power, access
    scheme, obstacles, bandwidth) as the drone moves r metres away, averaged over 8 directions; rho = the smallest r
    at which it falls to half its value at r = 0 (linear interpolation between the 10 m steps)."""
    md.apply_profile(cell)
    env = UAVEnv()
    env.reset(seed=seed)
    xy, mr, rs = env.users_now(0)
    cid = env.users["cluster_id"].values
    m = env.active_mask(0)
    inA = (cid[m] if m is not None else cid) == 0
    cA = np.array([env.sc["site_x"][0], env.sc["site_y"][0]])
    p_w = env.p_max_w * md.CFG["baselines"]["power_frac"]

    def cov_A(X, Y, H):
        gains = md.channel_gain(xy[:, 0], xy[:, 1], X, Y, H, env.boxes)
        served = env.access_rates(gains, p_w, return_info=True, min_rate=mr, rescue=rs)[1]["served"]
        return served[:, inA].mean(axis=1)

    levels = np.array(md.CFG["baselines"]["altitude_levels_m"], dtype=float)
    c0 = cov_A(np.full(len(levels), cA[0]), np.full(len(levels), cA[1]), levels)
    j = int(np.argmax(c0))
    ang = 2 * np.pi * np.arange(FOOT_DIRS) / FOOT_DIRS
    R, AN = np.meshgrid(FOOT_R, ang, indexing="ij")
    c = cov_A((cA[0] + R * np.cos(AN)).ravel(), (cA[1] + R * np.sin(AN)).ravel(),
              np.full(R.size, levels[j])).reshape(R.shape).mean(axis=1)
    half = c[0] / 2.0
    below = np.flatnonzero(c <= half)
    if c[0] <= 0 or not len(below):
        rho = np.nan
    else:
        k = int(below[0])
        rho = float(FOOT_R[k - 1] + (c[k - 1] - half) / (c[k - 1] - c[k]) * (FOOT_R[k] - FOOT_R[k - 1])) if k else 0.0
    md.apply_profile("default")
    return dict(cell=cell, seed=seed, n_users=env.sc["n_users"], n_A=int(inA.sum()), h_star=float(levels[j]),
                cov_A0=float(c[0]), rho_m=rho)


def footprint(cells):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [footprint_one(c, s) for c in cells for s in FOOT_SEEDS]
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "footprint.csv", index=False)
    print(df.groupby("cell").rho_m.describe().round(1).to_string())


def cell_params(cell, rho):
    """D, tau, v_max, T (s) of a cell's profile and the rule's numbers A, M."""
    md.apply_profile(cell)
    D, tau = float(md.CFG["sites"]["distance_m"]), float(md.CFG["sites"]["tau_s"])
    v, T = float(md.CFG["uav"]["v_max_mps"]), md.CFG["mobility"]["episode_steps"] * md.CFG["energy"]["dt_s"]
    md.apply_profile("default")
    t_tr = max(0.0, D - 2.0 * rho) / v
    return dict(D_m=D, tau_s=tau, v_max=v, T_s=T, rho_m=rho, T_tr_s=t_tr, A=(t_tr + DECISION_S) / (tau + DECISION_S),
                M=t_tr / T)


# ---------------------------------------------------------------- runs
def _done(csv):
    if not csv.exists():
        return set()
    old = pd.read_csv(csv)
    return set(zip(old.cell, old.seed, strict=True))


def shard_seeds(seeds, cells, n_shards, done):
    """Deterministic, disjoint split of the seeds that still have jobs, balanced by crowd size (largest first, each to
    the least-loaded shard; ties: lowest shard). A seed is never split."""
    md.apply_profile(cells[0])
    size = {s: md.make_scenario(s)["n_users"] for s in seeds}
    md.apply_profile("default")
    left = [s for s in seeds if any((c, s) not in done for c in cells)]
    shards, load = [[] for _ in range(n_shards)], [0] * n_shards
    for s in sorted(left, key=lambda s: (-size[s], s)):
        k = min(range(n_shards), key=lambda k: (load[k], k))
        shards[k].append(s)
        load[k] += size[s]
    return [sorted(x) for x in shards]


def oldcell_one(cell, seed):
    """B6dep (announced) and B6 (a check against the phase-4 file) on one fresh scenario of a D-52 cell."""
    md.apply_profile(cell)
    t0 = time.time()
    env = UAVEnv()
    env.reset(seed=seed)
    memo_backed(env)
    sc = dict(env.sc)
    row = dict(cell=cell, seed=seed, n_users=sc["n_users"], t0_s=sc["event_t0_s"])
    t_ev = int(sc["event_t0_s"])
    for name in ("B6", "B6dep"):
        t1 = time.time()
        c, steps = run_pilot(env, name, seed)
        row[name] = float(c.mean())
        row[f"{name}_survived"] = bool(steps >= env.T)
        row[f"{name}_pre"], row[f"{name}_post"] = float(c[:t_ev].mean()), float(c[t_ev:].mean())
        row[f"secs_{name}"] = time.time() - t1
    row["secs_total"] = time.time() - t0
    md.apply_profile("default")
    return row


def newcell_one(cell, seed):
    """One fresh scenario of a new cell: teleport bound, dp (energy-free plan, replayed with the cell's battery and
    acceleration limit) and B6, B6fc_u, B6fc_a, B6dep (replayed; B6's lattice served from the coverage tensor)."""
    md.apply_profile(cell)
    md.CFG["b6fc"]["screen_top"] = SCREEN_TOP
    t0 = time.time()
    env = UAVEnv()
    env.reset(seed=seed)
    sc = dict(env.sc)
    nodes = orc.oracle_nodes(env)
    cov = sites_exp.shared_tensor(env, nodes)
    sites_exp.tensor_backed(env, nodes, cov)
    t_tensor = time.time() - t0
    S = orc.segment_scores(cov)
    value, _, target, _ = orc.dp_plan(S, orc.hop_graph(nodes, len(nodes) - 1), len(nodes) - 1)
    row = dict(cell=cell, seed=seed, distance_m=sc["distance_m"], tau_s=sc["tau_s"], n_users=sc["n_users"],
               n_sites=sc["n_sites"], t0_s=sc["event_t0_s"], share=sc["event_share"], access=env.access,
               v_max=env.uav["v_max_mps"], T_s=env.T * env.dt, battery_wh=env.battery_j / 3600.0,
               teleport=float(S.max(axis=1).mean()), dp_model=value / S.shape[0], secs_tensor=t_tensor,
               screen_top=SCREEN_TOP)
    t_ev = int(sc["event_t0_s"])
    for name in (*NEW_PILOTS, "dp"):
        t1 = time.time()
        if name == "dp":
            c, steps = orc.episode_coverage(env, orc.PlanPolicy(nodes, target, "dp"), seed)
        else:
            c, steps = run_pilot(env, name, seed)
        row[name] = float(c.mean())
        row[f"{name}_survived"] = bool(steps >= env.T)
        row[f"{name}_pre"], row[f"{name}_post"] = float(c[:t_ev].mean()), float(c[t_ev:].mean())
        row[f"secs_{name}"] = time.time() - t1
    row["secs_total"] = time.time() - t0
    md.apply_profile("default")
    return row


def run_cells(kind, shard=None, only=None):
    """kind 'old' (B6dep on the 9 D-52 cells) or 'new' (the 8 new cells); only = a subset of those cells (one Kaggle
    kernel per subset). Seed-major; all cells of a seed in one process, rows shared only within a seed."""
    OUT.mkdir(parents=True, exist_ok=True)
    cells, seeds, one = (OLD_CELLS, OLD_SEEDS, oldcell_one) if kind == "old" else (NEW_CELLS, NEW_SEEDS, newcell_one)
    if only:
        assert set(only) <= set(cells), f"unknown cells {sorted(set(only) - set(cells))}"
        cells = [c for c in cells if c in only]
    tag = "" if not only else "_" + hashlib.sha1(",".join(cells).encode()).hexdigest()[:6]
    main = OUT / f"{kind}cells_episodes.csv"
    done, csv = _done(main), main
    if shard is not None:
        k, n = shard
        seeds = shard_seeds(seeds, cells, n, done)[k]
        csv = OUT / f"{kind}cells_episodes{tag}_shard{k}.csv"
        done |= _done(csv)
    jobs = [(c, s) for s in seeds for c in cells if (c, s) not in done]
    print(f"{kind} cells: {len(jobs)} scenarios to run"
          f"{'' if shard is None else f', shard {shard[0]} of {shard[1]}, seeds {seeds}'}", flush=True)
    t0, last = time.time(), None
    for i, (c, s) in enumerate(jobs, 1):
        if s != last:
            _LAT.clear()
            sites_exp._ROWS.clear()
            bl.FC_MEMO = {}
            last = s
        row = one(c, s)
        sites_exp.append(csv, [row])
        pil = ("B6", "B6dep") if kind == "old" else (*NEW_PILOTS, "dp")
        print(f"  {i}/{len(jobs)} {c} seed {s}: " + " ".join(f"{p} {row[p]:.4f}" for p in pil)
              + f"  {row['secs_total']:.0f}s (total {(time.time() - t0) / 60:.1f} min)", flush=True)
    bl.FC_MEMO = None


def merge(kind):
    """Shard files -> {kind}cells_episodes.csv. Duplicated (cell, seed) rows must agree on every result column;
    every (cell, seed) must be present."""
    cells, seeds = (OLD_CELLS, OLD_SEEDS) if kind == "old" else (NEW_CELLS, NEW_SEEDS)
    main = OUT / f"{kind}cells_episodes.csv"
    rt = dict(float_precision="round_trip")
    files = ([main] if main.exists() else []) + sorted(OUT.glob(f"{kind}cells_episodes*_shard*.csv"))
    parts = [pd.read_csv(f, **rt) for f in files]
    cols = list(parts[0].columns)
    df = pd.concat([p.reindex(columns=cols) for p in parts], ignore_index=True)
    res = [c for c in cols if not c.startswith("secs")]
    for _, g in df.groupby(["cell", "seed"]):
        for i in range(1, len(g)):
            same = all((pd.isna(x) and pd.isna(y)) or x == y
                       for x, y in zip(g[res].iloc[0], g[res].iloc[i], strict=True))
            assert same, f"different duplicate rows for {g.cell.iloc[0]} seed {g.seed.iloc[0]}"
    df = df.drop_duplicates(["cell", "seed"], keep="first")
    missing = [(c, s) for c in cells for s in seeds if not ((df.cell == c) & (df.seed == s)).any()]
    assert not missing, f"missing rows: {missing}"
    df.sort_values(["seed", "cell"]).to_csv(main, index=False)
    print(f"merged {len(files)} files: {len(df)} rows ({len(cells)} cells x {len(seeds)} seeds)")


# ---------------------------------------------------------------- the models (pre-registered candidates + selection)
H_FLOOR = 1e-3      # loglin: h below this is set to it before taking logs (pre-registered; h is a mean of differences)


def model_h(k, A, M):
    """Candidate 'ratio': h = k * M * A / (1 + A). Monotone increasing in A and in M; h -> 0 when the transit vanishes
    (M = 0) and h -> k M when the switch is much faster than the transit (A >> 1)."""
    A, M = np.asarray(A, dtype=float), np.asarray(M, dtype=float)
    return k * M * A / (1.0 + A)


def fit_k(A, M, h):
    """Least-squares k (closed form) for the 'ratio' candidate."""
    g = M * A / (1.0 + A)
    return float(np.dot(g, h) / np.dot(g, g))


def fit_loglin(A, M, h):
    """Candidate 'loglin': log h = a + b log A + c M (ordinary least squares on log max(h, H_FLOOR));
    h = e^a A^b e^(cM). Monotone (increasing) only if b >= 0 and c >= 0."""
    X = np.column_stack([np.ones(len(A)), np.log(A), M])
    coef, *_ = np.linalg.lstsq(X, np.log(np.maximum(h, H_FLOOR)), rcond=None)
    return [float(v) for v in coef]


def pred_loglin(p, A, M):
    a, b, c = p
    return np.exp(a + b * np.log(np.asarray(A, dtype=float)) + c * np.asarray(M, dtype=float))


POW_P = np.round(np.arange(0.05, 2.0001, 0.01), 2)        # power: exponent grids (pre-registered)
POW_Q = np.round(np.arange(0.0, 2.0001, 0.01), 2)


def pred_power(p, A, M):
    a, pm, q = p
    A, M = np.asarray(A, dtype=float), np.asarray(M, dtype=float)
    return a * np.power(M, pm) * np.power(A / (1.0 + A), q)


def fit_power(A, M, h):
    """Candidate 'power': h = a * M^p * (A / (1 + A))^q, p in [0.05, 2], q in [0, 2] (grid, step 0.01), a by least
    squares (closed form) for each (p, q); the (p, q) with the smallest squared error (ties: first in grid order).
    Monotone increasing in A and M for a >= 0; h = 0 when M = 0."""
    best = None
    for pm in POW_P:
        Mp = np.power(M, pm)
        for q in POW_Q:
            g = Mp * np.power(A / (1.0 + A), q)
            gg = float(np.dot(g, g))
            a = float(np.dot(g, h) / gg) if gg > 0 else 0.0
            sse = float(np.sum((h - a * g) ** 2))
            if best is None or sse < best[0] - 1e-18:
                best = (sse, [a, float(pm), float(q)])
    return best[1]


MODELS = {          # name -> (fit(A, M, h) -> params, predict(params, A, M), monotone(params))
    "ratio": (lambda A, M, h: [fit_k(A, M, h)], lambda p, A, M: model_h(p[0], A, M), lambda p: p[0] >= 0),
    "power": (fit_power, pred_power, lambda p: p[0] >= 0),
    "loglin": (fit_loglin, pred_loglin, lambda p: p[1] >= 0 and p[2] >= 0),
}
# loglin is reported but NOT selectable: on the fit cells it won the leave-one-out comparison against 'ratio', but its
# exp(c M) term extrapolates to h = 0.31 on a test cell with M twice the fit range (seen BEFORE any new-cell run; the
# candidate set was then fixed as below; docs/prereg/anticipation_rule.md section 4).
SELECTABLE = ("ratio", "power")


def loo_rmse(name, A, M, h):
    """Leave-one-out RMSE of a candidate on the fit cells (each cell predicted by the model fitted on the other 8)."""
    f, pr, _ = MODELS[name]
    err = []
    for i in range(len(h)):
        m = np.arange(len(h)) != i
        err.append(pr(f(A[m], M[m], h[m]), A[i:i + 1], M[i:i + 1])[0] - h[i])
    return float(np.sqrt(np.mean(np.square(err))))


def r2(pred, meas):
    """Coefficient of determination of the predictions: 1 - SS_res / SS_tot (SS_tot about the measured mean)."""
    pred, meas = np.asarray(pred, dtype=float), np.asarray(meas, dtype=float)
    return float(1.0 - np.sum((meas - pred) ** 2) / np.sum((meas - meas.mean()) ** 2))


def headroom_table(df, cells, bar):
    """Per cell: bar pilot (best by cell mean), h = paired mean dp - bar, its 95% CI, p, and the pilots' means."""
    rows = []
    for c in cells:
        d = df[df.cell == c].sort_values("seed")
        means = {p: d[p].mean() for p in bar}
        best = max(bar, key=lambda p: means[p])
        m, hw = paired_diff(d.dp, d[best])
        rows.append(dict(cell=c, n=len(d), bar_pilot=best, bar=means[best], dp=d.dp.mean(), h=m, h_ci=hw,
                         p=paired_p(d.dp, d[best]), **{f"mean_{p}": means[p] for p in bar}))
    return pd.DataFrame(rows)


def old_data(confirm_csv):
    """The 9 fit cells: phase-4 rows (seeds 1000-1019) joined with this run's B6dep rows (checked: B6 identical)."""
    rt = dict(float_precision="round_trip")
    a = pd.read_csv(confirm_csv, **rt)
    b = pd.read_csv(OUT / "oldcells_episodes.csv", **rt)
    a = a[a.seed.isin(OLD_SEEDS) & a.cell.isin(OLD_CELLS)]
    df = a.merge(b[["cell", "seed", "B6", "B6dep", "B6dep_pre", "B6dep_post", "B6dep_survived"]],
                 on=["cell", "seed"], suffixes=("", "_rerun"), validate="one_to_one")
    assert len(df) == len(OLD_CELLS) * len(OLD_SEEDS)
    diff = float(np.max(np.abs(df.B6 - df.B6_rerun)))
    return df, diff


def rho_by_cell():
    f = pd.read_csv(OUT / "footprint.csv")
    return f.groupby("cell").rho_m.median().to_dict()


def fit(confirm_csv):
    df, diff = old_data(confirm_csv)
    rho = rho_by_cell()
    ann = headroom_table(df, OLD_CELLS, BAR_ANN_OLD)
    una = headroom_table(df, OLD_CELLS, BAR_UNANN_OLD)
    par = pd.DataFrame([dict(cell=c, **cell_params(c, rho[c])) for c in OLD_CELLS])
    t = par.merge(ann[["cell", "bar_pilot", "bar", "dp", "h", "h_ci"]], on="cell")
    t["h_unann"] = una.set_index("cell").loc[t.cell, "h"].values
    A, M, h = t.A.values, t.M.values, t.h.values
    new = pd.DataFrame([dict(cell=c, **cell_params(c, rho[c])) for c in NEW_CELLS])
    cand = {}
    for name, (f, pr, mono) in MODELS.items():
        p = f(A, M, h)
        cand[name] = dict(params=p, monotone=bool(mono(p)), loo_rmse=loo_rmse(name, A, M, h),
                          r2_fit=r2(pr(p, A, M), h), fitted=pr(p, A, M).tolist(), pred=pr(p, new.A, new.M).tolist())
    ok = [n for n in SELECTABLE if cand[n]["monotone"]]
    chosen = min(ok, key=lambda n: (cand[n]["loo_rmse"], n))        # pre-registered selection rule (SELECTABLE only)
    t["h_fit"] = cand[chosen]["fitted"]
    new["h_pred"] = cand[chosen]["pred"]
    for n in MODELS:
        new[f"h_pred_{n}"] = cand[n]["pred"]
    new["call"] = np.where(new.h_pred >= PASS_MARK, "room", "no room")
    res = dict(model=chosen, params=cand[chosen]["params"], r2_fit=cand[chosen]["r2_fit"], candidates=cand,
               b6_rerun_max_abs_diff=diff, rho=rho, fit_cells=t.to_dict(orient="records"),
               predictions=new.to_dict(orient="records"))
    (OUT / "fit.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    L = [f"chosen model: {chosen} (lowest leave-one-out RMSE among the selectable monotone candidates "
         f"{SELECTABLE}), params "
         f"{cand[chosen]['params']}; fit R^2 on the 9 cells = {res['r2_fit']:.3f}; B6 re-run vs phase-4 file: max "
         f"|diff| = {diff:.2e}", "", "| candidate | params | monotone | LOO RMSE | fit R^2 |", "|---|---|---|---|---|"]
    L += [f"| {n} | {', '.join(f'{v:.4g}' for v in c['params'])} | {c['monotone']} | {c['loo_rmse']:.4f} | "
          f"{c['r2_fit']:.3f} |" for n, c in cand.items()]
    L += ["", "| cell | D m | tau s | v_max | T s | rho m | T_tr s | A | M | bar (ann.) | h ann. (95% CI) | "
          "h unann. | model |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in t.itertuples():
        L.append(f"| {r.cell} | {r.D_m:.0f} | {r.tau_s:.0f} | {r.v_max:.0f} | {r.T_s:.0f} | {r.rho_m:.0f} | "
                 f"{r.T_tr_s:.1f} | {r.A:.3f} | {r.M:.4f} | {r.bar_pilot} {r.bar:.3f} | {r.h:+.4f} +/- {r.h_ci:.4f} | "
                 f"{r.h_unann:+.4f} | {r.h_fit:.4f} |")
    L += ["", "| new cell | D m | tau s | v_max | T s | rho m | T_tr s | A | M | PREDICTED h | call (h >= 0.02) | "
          + " | ".join(f"({n})" for n in MODELS) + " |", "|" + "---|" * (11 + len(MODELS))]
    for r in new.itertuples():
        L.append(f"| {r.cell} | {r.D_m:.0f} | {r.tau_s:.0f} | {r.v_max:.0f} | {r.T_s:.0f} | {r.rho_m:.0f} | "
                 f"{r.T_tr_s:.1f} | {r.A:.3f} | {r.M:.4f} | {r.h_pred:.4f} | {r.call} | "
                 + " | ".join(f"{getattr(r, f'h_pred_{n}'):.4f}" for n in MODELS) + " |")
    text = "\n".join(L)
    (OUT / "fit.md").write_text(text + "\n", encoding="utf-8")
    print(text)


# ---------------------------------------------------------------- gap decomposition (G5 cells, val seeds)
DECOMP_CELLS = ["sites_d20_t0_ann", "sites_d20_t60_ann"]      # the G5 round-1 training cells (announced)
DECOMP_SEEDS = list(range(100, 120))                          # the G5 evaluation split (val)
DECOMP_PILOTS = ("B6", "B6dep", "B3", "B3obsUN")


def decomp_one(cell, seed):
    """dp, teleport and B6 (check), B6dep, B3 (fixed 150 m altitude, full information: the control set of the G5
    'goto' agents), B3obsUN (B3's search with only the agent's information: uncapped maps + crowd size) on one G5
    evaluation scenario."""
    md.apply_profile(cell)
    t0 = time.time()
    env = UAVEnv()
    env.reset(seed=seed)
    nodes = orc.oracle_nodes(env)
    cov = sites_exp.shared_tensor(env, nodes)
    sites_exp.tensor_backed(env, nodes, cov)
    S = orc.segment_scores(cov)
    value, _, target, _ = orc.dp_plan(S, orc.hop_graph(nodes, len(nodes) - 1), len(nodes) - 1)
    row = dict(cell=cell, seed=seed, n_users=env.sc["n_users"], announced=bool(env.sc["announced"]),
               teleport=float(S.max(axis=1).mean()), dp_model=value / S.shape[0])
    c, _ = orc.episode_coverage(env, orc.PlanPolicy(nodes, target, "dp"), seed)
    row["dp"] = float(c.mean())
    for name in DECOMP_PILOTS:
        c, steps = orc.episode_coverage(env, make_policy(name), seed)
        row[name], row[f"{name}_survived"] = float(c.mean()), bool(steps >= env.T)
    row["secs_total"] = time.time() - t0
    md.apply_profile("default")
    return row


def decomp():
    OUT.mkdir(parents=True, exist_ok=True)
    csv = OUT / "decomp_episodes.csv"
    done = _done(csv)
    jobs = [(c, s) for s in DECOMP_SEEDS for c in DECOMP_CELLS if (c, s) not in done]
    print(f"decomposition: {len(jobs)} scenarios to run", flush=True)
    for i, (c, s) in enumerate(jobs, 1):
        sites_exp._ROWS.clear()
        row = decomp_one(c, s)
        sites_exp.append(csv, [row])
        print(f"  {i}/{len(jobs)} {c} seed {s}: " + " ".join(f"{p} {row[p]:.4f}" for p in ("dp", *DECOMP_PILOTS))
              + f"  {row['secs_total']:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["footprint", "oldcells", "newcells", "merge", "fit", "decomp", "evaluate"])
    ap.add_argument("kind", nargs="?", default=None, help="merge: old or new")
    ap.add_argument("--shard", default=None, help="k/n = run shard k (0-based) of n in this process")
    ap.add_argument("--cells", default=None, help="oldcells / newcells: a comma list, a subset of the cells")
    ap.add_argument("--confirm", default=str(sites_exp.OUT / "confirm_episodes.csv"),
                    help="the merged D-52 phase-4 file (seeds 1000-1019)")
    g5 = Path(__file__).parent / "results" / "g5"
    ap.add_argument("--g5", default=f"sites_d20_t0_ann={g5 / 'r1_t0'},sites_d20_t60_ann={g5 / 'r1_t60'}",
                    help="evaluate: cell=folder of a G5 evaluation (episodes.csv), comma separated")
    a = ap.parse_args()
    shard = tuple(int(x) for x in a.shard.split("/")) if a.shard else None
    if a.cmd == "footprint":
        footprint(OLD_CELLS + NEW_CELLS)
    elif a.cmd in ("oldcells", "newcells"):
        run_cells(a.cmd[:3], shard, a.cells.split(",") if a.cells else None)
    elif a.cmd == "merge":
        merge(a.kind)
    elif a.cmd == "fit":
        fit(a.confirm)
    elif a.cmd == "decomp":
        decomp()
    else:
        import anticip_report
        g5 = dict(kv.split("=", 1) for kv in a.g5.split(","))
        anticip_report.evaluate(a.confirm, g5)


if __name__ == "__main__":
    sys.exit(main())
