"""
UAV-NOMA dataset generator.

Run:
    python make_dataset.py users     # step 1: make users + picture
    python make_dataset.py sweep     # step 2: drone-position sweep -> CSV
    python make_dataset.py all       # both

Outputs go to ./data/
    users_<split>.csv   one row per user per scenario
    sweep_<split>.csv   one row per (scenario, drone x, y, h, power)
    users_preview.png   look at this first
    altitude_check.png  coverage vs altitude (an optimum must appear)
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).parent
CFG = yaml.safe_load(open(HERE / "config.yaml"))
OUT = HERE / "data"
OUT.mkdir(exist_ok=True)
C = 3e8


# ---------------------------------------------------------------- users
def make_scenario(seed):
    """Draw this scenario's own settings from the ranges in config (domain randomization)."""
    rng = np.random.default_rng([seed, 0])
    k_lo, k_hi = CFG["n_clusters_range"]
    r_lo, r_hi = CFG["cluster_radius_range_m"]
    s_lo, s_hi = CFG["scatter_fraction_range"]
    n = int(rng.choice(CFG["n_users_choices"]))
    assert n % 2 == 0, "n_users must be even (NOMA pairs)"
    return {
        "seed": seed,
        "n_users": n,
        "n_clusters": int(rng.integers(k_lo, k_hi + 1)),
        "cluster_radius_m": float(rng.uniform(r_lo, r_hi)),
        "scatter_fraction": float(rng.uniform(s_lo, s_hi)),
        "area_m": CFG["area_m"],
        "bandwidth_hz": n * CFG["bandwidth_per_user_hz"],
        "pairing": CFG["pairing"],
        "mobility": str(rng.choice(CFG["mobility"]["choices"])),   # drawn after the basics, so earlier draws are unchanged
        "n_obstacles": int(rng.integers(CFG["obstacles"]["n_range"][0], CFG["obstacles"]["n_range"][1] + 1)),
    }


def make_users(seed, sc=None):
    """Users in clusters (2D Gaussian, truncated) + scattered users, with a QoS class each."""
    sc = sc or make_scenario(seed)
    rng = np.random.default_rng([seed, 1])
    L = CFG["area_m"]
    n = sc["n_users"]
    n_scatter = int(round(n * sc["scatter_fraction"]))
    n_cl = n - n_scatter
    k = sc["n_clusters"]
    radius = sc["cluster_radius_m"]

    # cluster centres, kept away from the border
    m = radius
    centres = rng.uniform(m, L - m, size=(k, 2))
    # split users across clusters with random weights
    w = rng.dirichlet(np.ones(k) * 3)
    counts = rng.multinomial(n_cl, w)

    xs, ys, cid = [], [], []
    for j, cnt in enumerate(counts):
        pts = []
        while len(pts) < cnt:  # truncated Gaussian: redraw if outside radius
            p = rng.normal(0, radius / 2, size=2)
            if np.hypot(*p) <= radius:
                pts.append(centres[j] + p)
        pts = np.array(pts).reshape(-1, 2)
        xs += list(pts[:, 0]); ys += list(pts[:, 1]); cid += [j] * cnt
    sc = rng.uniform(0, L, size=(n_scatter, 2))
    xs += list(sc[:, 0]); ys += list(sc[:, 1]); cid += [-1] * n_scatter

    x = np.clip(xs, 0, L); y = np.clip(ys, 0, L)
    names = list(CFG["classes"])
    shares = np.array([CFG["classes"][c]["share"] for c in names])
    cls = rng.choice(names, size=n, p=shares / shares.sum())
    min_rate = np.array([CFG["classes"][c]["min_rate_bps"] for c in cls])
    return pd.DataFrame({
        "seed": seed, "user_id": np.arange(n), "x": x, "y": y,
        "cluster_id": cid, "class": cls, "min_rate_bps": min_rate,
    })


def make_obstacles(seed, sc):
    """Collapsed-building rectangles for one scenario. Returns a DataFrame (may be empty)."""
    rng = np.random.default_rng([seed, 4])
    L = CFG["area_m"]
    lo, hi = CFG["obstacles"]["size_range_m"]
    n = sc["n_obstacles"]
    w, h = rng.uniform(lo, hi, size=n), rng.uniform(lo, hi, size=n)
    cx, cy = rng.uniform(0, L, size=n), rng.uniform(0, L, size=n)
    return pd.DataFrame({
        "seed": seed, "obstacle_id": np.arange(n),
        "x_min": np.clip(cx - w / 2, 0, L), "y_min": np.clip(cy - h / 2, 0, L),
        "x_max": np.clip(cx + w / 2, 0, L), "y_max": np.clip(cy + h / 2, 0, L)})


def obstacle_array(obs):
    """DataFrame -> (M, 4) array [x_min, y_min, x_max, y_max]."""
    return obs[["x_min", "y_min", "x_max", "y_max"]].values.astype(float) if len(obs) else np.zeros((0, 4))


def link_blocked(ux, uy, X, Y, boxes):
    """True where the 2D segment drone->user crosses any rectangle. Shapes: (P,), (N,) -> (P, N).
    Slab method (Liang-Barsky), vectorized over drones and users, looped over the few rectangles."""
    blocked = np.zeros((len(X), len(ux)), bool)
    x0, y0 = X[:, None], Y[:, None]
    dx, dy = ux[None, :] - x0, uy[None, :] - y0
    for xmin, ymin, xmax, ymax in boxes:
        tmin = np.full(blocked.shape, -np.inf); tmax = np.full(blocked.shape, np.inf)
        ok = np.ones(blocked.shape, bool)
        for p0, d, lo, hi in ((x0, dx, xmin, xmax), (y0, dy, ymin, ymax)):
            zero = np.abs(d) < 1e-12
            with np.errstate(divide="ignore", invalid="ignore"):
                t1, t2 = (lo - p0) / d, (hi - p0) / d
            tlo, thi = np.where(zero, -np.inf, np.minimum(t1, t2)), np.where(zero, np.inf, np.maximum(t1, t2))
            ok &= ~(zero & ((p0 < lo) | (p0 > hi)))         # parallel to the slab and outside it
            tmin, tmax = np.maximum(tmin, tlo), np.minimum(tmax, thi)
        blocked |= ok & (tmax >= np.maximum(tmin, 0.0)) & (tmin <= 1.0)
    return blocked


def simulate_positions(seed, sc, u):
    """Move the users of one scenario for the configured number of steps (vectorized over users).
    Returns pos, vel of shape (T+1, n, 2). vel[t] is the velocity applied in the step that starts at t."""
    mob = CFG["mobility"]
    rng = np.random.default_rng([seed, 3])
    L, dt, T = CFG["area_m"], mob["dt_s"], mob["episode_steps"]
    pos = u[["x", "y"]].values.astype(float)
    n = len(pos)
    cid = u["cluster_id"].values
    k = CFG["n_clusters_range"][1]
    speed = rng.uniform(*mob["speed_mps"], size=n)
    model = sc["mobility"]
    m = sc["cluster_radius_m"]

    def heading(size):
        a = rng.uniform(0, 2 * np.pi, size)
        return np.stack([np.cos(a), np.sin(a)], axis=1)

    def disc(centre, radius, size):
        r = radius * np.sqrt(rng.uniform(size=size)); a = rng.uniform(0, 2 * np.pi, size)
        return centre + np.stack([r * np.cos(a), r * np.sin(a)], axis=1)

    t_start = 0
    if model == "random_waypoint":
        target = rng.uniform(0, L, size=(n, 2))
    elif model == "attraction":
        n_sh = int(rng.integers(mob["n_shelters_range"][0], mob["n_shelters_range"][1] + 1))
        shelters = rng.uniform(0.1 * L, 0.9 * L, size=(n_sh, 2))
        nearest = np.argmin(np.linalg.norm(pos[:, None, :] - shelters[None], axis=2), axis=1)
        target = disc(shelters[nearest], mob["arrival_radius_m"], n)
    elif model == "surge":       # everyone stays put, then suddenly runs to one new point
        t_start = int(rng.integers(*mob["surge_start_range_s"]))
        target = disc(rng.uniform(0.15 * L, 0.85 * L, size=2), mob["surge_radius_m"], n)
        speed = np.full(n, mob["surge_speed_mps"])
    elif model in ("group_drift", "hotspot_jump"):
        cen = np.zeros((k, 2)); cvel = heading(k) * rng.uniform(*mob["speed_mps"], size=(k, 1))
        for j in range(k):
            if (cid == j).any():
                cen[j] = pos[cid == j].mean(axis=0)
        off = pos - cen[np.clip(cid, 0, k - 1)]            # offset of each member from its group centre
        own_vel = heading(n) * speed[:, None]              # scattered users walk on their own
        if model == "hotspot_jump":                        # one crowd suddenly relocates fast
            t_start = int(rng.integers(*mob["surge_start_range_s"]))
            present = [j for j in range(k) if (cid == j).any()]
            jump_j = int(rng.choice(present)) if present else 0
            dest = rng.uniform(m, L - m, size=2)
    else:
        raise ValueError(f"unknown mobility model: {model}")

    P = np.empty((T + 1, n, 2)); V = np.empty((T + 1, n, 2))
    for t in range(T + 1):
        if model in ("random_waypoint", "attraction", "surge"):
            if t < t_start:
                new = pos
            else:
                d = target - pos
                dist = np.linalg.norm(d, axis=1)
                step = speed * dt
                arrive = dist <= step
                new = np.where(arrive[:, None], target, pos + d / np.maximum(dist, 1e-9)[:, None] * step[:, None])
                if model == "random_waypoint" and arrive.any():
                    target[arrive] = rng.uniform(0, L, size=(arrive.sum(), 2))
        else:
            if model == "hotspot_jump" and t >= t_start:
                to = dest - cen[jump_j]; dist = np.linalg.norm(to)
                cvel[jump_j] = to / dist * mob["surge_speed_mps"] if dist > mob["surge_speed_mps"] * dt else 0.0
            cen_new = cen + cvel * dt
            flip = (cen_new < m) | (cen_new > L - m)       # keep whole group inside the area
            cvel = np.where(flip, -cvel, cvel)
            cen_new = cen + cvel * dt
            off = off + rng.normal(0, mob["group_jitter_mps"] * dt, size=off.shape)
            grouped = cid >= 0
            new = np.where(grouped[:, None], cen_new[np.clip(cid, 0, k - 1)] + off, pos + own_vel * dt)
            out = (new < 0) | (new > L)
            own_vel = np.where(out & ~grouped[:, None], -own_vel, own_vel)
            new = np.clip(new, 0, L)
            cen = cen_new
        P[t], V[t] = pos, (new - pos) / dt
        pos = new
    return P, V


def simulate(seed, sc, u):
    """Trajectory table: one row per user per stored snapshot (every store_every_steps)."""
    mob = CFG["mobility"]
    P, V = simulate_positions(seed, sc, u)
    rows = []
    for t in range(0, P.shape[0], mob["store_every_steps"]):
        rows.append(pd.DataFrame({
            "seed": seed, "t": t * mob["dt_s"], "user_id": u["user_id"].values, "x": P[t, :, 0], "y": P[t, :, 1],
            "vx": V[t, :, 0], "vy": V[t, :, 1], "cluster_id": u["cluster_id"].values, "class": u["class"].values}))
    return pd.concat(rows, ignore_index=True)


def seeds(split):
    lo, hi = CFG[f"seeds_{split}"]
    return list(range(lo, hi + 1))


# ---------------------------------------------------------------- channel + NOMA
def channel_gain(ux, uy, X, Y, H, boxes=None, rng=None, fading=None):
    """Linear power gain from drone(s) at (X,Y,H) to users (ux,uy).
    X,Y,H are arrays of shape (P,). Returns (P, N).
    Mean path loss = FSPL + P_LoS*eta_LoS + (1-P_LoS)*eta_NLoS (Al-Hourani).
    boxes: (M,4) obstacle rectangles; a blocked link gets obstacles.excess_loss_db extra loss.
    rng + fading: if rng is given AND fading is on (default: config fading.enabled), each link is drawn LoS/NLoS and gets Rician (LoS) / Rayleigh (NLoS) fading
    (unit mean power) instead of the average path loss."""
    a2g = CFG["a2g"]
    dx = ux[None, :] - X[:, None]
    dy = uy[None, :] - Y[:, None]
    d = np.sqrt(dx**2 + dy**2 + H[:, None]**2)
    theta = np.degrees(np.arcsin(H[:, None] / d))
    p_los = 1.0 / (1.0 + a2g["a"] * np.exp(-a2g["b"] * (theta - a2g["a"])))
    fspl = 20 * np.log10(4 * np.pi * CFG["fc_hz"] * d / C)
    fade = 1.0
    if rng is not None and (CFG["fading"]["enabled"] if fading is None else fading):
        los = rng.uniform(size=d.shape) < p_los
        pl_db = fspl + np.where(los, a2g["eta_los_db"], a2g["eta_nlos_db"])
        K = 10 ** (CFG["fading"]["rician_k_db"] / 10)
        cn = (rng.normal(size=d.shape) + 1j * rng.normal(size=d.shape)) / np.sqrt(2)
        fade = np.where(los, np.abs(np.sqrt(K / (K + 1)) + cn / np.sqrt(K + 1)) ** 2, np.abs(cn) ** 2)
    else:
        pl_db = fspl + p_los * a2g["eta_los_db"] + (1 - p_los) * a2g["eta_nlos_db"]
    if boxes is not None and len(boxes):
        pl_db = pl_db + CFG["obstacles"]["excess_loss_db"] * link_blocked(ux, uy, X, Y, boxes)
    return 10 ** (-pl_db / 10) * fade


def pair_users(g, pairing, rng=None):
    """Return (weak, strong) index arrays, one entry per pair. Roles are set by gain."""
    n_pairs = len(g) // 2
    if pairing == "extreme":              # weakest with strongest, 2nd weakest with 2nd strongest
        order = np.argsort(g)
        return order[:n_pairs], order[::-1][:n_pairs]
    if pairing == "random":               # random pairs; the lower-gain user of each pair is "weak"
        pr = rng.permutation(len(g))[: 2 * n_pairs].reshape(-1, 2)
        a, b = pr[:, 0], pr[:, 1]
        a_weaker = g[a] <= g[b]
        return np.where(a_weaker, a, b), np.where(a_weaker, b, a)
    raise ValueError(f"unknown pairing: {pairing}")


def sic_feasible(aw, p, gs, gw, N0):
    """SIC works if the strong user decodes the weak message at least as well as the weak user does."""
    as_ = 1 - aw
    sinr_w = aw * p * gw / (as_ * p * gw + N0)
    sinr_sw = aw * p * gs / (as_ * p * gs + N0)
    return sinr_sw >= sinr_w


def noma_rates(g, p_tx_w, noise_psd_w, B=None, pairing="extreme", rng=None):
    """g: (N,) gains for ONE drone position. Returns (noma_rate, oma_rate) per user, bits/s.
    Bandwidth is split equally between pairs. B defaults to n_users x bandwidth_per_user_hz."""
    n = len(g)
    B = B if B is not None else n * CFG["bandwidth_per_user_hz"]
    n_pairs = n // 2
    weak, strong = pair_users(g, pairing, rng)
    aw = CFG["noma_alpha_weak"]; as_ = 1 - aw
    bw = B / n_pairs
    p_tx_w = p_tx_w / n_pairs             # total power is SHARED across pairs
    N0 = noise_psd_w * bw
    gw, gs = g[weak], g[strong]
    sinr_w = aw * p_tx_w * gw / (as_ * p_tx_w * gw + N0)
    sinr_s = as_ * p_tx_w * gs / N0
    feasible = sic_feasible(aw, p_tx_w, gs, gw, N0)
    r_w = bw * np.log2(1 + sinr_w)
    r_s = np.where(feasible, bw * np.log2(1 + sinr_s), 0.0)
    noma = np.zeros(n)
    noma[weak] = r_w; noma[strong] = r_s
    # OMA reference: same total bandwidth, equal split between ALL users (FDMA), full power
    bo = B / n
    oma = bo * np.log2(1 + (p_tx_w * n_pairs / n) * g / (noise_psd_w * bo))  # same total power, split over all users
    return noma, oma


def propulsion_power_w(v):
    """Rotary-wing propulsion power (Zeng, Xu, Zhang) at horizontal speed v (m/s). Hover = P0 + Pi."""
    e = CFG["energy"]
    blade = e["P0_w"] * (1 + 3 * v**2 / e["Utip_mps"] ** 2)
    induced = e["Pi_w"] * np.sqrt(np.sqrt(1 + v**4 / (4 * e["v0_mps"] ** 4)) - v**2 / (2 * e["v0_mps"] ** 2))
    parasite = 0.5 * e["d0"] * e["rho_kg_m3"] * e["s"] * e["A_m2"] * v**3
    return blade + induced + parasite


def energy_step_j(v_h, vz, p_tx_w):
    """Energy for one step: propulsion + climbing (weight x climb rate, no recovery when descending)
    + communication (P_tx / PA efficiency) + circuit."""
    e = CFG["energy"]
    climb = e["weight_n"] * np.maximum(vz, 0.0)
    comm = p_tx_w / e["pa_efficiency"]
    return (propulsion_power_w(v_h) + climb + comm + e["P_circuit_w"]) * e["dt_s"]


def jain(r):
    s = r.sum()
    return float(s**2 / (len(r) * (r**2).sum())) if s > 0 else 0.0


# ---------------------------------------------------------------- sweep
def sweep_one(u, sc, boxes=None):
    ux, uy = u["x"].values, u["y"].values
    minr = u["min_rate_bps"].values
    resc = (u["class"] == "rescue").values
    L = CFG["area_m"]; step = CFG["sweep"]["xy_step_m"]
    gx = np.arange(0, L + 1, step)
    X, Y, H = [a.ravel() for a in np.meshgrid(gx, gx, CFG["sweep"]["altitudes_m"], indexing="ij")]
    G = channel_gain(ux, uy, X, Y, H, boxes)      # (P, N); average channel (no fading) in the dataset

    noise_psd_w = 10 ** ((CFG["noise_density_dbm_hz"] + CFG["noise_figure_db"] - 30) / 10)
    B = sc["bandwidth_hz"]
    rng = np.random.default_rng([sc["seed"], 2])   # only used by random pairing
    rows = []
    for pdbm in CFG["tx_power_dbm_levels"]:
        p_w = 10 ** ((pdbm - 30) / 10)
        for i in range(len(X)):
            r, ro = noma_rates(G[i], p_w, noise_psd_w, B, sc["pairing"], rng)
            cov = r >= minr
            rows.append((
                sc["seed"], X[i], Y[i], H[i], pdbm, sc["pairing"],
                cov.mean(), r.sum() / 1e6, r.sum() / B, jain(r),
                1 - cov[resc].mean() if resc.any() else 0.0,
                (ro >= minr).mean(), ro.sum() / 1e6,
                energy_step_j(0.0, 0.0, p_w),     # drone hovers at each sweep point
            ))
    return rows


COLS = ["seed", "x", "y", "h", "p_dbm", "pairing", "coverage", "sum_rate_mbps", "spectral_eff",
        "fairness", "outage_rescue", "coverage_oma", "sum_rate_oma_mbps", "energy_j_per_step"]


def run_users():
    for split in ["train", "val", "test"]:
        scs = [make_scenario(s) for s in seeds(split)]
        df = pd.concat([make_users(sc["seed"], sc) for sc in scs], ignore_index=True)
        df.to_csv(OUT / f"users_{split}.csv", index=False)
        pd.DataFrame(scs).to_csv(OUT / f"scenarios_{split}.csv", index=False)
        pd.concat([make_obstacles(sc["seed"], sc) for sc in scs], ignore_index=True).to_csv(
            OUT / f"obstacles_{split}.csv", index=False)
        us = {sc["seed"]: df[df.seed == sc["seed"]] for sc in scs}
        tr = pd.concat([simulate(sc["seed"], sc, us[sc["seed"]]) for sc in scs], ignore_index=True)
        tr.to_csv(OUT / f"trajectory_{split}.csv", index=False)
        print(f"users_{split}.csv  {len(df)} rows,  scenarios_{split}.csv  {len(scs)} rows,  "
              f"trajectory_{split}.csv  {len(tr)} rows")
    # preview picture: 4 scenarios
    fig, ax = plt.subplots(1, 4, figsize=(16, 4))
    for a, s in zip(ax, seeds("train")[:4]):
        sc = make_scenario(s); u = make_users(s, sc)
        for cid, g in u.groupby("cluster_id"):
            a.scatter(g.x, g.y, s=8, label="scatter" if cid == -1 else f"cluster {cid}")
        r = u[u["class"] == "rescue"]
        a.scatter(r.x, r.y, s=30, facecolors="none", edgecolors="k", label="rescue")
        a.set_title(f"seed {s}: {sc['n_users']} users, {sc['n_clusters']} clusters"); a.set_xlim(0, CFG["area_m"]); a.set_ylim(0, CFG["area_m"]); a.set_aspect("equal")
    ax[0].legend(fontsize=7)
    plt.tight_layout(); plt.savefig(OUT / "users_preview.png", dpi=110)
    print("saved users_preview.png")


def run_sweep(splits=("train", "val", "test"), limit=None):
    for split in splits:
        rows = []
        sl = seeds(split)[:limit] if limit else seeds(split)
        for k, s in enumerate(sl):
            sc = make_scenario(s)
            rows += sweep_one(make_users(s, sc), sc, obstacle_array(make_obstacles(s, sc)))
            if k % 10 == 0:
                print(f"  {split}: scenario {k+1}/{len(sl)}")
        df = pd.DataFrame(rows, columns=COLS)
        df.to_csv(OUT / f"sweep_{split}.csv", index=False)
        print(f"sweep_{split}.csv  {len(df)} rows")
    # sanity plot: mean coverage vs altitude (NOMA vs OMA) at each power
    df = pd.read_csv(OUT / f"sweep_{splits[0]}.csv")
    fig, ax = plt.subplots(figsize=(6, 4))
    for p, g in df.groupby("p_dbm"):
        m = g.groupby("h")[["coverage", "coverage_oma"]].mean()
        ax.plot(m.index, m.coverage, "-o", label=f"NOMA {p} dBm")
        ax.plot(m.index, m.coverage_oma, "--", color=ax.lines[-1].get_color(), label=f"OMA {p} dBm")
    ax.set_xlabel("altitude (m)"); ax.set_ylabel("mean coverage"); ax.legend(fontsize=7)
    plt.tight_layout(); plt.savefig(OUT / "altitude_check.png", dpi=110)
    print("saved altitude_check.png")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("users", "all"):
        run_users()
    if what in ("sweep", "all"):
        run_sweep()
    if what == "quick":          # tiny test: 3 scenarios
        run_sweep(splits=("train",), limit=3)
