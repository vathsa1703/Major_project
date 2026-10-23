"""Clairvoyant oracle (book 14.6 step 3): how much could ANTICIPATION add over the best myopic pilot B6?

In plain words: B6 looks at where people are NOW and flies to the best spot for them. The oracle is allowed to know
where people WILL be (we simulate the crowd, so we know its future). If even a pilot that knows the future barely beats
B6, then no AI that learns to anticipate can beat B6 either, and H2 has nothing to win in these scenarios.

How it works (all settings in config.yaml `oracle:`):
1. Coverage tensor. For one scenario, cov[i, n] = coverage the drone would get at node n with the user positions at
   t_i = 0, 5, ..., 295 s (UAVEnv.evaluate(..., t)). Nodes = B6's own candidates: the grid_n x grid_n grid at every
   altitude level, in B6's order, plus the start spot as the last node. Same access scheme and power as the env / B6.
   Cached on disk under results/oracle_cache/ (not committed).
2. Segments. Like B6, the drone decides every 10 s (decision k at t = 10k). Segment k = [10k, 10k + 10) is scored by
   the mean of the tensor at its two 5 s samples (10k and 10k + 5) at the node the drone is AT in that segment.
3. Moves (hops). A hop i -> j is a straight flight like go_to flies it: horizontal at v_max x (1 + reach_slack),
   vertical at vz_max, both at once. It takes tau decisions = the flight time rounded UP to whole 10 s decisions
   (staying = 1).
   reach_slack (3%) exists because the grid spacing on `hard` (2000/13 = 153.8 m) is just above v_max x 10 s = 150 m:
   without it, a one-cell move would cost two decisions.
   APPROXIMATION (transit): each segment of a hop is scored at the lattice node NEAREST to where the drone is at the END
   of that segment; the last segment is scored at the target (the drone arrives within it, though it is in flight for
   part of it). So the tensor score of a plan is only the planner's model; every reported number comes from REPLAYING
   the plan through the real env (env.step), never from the tensor.
4. Plans (each a target node per decision; the replay flies there with go_to at B6's power):
   - teleport: best node in every segment, ignoring travel. Tensor-level UPPER BOUND only (not flyable).
   - dp:       dynamic programming (Viterbi) over all 30 decisions and every feasible hop, from the start spot. The last
               hop may still be in flight at 300 s.
   - mpc30, mpc60: receding horizon: DP over the next 30 / 60 s only, commit to its first hop, replan when it ends
               (every 10 s when the drone stays or moves one cell; a long flight is flown to the end before replanning).
   - frozen:   B6's rule on the tensor: at decision k, the best node for the CURRENT positions (sample t = 10k), ties to
               the node closest to the previous target. Its first decision is exactly B6's. Later it differs from B6
               only in that B6 also scores the spot it is flying through and ties to its real position.
   - frozen_path: path-aware like mpc60, but every future segment is scored with the users frozen at t = 10k.
   Decomposition: B6 ~ frozen (same rule) -> frozen_path (adds path awareness, no future) -> mpc30/mpc60 (adds a
   bounded look-ahead) -> dp (the whole future).
5. Start: the env starts at the map centre (L/2, L/2, start_h), which is NOT a grid node (it is equidistant from four
   nodes), so it is kept as its own node (B6 also scores it at t = 0) instead of snapping to an arbitrary neighbour.

    python oracle.py --profile hard --seeds 0-119                 # main experiment (1 process by default)
    python oracle.py --profile rl_static --seeds 100-109 --tag sanity_static
    python oracle.py --profile hard --seeds 0-29 --access noma_opt --tag noma_opt
Outputs (results/oracle/, not committed): oracle_episodes_<tag>.csv and oracle_summary_<tag>.md.
This module is a measurement tool. It is never imported by the rl_* code (a test checks that): the AI must not see it.
"""
import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import make_dataset as md
from baselines import Policy, _grid, make_policy
from evalstats import holm, mean_ci, paired_p
from uav_env import UAVEnv

CFG = md.CFG
OCFG = CFG["oracle"]
BCFG = CFG["baselines"]
RESULTS = Path(__file__).parent / "results"
CACHE = RESULTS / "oracle_cache"
PLANS = ("frozen", "frozen_path", "mpc30", "mpc60", "dp")      # flyable plans, replayed through the env
NEG = -np.inf


# ---------------------------------------------------------------- geometry
def oracle_nodes(env):
    """(N, 3) candidate nodes (x, y, h): B6's grid x altitude levels in B6's order, then the env's start spot.
    Call right after env.reset() (the last node is the drone's position then)."""
    X, Y = _grid(env)
    levels = np.array(BCFG["altitude_levels_m"], dtype=float)
    nx, ny, nh = np.repeat(X, len(levels)), np.repeat(Y, len(levels)), np.tile(levels, len(X))
    return np.column_stack([np.append(nx, env.x), np.append(ny, env.y), np.append(nh, env.h)])


def decision_steps():
    return int(BCFG["replan_every_steps"])


class _Group:
    """All hops that take exactly t decisions, sorted by target J then origin I. W[p, m] = node scored in segment m
    of hop p (the last one is J)."""

    def __init__(self, t, I, J, W):
        self.t, self.I, self.J, self.W = t, I, J, W
        self.starts = np.flatnonzero(np.r_[True, J[1:] != J[:-1]])
        self.uJ = J[self.starts]
        self.ends = np.r_[self.starts[1:], len(J)]

    def slice_to(self, j):
        """Index range of the hops that end at node j (empty if none)."""
        q = np.searchsorted(self.uJ, j)
        if q == len(self.uJ) or self.uJ[q] != j:
            return slice(0, 0)
        return slice(self.starts[q], self.ends[q])


class HopGraph:
    """Every straight flight between two nodes (module docstring, point 3). tau[i, j] = decisions needed (>= 1;
    staying = 1); 0 = longer than max_hop_decisions (null = no limit).
    nodes[:n_lattice] must be a full x-major lattice (x, then y, then altitude), like oracle_nodes; the remaining
    nodes (the start spot) can be flown from and to but are never used as in-flight waypoints."""

    def __init__(self, nodes, n_lattice=None):
        u = CFG["uav"]
        nodes = np.asarray(nodes, dtype=float)
        n_lat = len(nodes) if n_lattice is None else int(n_lattice)
        period = decision_steps() * CFG["energy"]["dt_s"]
        v_xy, v_z = u["v_max_mps"] * (1.0 + OCFG["reach_slack"]), u["vz_max_mps"]
        self.axes = [np.unique(nodes[:n_lat, c]) for c in range(3)]
        assert np.array_equal(self.snap(nodes[:n_lat]), np.arange(n_lat)), "nodes[:n_lattice] must be a full lattice"
        d = nodes[None, :, :] - nodes[:, None, :]                      # d[i, j] = node j - node i
        dxy, dz = np.hypot(d[..., 0], d[..., 1]), np.abs(d[..., 2])
        need = np.maximum(dxy / (v_xy * period), dz / (v_z * period))
        tau = np.maximum(1, np.ceil(need - 1e-9)).astype(int)
        if OCFG["max_hop_decisions"]:
            tau[tau > OCFG["max_hop_decisions"]] = 0
        self.nodes, self.tau, self.tmax = nodes, tau, int(tau.max())
        self.groups = []
        for t in range(1, self.tmax + 1):
            J, I = np.nonzero(tau.T == t)                              # sorted by J, then I
            if len(J) == 0:
                continue
            W = np.empty((len(J), t), dtype=np.int32)
            W[:, t - 1] = J
            if t > 1:
                s = period * np.arange(1, t)                           # end times of the in-flight segments
                dij, hxy, hz = d[I, J], dxy[I, J], dz[I, J]
                ux = np.divide(dij[:, :2], hxy[:, None], out=np.zeros((len(J), 2)), where=hxy[:, None] > 0)
                gone_xy = np.minimum(v_xy * s[None, :], hxy[:, None])  # (P, t - 1) metres flown so far
                gone_z = np.minimum(v_z * s[None, :], hz[:, None])
                pos = np.empty((len(J), t - 1, 3))
                pos[..., :2] = nodes[I][:, None, :2] + ux[:, None, :] * gone_xy[..., None]
                pos[..., 2] = nodes[I][:, None, 2] + np.sign(dij[:, 2])[:, None] * gone_z
                W[:, : t - 1] = self.snap(pos)
            self.groups.append(_Group(t, I, J, W))

    def snap(self, pos):
        """Index of the nearest lattice node for positions (..., 3) (per axis, since the lattice is a product)."""
        idx = []
        for c, ax in enumerate(self.axes):
            hi = np.clip(np.searchsorted(ax, pos[..., c]), 0, len(ax) - 1)
            lo = np.maximum(hi - 1, 0)
            idx.append(np.where(np.abs(pos[..., c] - ax[lo]) <= np.abs(ax[hi] - pos[..., c]), lo, hi))
        return (idx[0] * len(self.axes[1]) + idx[1]) * len(self.axes[2]) + idx[2]

    def path(self, i, j):
        """Segment nodes of the hop i -> j (length tau[i, j])."""
        g = next(g for g in self.groups if g.t == self.tau[i, j])
        sl = g.slice_to(j)
        return g.W[sl][np.searchsorted(g.I[sl], i)]


_GRAPHS = {}


def hop_graph(nodes, n_lattice=None):
    """HopGraph, cached per node set and motion settings (the same for every scenario of a profile)."""
    key = (np.asarray(nodes, dtype=float).tobytes(), n_lattice,
           json.dumps([CFG["uav"], CFG["energy"]["dt_s"], OCFG, BCFG], sort_keys=True))
    if key not in _GRAPHS:
        _GRAPHS.clear()
        _GRAPHS[key] = HopGraph(nodes, n_lattice)
    return _GRAPHS[key]


# ---------------------------------------------------------------- coverage tensor
def sample_times(env):
    return np.arange(0, env.T, OCFG["sample_every_s"] / env.dt).astype(int)


def _cache_key(env):
    # b6fc, hybrid: sections added later (the forecasting pilot, the hybrid timing AI); excluded so the existing caches
    # stay valid
    cfg = {k: v for k, v in CFG.items() if k not in ("rl", "profiles", "active_profile", "oracle", "b6fc", "hybrid")}
    blob = json.dumps([cfg, OCFG["sample_every_s"], env.access, env.sic_eps, env.rescue_first,
                       env.scenario_overrides], sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def coverage_tensor(env, nodes=None, cache=True):
    """cov[i, n]: coverage at node n for the users at sample time i (every sample_every_s). Average channel, B6's power.
    Pure: uses env.evaluate(..., t), which leaves the env state and rng untouched."""
    nodes = oracle_nodes(env) if nodes is None else nodes
    path = CACHE / f"{CFG.get('active_profile', 'default')}_{env.access}_s{env.scenario_seed}_{_cache_key(env)}.npz"
    if cache and path.exists():
        z = np.load(path)
        if z["nodes"].shape == nodes.shape and np.allclose(z["nodes"], nodes):
            return z["cov"]
    p_w = env.p_max_w * BCFG["power_frac"]
    cov = np.stack([env.evaluate(nodes[:, 0], nodes[:, 1], nodes[:, 2], p_w, t=t) for t in sample_times(env)])
    if cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, cov=cov, nodes=nodes)
    return cov


def segment_scores(cov):
    """(K, N): score of each 10 s segment = mean of the tensor samples inside it (here the two at 10k and 10k + 5)."""
    per = int(round(decision_steps() / OCFG["sample_every_s"]))
    K = cov.shape[0] // per
    return cov[: K * per].reshape(K, per, -1).mean(axis=1)


def frozen_scores(cov):
    """(K, N): the tensor at each DECISION time only (t = 10k): what a pilot that only sees the present knows."""
    per = int(round(decision_steps() / OCFG["sample_every_s"]))
    return cov[::per]


# ---------------------------------------------------------------- planners
def _transit(g, a, S, k, K, sl=slice(None)):
    """Value of every hop of group g (or the slice sl of it) that starts at decision k from a node with value a:
    a[origin] + the scores of its segments that fall inside the horizon (k .. K - 1)."""
    v = a[g.I[sl]].copy()
    W = g.W[sl]
    for m in range(min(g.t, K - k)):
        v += S[k + m][W[:, m]]
    return v


def dp_plan(S, graph, start):
    """Best flight plan for segment scores S (K, N) on a HopGraph, starting at node `start` at decision 0.
    Maximises the sum of S over the segments (transit convention: module docstring). The last hop may still be in
    flight at the end (only its segments before K count). Ties prefer staying, then shorter hops.
    Returns (value, at, target, hops): at[k] = node scored in segment k, target[k] = node flown to at decision k,
    hops = [(k0, i, j, t)]. Vectorised over all hops (grouped by duration); loops only over decisions and durations."""
    K, N = S.shape
    A = np.full((K + 1, N), NEG)                       # A[k, j]: best score of segments < k, being at node j at k
    A[0, start] = 0.0
    fin_val, fin = NEG, None                           # best plan that ends in flight
    for k in range(K):
        a = A[k]
        if not np.isfinite(a).any():
            continue
        for g in graph.groups:
            v = _transit(g, a, S, k, K)
            if k + g.t <= K:
                A[k + g.t, g.uJ] = np.maximum(A[k + g.t, g.uJ], np.maximum.reduceat(v, g.starts))
            else:
                p = int(np.argmax(v))
                if v[p] > fin_val + 1e-12:
                    fin_val, fin = float(v[p]), (k, int(g.I[p]), int(g.J[p]), g.t)
    j = int(np.argmax(A[K]))
    value, hops, k = float(A[K, j]), [], K
    if fin is not None and fin_val > value + 1e-12:
        value, hops = fin_val, [fin]
        k, j = fin[0], fin[1]
    while k > 0:                                       # backtrack: recompute the hops into (k, j), keep a best one
        hop = None
        for g in graph.groups:                         # shortest hops first
            if g.t > k:
                break
            sl = g.slice_to(j)
            v = _transit(g, A[k - g.t], S, k - g.t, K, sl)
            ok = np.flatnonzero(v >= A[k, j] - 1e-9)
            if len(ok):
                I = g.I[sl][ok]
                hop = (k - g.t, j if (g.t == 1 and j in I) else int(I[0]), j, g.t)
                break
        assert hop is not None, "dp backtrack failed"
        hops.append(hop)
        k, j = hop[0], hop[1]
    hops.reverse()
    at, target = hops_to_schedule(hops, K, graph)
    return value, at, target, hops


def hops_to_schedule(hops, K, graph):
    """Per-decision arrays from a hop list: at[k] (node scored in segment k) and target[k] (node flown to)."""
    at, target = np.full(K, -1), np.full(K, -1)
    for k0, i, j, t in hops:
        w = graph.path(i, j)
        for m in range(t):
            if k0 + m < K:
                at[k0 + m], target[k0 + m] = w[m], j
    return at, target


def plan_score(S, at):
    """Model (tensor) score of a schedule: mean over segments of S[k, at[k]]."""
    return float(S[np.arange(len(at)), at].mean())


def receding_plan(S_at, graph, start, K, h_dec):
    """Receding-horizon planner: at decision k, run dp_plan on S_at(k, H) (H = min(h_dec, K - k) segments) and
    commit to its first hop (the whole hop, even if it is longer than H: the drone flies straight to that node), then
    replan from the node where the hop ends. Returns (at, target, hops)."""
    hops, k, node = [], 0, start
    while k < K:
        _, _, _, sub = dp_plan(S_at(k, min(h_dec, K - k)), graph, node)
        _, i, j, t = sub[0]
        hops.append((k, i, j, t))
        k, node = k + t, j
    at, target = hops_to_schedule(hops, K, graph)
    return at, target, hops


def frozen_plan(cov, nodes, start):
    """B6's rule on the tensor: best node for the users as they are at each decision time, ties to the node closest
    to the previous target (at k = 0: the start spot, exactly like B6)."""
    F = frozen_scores(cov)
    target, prev = np.empty(len(F), dtype=int), start
    for k, f in enumerate(F):
        best = np.flatnonzero(f >= f.max() - 1e-12)
        d = np.linalg.norm(nodes[best] - nodes[prev], axis=1)
        prev = target[k] = int(best[np.argmin(d)])
    return target


def all_plans(cov, nodes, graph=None):
    """Every plan for one scenario (nodes from oracle_nodes: lattice + start spot last). Returns
    {name: dict(target=..., at=..., model=tensor score or nan)} and the teleport bound (per-segment best, (K,))."""
    graph = hop_graph(nodes, len(nodes) - 1) if graph is None else graph
    S, F = segment_scores(cov), frozen_scores(cov)
    K, start = S.shape[0], len(nodes) - 1
    step = decision_steps()
    out = {}
    v, at, target, _ = dp_plan(S, graph, start)
    out["dp"] = dict(at=at, target=target, model=v / K)
    for h in OCFG["horizons_s"]:
        at, target, _ = receding_plan(lambda k, H: S[k:k + H], graph, start, K, int(h // step))
        out[f"mpc{h}"] = dict(at=at, target=target, model=plan_score(S, at))
    hf = int(OCFG["frozen_path_horizon_s"] // step)
    at, target, _ = receding_plan(lambda k, H: np.repeat(F[k][None], H, axis=0), graph, start, K, hf)
    out["frozen_path"] = dict(at=at, target=target, model=plan_score(S, at))
    out["frozen"] = dict(at=None, target=frozen_plan(cov, nodes, start), model=np.nan)
    return out, S.max(axis=1)


# ---------------------------------------------------------------- replay through the real env
class PlanPolicy(Policy):
    """Flies a precomputed plan: at decision k (every replan_every_steps seconds) it flies to node target[k] with
    go_to (Policy.act), at B6's power. Deterministic: the plan is fixed before the episode starts."""

    def __init__(self, nodes, target, name="plan"):
        self.nodes, self.targets, self.name = np.asarray(nodes), np.asarray(target), name

    def reset(self, env):
        super().reset(env)
        self.power = BCFG["power_frac"]

    def plan(self, env):
        k = min(env.t // decision_steps(), len(self.targets) - 1)
        self.target = tuple(float(v) for v in self.nodes[self.targets[k]])


def episode_coverage(env, policy, seed):
    """Per-step coverage (length T; steps after battery death count 0, like coverage_full) and the steps flown."""
    env.reset(seed=seed)
    policy.reset(env)
    cov, done = np.zeros(env.T), False
    while not done:
        _, _, term, trunc, info = env.step(policy.act(env))
        cov[env.t - 1] = info["coverage"]
        done = term or trunc
    return cov, int(env.t)


def window_means(per_step, windows, dt=1.0):
    """Mean of a per-step series (step s covers time s*dt .. (s+1)*dt) over each [lo, hi) window in seconds."""
    t = np.arange(len(per_step)) * dt
    return [float(per_step[(t >= lo) & (t < hi)].mean()) for lo, hi in windows]


def run_scenario(seed, access=None, use_cache=True):
    """All plans + B6 on one scenario. Returns a list of rows (one per policy) with coverage_full and window means."""
    t0 = time.time()
    env = UAVEnv(access=access)
    env.reset(seed=seed)
    nodes = oracle_nodes(env)
    cov = coverage_tensor(env, nodes, cache=use_cache)
    t_tensor = time.time() - t0
    plans, tele = all_plans(cov, nodes)
    t_plan = time.time() - t0 - t_tensor
    windows = OCFG["windows_s"]
    base = dict(seed=seed, mobility=env.sc["mobility"], n_users=env.sc["n_users"], access=env.access)
    rows = [dict(base, policy="teleport", kind="bound (tensor)", coverage_full=float(tele.mean()),
                 **{f"w{i}": v for i, v in enumerate(window_means(tele, windows, decision_steps() * env.dt))},
                 survived_s=np.nan, model_score=float(tele.mean()))]
    pols = [("B6", make_policy("B6"), np.nan)] + [
        (n, PlanPolicy(nodes, plans[n]["target"], n), plans[n]["model"]) for n in PLANS]
    for name, pol, model in pols:
        c, steps = episode_coverage(env, pol, seed)
        # c[i] is the step that flies from t = i to i + 1 (coverage measured at i + 1); windows use the start time i,
        # so window [0, 60) = the first 60 steps, matching the tensor's segments [10k, 10k + 10)
        rows.append(dict(base, policy=name, kind="replay (env.step)", coverage_full=float(c.mean()),
                         **{f"w{i}": v for i, v in enumerate(window_means(c, windows, env.dt))},
                         survived_s=steps * env.dt, model_score=model))
    for r in rows:
        r["secs_tensor"], r["secs_plan"], r["secs_total"] = t_tensor, t_plan, time.time() - t0
    return rows


def _task(args):
    seed, access, profile = args
    md.apply_profile(profile)
    return run_scenario(seed, access)


# ---------------------------------------------------------------- statistics and report
def comparison_table(df, value, plans, models):
    """Rows (plan, model): mean of plan, mean of B6, paired diff vs B6 +/- 95% CI, p, and Holm-adjusted p over the
    flyable (plan x mobility model) cells (the 'all' rows and the teleport bound are not in the Holm family)."""
    piv = df.pivot_table(index="seed", columns="policy", values=value)
    mob = df.drop_duplicates("seed").set_index("seed").mobility
    rows = []
    for m in models:
        s = mob.index[mob == m] if m != "all" else mob.index
        for p in plans:
            a, b = piv.loc[s, p], piv.loc[s, "B6"]
            d, h = mean_ci(a - b)
            rows.append(dict(plan=p, mobility=m, n=len(s), mean=a.mean(), B6=b.mean(), diff=d, ci=h,
                             p=paired_p(a, b)))
    t = pd.DataFrame(rows)
    fam = (t.mobility != "all") & t.plan.isin(PLANS)
    t["p_holm"] = np.nan
    if fam.any():
        t.loc[fam, "p_holm"] = holm(t.loc[fam, "p"].to_numpy())
    return t


def fmt_table(t):
    lines = ["| plan | mobility | n | mean | B6 | plan - B6 (95% CI) | Holm p |", "|---|---|---|---|---|---|---|"]
    for r in t.itertuples():
        if r.plan in PLANS:
            star = "*" if (r.p_holm < 0.05 if np.isfinite(r.p_holm) else abs(r.diff) > r.ci) else ""
            diff = f"{r.diff:+.3f} +/- {r.ci:.3f}{star}"
            hp = f"{r.p_holm:.3g}" if np.isfinite(r.p_holm) else "-"
        else:
            diff, hp = f"{r.diff:+.3f} (bound, not flyable)", "-"
        lines.append(f"| {r.plan} | {r.mobility} | {r.n} | {r.mean:.3f} | {r.B6:.3f} | {diff} | {hp} |")
    return "\n".join(lines)


def summarize(df, header=""):
    models = sorted(df.mobility.unique()) + ["all"]
    show = ["teleport", *PLANS]
    counts = df.drop_duplicates("seed").mobility.value_counts()
    out = [header, "",
           f"Scenarios: {df.seed.nunique()} ({', '.join(f'{k} {v}' for k, v in counts.items())}).",
           "Replay numbers = mean coverage over the 300 s from env.step (dead drone = 0). 'teleport' is a tensor-level",
           "upper bound (best node in every 10 s segment, travel ignored), not a flyable plan. Paired differences vs",
           "B6 with 95% CI. Holm-adjusted p over the flyable (plan x mobility model) cells of each table; the 'all'",
           "rows are not in the family (their * = CI excludes 0). * on a model row = Holm p < 0.05.",
           "", "### Whole episode (coverage_full)", "", fmt_table(comparison_table(df, "coverage_full", show, models))]
    for i, (lo, hi) in enumerate(OCFG["windows_s"]):
        out += ["", f"### Time window {lo}-{hi} s", "", fmt_table(comparison_table(df, f"w{i}", show, models))]
    piv = df.pivot_table(index="seed", columns="policy", values="coverage_full")
    model = df.pivot_table(index="seed", columns="policy", values="model_score")
    out += ["", "### Sanity checks", "",
            f"- teleport bound >= dp model (tensor) score on every scenario: "
            f"{bool((model.teleport + 1e-9 >= model.dp).all())}",
            f"- dp model (tensor) score mean {model.dp.mean():.3f} vs dp replay {piv.dp.mean():.3f} "
            f"(difference = transit approximation + sample timing)",
            f"- frozen - B6 (same rule on the tensor): {piv.frozen.mean() - piv.B6.mean():+.4f}; "
            f"identical on {(np.abs(piv.frozen - piv.B6) < 1e-12).mean():.0%} of scenarios",
            f"- dp replay >= B6 on {(piv.dp >= piv.B6 - 1e-12).mean():.0%} of scenarios; "
            f"teleport bound >= dp replay on {(piv.teleport >= piv.dp).mean():.0%}"]
    t = comparison_table(df, "coverage_full", ["dp"], [m for m in models if m != "all"])
    gain = bool((t["diff"] >= OCFG["min_gain"]).any())
    rule = (f"At least one mobility model reaches dp - B6 >= {OCFG['min_gain']:.2f}: there is room for anticipation."
            if gain else f"dp - B6 < {OCFG['min_gain']:.2f} for every mobility model: no room for anticipation in "
            "these regimes; redesign scenarios before G5.")
    out += ["", "### Pre-registered decision rule", "",
            "dp - B6 per mobility model: " + ", ".join(f"{r.mobility} {r.diff:+.3f}" for r in t.itertuples()) + ".",
            rule]
    return "\n".join(out)


def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        seeds += list(range(int(lo), int(hi or lo) + 1))
    return seeds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="hard")
    ap.add_argument("--seeds", default="0-119", help="e.g. 0-119 or 0-9,100-109")
    ap.add_argument("--access", default=None, help="noma (config default) | oma | oma_opt | noma_opt")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--workers", type=int, default=1, help="keep 1 while other jobs run on the machine")
    a = ap.parse_args()
    os.environ["UAV_PROFILE"] = a.profile
    md.apply_profile(a.profile)
    access = a.access or CFG["env"]["access"]
    tag = a.tag or f"{a.profile}_{access}"
    seeds = parse_seeds(a.seeds)
    print(f"oracle: profile {a.profile}, access {access}, {len(seeds)} scenarios, {a.workers} worker(s)", flush=True)
    t0, rows = time.time(), []
    tasks = [(s, access, a.profile) for s in seeds]
    if a.workers > 1:
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            for i, r in enumerate(pool.map(_task, tasks), 1):
                rows += r
                print(f"  {i}/{len(seeds)}  {time.time() - t0:.0f}s", flush=True)
    else:
        for i, task in enumerate(tasks, 1):
            rows += _task(task)
            print(f"  {i}/{len(seeds)} seed {task[0]}  {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    out = RESULTS / "oracle"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"oracle_episodes_{tag}.csv", index=False)
    head = (f"## Oracle vs B6: profile {a.profile}, access {access}, battery {CFG['energy']['battery_wh']:g} Wh, "
            f"seeds {a.seeds}. Run time {time.time() - t0:.0f} s, {a.workers} process(es).")
    text = summarize(df, head)
    (out / f"oracle_summary_{tag}.md").write_text(text, encoding="utf-8")
    print("\n" + text)


if __name__ == "__main__":
    main()
