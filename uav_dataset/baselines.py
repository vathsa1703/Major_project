"""Baseline controllers B0-B5, plus B6 (B3 with altitude search), B7 (B6's targets, but circling at the
minimum-power speed instead of hovering; plan step 5) and B8 (B6's targets; hovers while the battery would last
hovering to the end, circles like B7 otherwise; D-52) and B6fc (B6 scoring its candidates on a forecast of the active
users at the drone's arrival: velocity extrapolation, plus the announced event when there is one; D-52 phase 3) and
B6dep (B6 plus WHEN to leave for the announced event's destination, two-leg plans on one common horizon).
Each one drives the SAME UAVEnv through env.step(), so comparisons are fair.

    policy = make_policy("B2")
    obs, info = env.reset(seed=3); policy.reset(env)
    action = policy.act(env)          # numpy array of 4 numbers in [-1, 1]

Baselines may look at the true user positions (privileged information); the RL agent only sees heatmaps.
That makes them a strong test: RL has to beat them, not B0 (a drone that does nothing).
The information ladder B3obs -> B3obsU -> B3obsUO -> B3 runs B3's exact search with less information (only the agent's
capped maps; uncapped maps; plus obstacles; full truth), to tell whether the agent is limited by what it can see.
All settings are in config.yaml under `baselines:`.
"""
import hashlib
import itertools

import numpy as np

import make_dataset as md

BCFG = md.CFG["baselines"]


# ---------------------------------------------------------------- shared helpers
def brake_speed(dist, a, dt):
    """Fastest speed (m/s) from which the drone can still stop within `dist` metres when it may change its speed
    by only a * dt per step. Discrete braking from k * a * dt moves a * dt^2 * k(k+1)/2 before it stops, so
    k = (sqrt(1 + 8 dist / (a dt^2)) - 1) / 2. Always <= sqrt(2 a dist), the continuous braking curve."""
    k = (np.sqrt(1.0 + 8.0 * dist / (a * dt * dt)) - 1.0) / 2.0
    return a * dt * k


def vertical_action(env, th):
    """Normalised climb command toward altitude th (as fast as allowed; brakes when uav.a_max_mps2 is set)."""
    u = env.uav
    if u.get("a_max_mps2") is None:
        return np.clip((th - env.h) / (u["vz_max_mps"] * env.dt), -1.0, 1.0)
    dh = th - env.h
    s = min(u["vz_max_mps"], abs(dh) / env.dt, brake_speed(abs(dh), u["az_max_mps2"], env.dt))
    return float(np.sign(dh) * s / u["vz_max_mps"])


def go_to(env, tx, ty, th, power_frac):
    """Action that flies toward (tx, ty, th) as fast as allowed and sets the transmit power.
    With the acceleration limit on (uav.a_max_mps2 set) it brakes in time: commanded speed
    <= brake_speed(distance) <= sqrt(2 a_max distance), so it does not overshoot the target."""
    u = env.uav
    a_max = u.get("a_max_mps2")
    if a_max is None:                                   # old model: unchanged, bit-exact
        d = np.array([tx - env.x, ty - env.y]) / (u["v_max_mps"] * env.dt)
        n = np.linalg.norm(d)
        if n > 1.0:
            d = d / n
    else:
        delta = np.array([tx - env.x, ty - env.y])
        dist = float(np.linalg.norm(delta))
        s = min(u["v_max_mps"], dist / env.dt, brake_speed(dist, a_max, env.dt))
        d = delta / dist * s / u["v_max_mps"] if dist > 0 else np.zeros(2)
    az = vertical_action(env, th)
    return np.array([d[0], d[1], az, 2.0 * power_frac - 1.0])


def kmeans(points, weights, k, iters, rng):
    """Small weighted k-means (Lloyd). Returns centres (k, 2) and the label of every point."""
    k = min(k, len(points))
    centres = points[rng.choice(len(points), size=k, replace=False)].astype(float)
    labels = np.zeros(len(points), int)
    for _ in range(iters):
        labels = np.argmin(((points[:, None, :] - centres[None]) ** 2).sum(axis=2), axis=1)
        for j in range(k):
            m = labels == j
            if m.any():
                centres[j] = np.average(points[m], axis=0, weights=weights[m])
    return centres, labels


def reward_estimate(env, cov, p_w):
    """The env's v2 reward for hovering at a candidate with coverage `cov` and power p_w (used by B4 and B5)."""
    e = md.energy_step_j(0.0, 0.0, p_w)
    return cov - md.CFG["env"]["lambda_energy"] * e / env.hover_step_j


class Policy:
    name = "?"

    def reset(self, env):
        self.target = (env.x, env.y, BCFG["altitude_m"])
        self.power = BCFG["power_frac"]

    def replan_due(self, env):
        return env.t % BCFG["replan_every_steps"] == 0

    def plan(self, env):                       # subclasses set self.target / self.power
        raise NotImplementedError

    def act(self, env):
        if self.replan_due(env):
            self.plan(env)
        return go_to(env, *self.target, self.power)


# ---------------------------------------------------------------- B0 - B5
class B0Fixed(Policy):
    """B0: sit at the centre of the map at a fixed altitude and power, forever."""
    name = "B0"

    def reset(self, env):
        super().reset(env)
        self.target = (env.L / 2, env.L / 2, BCFG["altitude_m"])

    def plan(self, env):
        pass


class B1FollowCrowd(Policy):
    """B1: every step, fly toward the centre of the biggest crowd (largest true cluster)."""
    name = "B1"

    def replan_due(self, env):
        return True

    def plan(self, env):
        xy, cid = env.user_xy(), env.users["cluster_id"].values
        m = env.active_mask()                       # competing sites: only the users that count now
        if m is not None:
            xy, cid = xy[m], cid[m]
        ids = cid[cid >= 0]
        if len(ids) == 0:
            self.target = (env.L / 2, env.L / 2, BCFG["altitude_m"])
            return
        big = np.bincount(ids).argmax()
        c = xy[cid == big].mean(axis=0)
        self.target = (c[0], c[1], BCFG["altitude_m"])


class B2KMeans(Policy):
    """B2: weighted k-means on the users (rescue users weigh more); go to the centre of the heaviest cluster.
    Recomputed every K steps."""
    name = "B2"

    def reset(self, env):
        super().reset(env)
        self.rng = np.random.default_rng([env.scenario_seed, 22])
        self.rescue = env.rescue

    def plan(self, env):
        xy, _, rescue = env.users_now()             # all users (only the active ones in competing sites)
        w = np.where(rescue, BCFG["rescue_weight"], 1.0)
        centres, labels = kmeans(xy, w, BCFG["kmeans_k"], BCFG["kmeans_iters"], self.rng)
        heavy = np.argmax([w[labels == j].sum() for j in range(len(centres))])
        self.target = (centres[heavy][0], centres[heavy][1], BCFG["altitude_m"])


def _grid(env):
    g = np.linspace(0, env.L, BCFG["grid_n"])
    X, Y = np.meshgrid(g, g, indexing="ij")
    return X.ravel(), Y.ravel()


class B3GridSearch(Policy):
    """B3: every K steps, score grid_n x grid_n candidate positions (plus the current one), go to the best.
    Oracle-ish and slow, on purpose."""
    name = "B3"

    def score(self, env, X, Y, H, p_w):
        """Coverage at every candidate. B3 uses the env's true model (true users, obstacles and classes)."""
        return env.evaluate(X, Y, H, p_w)

    def plan(self, env):
        X, Y = _grid(env)
        X, Y = np.append(X, env.x), np.append(Y, env.y)
        p_w = env.p_max_w * self.power
        cov = self.score(env, X, Y, np.full(len(X), BCFG["altitude_m"]), p_w)
        best = np.flatnonzero(cov >= cov.max() - 1e-12)
        j = best[np.argmin(np.hypot(X[best] - env.x, Y[best] - env.y))]      # ties: the closest one
        self.target = (X[j], Y[j], BCFG["altitude_m"])


# ---------------------------------------------------------------- information ladder: B3 with less information
def cell_shares(env, xy):
    """UNCAPPED version of the agent's heatmap: share of the users in each grid cell (same cells and order as
    env._heatmap, which multiplies this by 10 and caps it at 1)."""
    if len(xy) == 0:
        return np.zeros(env.grid**2)
    h, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=env.grid, range=[[0, env.L], [0, env.L]])
    return h.ravel() / len(xy)


def cell_centres(env):
    """(grid*grid, 2) centres of the heatmap cells, in the heatmap's ravel order (x index major)."""
    c = (np.arange(env.grid) + 0.5) * env.L / env.grid
    CX, CY = np.meshgrid(c, c, indexing="ij")
    return np.column_stack([CX.ravel(), CY.ravel()])


def allocate(weights, n):
    """Split n pseudo-users over cells proportionally to `weights` (largest-remainder rounding, deterministic).
    All-zero weights -> nobody."""
    weights = np.asarray(weights, dtype=float)
    if n <= 0 or weights.sum() <= 0:
        return np.zeros(len(weights), int)
    q = weights / weights.sum() * n
    counts = np.floor(q).astype(int)
    extra = n - counts.sum()
    counts[np.argsort(-(q - counts), kind="stable")[:extra]] += 1
    return counts


def pseudo_population(env, all_map, rescue_map, n=None):
    """A stand-in crowd of `n` (default `obs_pseudo_users`) users at the heatmap cell centres, built only from two maps.
    Rescue pseudo-users (prior share of the rescue class from config) are placed by the rescue map, the others
    by the all-users map. Returns xy (n, 2) and class_probs (n, n_classes): rescue users are certainly rescue,
    the others follow the config class mix over the non-rescue classes (the agent cannot see their classes)."""
    n = BCFG["obs_pseudo_users"] if n is None else int(n)
    assert n % 2 == 0, "the pseudo-crowd size must be even (NOMA pairs)"
    names = list(md.CFG["classes"])
    shares = np.array([md.CFG["classes"][c]["share"] for c in names], dtype=float)
    shares = shares / shares.sum()
    r = names.index("rescue")
    n_rescue = int(round(n * shares[r])) if np.sum(rescue_map) > 0 else 0
    counts_r, counts_o = allocate(rescue_map, n_rescue), allocate(all_map, n - n_rescue)
    centres = cell_centres(env)
    xy = np.vstack([np.repeat(centres, counts_r, axis=0), np.repeat(centres, counts_o, axis=0)])
    prior = shares.copy()
    prior[r] = 0.0
    prior = prior / prior.sum()
    probs = np.vstack([np.tile(np.eye(len(names))[r], (counts_r.sum(), 1)), np.tile(prior, (counts_o.sum(), 1))])
    return xy, probs


def explicit_classes(class_probs):
    """One class index per pseudo-user, for the QoS-aware schemes (their rates depend on each user's own class).
    Users with a certain class (probability 1, e.g. rescue) keep it. The others get the config mix: class counts by
    largest-remainder rounding, then interleaved evenly along the list (users are ordered by cell, so every part of
    the map gets the mix). Deterministic."""
    probs = np.asarray(class_probs, dtype=float)
    cls = np.argmax(probs, axis=1)
    rest = np.flatnonzero(probs.max(axis=1) < 1.0)
    if len(rest):
        counts = allocate(probs[rest].mean(axis=0), len(rest))
        pos = np.concatenate([(np.arange(n) + 0.5) / n for n in counts if n > 0])
        lab = np.concatenate([np.full(n, k) for k, n in enumerate(counts) if n > 0])
        cls[rest] = lab[np.argsort(pos, kind="stable")]
    return cls


def expected_coverage(env, xy, class_probs, X, Y, H, p_w, boxes=None):
    """Expected share of pseudo-users served at each candidate (X, Y, H): a pseudo-user counts with the probability
    that its class's min rate is met. Same physics path and rng recipe as UAVEnv.evaluate (channel_gain +
    noma_rates, env.access noma/oma, seeded by (scenario, t)); bandwidth follows make_scenario's rule
    (pseudo count x bandwidth_per_user_hz). With a QoS-aware scheme (oma_opt / noma_opt) each pseudo-user gets one
    explicit class (explicit_classes) and the score is the share served by md.access_rates."""
    X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
    if len(xy) < 2:
        return np.zeros(len(X))
    min_rates = np.array([c["min_rate_bps"] for c in md.CFG["classes"].values()], dtype=float)
    gains = md.channel_gain(xy[:, 0], xy[:, 1], X, Y, H, boxes)
    if env.access in md.QOS_SCHEMES:
        cls = explicit_classes(class_probs)
        rescue = cls == list(md.CFG["classes"]).index("rescue")
        _, info = md.access_rates(gains, p_w, env.noise_psd, len(xy) * md.CFG["bandwidth_per_user_hz"],
                                  min_rates[cls], env.access, eps=env.sic_eps, rescue=rescue,
                                  rescue_first=env.rescue_first, return_info=True)
        return info["served"].mean(axis=1)
    rng = np.random.default_rng([env.scenario_seed, env.t])
    pick = 0 if env.access == "noma" else 1
    bw = len(xy) * md.CFG["bandwidth_per_user_hz"]
    return np.array([
        ((md.noma_rates(g, p_w, env.noise_psd, bw, env.sc["pairing"], rng)[pick][:, None] >= min_rates)
         * class_probs).sum(axis=1).mean() for g in gains])


class B3Obs(B3GridSearch):
    """B3obs (information ladder, rung 1): B3's search, but it knows ONLY what the RL agent sees: the two observed
    heatmaps (share of users per cell x10, CAPPED at 1; all users and rescue users), taken from env.observation().
    It scores candidates on a pseudo-crowd of `obs_pseudo_users` users at the cell centres, weighted by the
    capped cell values (see pseudo_population): no true positions, no true crowd size, no obstacles, no classes
    beyond the rescue map (config class mix as a prior). Everything else (grid, altitude, power, rhythm, tie-break,
    go_to, physics) is B3's. It also uses its own position and t (the agent sees both) and the scenario seed, which
    only seeds random pairing (unused with pairing: extreme)."""
    name = "B3obs"
    use_boxes = False
    true_n = False              # B3obsN / B3obsUN: the pseudo-crowd has the TRUE number of users (the agent's crowd_n)

    def maps(self, env):
        o = env.observation(("heat_all", "heat_rescue")).astype(float)
        return o[: env.grid**2], o[env.grid**2:]

    def score(self, env, X, Y, H, p_w):
        xy, probs = pseudo_population(env, *self.maps(env), n=env.sc["n_users"] if self.true_n else None)
        return expected_coverage(env, xy, probs, X, Y, H, p_w, env.links if self.use_boxes else None)


class B3ObsN(B3Obs):
    """B3obsN: B3obs told the true number of users (what the agent's crowd_n input gives it). Capped maps."""
    name = "B3obsN"
    true_n = True


class B3ObsUncapped(B3Obs):
    """B3obsU (rung 2): B3obs with the heatmaps UNCAPPED (true share of users per cell, not x10 capped at 1).
    The pseudo-crowd size stays obs_pseudo_users, so the ONLY difference from B3obs is the saturation cap."""
    name = "B3obsU"

    def maps(self, env):
        xy, _, rescue = env.users_now()
        return cell_shares(env, xy), cell_shares(env, xy[rescue])


class B3ObsUncappedObstacles(B3ObsUncapped):
    """B3obsUO (rung 3): B3obsU plus the true obstacles (env.boxes). Still cell-centre pseudo-users, assumed crowd
    size and class prior; full B3 adds true positions inside cells, the true crowd size and the true classes."""
    name = "B3obsUO"
    use_boxes = True


class B3ObsUncappedN(B3ObsUncapped):
    """B3obsUN: uncapped maps plus the true number of users. This is exactly the information of the Track 2 agent's
    inputs (heat_all_u, heat_rescue_u, crowd_n), so it is the information-matched bar for that agent."""
    name = "B3obsUN"
    true_n = True


class B6GridAltitude(Policy):
    """B6 (B3 plus altitude): every K steps, score every grid position at every altitude level (plus the current
    spot), go to the best. Added so B4's lead over B3 can be split into 'chooses altitude' and 'places better'.
    Power stays at full, like B3."""
    name = "B6"

    def here(self, env):
        """The 'stay' candidate, also the reference point for ties: B6 uses where the drone is now."""
        return env.x, env.y, env.h

    def candidates(self, env):
        """B6's candidates: the grid at every altitude level (x-major, like oracle_nodes), then the 'stay' spot."""
        X, Y = _grid(env)
        hx, hy, hh = self.here(env)
        levels = np.array(BCFG["altitude_levels_m"], dtype=float)
        CX, CH = np.repeat(X, len(levels)), np.tile(levels, len(X))
        CY = np.repeat(Y, len(levels))
        return np.append(CX, hx), np.append(CY, hy), np.append(CH, hh)

    def pick(self, env, cov, CX, CY, CH):
        """Index of the best candidate; ties: the one closest to the 'stay' spot."""
        hx, hy, hh = self.here(env)
        best = np.flatnonzero(cov >= cov.max() - 1e-12)
        d = np.sqrt((CX[best] - hx) ** 2 + (CY[best] - hy) ** 2 + (CH[best] - hh) ** 2)
        return best[np.argmin(d)]                                        # ties: the closest one

    def plan(self, env):
        CX, CY, CH = self.candidates(env)
        cov = env.evaluate(CX, CY, CH, env.p_max_w * self.power)
        j = self.pick(env, cov, CX, CY, CH)
        self.target = (CX[j], CY[j], CH[j])


class B7Loiter(B6GridAltitude):
    """B7 (loiter): B6's target choice (grid x altitude levels, every K steps), but instead of hovering over the
    target it circles it: transit at v_max to the nearest point of the circle (braking in time), then fly a circle
    of radius loiter_radius_m at the constant minimum-power speed v_loiter, at the chosen altitude.
    Why: in the rotary-wing model flying at about 10 m/s costs ~25% less power than hovering, so circling may serve
    users for longer on one battery, at the price of being up to r away from the best spot.
    v_loiter comes from the energy model (make_dataset.min_power_speed): Zeng's v* when the accel-energy term is off;
    with it on, the speed that minimises P(v, kappa(v^2/r)) on this circle, capped at sqrt(a_max * r).
    The circle centre is the target clamped to [r, L - r], so the circle stays inside the map. The 'stay' candidate in
    planning is the current target (the drone itself is on the circle, up to r away from it).
    Discrete flight: every step the drone aims at the circle point one chord ahead (counter-clockwise), with the
    chord angle 2 asin(v dt / 2r), so on the circle each step moves exactly v_loiter * dt and changes the velocity by
    v^2 dt / r (the centripetal acceleration)."""
    name = "B7"

    def reset(self, env):
        super().reset(env)
        self.r = float(BCFG["loiter_radius_m"])
        a_max = env.uav.get("a_max_mps2")
        turn_energy = a_max is not None and md.CFG["energy"]["accel_power"]
        self.v_loiter = md.min_power_speed(env.uav["v_max_mps"], self.r if turn_energy else None, a_max)
        self.dtheta = 2.0 * np.arcsin(min(1.0, self.v_loiter * env.dt / (2.0 * self.r)))

    def here(self, env):
        return self.target

    def centre(self, env):
        tx, ty, _ = self.target
        lo, hi = self.r, env.L - self.r
        return float(np.clip(tx, lo, hi)), float(np.clip(ty, lo, hi))

    def act(self, env):
        if self.replan_due(env):
            self.plan(env)
        return self.loiter_action(env)

    def loiter_action(self, env):
        """One step of B7's flight around the current target: transit to the circle, then circle at v_loiter."""
        cx, cy = self.centre(env)
        th = self.target[2]
        rx, ry = env.x - cx, env.y - cy
        rho = float(np.hypot(rx, ry))
        if rho > self.r + self.v_loiter * env.dt:                       # transit: to the nearest circle point
            return go_to(env, cx + self.r * rx / rho, cy + self.r * ry / rho, th, self.power)
        theta = float(np.arctan2(ry, rx)) if rho > 0 else 0.0
        px, py = cx + self.r * np.cos(theta + self.dtheta), cy + self.r * np.sin(theta + self.dtheta)
        v = np.array([px - env.x, py - env.y]) / env.dt
        n = float(np.linalg.norm(v))
        if n > env.uav["v_max_mps"]:
            v *= env.uav["v_max_mps"] / n
        vn = v / env.uav["v_max_mps"]
        return np.array([vn[0], vn[1], vertical_action(env, th), 2.0 * self.power - 1.0])


class B8BatteryAware(B7Loiter):
    """B8 (hover or circle by the battery; D-52): B6's target choice (grid x altitude levels, every K steps). On station
    it hovers like B6 while the battery would last hovering to the end of the mission, and circles like B7 otherwise:
        circle  if  E_left < T_left x E_hover_step,   E_hover_step = md.energy_step_j(0, 0, P_tx)
    (hover propulsion + comm P_tx / PA efficiency + circuit, per step; T_left = steps left in the episode).
    Switching rule (hysteresis, so it does not chatter between the two modes every second): hover -> circle at ANY step
    where the rule says circle (as soon as hovering would no longer last); circle -> hover only at a decision time
    (every K steps), when the rule is re-evaluated. While circling, the circle gains margin (circling costs less than
    hovering), so B8 returns to hovering once the saved energy covers hovering to the end.
    The 'stay' candidate in planning is B6's (the drone's position) while hovering and B7's (the target) while circling.
    With an ample battery it never circles and is then exactly B6."""
    name = "B8"

    def reset(self, env):
        super().reset(env)
        self.circling = False

    def must_circle(self, env):
        hover_step_j = md.energy_step_j(0.0, 0.0, env.p_max_w * self.power)
        return env.energy_left_j < (env.T - env.t) * hover_step_j

    def here(self, env):
        return self.target if self.circling else (env.x, env.y, env.h)

    def act(self, env):
        if self.replan_due(env):
            self.circling = self.must_circle(env)
            self.plan(env)
        elif not self.circling and self.must_circle(env):
            self.circling = True
        if self.circling:
            return self.loiter_action(env)
        return go_to(env, *self.target, self.power)


# ---------------------------------------------------------------- B6fc: the forecasting greedy pilot (D-52 phase 3)
def flight_steps(env, X, Y, H, max_steps):
    """Whole steps go_to needs to bring the drone from its CURRENT state (position and velocity) to each candidate
    (X, Y, H): env.step's kinematics (speed limits, acceleration limit, map and altitude clipping) driven by go_to's
    commands (braking included), vectorised over the candidates. Arrived = within b6fc.arrive_tol_m of the target
    horizontally and vertically. inf if not arrived within max_steps. Pure: reads only the drone's own state."""
    u, dt, L = env.uav, env.dt, env.L
    vmax, vzmax, a_max = u["v_max_mps"], u["vz_max_mps"], u.get("a_max_mps2")
    tol = float(md.CFG["b6fc"]["arrive_tol_m"])
    X, Y, H = (np.asarray(a, dtype=float) for a in (X, Y, H))
    n = len(X)
    x, y, h = np.full(n, env.x), np.full(n, env.y), np.full(n, env.h)
    vx, vy, vz = np.full(n, env.vx), np.full(n, env.vy), np.full(n, env.vz)
    arr = np.full(n, np.inf)
    for k in range(int(max_steps) + 1):
        dx, dy, dh = X - x, Y - y, H - h
        dist = np.hypot(dx, dy)
        arr[np.isinf(arr) & (dist <= tol) & (np.abs(dh) <= tol)] = k
        if k == max_steps or not np.isinf(arr).any():
            break
        if a_max is None:                                   # go_to, old model
            cx, cy = dx / (vmax * dt), dy / (vmax * dt)
            nrm = np.hypot(cx, cy)
            sc = np.where(nrm > 1.0, 1.0 / np.maximum(nrm, 1e-300), 1.0)
            cx, cy = cx * sc, cy * sc
            cz = np.clip(dh / (vzmax * dt), -1.0, 1.0)
        else:                                               # go_to with braking
            s = np.minimum(np.minimum(vmax, dist / dt), brake_speed(dist, a_max, dt))
            safe = np.where(dist > 0, dist, 1.0)
            cx, cy = np.where(dist > 0, dx / safe * s / vmax, 0.0), np.where(dist > 0, dy / safe * s / vmax, 0.0)
            sz = np.minimum(np.minimum(vzmax, np.abs(dh) / dt), brake_speed(np.abs(dh), u["az_max_mps2"], dt))
            cz = np.sign(dh) * sz / vzmax
        cx, cy, cz = np.clip(cx, -1, 1), np.clip(cy, -1, 1), np.clip(cz, -1, 1)          # env.step from here
        hx, hy = cx * vmax, cy * vmax
        nrm = np.hypot(hx, hy)
        sc = np.where(nrm > vmax, vmax / np.maximum(nrm, 1e-300), 1.0)
        hx, hy, hz = hx * sc, hy * sc, cz * vzmax
        if a_max is not None:
            ddx, ddy = hx - vx, hy - vy
            nrm = np.hypot(ddx, ddy)
            sc = np.where(nrm > a_max * dt, a_max * dt / np.maximum(nrm, 1e-300), 1.0)
            hx, hy = vx + ddx * sc, vy + ddy * sc
            az = u["az_max_mps2"] * dt
            hz = vz + np.clip(hz - vz, -az, az)
        nx, ny = np.clip(x + hx * dt, 0, L), np.clip(y + hy * dt, 0, L)
        nh = np.clip(h + hz * dt, u["h_min_m"], u["h_max_m"])
        vx, vy, vz = (nx - x) / dt, (ny - y) / dt, (nh - h) / dt
        x, y, h = nx, ny, nh
    return arr


FC_MEMO = None      # optional {key: per-lattice-node coverage} shared by B6fc runs (sites_exp sets it; None = off)


class B6Forecast(B6GridAltitude):
    """B6fc (D-52 phase 3): B6 that scores its candidates by where the active users WILL be when the drone gets there.
    Every K steps, for every B6 candidate (grid x altitude levels + 'stay'):
      arrival a = flight_steps (go_to at v_max from the drone's current position and velocity, braking included);
      score = mean coverage over the forecast times ceil5(t + a) + {0, 10, ..., 60} s (inside the episode; config
              `b6fc:`), each computed with env.evaluate's physics (UAVEnv.evaluate_users: same channel, access scheme,
              power, bandwidth) on a FORECAST of the active users.
    Pick the best; ties (1e-12) -> B6's own choice if it is among the best, else the closest to the drone (B6's rule).
    The forecast uses ONLY:
      - the drone's own state (position, velocity), like B6;
      - the users active NOW (positions, min rates, rescue flags), exactly what B6 already uses;
      - their velocities from the last frame: (position now - position 1 s ago) for users active now and 1 s ago
        (0 otherwise, and 0 at t = 0); forecast position = position now + velocity x lead time, clipped to the map;
      - ONLY when the scenario's event is announced (env.sc['announced'], competing sites): the announcement, i.e. the
        event time t0, the duration tau, the number of people that move m = round(share x n active) (md.n_movers),
        and the two sites' centres and radii (where they leave, where they go). This is what an operator message would
        carry ("from t0, about m people will be taken from the school at A to the shelter at B over tau minutes").
        Forecast: by time t the announced linear schedule has switched min(m, floor((t - t0) m / tau) + 1) movers
        (all m if tau = 0); the ones still to switch after now are taken from the users active now inside A's disc
        (in user order: the pilot does NOT know which individuals move) and placed at B at their position relative
        to A scaled by r_B / r_A (they keep their class). It never reads the true movers, the true arrival positions
        or any future position or mask.
    It does NOT read the battery (it hovers like B6). Without an event and with still crowds every forecast equals the
    present, so B6fc is exactly B6 (test)."""
    name = "B6fc"

    def reset(self, env):
        super().reset(env)
        c = md.CFG["b6fc"]
        self.window, self.sample, self.quantum = int(c["window_s"]), int(c["sample_s"]), int(c["quantum_s"])

    def announced(self, env):
        sc = env.sc
        return bool(sc.get("announced", False)) and sc.get("event_t0_s") is not None

    def snapshot(self, env):
        """Everything the forecast may use, read once at the decision time (present and last frame only)."""
        t, dt = env.t, env.dt
        m = env.active_mask()
        xy = env.user_xy(t)
        prev = env.user_xy(t - 1) if t > 0 else xy
        was = np.ones(len(xy), bool) if (m is None or t == 0) else env.active_mask(t - 1)
        keep = np.ones(len(xy), bool) if m is None else m
        v = np.where(was[keep][:, None], (xy[keep] - prev[keep]) / dt, 0.0)
        snap = dict(t=t, xy=xy[keep], v=v, mr=env.min_rate[keep], rs=env.rescue[keep], moved=None)
        if self.announced(env):
            sc = env.sc
            cA, cB = (np.array([sc["site_x"][i], sc["site_y"][i]]) for i in (0, 1))
            rA, rB = (float(sc["site_radius_m"][i]) for i in (0, 1))
            inA = np.flatnonzero(np.hypot(*(snap["xy"] - cA).T) <= rA)
            snap.update(t0=float(sc["event_t0_s"]), tau=float(sc["tau_s"]), m=md.n_movers(sc), inA=inA,
                        dest=cB + (snap["xy"][inA] - cA) * (rB / rA))
        return snap

    @staticmethod
    def switched(s, time_s):
        """Movers switched by time_s on the announced linear schedule."""
        if time_s < s["t0"]:
            return 0
        if s["tau"] <= 0:
            return s["m"]
        return min(s["m"], int(np.floor((time_s - s["t0"]) * s["m"] / s["tau"])) + 1)

    def extrap_lead(self, lead):
        """Seconds of velocity extrapolation used for a forecast `lead` seconds ahead (B6fc: all of it)."""
        return lead

    def forecast(self, env, s, tt):
        """(xy, min_rate, rescue) of the forecast active users at time index tt >= now."""
        lead = self.extrap_lead((tt - s["t"]) * env.dt)
        xy = np.clip(s["xy"] + s["v"] * lead, 0.0, env.L) if lead > 0 else s["xy"]
        if "t0" in s:
            k = min(len(s["inA"]), self.switched(s, tt * env.dt) - self.switched(s, s["t"] * env.dt))
            if k > 0:
                xy = xy.copy()
                xy[s["inA"][:k]] = s["dest"][:k]
        return xy, s["mr"], s["rs"]

    def forecast_cov(self, env, s, tt, idx, CX, CY, CH, p_w):
        """Coverage of candidates idx at forecast time tt (memoised per forecast user set when FC_MEMO is on)."""
        xy, mr, rs = self.forecast(env, s, tt)
        n_lat = len(CX) - 1
        memo = FC_MEMO if (FC_MEMO is not None and (env.access in md.QOS_SCHEMES or env.sc["pairing"] == "extreme")) \
            else None
        if memo is None:
            return env.evaluate_users(xy, mr, rs, CX[idx], CY[idx], CH[idx], p_w, tt)
        blob = b"".join(np.ascontiguousarray(a).tobytes() for a in (xy, mr, rs, env.boxes, CX[:-1], CY[:-1], CH[:-1]))
        blob += repr((int(tt), p_w, env.access, env.sic_eps, env.rescue_first, env.sc["bandwidth_hz"],
                      env.sc["pairing"], env.scenario_seed)).encode()
        key = hashlib.sha1(blob).hexdigest()
        row = memo.get(key)
        if row is None:
            row = memo[key] = np.full(n_lat, np.nan)
        out = np.empty(len(idx))
        lat = idx < n_lat
        need = idx[lat][np.isnan(row[idx[lat]])]
        if len(need):
            row[need] = env.evaluate_users(xy, mr, rs, CX[need], CY[need], CH[need], p_w, tt)
        out[lat] = row[idx[lat]]
        if (~lat).any():
            j = idx[~lat]
            out[~lat] = env.evaluate_users(xy, mr, rs, CX[j], CY[j], CH[j], p_w, tt)
        return out

    def _mean_cov(self, env, s, times, valid, CX, CY, CH, p_w):
        """Mean forecast coverage of each candidate over its valid sample times (-inf if it has none)."""
        acc, cnt = np.zeros(len(CX)), valid.sum(axis=1)
        tv = np.where(valid, times, np.inf)
        for tt in np.unique(tv[valid]):
            idx = np.flatnonzero((tv == tt).any(axis=1))
            acc[idx] += self.forecast_cov(env, s, int(tt), idx, CX, CY, CH, p_w)
        return np.where(cnt > 0, acc / np.maximum(cnt, 1), -np.inf)

    def scores(self, env, CX, CY, CH, keep=()):
        """Forecast score of every candidate (-inf if it cannot be reached before the end).
        With b6fc.screen_top = K (ENGINEERING CHOICE, for run time): stage 1 scores every candidate at ONE forecast
        time (the middle sample of its window, or its last sample inside the episode); only the K best of stage 1
        plus the candidates in `keep` (B6's choice, 'stay') get the full window score, the others -inf.
        screen_top null = the full rule for every candidate."""
        p_w = env.p_max_w * self.power
        s = self.snapshot(env)
        arr = flight_steps(env, CX, CY, CH, env.T - env.t)
        q = self.quantum
        start = np.full(len(CX), np.inf)
        ok = np.isfinite(arr)
        start[ok] = np.ceil((env.t + arr[ok]) / q) * q
        offs = np.arange(0, self.window + 1, self.sample)
        times = start[:, None] + offs[None, :]
        valid = times < env.T
        top = md.CFG["b6fc"].get("screen_top")
        if top and top < len(CX):
            cnt = valid.sum(axis=1)
            col = np.minimum(len(offs) // 2, np.maximum(cnt - 1, 0))
            rows = np.arange(len(CX))
            one = np.zeros_like(valid)
            one[rows, col] = cnt > 0
            s1 = self._mean_cov(env, s, times, one, CX, CY, CH, p_w)
            kept = np.zeros(len(CX), bool)
            kept[np.argsort(-s1, kind="stable")[:top]] = True
            kept[list(keep)] = True
            valid &= kept[:, None]
        return self._mean_cov(env, s, times, valid, CX, CY, CH, p_w)

    def plan(self, env):
        super().plan(env)                                  # B6's own choice (the tie-break)
        b6 = self.target
        CX, CY, CH = self.candidates(env)
        j6 = int(np.flatnonzero((CX == b6[0]) & (CY == b6[1]) & (CH == b6[2]))[0])
        sc = self.scores(env, CX, CY, CH, keep=(j6, len(CX) - 1))
        if not np.isfinite(sc).any():
            return
        if sc[j6] >= sc.max() - 1e-12:                      # tie (or best): B6's choice
            return
        j = self.pick(env, sc, CX, CY, CH)
        self.target = (CX[j], CY[j], CH[j])


# ---------------------------------------------------------------- B6dep: the departure-time planner (anticipation rule)
def fly_two_legs(env, first, second, dep, n_steps):
    """Positions (n_steps + 1, P, 3) of P planned flights from the drone's CURRENT state (position and velocity):
    flight p flies go_to toward first[p] (x, y, h) at steps k < dep[p] and toward second[p] from step dep[p] on
    (dep = inf: never leaves the first leg). Row k = the position k steps from now (row 0 = now). env.step's
    kinematics (speed limits, acceleration limit, map and altitude clipping) driven by go_to's commands, braking
    included, exactly as flight_steps; vectorised over the plans. Pure: reads only the drone's own state."""
    u, dt, L = env.uav, env.dt, env.L
    vmax, vzmax, a_max = u["v_max_mps"], u["vz_max_mps"], u.get("a_max_mps2")
    first, second = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    dep = np.asarray(dep, dtype=float)
    n = len(dep)
    x, y, h = np.full(n, env.x), np.full(n, env.y), np.full(n, env.h)
    vx, vy, vz = np.full(n, env.vx), np.full(n, env.vy), np.full(n, env.vz)
    out = np.empty((int(n_steps) + 1, n, 3))
    for k in range(int(n_steps) + 1):
        out[k, :, 0], out[k, :, 1], out[k, :, 2] = x, y, h
        if k == n_steps:
            break
        tgt = np.where((k < dep)[:, None], first, second)
        dx, dy, dh = tgt[:, 0] - x, tgt[:, 1] - y, tgt[:, 2] - h
        dist = np.hypot(dx, dy)
        if a_max is None:                                   # go_to, old model
            cx, cy = dx / (vmax * dt), dy / (vmax * dt)
            nrm = np.hypot(cx, cy)
            sc = np.where(nrm > 1.0, 1.0 / np.maximum(nrm, 1e-300), 1.0)
            cx, cy = cx * sc, cy * sc
            cz = np.clip(dh / (vzmax * dt), -1.0, 1.0)
        else:                                               # go_to with braking
            s = np.minimum(np.minimum(vmax, dist / dt), brake_speed(dist, a_max, dt))
            safe = np.where(dist > 0, dist, 1.0)
            cx, cy = np.where(dist > 0, dx / safe * s / vmax, 0.0), np.where(dist > 0, dy / safe * s / vmax, 0.0)
            sz = np.minimum(np.minimum(vzmax, np.abs(dh) / dt), brake_speed(np.abs(dh), u["az_max_mps2"], dt))
            cz = np.sign(dh) * sz / vzmax
        cx, cy, cz = np.clip(cx, -1, 1), np.clip(cy, -1, 1), np.clip(cz, -1, 1)          # env.step from here
        hx, hy = cx * vmax, cy * vmax
        nrm = np.hypot(hx, hy)
        sc = np.where(nrm > vmax, vmax / np.maximum(nrm, 1e-300), 1.0)
        hx, hy, hz = hx * sc, hy * sc, cz * vzmax
        if a_max is not None:
            ddx, ddy = hx - vx, hy - vy
            nrm = np.hypot(ddx, ddy)
            sc = np.where(nrm > a_max * dt, a_max * dt / np.maximum(nrm, 1e-300), 1.0)
            hx, hy = vx + ddx * sc, vy + ddy * sc
            az = u["az_max_mps2"] * dt
            hz = vz + np.clip(hz - vz, -az, az)
        nx, ny = np.clip(x + hx * dt, 0, L), np.clip(y + hy * dt, 0, L)
        nh = np.clip(h + hz * dt, u["h_min_m"], u["h_max_m"])
        vx, vy, vz = (nx - x) / dt, (ny - y) / dt, (nh - h) / dt
        x, y, h = nx, ny, nh
    return out


class B6Depart(B6Forecast):
    """B6dep (anticipation rule; reviewer's proposal after D-52 phase 4): B6 that also decides WHEN to leave for
    where the announced event will put the demand. B6fc scores every candidate over its own window after its own
    arrival, so far spots look good too early and it leaves too soon; B6dep scores whole two-leg plans on ONE common
    horizon instead. Every K steps, while an announced move has not finished (now < t0 + tau):
      S = B6's own choice now (the 'stay' leg);
      post spots = the top_k of B6's candidates by forecast coverage at the end of the move (time t0 + tau, the
                   B6fc forecast: the announced schedule plus velocity extrapolation, capped at extrap_cap_s);
      plans = 'never leave' (fly to / hover at S to the end) plus, for every departure time d in now, now + 10 s,
              ... up to t0 + tau and every post spot P: fly to S until d, then to P (go_to with braking; positions
              from fly_two_legs, i.e. the env's own kinematics);
      score = mean forecast coverage at the plan's position over the common horizon now, now + sample_s, ... < T.
    It flies to P if the best plan leaves NOW, otherwise it does what B6 does (the stay leg). Ties (1e-12): 'never
    leave' (B6) first, then the latest departure, then the better post spot.
    Information: exactly B6fc's (the drone's own state, the users active now and their last-frame velocities, and the
    announcement: t0, tau, share, sites A/B centres and radii). It never reads a future position, mask or the true
    movers. Unannounced, no event, or after t0 + tau: exactly B6 (test). It does not read the battery."""
    name = "B6dep"

    def reset(self, env):
        super().reset(env)
        c = md.CFG["b6dep"]
        self.top_k, self.dep_every = int(c["top_k"]), int(c["depart_every_s"])
        self.dep_sample, self.cap = int(c["sample_s"]), c["extrap_cap_s"]

    def extrap_lead(self, lead):
        return lead if self.cap is None else min(lead, float(self.cap))

    def plan(self, env):
        B6GridAltitude.plan(self, env)                     # B6's own choice: the stay leg (and B6 itself)
        if not self.announced(env):
            return
        sc, now = env.sc, env.t
        t_end = float(sc["event_t0_s"]) + float(sc["tau_s"])           # the announced move is over by then (s)
        if now * env.dt >= t_end:
            return
        S = np.array(self.target, dtype=float)
        s = self.snapshot(env)
        p_w = env.p_max_w * self.power
        CX, CY, CH = self.candidates(env)
        t_post = min(int(np.ceil(t_end / env.dt)), env.T - 1)
        post = self.evaluate_forecast(env, s, t_post, np.column_stack([CX, CY, CH]), p_w)
        top = np.argsort(-post, kind="stable")[: self.top_k]
        P = np.column_stack([CX[top], CY[top], CH[top]])
        step = int(round(self.dep_every / env.dt))
        deps = np.arange(0, int(np.floor(t_end / env.dt)) - now + 1, step)            # steps from now
        deps = deps[now + deps < env.T]
        # plan 0 = never leave; then (d, rank) d-major
        dep = np.concatenate([[np.inf], np.repeat(deps, len(top)).astype(float)])
        second = np.vstack([S[None], np.tile(P, (len(deps), 1))])
        rank = np.concatenate([[-1], np.tile(np.arange(len(top)), len(deps))])
        horizon = env.T - now
        pos = fly_two_legs(env, np.tile(S, (len(dep), 1)), second, dep, horizon - 1)
        ks = np.arange(0, horizon, int(round(self.dep_sample / env.dt)))
        score = np.zeros(len(dep))
        for k in ks:
            uniq, inv = np.unique(np.round(pos[k], 6), axis=0, return_inverse=True)
            cov = self.evaluate_forecast(env, s, now + int(k), uniq, p_w)
            score += cov[inv.ravel()]
        score /= len(ks)
        best = np.flatnonzero(score >= score.max() - 1e-12)
        if best[0] == 0:                                   # 'never leave' among the best: B6
            return
        j = best[np.lexsort((rank[best], -dep[best]))[0]]  # latest departure, then the better post spot
        if dep[j] == 0:
            self.target = tuple(float(v) for v in second[j])

    def evaluate_forecast(self, env, s, tt, nodes, p_w):
        """Forecast coverage at time index tt of the drone at each row (x, y, h) of nodes."""
        xy, mr, rs = self.forecast(env, s, tt)
        return env.evaluate_users(xy, mr, rs, nodes[:, 0], nodes[:, 1], nodes[:, 2], p_w, tt)


# ---------------------------------------------------------------- model mismatch: B6r, B6true, B6meas
def refine_spot(env, x, y, h, p_w, model="nominal", value=None):
    """Off-grid pattern search around (x, y, h) on a MODEL (env.evaluate(..., model=model)): at each probe distance s
    of refine.steps_m (coarse to fine) score the 8 horizontal neighbours at s and the 2 altitude neighbours at +/- s/2
    (clipped to the map and the altitude limits) in one vectorised call; move to the best one while it is strictly
    better, then go to the next (smaller) s. Returns (x, y, h, coverage). Deterministic (ties: the first neighbour)."""
    rc, u = md.CFG["refine"], env.uav
    if value is None:
        value = float(env.evaluate([x], [y], [h], p_w, model=model)[0])
    dirs = np.array([[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]], dtype=float)
    for s in rc["steps_m"]:
        for _ in range(int(rc["max_moves_per_step"])):
            NX = np.clip(np.r_[x + dirs[:, 0] * s, x, x], 0.0, env.L)
            NY = np.clip(np.r_[y + dirs[:, 1] * s, y, y], 0.0, env.L)
            NH = np.clip(np.r_[np.full(len(dirs), h), h + s / 2, h - s / 2], u["h_min_m"], u["h_max_m"])
            cov = env.evaluate(NX, NY, NH, p_w, model=model)
            j = int(np.argmax(cov))
            if cov[j] <= value + 1e-12:
                break
            x, y, h, value = float(NX[j]), float(NY[j]), float(NH[j]), float(cov[j])
    return x, y, h, value


class B6Refined(B6GridAltitude):
    """B6r: B6 (grid x altitude levels, every K steps, on the NOMINAL model) plus an off-grid pattern search
    (refine_spot) from the chosen candidate. Separates 'finer placement' from 'knows the true channel'."""
    name = "B6r"
    model = "nominal"

    def plan(self, env):
        CX, CY, CH = self.candidates(env)
        p_w = env.p_max_w * self.power
        cov = env.evaluate(CX, CY, CH, p_w, model=self.model)
        j = self.pick(env, cov, CX, CY, CH)
        x, y, h, _ = refine_spot(env, CX[j], CY[j], CH[j], p_w, self.model, value=float(cov[j]))
        self.target = (x, y, h)


class B6True(B6Refined):
    """B6true (UPPER BOUND, not a fair competitor): B6r scoring on the TRUE channel (env.evaluate(model="true")):
    it knows the shadowing map, the true building loss and the hidden buildings. Equal to B6r without mismatch."""
    name = "B6true"
    model = "true"


class MeasuredView:
    """The ONLY window B6meas has on the world (level-1 information parity with the AI): its own state, the clock, the
    NOMINAL model (env.evaluate(model="nominal") on the users now, like B6) and the aggregate coverage the drone
    measured in the last second (env.prev["coverage"], the AI's `prev` observation). Anything else raises."""
    _ALLOWED = ("x", "y", "h", "vx", "vy", "vz", "t", "dt", "L", "T", "uav", "p_max_w")

    def __init__(self, env):
        object.__setattr__(self, "_env", env)

    def __getattr__(self, k):
        if k in MeasuredView._ALLOWED:
            return getattr(object.__getattribute__(self, "_env"), k)
        raise AttributeError(f"B6meas may not read env.{k}")

    def evaluate(self, X, Y, H, p_w):
        return object.__getattribute__(self, "_env").evaluate(X, Y, H, p_w, model="nominal")

    def measured_coverage(self):
        return float(object.__getattribute__(self, "_env").prev["coverage"])


def leg_time(ax, ay, ah, bx, by, bh, uav):
    """Rough flight time (s) between two spots: horizontal at v_max, then vertical at vz_max (tour ordering only)."""
    return float(np.hypot(bx - ax, by - ay) / uav["v_max_mps"] + abs(bh - ah) / uav["vz_max_mps"])


class B6Measured(B6GridAltitude):
    """B6meas: model-based proposal, measurement-based choice. Learning-free; level-1 information (MeasuredView):
    the nominal model + the aggregate coverage it measures each second where it flies. Same flight cost as everyone.
      1. survey  : B6's candidates scored on the NOMINAL model; the top-k spots at least min_sep_m apart (each at its
                   best nominal altitude) are visited in the shortest open tour from the drone (brute force, k <= 5),
                   and the coverage is measured for dwell_s seconds at each.
      2. refine  : from the best MEASURED spot, a measured pattern search: probes at s = b6meas.steps_m (4 compass
                   points, and altitude +/- s/2 if alt_probes) visited in nearest-neighbour order, probe_dwell_s each;
                   the first probe that beats the centre by improve_min becomes the centre (the drone is already
                   there) and the probes are rebuilt around it at the same s; otherwise the next smaller s. Only
                   improving moves are kept.
      3. hold    : fly to the centre and stay. Every recheck_s, if the measured coverage fell by more than
                   recheck_drop below the committed value (the crowd moved), restart from 1.
    It never reads the true channel, the shadowing map, the true building loss or the hidden buildings."""
    name = "B6meas"

    def reset(self, env):
        super().reset(env)
        self.c = md.CFG["b6meas"]
        self.steps = list(self.c.get("steps_m") or md.CFG["refine"]["steps_m"])
        self.mode, self.queue, self.samples, self.leg_t = "start", [], [], 0
        self.measured, self.center, self.center_val, self.scale_i, self.t_commit = {}, None, None, 0, None
        self.log = []                                     # (t, mode, x, y, h, measured value) for reports and tests
        self.last_sample_t = -1

    def act(self, env):
        return self._act(MeasuredView(env))

    # -- steps
    def start_survey(self, v):
        c = self.c
        CX, CY, CH = self.candidates(v)
        cov = v.evaluate(CX, CY, CH, v.p_max_w * self.power)
        d = np.hypot(CX - v.x, CY - v.y)
        order = np.lexsort((d, -cov))                     # best nominal first; ties: the closest
        picks = []
        for j in order:
            if all(np.hypot(CX[j] - CX[i], CY[j] - CY[i]) >= c["min_sep_m"] for i in picks):
                picks.append(int(j))
            if len(picks) == int(c["k"]):
                break
        spots = [(float(CX[j]), float(CY[j]), float(CH[j])) for j in picks]
        best, best_t = None, np.inf
        for perm in itertools.permutations(range(len(spots))):
            pos, tt = (v.x, v.y, v.h), 0.0
            for i in perm:
                tt += leg_time(*pos, *spots[i], v.uav)
                pos = spots[i]
            if tt < best_t - 1e-9:
                best, best_t = perm, tt
        self.queue = [(*spots[i], int(c["dwell_s"])) for i in best]
        self.mode, self.measured, self.samples, self.leg_t = "survey", {}, [], 0

    def probes(self, v):
        """Unmeasured probes around the centre at the current scale, in nearest-neighbour order from the drone."""
        s = float(self.steps[self.scale_i])
        x, y, h = self.center
        u = v.uav
        pts = [(float(np.clip(x + dx * s, 0, v.L)), float(np.clip(y + dy * s, 0, v.L)), h)
               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        if self.c["alt_probes"]:
            pts += [(x, y, float(np.clip(h + dh * s / 2, u["h_min_m"], u["h_max_m"]))) for dh in (1, -1)]
        pts = [p for p in dict.fromkeys(pts) if p != self.center and self.key(p) not in self.measured]
        out, pos = [], (v.x, v.y, v.h)
        while pts:
            i = int(np.argmin([leg_time(*pos, *p, u) for p in pts]))
            pos = pts.pop(i)
            out.append((*pos, int(self.c["probe_dwell_s"])))
        return out

    @staticmethod
    def key(p):
        return tuple(round(float(a), 3) for a in p[:3])

    def next_scale(self, v):
        """Probes at the current scale, or at the next smaller scales; when none are left, hold at the centre."""
        while self.scale_i < len(self.steps):
            self.queue = self.probes(v)
            if self.queue:
                return
            self.scale_i += 1
        self.mode, self.t_commit, self.queue = "hold", v.t, []

    def on_measured(self, v, wp, value):
        self.measured[self.key(wp)] = value
        self.log.append((v.t, self.mode, *wp[:3], value))
        self.queue.pop(0)
        if self.mode == "survey":
            if not self.queue:
                k = max(self.measured, key=self.measured.get)
                self.center, self.center_val, self.scale_i, self.mode = k, self.measured[k], 0, "refine"
                self.next_scale(v)
            return
        if value > self.center_val + self.c["improve_min"]:           # refine: keep only improving moves
            self.center, self.center_val = self.key(wp), value
            self.next_scale(v)
        elif not self.queue:
            self.scale_i += 1
            self.next_scale(v)

    def _act(self, v):
        c, tol = self.c, float(self.c["arrive_tol_m"])
        if self.mode == "start":
            self.start_survey(v)
        if self.mode == "hold":
            x, y, h = self.center
            here = abs(v.x - x) <= tol and abs(v.y - y) <= tol and abs(v.h - h) <= tol
            if here and v.t > 0 and (v.t - self.t_commit) % int(c["recheck_s"]) == 0 and v.t > self.t_commit:
                if v.measured_coverage() < self.center_val - c["recheck_drop"]:
                    self.start_survey(v)
        while self.mode in ("survey", "refine") and self.queue:
            wp = self.queue[0]
            arrived = abs(v.x - wp[0]) <= tol and abs(v.y - wp[1]) <= tol and abs(v.h - wp[2]) <= tol
            if arrived:
                if v.t > 0 and v.t != self.last_sample_t:     # one measurement per second, at this spot
                    self.samples.append(v.measured_coverage())
                    self.last_sample_t = v.t
            else:
                self.leg_t += 1
                if self.leg_t > c["max_leg_s"]:          # never reached: drop it unmeasured
                    self.queue.pop(0)
                    self.samples, self.leg_t = [], 0
                    if not self.queue:
                        self.on_empty(v)
                    continue
            if len(self.samples) >= wp[3]:
                self.on_measured(v, wp, float(np.mean(self.samples)))
                self.samples, self.leg_t = [], 0
                continue                                  # the next waypoint (the drone may already be there)
            break
        if self.mode == "hold" or not self.queue:
            self.target = self.center
        else:
            self.target = self.queue[0][:3]
        return go_to(v, *self.target, self.power)

    def on_empty(self, v):
        if self.mode == "survey":
            if self.measured:
                k = max(self.measured, key=self.measured.get)
                self.center, self.center_val, self.scale_i, self.mode = k, self.measured[k], 0, "refine"
                self.next_scale(v)
            else:
                self.start_survey(v)
        else:
            self.scale_i += 1
            self.next_scale(v)


class B4PSO(Policy):
    """B4: particle swarm over (x, y, altitude, power) every K steps.
    Objective = the env's v2 reward at the candidate."""
    name = "B4"

    def reset(self, env):
        super().reset(env)
        self.rng = np.random.default_rng([env.scenario_seed, 44])
        self.best = np.array([env.x, env.y, BCFG["altitude_m"], BCFG["power_frac"]])

    def plan(self, env):
        cfg, u = BCFG["pso"], env.uav
        lo = np.array([0.0, 0.0, u["h_min_m"], 0.05])
        hi = np.array([env.L, env.L, u["h_max_m"], 1.0])
        n = cfg["particles"]
        pos = self.rng.uniform(lo, hi, size=(n, 4))
        pos[0] = self.best                                              # warm start from the last answer
        vel = np.zeros_like(pos)

        def score(P):
            cov = np.empty(len(P))
            for i, p in enumerate(P):                                   # one power per particle
                cov[i] = env.evaluate(p[0], p[1], p[2], env.p_max_w * p[3])[0]
            return np.array([reward_estimate(env, c, env.p_max_w * p[3]) for c, p in zip(cov, P, strict=True)])

        pbest, pscore = pos.copy(), score(pos)
        g = pbest[np.argmax(pscore)].copy()
        for _ in range(cfg["iters"]):
            r1, r2 = self.rng.uniform(size=(2, n, 1))
            vel = cfg["inertia"] * vel + cfg["c1"] * r1 * (pbest - pos) + cfg["c2"] * r2 * (g - pos)
            pos = np.clip(pos + vel, lo, hi)
            s = score(pos)
            better = s > pscore
            pbest[better], pscore[better] = pos[better], s[better]
            g = pbest[np.argmax(pscore)].copy()
        self.best = g
        self.target = (g[0], g[1], g[2])
        self.power = float(g[3])


class B5EnergyAware(Policy):
    """B5: hover unless moving to the best grid position gains enough coverage to pay for the extra energy.
    Moves if (coverage gain x K steps) > margin x (lambda_E x extra energy / hover energy)."""
    name = "B5"

    def plan(self, env):
        X, Y = _grid(env)
        p_w = env.p_max_w * self.power
        cov = env.evaluate(np.append(X, env.x), np.append(Y, env.y), np.full(len(X) + 1, BCFG["altitude_m"]), p_w)
        here, j = cov[-1], int(np.argmax(cov[:-1]))
        dist = float(np.hypot(X[j] - env.x, Y[j] - env.y))
        t_fly = dist / env.uav["v_max_mps"]
        # In the Zeng model, flying at v_max can cost LESS than hovering; then moving has no energy penalty,
        # so the extra cost is clamped at 0 (B5 then moves whenever it gains coverage).
        extra_j = max(0.0, md.propulsion_power_w(env.uav["v_max_mps"]) - md.propulsion_power_w(0.0)) * t_fly
        cost = md.CFG["env"]["lambda_energy"] * extra_j / env.hover_step_j
        gain = (cov[j] - here) * BCFG["replan_every_steps"]
        if gain > BCFG["energy_aware_margin"] * cost:
            self.target = (X[j], Y[j], BCFG["altitude_m"])
        else:
            self.target = (env.x, env.y, BCFG["altitude_m"])             # stay where we are


# ---------------------------------------------------------------- value of information: planners fed by phone reports
class ReportsView:
    """What a planner knows when the users' positions come only from their phones' GPS reports (contribution 2,
    docs/prereg/value_of_info.md). Pure NumPy; reads the env's true users but never changes the env.
    Towers are down, so the drone IS the network: an attached phone can send its GPS position (emergency-location
    reporting), but only some phones do, with GPS error, and only every few seconds.
      f       share of phones that report. Fixed per user and episode: user u reports iff U_u < f, U_u ~ U[0, 1) seeded
              by (scenario, voi.rng_stream, rep), so the reporters at a smaller f are a subset of those at a larger f.
      sigma_m GPS error: every report gets its own 2-D Gaussian error, std sigma_m per axis (E[t, u] = sigma_m Z[t, u],
              Z standard normal, seeded once per episode, so every sigma uses the same Z); the reported position is
              clipped to the map.
      age_s   reporting interval (whole seconds): phone u reports at the times phase_u + k age_s (phase_u uniform
              in {0, ..., age_s - 1}, seeded: phones are not synchronised), and once on attach (its first active
              second; t = 0 for everyone in non-sites scenarios). The planner sees each phone's LAST report: age of
              information in [0, age_s). age_s = 0: every phone reports every second (the planner sees now).
    Belief at time t = the reporting phones whose last report (time t_r <= t) was sent while they were attached
    (active at t_r), at their reported position (true position at t_r + error), with their own class and min rate
    (they are in the report). A phone that has left since (competing sites: a mover deactivates) stays in the belief
    at its stale position until its next scheduled report. Unreported users are INVISIBLE. In competing sites a mover
    and its reserve twin at B are separate entries with separate report draws (re-attach = a new phone; expected
    reporter share stays f).
    Count scaling (f < 1; f is assumed known): k visible reporters stand for n_hat = round(k / f) users (rounded up
    to even: NOMA pairs). The n_hat - k extra pseudo-users sit at the reporters' reported positions (copies split
    evenly over the reporters, largest remainder, deterministic) and get classes from the config class mix
    (explicit_classes: counts by largest remainder, interleaved along the list), because their classes are unknown.
    f = 1, sigma_m = 0, age_s = 0 gives exactly env.users_now() (same users, order, values): B6rep == B6, bit for
    bit."""

    def __init__(self, env, f=None, sigma_m=None, age_s=None, rep=0):
        c = md.CFG["voi"]
        self.env = env
        self.f = float(c["f"] if f is None else f)
        self.sigma = float(c["sigma_m"] if sigma_m is None else sigma_m)
        age = float(c["age_s"] if age_s is None else age_s)
        assert 0.0 < self.f <= 1.0, f"report share f must be in (0, 1], not {self.f}"
        assert self.sigma >= 0.0, "sigma_m must be >= 0"
        assert age >= 0 and age == int(age), "age_s must be a whole number of seconds >= 0"
        self.age = int(age)
        n = env.P.shape[1]
        key = [env.scenario_seed, int(c["rng_stream"]), int(rep)]
        self.reports = np.random.default_rng(key + [0]).uniform(size=n) < self.f
        ph = np.random.default_rng(key + [1]).uniform(size=n)
        self.phase = np.floor(ph * self.age).astype(int) if self.age > 0 else np.zeros(n, int)
        self.z = np.random.default_rng(key + [2]).standard_normal(size=env.P.shape) if self.sigma > 0 else None
        if env.active is None:
            self.first = np.zeros(n, int)
        else:                                       # first active second (never active -> after the episode)
            self.first = np.where(env.active.any(axis=0), np.argmax(env.active, axis=0), env.P.shape[0])
        names = list(md.CFG["classes"])
        mix = np.array([md.CFG["classes"][k]["share"] for k in names], dtype=float)
        self.mix = mix / mix.sum()
        self.class_rate = np.array([md.CFG["classes"][k]["min_rate_bps"] for k in names], dtype=float)
        self.rescue_idx = names.index("rescue")

    def last_report(self, t):
        """Time index of every phone's last report at or before t (attach report included)."""
        n = len(self.reports)
        tr = np.full(n, int(t)) if self.age == 0 else t - np.mod(t - self.phase, self.age)
        return np.maximum(tr, self.first)

    def visible(self, t=None):
        """(indices, report times) of the users the planner sees at time index t (default now)."""
        env = self.env
        t = env.t if t is None else int(t)
        tr = self.last_report(t)
        ok = self.reports & (self.first <= t)
        if env.active is not None:
            ok &= env.active[np.minimum(tr, env.P.shape[0] - 1), np.arange(len(tr))]
        idx = np.flatnonzero(ok)
        return idx, tr[idx]

    def belief(self, t=None):
        """(xy (k, 2), min_rate (k,), rescue (k,)) of the planner's belief at time index t (default now)."""
        env = self.env
        idx, tr = self.visible(t)
        xy = env.P[tr, idx]
        if self.sigma > 0:
            xy = np.clip(xy + self.sigma * self.z[tr, idx], 0.0, env.L)
        mr, rs = env.min_rate[idx], env.rescue[idx]
        k = len(idx)
        if self.f < 1.0 and k > 0:
            n_hat = int(round(k / self.f))
            n_hat += n_hat % 2
            n_fill = n_hat - k
            if n_fill > 0:
                copies = allocate(np.ones(k), n_fill)
                cls = explicit_classes(np.tile(self.mix, (n_fill, 1)))
                xy = np.vstack([xy, np.repeat(xy, copies, axis=0)])
                mr = np.concatenate([mr, self.class_rate[cls]])
                rs = np.concatenate([rs, cls == self.rescue_idx])
        return xy, mr, rs


def belief_coverage(env, view, X, Y, H, p_w):
    """Coverage the planner EXPECTS at the candidates, computed with env.evaluate's physics on its belief (zeros if the
    belief holds fewer than 2 users: nothing to plan on, the pilot then stays where it is)."""
    xy, mr, rs = view.belief()
    if len(xy) < 2:
        return np.zeros(len(np.atleast_1d(X)))
    return env.evaluate_users(xy, mr, rs, X, Y, H, p_w, env.t)


class _Reports:
    """Mixin: a planner that sees the users only through phone reports (ReportsView). Parameters from config `voi:`
    unless given."""

    def __init__(self, f=None, sigma_m=None, age_s=None, rep=0):
        self.voi = dict(f=f, sigma_m=sigma_m, age_s=age_s, rep=rep)

    def reset(self, env):
        super().reset(env)
        self.view = ReportsView(env, **self.voi)


class B6Reports(_Reports, B6GridAltitude):
    """B6rep: B6's search (grid x altitude levels + 'stay', every K steps, ties to the closest), scored on the belief
    built from phone reports instead of the true users. The drone still serves the TRUE users (env.step unchanged)."""
    name = "B6rep"

    def plan(self, env):
        CX, CY, CH = self.candidates(env)
        cov = belief_coverage(env, self.view, CX, CY, CH, env.p_max_w * self.power)
        j = self.pick(env, cov, CX, CY, CH)
        self.target = (CX[j], CY[j], CH[j])


class B3Reports(_Reports, B3GridSearch):
    """B3rep: B3's search (grid at the fixed altitude + the current spot), scored on the phone-report belief."""
    name = "B3rep"

    def score(self, env, X, Y, H, p_w):
        return belief_coverage(env, self.view, X, Y, H, p_w)


POLICIES = {"B0": B0Fixed, "B1": B1FollowCrowd, "B2": B2KMeans, "B3": B3GridSearch, "B4": B4PSO, "B5": B5EnergyAware,
            "B6": B6GridAltitude, "B6r": B6Refined, "B6true": B6True, "B6meas": B6Measured,
            "B7": B7Loiter, "B8": B8BatteryAware, "B6fc": B6Forecast, "B6dep": B6Depart,
            "B3obs": B3Obs, "B3obsU": B3ObsUncapped, "B3obsUO": B3ObsUncappedObstacles,
            "B3obsN": B3ObsN, "B3obsUN": B3ObsUncappedN}
# Parametrised pilots, NOT in POLICIES (so no default run list changes). Name them as "B6rep:f=0.2,sigma=10,age=30".
REP_POLICIES = {"B6rep": B6Reports, "B3rep": B3Reports}


def parse_rep(name):
    """'B6rep:f=0.2,sigma=10,age=30[,rep=0]' -> (class, kwargs). Missing keys come from config `voi:`."""
    base, _, args = name.partition(":")
    keys = {"f": "f", "sigma": "sigma_m", "age": "age_s", "rep": "rep"}
    kw = {}
    for a in filter(None, args.split(",")):
        k, v = a.split("=")
        assert k in keys, f"unknown report parameter {k!r} in {name!r}; use f, sigma, age, rep"
        kw[keys[k]] = int(v) if k == "rep" else float(v)
    return REP_POLICIES[base], kw


def make_policy(name):
    if name.partition(":")[0] in REP_POLICIES:
        cls, kw = parse_rep(name)
        return cls(**kw)
    return POLICIES[name]()
