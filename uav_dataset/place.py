"""Real-place scenarios (case study: a scenario based on the September 2024 Kathmandu (Bagmati river) floods).
Map data (c) OpenStreetMap contributors, ODbL 1.0. Only used when a scenario's mobility model is `place`.

Three parts, all driven by config.yaml `place:` / `places:` and the committed processed map places/<name>.json
(osm_place.py makes it; no internet is needed here):

1. The city (`Scene`, loaded once per process): building footprints rasterised to a HEIGHT GRID (cell raster_m, 2 m);
   missing heights are filled deterministically; the distance of every cell to the flood river's centreline; the
   shelter candidates.
2. The crowd (`make_place_scenario`, `make_place_users`): RECONSTRUCTED from the map with engineering assumptions
   (flood band, stranded people on roofs, people on dry ground and at shelters, an evacuation event). Static positions;
   the event switches people from roofs to shelters with the activity mask of the competing-sites scenarios (D-52).
3. The radio links (`PlaceLinks`): a HEIGHT-AWARE line-of-sight test. A user at height z_u (ground or roof + handset
   height) sees a drone at (X, Y, H) if no raster cell along the straight 3-D ray is taller than the ray there. The ray
   is sampled every raster_m metres horizontally, from the user toward the drone, and only as far as the ray is still
   below the tallest building of the map (beyond that nothing can block it). Results are cached per drone position for
   the whole user pool of the scenario (users never move in place scenarios, only switch on/off), so the 980-candidate
   search of B6 costs one ray test per scenario, not one per decision.
make_dataset.channel_gain uses PlaceLinks when it is passed as `boxes` (see there for the path-loss rule).
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MplPath

import make_dataset as md

HERE = Path(__file__).parent


def pcfg():
    return md.CFG["place"]


def place_info(name=None):
    name = name or pcfg()["name"]
    return {**md.CFG["places"][name], "name": name}


# ---------------------------------------------------------------- the city
def load_place(name):
    """The committed processed map (dict, local metres)."""
    return json.loads((HERE / "places" / f"{name}.json").read_text(encoding="utf-8"))


def fill_heights(buildings, c):
    """Heights (m) for every building. Tagged heights (height, or levels x levels_m) are kept unless above
    max_plausible_height_m (treated as a tagging error = missing). Missing ones: drawn from the plausible tagged heights
    of the same map (`empirical`, if at least min_tagged) or uniform in default_height_range_m; one seeded draw over the
    buildings in file order (deterministic). Returns (heights, source) with source 0 = tag, 1 = filled, 2 = implausible
    tag replaced."""
    h = np.array([np.nan if b["h"] is None else float(b["h"]) for b in buildings])
    src = np.where(np.isnan(h), 1, 0)
    bad = h > float(c["max_plausible_height_m"])
    src[bad], h[bad] = 2, np.nan
    miss = np.isnan(h)
    rng = np.random.default_rng([int(c["height_seed"]), 9])
    pool = h[~miss]
    if c["default_height"] == "empirical" and len(pool) >= int(c["min_tagged"]):
        h[miss] = rng.choice(np.sort(pool), size=int(miss.sum()))
    else:
        h[miss] = rng.uniform(*c["default_height_range_m"], size=int(miss.sum()))
    return h, src


def rasterise(buildings, heights, side, cell):
    """Height grid (n, n) float32, index [ix, iy] (x major, like the maps): the tallest building whose footprint
    contains the cell centre. Also the building id grid (-1 = open ground)."""
    n = int(round(side / cell))
    grid = np.zeros((n, n), np.float32)
    bid = np.full((n, n), -1, np.int32)
    for k, b in enumerate(buildings):
        xy = np.asarray(b["xy"], dtype=float)
        i0, j0 = np.floor(xy.min(axis=0) / cell).astype(int)
        i1, j1 = np.ceil(xy.max(axis=0) / cell).astype(int)
        i0, j0, i1, j1 = max(i0, 0), max(j0, 0), min(i1, n), min(j1, n)
        if i1 <= i0 or j1 <= j0:
            continue
        ci, cj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1), indexing="ij")
        pts = np.column_stack([(ci.ravel() + 0.5) * cell, (cj.ravel() + 0.5) * cell])
        inside = MplPath(xy).contains_points(pts).reshape(ci.shape)
        upd = inside & (heights[k] > grid[i0:i1, j0:j1])
        grid[i0:i1, j0:j1][upd] = heights[k]
        bid[i0:i1, j0:j1][upd] = k
    return grid, bid


def polyline_distance(px, py, lines):
    """Distance (m) of points (px, py) to a set of polylines (list of (k, 2) arrays); vectorised, chunked."""
    seg = np.vstack([np.column_stack([ln[:-1], ln[1:]]) for ln in lines if len(ln) > 1])     # (S, 4)
    ax, ay, bx, by = seg.T
    vx, vy = bx - ax, by - ay
    vv = np.maximum(vx * vx + vy * vy, 1e-12)
    out = np.full(len(px), np.inf)
    step = max(1, 4_000_000 // max(len(seg), 1))
    for s in range(0, len(px), step):
        x, y = px[s:s + step, None], py[s:s + step, None]
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / vv, 0.0, 1.0)
        out[s:s + step] = np.sqrt((x - ax - t * vx) ** 2 + (y - ay - t * vy) ** 2).min(axis=1)
    return out


def distance_field(lines, side, cc, step):
    """Distance (m) to the polylines at the raster cell centres cc (both axes): exact on a coarse grid (spacing `step`,
    ENGINEERING CHOICE 10 m), bilinear in between (distance is 1-Lipschitz: the error is below step / sqrt(2) and in
    practice well under a metre except right on the centreline). Segments farther than `side` from the map are dropped
    (they cannot be the nearest one for any distance below that)."""
    keep = []
    for ln in lines:
        far = (ln[:, 0] < -side) | (ln[:, 0] > 2 * side) | (ln[:, 1] < -side) | (ln[:, 1] > 2 * side)
        near = ~(far[:-1] & far[1:])
        for k in np.flatnonzero(near):
            keep.append(ln[k:k + 2])
    g = np.arange(0.0, side + step, step)
    GX, GY = np.meshgrid(g, g, indexing="ij")
    D = polyline_distance(GX.ravel(), GY.ravel(), keep).reshape(len(g), len(g))
    f = np.clip(cc / step, 0, len(g) - 1 - 1e-9)
    i0 = f.astype(int)
    w = f - i0
    a = D[i0][:, i0] * (1 - w)[None, :] + D[i0][:, i0 + 1] * w[None, :]
    b = D[i0 + 1][:, i0] * (1 - w)[None, :] + D[i0 + 1][:, i0 + 1] * w[None, :]
    return a * (1 - w)[:, None] + b * w[:, None]


class Scene:
    """The static city of one place: height grid, building ids, distance to the flood river, shelters."""

    def __init__(self, name):
        c, info = pcfg(), place_info(name)
        raw = load_place(name)
        self.name, self.title, self.credit = name, info["title"], raw["credit"]
        self.side, self.cell = float(raw["side_m"]), float(c["raster_m"])
        assert abs(self.side - md.CFG["area_m"]) < 1e-9, "the place side must equal area_m (use the place profile)"
        self.buildings = raw["buildings"]
        self.heights, self.height_src = fill_heights(self.buildings, c)
        self.grid, self.bid = rasterise(self.buildings, self.heights, self.side, self.cell)
        self.n = self.grid.shape[0]
        self.hmax = float(self.grid.max())
        want = [w.lower() for w in info["rivers"]]
        self.rivers = [np.asarray(r["xy"], dtype=float) for r in raw["rivers"]
                       if any(w in r["name"].lower() for w in want)]
        self.other_rivers = [np.asarray(r["xy"], dtype=float) for r in raw["rivers"]
                             if not any(w in r["name"].lower() for w in want)]
        assert self.rivers, f"no waterway named {info['rivers']} in places/{name}.json"
        cc = (np.arange(self.n) + 0.5) * self.cell
        CX, CY = np.meshgrid(cc, cc, indexing="ij")
        self.dist = distance_field(self.rivers, self.side, cc, float(c["dist_grid_m"])).astype(np.float32)
        self.shelters = raw["shelters"]
        # building centroid (mean of its raster cells) and its distance to the river, area in cells
        flat = self.bid.ravel()
        on = flat >= 0
        nb = len(self.buildings)
        self.b_cells = np.bincount(flat[on], minlength=nb)
        self.b_cx = np.bincount(flat[on], weights=CX.ravel()[on], minlength=nb) / np.maximum(self.b_cells, 1)
        self.b_cy = np.bincount(flat[on], weights=CY.ravel()[on], minlength=nb) / np.maximum(self.b_cells, 1)
        self.b_dist = np.bincount(flat[on], weights=self.dist.ravel()[on], minlength=nb) / np.maximum(self.b_cells, 1)

    def cell_of(self, x, y):
        i = np.clip((np.asarray(x) / self.cell).astype(int), 0, self.n - 1)
        j = np.clip((np.asarray(y) / self.cell).astype(int), 0, self.n - 1)
        return i, j

    def height_at(self, x, y):
        i, j = self.cell_of(x, y)
        return self.grid[i, j].astype(float)

    def dist_at(self, x, y):
        i, j = self.cell_of(x, y)
        return self.dist[i, j].astype(float)

    def fingerprint(self):
        """Hash of the height grid (tests: processing is deterministic)."""
        return hashlib.sha1(self.grid.tobytes() + self.bid.tobytes()).hexdigest()


def _settings_key():
    c = pcfg()
    return json.dumps({k: c[k] for k in ("name", "levels_m", "default_height", "min_tagged", "default_height_range_m",
                                         "height_seed", "raster_m", "max_plausible_height_m")}, sort_keys=True) \
        + f"|{md.CFG['area_m']}|" + json.dumps(md.CFG["places"][c["name"]], sort_keys=True)


@lru_cache(maxsize=2)
def _scene(key):
    return Scene(json.loads(key.split("|")[0])["name"])


def scene():
    """The Scene of the configured place (built once per process and settings)."""
    return _scene(_settings_key())


# ---------------------------------------------------------------- the crowd (all ENGINEERING ASSUMPTIONS)
def _shelter_candidates(S, c):
    kinds = set(c["shelter_kinds"])
    sh = [s for s in S.shelters if s["kind"] in kinds]
    xy = np.array([[s["x"], s["y"]] for s in sh]) if sh else np.zeros((0, 2))
    d = S.dist_at(xy[:, 0], xy[:, 1]) if len(xy) else np.zeros(0)
    W = float(c["flood_band_m"])
    ok = (d > W) & (d <= W + float(c["shelter_max_dist_m"]))
    return [s for s, k in zip(sh, ok, strict=True) if k], xy[ok]


def make_place_scenario(seed):
    """Scenario fields of a place scenario (own rng streams; the base make_scenario fields are overwritten)."""
    c, S = pcfg(), scene()
    rng = np.random.default_rng([seed, 8])
    n = int(rng.choice(c["n_users_choices"]))
    assert n % 2 == 0, "n_users must be even (NOMA pairs)"
    f_str = float(rng.uniform(*c["stranded_share_range"]))
    f_sh = float(rng.uniform(*c["shelter_share_range"]))
    f_sc = float(rng.uniform(*c["scatter_fraction_range"]))
    assert f_str + f_sh + f_sc < 1.0, "stranded + shelter + scatter shares must leave room for the dry-ground groups"
    k_dry = int(rng.integers(c["dry_groups_range"][0], c["dry_groups_range"][1] + 1))
    shel, sxy = _shelter_candidates(S, c)
    assert len(shel) > 0, "no dry shelter candidate within reach of the flood band"
    k_sh = int(min(len(shel), rng.integers(1, int(c["n_shelters_max"]) + 1)))
    pick = np.sort(rng.choice(len(shel), size=k_sh, replace=False))
    ev = np.random.default_rng([seed, 6])
    t0 = int(ev.integers(c["t0_range_s"][0], c["t0_range_s"][1] + 1))
    share = float(ev.uniform(*c["evac_share_range"])) if c["event"] else 0.0
    n_str = int(round(n * f_str)); n_sh = int(round(n * f_sh)); n_sc = int(round(n * f_sc))
    return {"n_users": n, "bandwidth_hz": n * md.CFG["bandwidth_per_user_hz"], "place": S.name,
            "flood_band_m": float(c["flood_band_m"]), "n_stranded": n_str, "n_shelter": n_sh, "n_scatter": n_sc,
            "n_dry": n - n_str - n_sh - n_sc, "n_dry_groups": k_dry, "n_clusters": k_dry + k_sh,
            "scatter_fraction": n_sc / n, "cluster_radius_m": float(c["shelter_radius_m"]), "n_obstacles": 0,
            "n_shelters": k_sh, "shelter_x": sxy[pick, 0].tolist(), "shelter_y": sxy[pick, 1].tolist(),
            "shelter_name": [shel[i]["name"] or shel[i]["kind"] for i in pick],
            "shelter_kind": [shel[i]["kind"] for i in pick],
            "event": "evacuation" if c["event"] else "none", "event_t0_s": t0 if c["event"] else None,
            "tau_s": float(c["tau_s"]), "event_share": share, "announced": False}


def _cells_point(S, rng, flat_idx):
    """Uniform points inside the given raster cells (flat indices, x major)."""
    i, j = np.divmod(np.asarray(flat_idx), S.n)
    u = rng.uniform(size=(len(i), 2))
    return np.column_stack([(i + u[:, 0]) * S.cell, (j + u[:, 1]) * S.cell])


def _near_cells(S, rng, open_flat, centres, std, counts):
    """counts[k] points on open cells around centres[k] (Gaussian weights with std[k] over the eligible cells)."""
    ci, cj = np.divmod(open_flat, S.n)
    cx, cy = (ci + 0.5) * S.cell, (cj + 0.5) * S.cell
    out = []
    for (x0, y0), sd, k in zip(centres, std, counts, strict=True):
        if k == 0:
            continue
        w = np.exp(-((cx - x0) ** 2 + (cy - y0) ** 2) / (2 * sd * sd))
        w[w < 1e-12] = 0.0
        if w.sum() <= 0:                                    # no open cell nearby: nearest open cells
            w = np.exp(-np.hypot(cx - x0, cy - y0) / S.cell)
        out.append(_cells_point(S, rng, open_flat[rng.choice(len(open_flat), size=k, p=w / w.sum())]))
    return np.vstack(out) if out else np.zeros((0, 2))


def _classes(rng, n, rescue_share=None):
    names = list(md.CFG["classes"])
    shares = np.array([md.CFG["classes"][c]["share"] for c in names], dtype=float)
    shares = shares / shares.sum()
    if rescue_share is not None:
        r = names.index("rescue")
        rest = shares.copy(); rest[r] = 0.0
        shares = rest / rest.sum() * (1.0 - rescue_share)
        shares[r] = rescue_share
    return rng.choice(names, size=n, p=shares)


def make_place_users(seed, sc):
    """Users of a place scenario: stranded (roofs in the flood band), shelter crowds, dry-ground groups, scatter, then
    the reserve twins of the evacuees (inactive until their switch time). Columns as make_users plus group, z_m and
    active_from_s / active_until_s (the user counts while from <= t < until)."""
    import pandas as pd
    c, S = pcfg(), scene()
    rng = np.random.default_rng([seed, 1])
    W, ring = float(c["flood_band_m"]), float(c["dry_ring_m"])
    hu = float(c["user_height_m"])
    flat_h, flat_d = S.grid.ravel(), S.dist.ravel()
    open_out = np.flatnonzero((flat_h <= 0) & (flat_d > W))              # open ground outside the band
    # stranded: buildings inside the band, weighted by footprint area, a uniform roof cell of that building
    bl = np.flatnonzero((S.b_dist <= W) & (S.b_cells > 0))
    assert len(bl) > 0, "no building inside the flood band"
    bsel = rng.choice(bl, size=sc["n_stranded"], p=S.b_cells[bl] / S.b_cells[bl].sum())
    flat_bid = S.bid.ravel()
    order = np.argsort(flat_bid, kind="stable")
    starts = np.searchsorted(flat_bid[order], bsel)
    cell = order[starts + (rng.uniform(size=len(bsel)) * S.b_cells[bsel]).astype(int)]
    xy_str = _cells_point(S, rng, cell)
    # shelter crowds: Dirichlet weights over the used shelters, open cells within shelter_radius_m (Gaussian std r/2)
    sh_c = np.column_stack([sc["shelter_x"], sc["shelter_y"]])
    w = rng.dirichlet(np.full(len(sh_c), 3.0))
    cnt_sh = rng.multinomial(sc["n_shelter"], w)
    r_sh = float(c["shelter_radius_m"])
    xy_sh = _near_cells(S, rng, open_out, sh_c, np.full(len(sh_c), r_sh / 2), cnt_sh)
    sh_id = np.repeat(np.arange(len(sh_c)), cnt_sh)
    # dry-ground groups: centres on open cells of the dry ring, Gaussian spread
    ring_cells = np.flatnonzero((flat_h <= 0) & (flat_d > W) & (flat_d <= W + ring))
    k = sc["n_dry_groups"]
    cen = _cells_point(S, rng, ring_cells[rng.choice(len(ring_cells), size=k)])
    std = rng.uniform(*c["dry_group_std_m"], size=k)
    cnt_dry = rng.multinomial(sc["n_dry"], rng.dirichlet(np.full(k, 3.0)))
    xy_dry = _near_cells(S, rng, open_out, cen, std, cnt_dry)
    dry_id = np.repeat(np.arange(k), cnt_dry)
    xy_sc = _cells_point(S, rng, open_out[rng.choice(len(open_out), size=sc["n_scatter"])])
    xy = np.vstack([xy_str, xy_sh, xy_dry, xy_sc])
    n = len(xy)
    assert n == sc["n_users"]
    group = np.array(["stranded"] * len(xy_str) + ["shelter"] * len(xy_sh) + ["dry"] * len(xy_dry)
                     + ["scatter"] * len(xy_sc))
    # cluster ids: shelters 0.., dry groups after them, stranded = one id per flood "cluster" (k_sh + k), scatter -1
    cid = np.concatenate([np.full(len(xy_str), len(sh_c) + k), sh_id, len(sh_c) + dry_id, np.full(len(xy_sc), -1)])
    cls = np.concatenate([_classes(rng, len(xy_str), float(c["stranded_rescue_share"])),
                          _classes(rng, n - len(xy_str))]).astype(object)
    # evacuation: a share of the stranded users is taken to the nearest used shelter (switch order random)
    m = int(round(sc["event_share"] * len(xy_str)))
    movers = rng.permutation(len(xy_str))[:m]
    near = np.argmin(np.hypot(xy_str[movers, None, 0] - sh_c[None, :, 0], xy_str[movers, None, 1] - sh_c[None, :, 1]),
                     axis=1)
    xy_tw = _near_cells(S, rng, open_out, sh_c, np.full(len(sh_c), r_sh / 2), np.bincount(near, minlength=len(sh_c)))
    order_tw = np.argsort(near, kind="stable")                  # twins were drawn shelter by shelter
    tw = np.empty((m, 2)); tw[order_tw] = xy_tw
    xy = np.vstack([xy, tw])
    group = np.concatenate([group, np.full(m, "evacuee")])
    cid = np.concatenate([cid, near])
    cls = np.concatenate([cls, cls[movers]])
    act_from, act_until = np.zeros(n + m), np.full(n + m, np.inf)
    if m:
        t_sw = sc["event_t0_s"] + sc["tau_s"] * np.arange(m) / m
        act_until[movers], act_from[n:] = t_sw, t_sw
    L = md.CFG["area_m"]
    x, y = np.clip(xy[:, 0], 0, L), np.clip(xy[:, 1], 0, L)
    z = S.height_at(x, y) + hu
    return pd.DataFrame({
        "seed": seed, "user_id": np.arange(n + m), "x": x, "y": y, "cluster_id": cid, "class": cls.astype(str),
        "min_rate_bps": np.array([md.CFG["classes"][q]["min_rate_bps"] for q in cls]), "group": group, "z_m": z,
        "active_from_s": act_from, "active_until_s": act_until})


# ---------------------------------------------------------------- height-aware line of sight
RAY_BLOCK = 64                       # samples per vectorised block along the rays (blocked rays leave early)
RAY_BUDGET = 4_000_000               # links x samples per block (memory bound, ~100 MB of temporaries)


def ray_clear(S, ux, uy, uz, X, Y, H):
    """(P, N) bool: True where the straight ray from user (ux, uy, uz) to drone (X, Y, H) passes above every raster
    cell. Samples every S.cell metres horizontally from the user (excluding the user's own point), up to the drone or
    to where the ray rises above S.hmax, whichever is first. A sample is blocked if the cell's height > ray height."""
    X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
    ux, uy, uz = (np.asarray(a, dtype=float) for a in (ux, uy, uz))
    P, N = len(X), len(ux)
    dx, dy = X[:, None] - ux[None], Y[:, None] - uy[None]
    dh = np.hypot(dx, dy)
    dz = H[:, None] - uz[None]
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.where(dh > 0, dz / dh, np.inf)
        reach = np.where(slope > 0, (S.hmax - uz[None]) / slope, np.inf)
    smax = np.minimum(dh, np.maximum(reach, 0.0))
    nsamp = np.ceil(smax / S.cell).astype(np.int64)            # samples k = 1..nsamp at s = k * cell (capped at smax)
    clear = np.ones((P, N), bool)
    todo = np.flatnonzero(nsamp.ravel() > 0)
    if len(todo) == 0:
        return clear
    todo = todo[np.argsort(nsamp.ravel()[todo], kind="stable")]
    ns = nsamp.ravel()[todo]
    with np.errstate(divide="ignore", invalid="ignore"):
        ex, ey = (dx.ravel()[todo] / dh.ravel()[todo]), (dy.ravel()[todo] / dh.ravel()[todo])
    x0, y0 = np.broadcast_to(ux[None], (P, N)).ravel()[todo], np.broadcast_to(uy[None], (P, N)).ravel()[todo]
    z0 = np.broadcast_to(uz[None], (P, N)).ravel()[todo]
    sl, sm = slope.ravel()[todo], smax.ravel()[todo]
    blocked = np.zeros(len(todo), bool)
    grid = S.grid.ravel()
    n, cell = S.n, S.cell
    alive = np.arange(len(todo))
    k0 = 1
    while len(alive):
        kk = np.arange(k0, k0 + RAY_BLOCK, dtype=float)[None]                   # (1, B)
        for a in np.array_split(alive, max(1, int(np.ceil(len(alive) * RAY_BLOCK / RAY_BUDGET)))):
            s = np.minimum(kk * cell, sm[a, None])                              # (a, B)
            i = np.clip((x0[a, None] + ex[a, None] * s) / cell, 0, n - 1).astype(np.int64)
            j = np.clip((y0[a, None] + ey[a, None] * s) / cell, 0, n - 1).astype(np.int64)
            hit = (grid[i * n + j] > z0[a, None] + sl[a, None] * s) & (kk <= ns[a, None])
            blocked[a] |= hit.any(axis=1)
        k0 += RAY_BLOCK
        alive = alive[(~blocked[alive]) & (ns[alive] >= k0)]
    out = clear.ravel()
    out[todo] = ~blocked
    return out.reshape(P, N)


class PlaceLinks:
    """The obstacle model of one place scenario, passed to make_dataset.channel_gain as `boxes`.
    Holds the scenario's user pool (all users incl. reserve twins; positions never change) and caches the ray test per
    drone position (one bool row over the pool). Queries for other user sets (not in the pool) are computed directly."""

    def __init__(self, S, pool_xy):
        self.S = S
        self.pool = np.asarray(pool_xy, dtype=float)
        self.pool_z = S.height_at(self.pool[:, 0], self.pool[:, 1]) + float(pcfg()["user_height_m"])
        self.order = np.argsort(self.pool[:, 0], kind="stable")
        self.xs = self.pool[self.order, 0]
        self.rows = {}
        self.hits = self.misses = 0

    def __len__(self):                       # truthy for channel_gain's "any obstacles?" check
        return 1

    def user_z(self, ux, uy):
        """Height of each user's handset: ground or roof height + user_height_m."""
        return self.S.height_at(ux, uy) + float(pcfg()["user_height_m"])

    def _pool_index(self, ux, uy):
        """Pool index of each user (-1 if it is not a pool user, e.g. a forecast position)."""
        k = np.clip(np.searchsorted(self.xs, ux), 0, len(self.xs) - 1)
        idx = self.order[k]
        ok = (self.pool[idx, 0] == ux) & (self.pool[idx, 1] == uy)
        return np.where(ok, idx, -1)

    def los_clear(self, ux, uy, X, Y, H):
        ux, uy = np.asarray(ux, dtype=float), np.asarray(uy, dtype=float)
        X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
        idx = self._pool_index(ux, uy)
        if (idx < 0).any():                  # not the pool: no cache
            return ray_clear(self.S, ux, uy, self.user_z(ux, uy), X, Y, H)
        keys = list(zip(X.tolist(), Y.tolist(), H.tolist(), strict=True))
        need = [p for p, k in enumerate(keys) if k not in self.rows]
        self.hits += len(keys) - len(need); self.misses += len(need)
        if need:
            nd = np.array(need)
            rows = ray_clear(self.S, self.pool[:, 0], self.pool[:, 1], self.pool_z, X[nd], Y[nd], H[nd])
            for p, r in zip(need, rows, strict=True):
                self.rows[keys[p]] = r
        return np.stack([self.rows[k] for k in keys])[:, idx]


_LINKS = {}


def links_for(seed, users):
    """PlaceLinks of a scenario, shared by every env of this process that loads the same scenario (so all pilots and
    both access schemes reuse one ray-test cache). Keeps the last two scenarios."""
    xy = users[["x", "y"]].values.astype(float)
    key = (_settings_key(), int(seed), hashlib.sha1(xy.tobytes()).hexdigest())
    if key not in _LINKS:
        while len(_LINKS) >= 2:
            _LINKS.pop(next(iter(_LINKS)))
        _LINKS[key] = PlaceLinks(scene(), xy)
    return _LINKS[key]


# ---------------------------------------------------------------- display payloads (dashboard 2D map and 3D page)
def simplify(xy, tol):
    """Douglas-Peucker simplification of an open polyline (k, 2) with tolerance tol (m)."""
    xy = np.asarray(xy, dtype=float)
    if len(xy) <= 2:
        return xy
    keep = np.zeros(len(xy), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        p, q = xy[a], xy[b]
        d = q - p
        n = np.hypot(*d)
        seg = xy[a + 1:b] - p
        dist = np.abs(seg[:, 0] * d[1] - seg[:, 1] * d[0]) / n if n > 0 else np.hypot(seg[:, 0], seg[:, 1])
        k = int(np.argmax(dist))
        if dist[k] > tol:
            keep[a + 1 + k] = True
            stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return xy[keep]


def band_outline(S, width):
    """Polylines of the flood-band edge (distance = width), from the distance field (contourpy, part of matplotlib)."""
    import contourpy
    cc = (np.arange(S.n) + 0.5) * S.cell
    gen = contourpy.contour_generator(cc, cc, S.dist.T)
    return [ln for ln in gen.lines(float(width)) if len(ln) > 1]


def payload3d(S, max_polys=None, tol=None, margin=50.0):
    """Compact JSON-ready description of the city for the 3D page: polys [[h, x0, y0, x1, y1, ...], ...] in whole
    metres (footprints simplified with tolerance tol, closing vertex dropped; the largest max_polys footprints if
    capped), the flood rivers and the band outline (simplified, clipped to the map + margin), the credit line."""
    c = pcfg()
    tol = float(c["display_simplify_m"] if tol is None else tol)
    cap = c["display_max_buildings"] if max_polys is None else max_polys
    idx = np.argsort(-S.b_cells, kind="stable")
    if cap is not None:
        idx = idx[: int(cap)]
    polys = []
    for k in np.sort(idx):
        ring = np.asarray(S.buildings[k]["xy"], dtype=float)
        ring = simplify(np.vstack([ring, ring[:1]]), tol)[:-1]
        if len(ring) >= 3:
            polys.append([int(round(S.heights[k]))] + np.rint(ring).astype(int).ravel().tolist())

    def lines(ls):
        out = []
        for ln in ls:
            ln = np.asarray(ln, dtype=float)
            inside = np.all((ln > -margin) & (ln < S.side + margin), axis=1)
            for part in np.split(ln, np.flatnonzero(np.diff(inside.astype(int)) != 0) + 1):
                if len(part) > 1 and np.all((part > -margin) & (part < S.side + margin)):
                    out.append(np.rint(simplify(part, 2.0)).astype(int).tolist())
        return out
    W = float(c["flood_band_m"])
    return dict(polys=polys, rivers=lines(S.rivers), band=lines(band_outline(S, W)), band_m=W, h_ref=30,
                credit=f"Map data (c) OpenStreetMap contributors (ODbL). {S.title}; crowd reconstructed, "
                       "not real data.",
                n_buildings=len(S.buildings), n_drawn=len(polys))
