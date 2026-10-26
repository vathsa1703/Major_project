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
import copy
import os
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
BASE_CFG = copy.deepcopy(CFG)          # untouched copy, so a profile can be switched off again


def deep_update(dst, src):
    """Merge src into dst IN PLACE, so every module holding a reference to a nested dict sees the change."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_update(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)


def apply_profile(name):
    """Switch to a named profile from config.yaml `profiles:` (None or 'default' = the base config)."""
    deep_update(CFG, copy.deepcopy(BASE_CFG))                       # always start from the base
    if name and name != "default":
        deep_update(CFG, CFG["profiles"][name])
    CFG["active_profile"] = name or "default"


apply_profile(os.environ.get("UAV_PROFILE"))                        # lets worker processes inherit the profile
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
    sc = {
        "seed": seed,
        "n_users": n,
        "n_clusters": int(rng.integers(k_lo, k_hi + 1)),
        "cluster_radius_m": float(rng.uniform(r_lo, r_hi)),
        "scatter_fraction": float(rng.uniform(s_lo, s_hi)),
        "area_m": CFG["area_m"],
        "bandwidth_hz": n * CFG["bandwidth_per_user_hz"],
        "pairing": CFG["pairing"],
        # drawn after the basics, so the earlier draws are unchanged
        "mobility": str(rng.choice(CFG["mobility"]["choices"])),
        "n_obstacles": int(rng.integers(CFG["obstacles"]["n_range"][0], CFG["obstacles"]["n_range"][1] + 1)),
    }
    if sc["mobility"] == "sites":                    # competing sites (D-52); other scenarios are unchanged
        sc.update(make_sites(seed))
        sc["n_clusters"] = sc["n_sites"]
    if sc["mobility"] == "place":                    # real-place case study (place.py); other scenarios are unchanged
        import place
        sc.update(place.make_place_scenario(seed))
    return sc


# ---------------------------------------------------------------- competing sites (D-52; config section `sites:`)
def place_sites(rng, radius, D, L, max_draws, min_sep):
    """Site centres (k, 2) for radii `radius` (k,): A and B exactly D apart, every site disc inside the L x L map,
    site C (if k == 3) at least min_sep from A and B (or, if no draw of the batch manages, the farthest one).
    For a direction theta, the A centres whose B = A + D (cos, sin) also fits form a box; the first direction of the
    batch with a non-empty box is used, and A is uniform in that box. Deterministic for a seeded rng."""
    rA, rB = radius[0], radius[1]
    th = rng.uniform(0.0, 2.0 * np.pi, size=max_draws)
    ux, uy = D * np.cos(th), D * np.sin(th)
    xlo, xhi = np.maximum(rA, rB - ux), np.minimum(L - rA, L - rB - ux)
    ylo, yhi = np.maximum(rA, rB - uy), np.minimum(L - rA, L - rB - uy)
    ok = (xhi >= xlo) & (yhi >= ylo)
    assert ok.any(), f"site distance {D} m does not fit in a {L} m map"
    i = int(np.argmax(ok))
    f = rng.uniform(size=2)
    A = np.array([xlo[i] + f[0] * (xhi[i] - xlo[i]), ylo[i] + f[1] * (yhi[i] - ylo[i])])
    centres = [A, A + np.array([ux[i], uy[i]])]
    if len(radius) > 2:
        rC = radius[2]
        cand = rng.uniform(rC, L - rC, size=(max_draws, 2))
        dmin = np.minimum(np.linalg.norm(cand - centres[0], axis=1), np.linalg.norm(cand - centres[1], axis=1))
        good = dmin >= min_sep
        centres.append(cand[int(np.argmax(good))] if good.any() else cand[int(np.argmax(dmin))])
    return np.array(centres)


def make_sites(seed):
    """Scenario fields of a competing-sites scenario. Event timing and share come from their own rng stream, so they
    are the same in every design-grid cell (D, tau) for a seed (paired cells); the geometry from another stream."""
    s, L = CFG["sites"], CFG["area_m"]
    ev = np.random.default_rng([seed, 6])
    t0 = int(ev.integers(s["t0_range_s"][0], s["t0_range_s"][1] + 1))
    share = float(ev.uniform(*s["share_range"]))
    k = int(ev.integers(s["n_sites_range"][0], s["n_sites_range"][1] + 1))
    geo = np.random.default_rng([seed, 7])
    radius = geo.uniform(*s["radius_range_m"], size=k)
    c = place_sites(geo, radius, float(s["distance_m"]), L, int(s["max_draws"]), float(s["min_separation_m"]))
    return {"n_sites": k, "site_x": c[:, 0].tolist(), "site_y": c[:, 1].tolist(), "site_radius_m": radius.tolist(),
            "distance_m": float(s["distance_m"]), "tau_s": float(s["tau_s"]), "announced": bool(s["announced"]),
            "event": str(s["event"]), "event_t0_s": t0, "event_share": share}


def n_movers(sc):
    """Number of users that move from site A to site B: round(share x active users)."""
    return int(round(sc["event_share"] * sc["n_users"]))


def make_site_users(seed, sc):
    """Users of a competing-sites scenario: n_users ACTIVE users at the start (scatter share as in other scenarios,
    n_move movers at A, the rest over the sites by Dirichlet weights) plus n_move RESERVE users at B, inactive at the
    start. Mover k (random order) becomes inactive and its reserve twin (same class) active at t0 + tau * k / n_move.
    Columns as make_users, plus active_from_s / active_until_s (the user counts while from <= t < until)."""
    s, L = CFG["sites"], CFG["area_m"]
    rng = np.random.default_rng([seed, 1])
    n, k, m = sc["n_users"], sc["n_sites"], n_movers(sc)
    n_scatter = int(round(n * sc["scatter_fraction"]))
    rest = n - n_scatter - m
    assert rest >= 0, "share + scatter fraction must not exceed 1"
    counts = rng.multinomial(rest, rng.dirichlet(np.full(k, float(s["site_weight_concentration"]))))
    counts[0] += m                                     # site A also holds the movers
    site = np.concatenate([np.full(c, j) for j, c in enumerate(counts)] + [np.full(n_scatter, -1), np.full(m, 1)])
    N = len(site)
    centres = np.column_stack([sc["site_x"], sc["site_y"]])
    rad = np.asarray(sc["site_radius_m"])
    on = site >= 0
    sid = np.clip(site, 0, None)
    off = np.zeros((N, 2))
    todo = on.copy()
    while todo.any():                                  # truncated Gaussian: redraw the offsets outside the radius
        p = rng.normal(0.0, 1.0, size=(int(todo.sum()), 2)) * (rad[sid[todo]] / 2)[:, None]
        off[todo] = p
        todo[todo] = np.hypot(p[:, 0], p[:, 1]) > rad[sid[todo]]
    xy = np.where(on[:, None], centres[sid] + off, rng.uniform(0, L, size=(N, 2)))
    names = list(CFG["classes"])
    shares = np.array([CFG["classes"][c]["share"] for c in names])
    cls = np.empty(N, dtype=object)
    cls[:n] = rng.choice(names, size=n, p=shares / shares.sum())
    movers = rng.permutation(np.flatnonzero(site[:n] == 0))[:m]       # A users, in switching order
    reserve = np.arange(n, N)
    cls[reserve] = cls[movers]
    t_sw = sc["event_t0_s"] + sc["tau_s"] * np.arange(m) / max(m, 1)
    act_from, act_until = np.zeros(N), np.full(N, np.inf)
    act_until[movers], act_from[reserve] = t_sw, t_sw
    return pd.DataFrame({
        "seed": seed, "user_id": np.arange(N), "x": np.clip(xy[:, 0], 0, L), "y": np.clip(xy[:, 1], 0, L),
        "cluster_id": site, "class": cls.astype(str), "min_rate_bps": np.array([CFG["classes"][c]["min_rate_bps"]
                                                                                for c in cls]),
        "active_from_s": act_from, "active_until_s": act_until})


def activity_mask(u, T, dt):
    """active[t, user] (T+1, n) for the times t * dt, or None when the users table has no activity columns (every user
    always counts: all scenarios except competing sites)."""
    if "active_from_s" not in u:
        return None
    t = np.arange(T + 1)[:, None] * dt
    return (t >= u["active_from_s"].values[None]) & (t < u["active_until_s"].values[None])


def simulate_sites(seed, sc, u):
    """Walking inside the sites: every site user walks random-waypoint legs to uniform points of its own site disc
    (so it never leaves the disc), each leg at a speed from sites.speed_mps, or with probability burst_prob from
    burst_speed_mps (cap 3 m/s). Scattered users stand still. Same output as simulate_positions."""
    s, mob = CFG["sites"], CFG["mobility"]
    rng = np.random.default_rng([seed, 3])
    dt, T = mob["dt_s"], mob["episode_steps"]
    pos = u[["x", "y"]].values.astype(float)
    n = len(pos)
    cid = u["cluster_id"].values
    walk = cid >= 0
    sid = np.clip(cid, 0, None)
    centre = np.column_stack([np.asarray(sc["site_x"])[sid], np.asarray(sc["site_y"])[sid]])
    rad = np.where(walk, np.asarray(sc["site_radius_m"])[sid], 0.0)

    def legs(idx):
        r = rad[idx] * np.sqrt(rng.uniform(size=len(idx))); a = rng.uniform(0, 2 * np.pi, len(idx))
        tgt = centre[idx] + np.column_stack([r * np.cos(a), r * np.sin(a)])
        burst = rng.uniform(size=len(idx)) < s["burst_prob"]
        fast = rng.uniform(*s["burst_speed_mps"], size=len(idx))
        return tgt, np.where(burst, fast, rng.uniform(*s["speed_mps"], size=len(idx)))

    target, speed = pos.copy(), np.zeros(n)
    idx = np.flatnonzero(walk)
    target[idx], speed[idx] = legs(idx)
    P = np.empty((T + 1, n, 2)); V = np.empty((T + 1, n, 2))
    for t in range(T + 1):
        d = target - pos
        dist = np.linalg.norm(d, axis=1)
        step = speed * dt
        arrive = dist <= step
        new = np.where(arrive[:, None], target, pos + d / np.maximum(dist, 1e-9)[:, None] * step[:, None])
        re = np.flatnonzero(arrive & walk)
        if len(re):
            target[re], speed[re] = legs(re)
        P[t], V[t] = pos, (new - pos) / dt
        pos = new
    return P, V


def make_users(seed, sc=None):
    """Users in clusters (2D Gaussian, truncated) + scattered users, with a QoS class each.
    Competing-sites scenarios (mobility `sites`) have their own generator, make_site_users."""
    sc = sc or make_scenario(seed)
    if sc.get("mobility") == "sites":
        return make_site_users(seed, sc)
    if sc.get("mobility") == "place":
        import place
        return place.make_place_users(seed, sc)
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
    """Collapsed-building rectangles for one scenario. Returns a DataFrame (may be empty).
    Place scenarios have no rectangles (their buildings are the height-aware model of scenario_links)."""
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


def scenario_links(seed, sc, users):
    """The obstacle model channel_gain gets for a scenario: the rectangle array (every synthetic scenario, exactly as
    before) or, for a place scenario, its height-aware place.PlaceLinks."""
    if sc.get("mobility") == "place":
        import place
        return place.links_for(seed, users)
    return obstacle_array(make_obstacles(seed, sc))


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
    if sc["mobility"] == "sites":
        return simulate_sites(seed, sc, u)
    if sc["mobility"] == "place":                         # people stay where they are; the event only switches them
        pos = u[["x", "y"]].values.astype(float)
        P = np.repeat(pos[None], CFG["mobility"]["episode_steps"] + 1, axis=0)
        return P, np.zeros_like(P)
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
    if model == "static":                                # the crowd never moves (RL curriculum step 1)
        P = np.repeat(pos[None], T + 1, axis=0)
        return P, np.zeros_like(P)
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
def channel_gain(ux, uy, X, Y, H, boxes=None, rng=None, fading=None, excess_loss_db=None, shadow=None):
    """Linear power gain from drone(s) at (X,Y,H) to users (ux,uy).
    X,Y,H are arrays of shape (P,). Returns (P, N).
    Mean path loss = FSPL + P_LoS*eta_LoS + (1-P_LoS)*eta_NLoS (Al-Hourani).
    boxes: (M,4) obstacle rectangles; a blocked link gets obstacles.excess_loss_db extra loss.
    rng + fading: if rng is given AND fading is on (default: config fading.enabled), each link is drawn
    LoS/NLoS and gets Rician (LoS) / Rayleigh (NLoS) fading
    (unit mean power) instead of the average path loss.
    boxes may instead be a place.PlaceLinks (real-place scenarios): then the user heights (ground or roof + handset)
    enter the distance and elevation angle, and a ray test through the building height grid decides each link
    (place.los_model): `geometric` = the ray test REPLACES Al-Hourani's P_LoS (clear -> eta_LoS, blocked -> eta_NLoS;
    with fading on, the link is LoS/Rician exactly when the ray is clear); `statistical` = Al-Hourani's mean loss plus
    obstacles.excess_loss_db on a blocked ray (the rectangle rule).
    Model mismatch (only the TRUE world passes these; None = the textbook model, bit-exact as before):
    excess_loss_db: the loss of a blocked link instead of obstacles.excess_loss_db.
    shadow: (z, sigma_db), z (N,) = the user's unit-variance shadowing value (user-side field, ShadowField.at);
    the link gets z * shadow_sigma(theta, sigma_db) extra dB (smaller at higher elevation angles)."""
    a2g = CFG["a2g"]
    if boxes is not None and hasattr(boxes, "los_clear"):
        if excess_loss_db is not None or shadow is not None:    # not combined yet: fail loudly, never silently
            raise NotImplementedError("model mismatch (excess_loss_db / shadow) is not defined for real-place links")
        return _place_gain(ux, uy, X, Y, H, boxes, rng, fading)
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
        loss = CFG["obstacles"]["excess_loss_db"] if excess_loss_db is None else excess_loss_db
        pl_db = pl_db + loss * link_blocked(ux, uy, X, Y, boxes)
    if shadow is not None:
        z, sigma_db = shadow
        pl_db = pl_db + np.asarray(z, dtype=float)[None, :] * shadow_sigma(theta, sigma_db)
    return 10 ** (-pl_db / 10) * fade


def _place_gain(ux, uy, X, Y, H, links, rng=None, fading=None):
    """channel_gain for a real-place scenario (see channel_gain)."""
    a2g = CFG["a2g"]
    uz = links.user_z(ux, uy)
    dx = ux[None, :] - X[:, None]
    dy = uy[None, :] - Y[:, None]
    dz = np.maximum(H[:, None] - uz[None, :], 0.0)
    d = np.maximum(np.sqrt(dx**2 + dy**2 + dz**2), 1.0)
    fspl = 20 * np.log10(4 * np.pi * CFG["fc_hz"] * d / C)
    clear = links.los_clear(ux, uy, X, Y, H)
    fade_on = rng is not None and (CFG["fading"]["enabled"] if fading is None else fading)
    if CFG["place"]["los_model"] == "geometric":
        pl_db = fspl + np.where(clear, a2g["eta_los_db"], a2g["eta_nlos_db"])
        los = clear
    else:
        theta = np.degrees(np.arcsin(dz / d))
        p_los = 1.0 / (1.0 + a2g["a"] * np.exp(-a2g["b"] * (theta - a2g["a"])))
        pl_db = fspl + p_los * a2g["eta_los_db"] + (1 - p_los) * a2g["eta_nlos_db"]
        los = None
        if fade_on:                      # LoS/NLoS drawn from Al-Hourani's P_LoS, as for the rectangles
            los = rng.uniform(size=d.shape) < p_los
            pl_db = fspl + np.where(los, a2g["eta_los_db"], a2g["eta_nlos_db"])
        pl_db = pl_db + CFG["obstacles"]["excess_loss_db"] * ~clear
    fade = 1.0
    if fade_on:
        K = 10 ** (CFG["fading"]["rician_k_db"] / 10)
        cn = (rng.normal(size=d.shape) + 1j * rng.normal(size=d.shape)) / np.sqrt(2)
        fade = np.where(los, np.abs(np.sqrt(K / (K + 1)) + cn / np.sqrt(K + 1)) ** 2, np.abs(cn) ** 2)
    return 10 ** (-pl_db / 10) * fade


# ---------------------------------------------------------------- model mismatch (the TRUE world vs the textbook)
# Config `mismatch:`. With every option at its default (sigma 0, excess_loss_db null, hidden_obstacles 0) nothing
# below is used and the game is the old one, bit for bit. Each perturbation has its OWN rng stream
# (scenario seed, stream id, mismatch.draw), so switching one on never changes the others, and `draw` re-draws the
# perturbation for the same scenario (memorisation check).
MM_STREAM_SHADOW, MM_STREAM_HIDDEN = 101, 103


def mismatch_cfg():
    return CFG.get("mismatch") or {}


def mismatch_on():
    m = mismatch_cfg()
    return bool(m.get("shadow_sigma_db", 0.0) or m.get("excess_loss_db") is not None
                or m.get("hidden_obstacles", 0))


def shadow_sigma(theta_deg, sigma_db):
    """Elevation-dependent shadowing std (dB): sigma_db * (1 - theta / 90). Full at grazing angles, 0 straight
    overhead (the user's surroundings block a low link more often). ENGINEERING ASSUMPTION (linear form; published A2G
    models use a std that falls with elevation, e.g. the Al-Hourani Globecom 2014 / 3GPP TR 36.777 Annex B shadow-fading
    tables: TO BE READ, not verified)."""
    return sigma_db * (1.0 - np.clip(theta_deg, 0.0, 90.0) / 90.0)


class ShadowField:
    """A fixed, spatially correlated, unit-variance Gaussian field over the map (the user's surroundings), one per
    scenario and draw. White noise on a grid of spacing corr_m * res_frac, smoothed by a Gaussian kernel of std corr_m/2
    (so the correlation exp(-d^2 / corr_m^2) falls to 1/e at d = corr_m), normalised by the kernel's norm (unit variance
    in expectation, not per map: a scenario may be darker or brighter overall). Users read it by bilinear interpolation
    at their own position. Vectorised; seeded (rng stream [seed, MM_STREAM_SHADOW, draw])."""

    def __init__(self, seed, L, corr_m, res_frac=0.25, draw=0):
        self.L, self.corr = float(L), float(corr_m)
        self.dx = self.corr * float(res_frac)
        s = self.corr / 2.0 / self.dx                         # kernel std in cells
        r = int(np.ceil(4 * s))
        n = int(np.ceil(self.L / self.dx)) + 1                # grid nodes 0, dx, ..., >= L
        rng = np.random.default_rng([int(seed), MM_STREAM_SHADOW, int(draw)])
        w = rng.standard_normal((n + 2 * r, n + 2 * r))
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
        k /= np.sqrt(np.sum(k ** 2))                          # unit variance after the 2-D filter outer(k, k)
        # separable convolution, 'valid' part only (the padding r keeps the edges as random as the middle)
        rows = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, w)
        self.z = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, rows)   # (n, n), x index major
        self.n = n

    def at(self, ux, uy):
        """Field value at user positions (bilinear interpolation; positions clipped to the map)."""
        fx = np.clip(np.asarray(ux, dtype=float), 0.0, self.L) / self.dx
        fy = np.clip(np.asarray(uy, dtype=float), 0.0, self.L) / self.dx
        i0 = np.minimum(np.floor(fx).astype(int), self.n - 2)
        j0 = np.minimum(np.floor(fy).astype(int), self.n - 2)
        tx, ty = fx - i0, fy - j0
        z = self.z
        return ((1 - tx) * (1 - ty) * z[i0, j0] + tx * (1 - ty) * z[i0 + 1, j0]
                + (1 - tx) * ty * z[i0, j0 + 1] + tx * ty * z[i0 + 1, j0 + 1])


def hidden_obstacles(seed, n, draw=0):
    """(n, 4) extra collapsed-building rectangles that exist in the TRUE world only (absent from the planner's map).
    Same size range and placement rule as make_obstacles, own rng stream [seed, MM_STREAM_HIDDEN, draw]."""
    if n <= 0:
        return np.zeros((0, 4))
    rng = np.random.default_rng([int(seed), MM_STREAM_HIDDEN, int(draw)])
    L = CFG["area_m"]
    lo, hi = CFG["obstacles"]["size_range_m"]
    w, h = rng.uniform(lo, hi, size=n), rng.uniform(lo, hi, size=n)
    cx, cy = rng.uniform(0, L, size=n), rng.uniform(0, L, size=n)
    return np.column_stack([np.clip(cx - w / 2, 0, L), np.clip(cy - h / 2, 0, L),
                            np.clip(cx + w / 2, 0, L), np.clip(cy + h / 2, 0, L)])


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


# ---------------------------------------------------------------- QoS-aware access (book 14.6 step 2)
# Two extra schemes that give every user JUST its minimum rate and admit as many users as the total power allows:
#   oma_opt : FDMA, equal slices b = B/N, minimum power per user, cheapest users first.
#   noma_opt: hybrid NOMA, admitted users paired weakest-with-strongest on slices 2b; each pair uses NOMA with the
#             minimum-power split (closed form below) or OMA inside the pair, whichever needs less power.
# Unserved users get rate 0 and their slice is wasted (same rule for both). Leftover power is spread over the admitted
# users by one common factor (keeps every power ratio, so NOMA decoding still works and every rate only goes up).
ACCESS_SCHEMES = ("noma", "oma", "oma_opt", "noma_opt")
QOS_SCHEMES = ("oma_opt", "noma_opt")


def oma_min_power(g, rate, noise_psd_w, b):
    """Minimum power (W) for `rate` (bit/s) on its own slice of b Hz: (2^(R/b) - 1) * noise_psd * b / g."""
    return (2.0 ** (rate / b) - 1.0) * noise_psd_w * b / g


def noma_pair_power(gs, gw, rs, rw, noise_psd_w, bp, eps=0.0):
    """Minimum powers (p_s, p_w) so a NOMA pair on bp Hz gives the strong user (gain gs >= gw) rate rs and the weak
    user rate rw. The weak user treats the strong user's signal as noise; the strong user removes the weak user's
    signal by SIC, leaving the fraction eps of its power (imperfect SIC, eps = 0: perfect):
        gamma = 2^(R / bp) - 1,  N = noise_psd * bp
        p_s = gamma_s N (eps gamma_w / g_w + 1 / g_s) / (1 - eps gamma_s gamma_w)
        p_w = gamma_w (p_s + N / g_w)
    Infeasible (both inf) when eps gamma_s gamma_w >= 1."""
    n0 = noise_psd_w * bp
    gam_s, gam_w = 2.0 ** (rs / bp) - 1.0, 2.0 ** (rw / bp) - 1.0
    den = 1.0 - eps * gam_s * gam_w
    ok = den > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        p_s = np.where(ok, gam_s * n0 * (eps * gam_w / gw + 1.0 / gs) / np.where(ok, den, 1.0), np.inf)
        p_w = np.where(ok, gam_w * (p_s + n0 / gw), np.inf)
    return p_s, p_w


def noma_pair_rates(p_s, p_w, gs, gw, noise_psd_w, bp, eps=0.0):
    """Rates (r_s, r_w) of a NOMA pair with powers p_s, p_w on bp Hz (imperfect SIC residual eps at the strong user)."""
    n0 = noise_psd_w * bp
    r_w = bp * np.log2(1.0 + p_w * gw / (p_s * gw + n0))
    r_s = bp * np.log2(1.0 + p_s * gs / (eps * p_w * gs + n0))
    return r_s, r_w


def _admission_order(c, p_tx_w, prio):
    """(P, N) user order for admission: cheapest OMA cost first. With a priority mask (rescue_first), the priority
    users that fit by OMA cost come first (cheapest first), then the others, then the priority users that cannot fit."""
    if prio is None or not prio.any():
        return np.argsort(c, axis=1, kind="stable")
    cr = np.where(prio[None], c, np.inf)
    rank_r = np.argsort(np.argsort(cr, axis=1, kind="stable"), axis=1, kind="stable")
    m_r = (np.cumsum(np.sort(cr, axis=1), axis=1) <= p_tx_w).sum(axis=1)       # priority users that fit alone
    group = np.where(prio[None], np.where(rank_r < m_r[:, None], 0, 2), 1)
    return np.lexsort((c, group), axis=-1)


def _ranks(order):
    rank = np.empty_like(order)
    np.put_along_axis(rank, order, np.arange(order.shape[1])[None].repeat(len(order), 0), axis=1)
    return rank


def _oma_opt(G, p_tx_w, noise_psd_w, B, R, prio):
    P_, N = G.shape
    b = B / N
    c = oma_min_power(G, R[None], noise_psd_w, b)
    order = _admission_order(c, p_tx_w, prio)
    cum = np.cumsum(np.take_along_axis(c, order, axis=1), axis=1)
    m = (cum <= p_tx_w).sum(axis=1)                            # prefix: the cheapest users that fit
    served = _ranks(order) < m[:, None]
    total = np.where(m > 0, cum[np.arange(P_), np.maximum(m - 1, 0)], 0.0)
    f = np.where(total > 0, p_tx_w / np.where(total > 0, total, 1.0), 0.0)
    gam = 2.0 ** (R / b) - 1.0                                  # admitted user's SNR at minimum power = gamma
    rates = np.where(served, b * np.log2(1.0 + f[:, None] * gam[None]), 0.0)
    zero = np.zeros(P_, int)
    return rates, served, dict(pairs=zero, noma_pairs=zero, alpha_lt_half=zero, power_used_w=f * total,
                               power_w=np.where(served, f[:, None] * c, 0.0), partner=np.full((P_, N), -1))


def _noma_plan(G, c, R, rank, order, k, noise_psd_w, b, eps):
    """Pair plan for admitting the first 2k users of `order` in every row (k: (P,) ints). The admitted users are
    sorted by gain and paired j <-> 2k-1-j. Returns per-pair arrays (P, N//2) and the total power per row."""
    P_, N = G.shape
    rows = np.arange(P_)[:, None]
    adm = rank < 2 * k[:, None]
    srt = np.argsort(np.where(adm, G, np.inf), axis=1, kind="stable")   # admitted users first, by rising gain
    j = np.arange(N // 2)[None]
    valid = j < k[:, None]
    wi = srt[:, : N // 2]
    si = np.take_along_axis(srt, np.clip(2 * k[:, None] - 1 - j, 0, N - 1), axis=1)
    gw, gs = G[rows, wi], G[rows, si]
    p_s, p_w = noma_pair_power(gs, gw, R[si], R[wi], noise_psd_w, 2 * b, eps)
    oma_cost = c[rows, si] + c[rows, wi]
    use_noma = (p_s + p_w) <= oma_cost
    cost = np.where(valid, np.minimum(p_s + p_w, oma_cost), 0.0)
    return dict(valid=valid, wi=wi, si=si, p_s=p_s, p_w=p_w, use_noma=use_noma & valid), cost.sum(axis=1)


def _noma_opt(G, p_tx_w, noise_psd_w, B, R, prio, eps, search="binary"):
    P_, N = G.shape
    b = B / N
    c = oma_min_power(G, R[None], noise_psd_w, b)
    order = _admission_order(c, p_tx_w, prio)
    rank = _ranks(order)
    lo, hi = np.zeros(P_, int), np.full(P_, N // 2)
    if search == "binary":          # largest k whose plan fits (k = 0 always fits); log2(N) plans per row
        while (lo < hi).any():
            mid = (lo + hi + 1) // 2
            ok = _noma_plan(G, c, R, rank, order, mid, noise_psd_w, b, eps)[1] <= p_tx_w
            act = lo < hi
            lo, hi = np.where(act & ok, mid, lo), np.where(act & ~ok, mid - 1, hi)
    else:                           # "linear": the full scan, for tests only
        for k in range(1, N // 2 + 1):
            ok = _noma_plan(G, c, R, rank, order, np.full(P_, k), noise_psd_w, b, eps)[1] <= p_tx_w
            lo = np.where(ok, k, lo)
    plan, total = _noma_plan(G, c, R, rank, order, lo, noise_psd_w, b, eps)
    rows = np.arange(P_)
    # one more user alone on a slice b, the next in the admission order, if its OMA power still fits
    nxt = order[rows, np.minimum(2 * lo, N - 1)]
    single = (2 * lo < N) & (total + c[rows, nxt] <= p_tx_w)
    total = total + np.where(single, c[rows, nxt], 0.0)
    f = np.where(total > 0, p_tx_w / np.where(total > 0, total, 1.0), 0.0)[:, None]
    rates = np.zeros((P_, N))
    served = np.zeros((P_, N), bool)
    v, wi, si, un = plan["valid"], plan["wi"], plan["si"], plan["use_noma"]
    rr = np.broadcast_to(rows[:, None], wi.shape)
    gam_b = 2.0 ** (R / b) - 1.0
    with np.errstate(invalid="ignore"):
        r_s, r_w = noma_pair_rates(f * plan["p_s"], f * plan["p_w"], G[rr, si], G[rr, wi], noise_psd_w, 2 * b, eps)
    o_s, o_w = (b * np.log2(1.0 + f * gam_b[idx]) for idx in (si, wi))
    rates[rr[v], si[v]] = np.where(un, r_s, o_s)[v]
    rates[rr[v], wi[v]] = np.where(un, r_w, o_w)[v]
    served[rr[v], si[v]] = served[rr[v], wi[v]] = True
    rates[rows[single], nxt[single]] = b * np.log2(1.0 + f[single, 0] * gam_b[nxt[single]])
    served[rows[single], nxt[single]] = True
    # final per-user powers, and each user's NOMA partner (-1: alone on its slice, OMA inside the pair, or unserved)
    power = np.where(served, f * c, 0.0)
    partner = np.full((P_, N), -1)
    vn = v & un
    power[rr[vn], si[vn]], power[rr[vn], wi[vn]] = (f * plan["p_s"])[vn], (f * plan["p_w"])[vn]
    partner[rr[vn], si[vn]], partner[rr[vn], wi[vn]] = wi[vn], si[vn]
    with np.errstate(invalid="ignore"):
        alpha = plan["p_w"] / (plan["p_s"] + plan["p_w"])
    info = dict(pairs=v.sum(axis=1), noma_pairs=un.sum(axis=1), alpha_lt_half=(un & (alpha < 0.5)).sum(axis=1),
                power_used_w=f[:, 0] * total, power_w=power, partner=partner)
    return rates, served, info


def access_rates(G, p_tx_w, noise_psd_w, B, min_rate, scheme, pairing="extreme", rng=None, eps=0.0, rescue=None,
                 rescue_first=False, return_info=False, search="binary"):
    """Per-user rates (bit/s) under one access scheme, for one drone position (G: (N,)) or many (G: (P, N)).
    scheme: noma | oma  -> exactly noma_rates (fixed 80/20 NOMA split; equal-power FDMA);
            oma_opt     -> QoS-aware FDMA (cheapest users first, each at its minimum power);
            noma_opt    -> hybrid NOMA (admit-then-pair, minimum-power split, NOMA or OMA per pair).
    min_rate: (N,) each user's minimum rate. eps: imperfect-SIC residual (noma_opt only). rescue + rescue_first:
    admit the rescue users first (lexicographic). pairing / rng apply to noma | oma only (noma_opt always pairs
    weakest with strongest inside the admitted set).
    return_info=True -> (rates, info): info["served"] (bool, same shape) plus, per position, pairs, noma_pairs,
    alpha_lt_half (NOMA-mode pairs whose weak user gets less than half the pair's power) and power_used_w; for
    oma_opt / noma_opt also per user power_w (final transmit power) and partner (NOMA partner index, else -1).
    search: "binary" (default) or "linear" (full scan of the number of pairs; for tests)."""
    assert scheme in ACCESS_SCHEMES, f"unknown access scheme {scheme!r}; choose from {ACCESS_SCHEMES}"
    G = np.asarray(G, dtype=float)
    one = G.ndim == 1
    G2 = G[None] if one else G
    R = np.broadcast_to(np.asarray(min_rate, dtype=float), G2.shape[1:])
    if scheme in ("noma", "oma"):
        pick = 0 if scheme == "noma" else 1
        rates = np.array([noma_rates(g, p_tx_w, noise_psd_w, B, pairing, rng)[pick] for g in G2])
        served = rates >= R[None]
        zero = np.zeros(len(G2), int)
        info = dict(pairs=zero + G2.shape[1] // 2 * (scheme == "noma"), noma_pairs=zero, alpha_lt_half=zero,
                    power_used_w=np.full(len(G2), float(p_tx_w)))
    else:
        prio = np.asarray(rescue, bool) if (rescue_first and rescue is not None) else None
        if scheme == "oma_opt":
            rates, served, info = _oma_opt(G2, p_tx_w, noise_psd_w, B, R, prio)
        else:
            rates, served, info = _noma_opt(G2, p_tx_w, noise_psd_w, B, R, prio, eps, search)
        # admitted users meet their rate exactly at the minimum powers and above it after scaling; only round-off
        # (relative 1e-9) can put them a hair below, which would wrongly count them as unserved
        rates = np.where(served & (rates >= R[None] * (1 - 1e-9)), np.maximum(rates, R[None]), rates)
    if one:
        rates, served = rates[0], served[0]
        info = {k: v[0] for k, v in info.items()}
    info["served"] = served
    return (rates, info) if return_info else rates


def load_factor(a_h):
    """Load factor kappa = thrust / weight when the drone accelerates horizontally at a_h (m/s^2):
    kappa = sqrt(1 + (a_h / g)^2). OUR EXTENSION (not in Zeng's steady straight-flight model): quasi-steady rotor
    thrust must carry the weight AND push the mass sideways, T = m * sqrt(g^2 + a_h^2), whatever the direction of
    a_h (speeding up, braking or turning). kappa = 1 at a_h = 0 and grows monotonically with |a_h|."""
    return np.sqrt(1.0 + (np.asarray(a_h, dtype=float) / CFG["energy"]["g_mps2"]) ** 2)


def propulsion_power_w(v, kappa=1.0):
    """Rotary-wing propulsion power (Zeng, Xu, Zhang) at horizontal speed v (m/s). Hover = P0 + Pi.
    kappa (load factor, default 1 = Zeng's steady flight): OUR EXTENSION for accelerating / turning flight. Momentum
    theory with thrust kappa * W: induced hover power Pi ~ T^1.5 -> Pi * kappa^1.5, induced velocity
    v0 ~ sqrt(T) -> v0 * sqrt(kappa); blade-profile and parasite terms are unchanged. kappa = 1 gives Zeng exactly."""
    e = CFG["energy"]
    pi_w = e["Pi_w"] * kappa**1.5
    v0 = e["v0_mps"] * kappa**0.5
    blade = e["P0_w"] * (1 + 3 * v**2 / e["Utip_mps"] ** 2)
    induced = pi_w * np.sqrt(np.sqrt(1 + v**4 / (4 * v0**4)) - v**2 / (2 * v0**2))
    parasite = 0.5 * e["d0"] * e["rho_kg_m3"] * e["s"] * e["A_m2"] * v**3
    return blade + induced + parasite


def energy_step_j(v_h, vz, p_tx_w, a_h=None):
    """Energy for one step: propulsion + climbing (weight x climb rate, no recovery when descending)
    + communication (P_tx / PA efficiency) + circuit.
    a_h: realised horizontal acceleration (m/s^2) during the step. None (default) = Zeng's steady flight, exactly the
    old numbers. Given (the env passes it only when uav.a_max_mps2 is set and energy.accel_power is true), the
    propulsion term becomes propulsion_power_w(v_h, load_factor(a_h)) (OUR EXTENSION)."""
    e = CFG["energy"]
    climb = e["weight_n"] * np.maximum(vz, 0.0)
    comm = p_tx_w / e["pa_efficiency"]
    prop = propulsion_power_w(v_h) if a_h is None else propulsion_power_w(v_h, load_factor(a_h))
    return (prop + climb + comm + e["P_circuit_w"]) * e["dt_s"]


def min_power_speed(v_max, radius_m=None, a_max=None, tol=1e-6):
    """Speed (m/s) in [0, v_max] that minimises the propulsion power: Zeng's minimum-power speed v* when
    radius_m is None. With radius_m (a loiter circle) and the accel-energy term on, the centripetal acceleration
    v^2 / r raises the load factor, so the minimum moves; a_max (if given) also caps v at sqrt(a_max * r), the fastest
    speed the drone can hold on that circle. Golden-section search on a fine grid's best bracket (no magic constant)."""
    hi = float(v_max) if radius_m is None or a_max is None else float(min(v_max, np.sqrt(a_max * radius_m)))

    def p(v):
        if radius_m is None:
            return propulsion_power_w(v)
        return propulsion_power_w(v, load_factor(v * v / radius_m))

    grid = np.linspace(0.0, hi, 401)
    vals = np.array([p(v) for v in grid])
    i = int(np.argmin(vals))
    lo_b, hi_b = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
    phi = (np.sqrt(5) - 1) / 2
    while hi_b - lo_b > tol:
        c, d = hi_b - phi * (hi_b - lo_b), lo_b + phi * (hi_b - lo_b)
        if p(c) <= p(d):
            hi_b = d
        else:
            lo_b = c
    return float((lo_b + hi_b) / 2)


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
    for a, s in zip(ax, seeds("train")[:4], strict=True):
        sc = make_scenario(s); u = make_users(s, sc)
        for cid, g in u.groupby("cluster_id"):
            a.scatter(g.x, g.y, s=8, label="scatter" if cid == -1 else f"cluster {cid}")
        r = u[u["class"] == "rescue"]
        a.scatter(r.x, r.y, s=30, facecolors="none", edgecolors="k", label="rescue")
        a.set_title(f"seed {s}: {sc['n_users']} users, {sc['n_clusters']} clusters")
        a.set_xlim(0, CFG["area_m"]); a.set_ylim(0, CFG["area_m"]); a.set_aspect("equal")
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
