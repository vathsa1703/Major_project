"""Baseline controllers B0-B5, plus B6 (B3 with altitude search) and B7 (B6's targets, but circling at the
minimum-power speed instead of hovering; plan step 5).
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
        xy = env.user_xy()
        w = np.where(self.rescue, BCFG["rescue_weight"], 1.0)
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
        return expected_coverage(env, xy, probs, X, Y, H, p_w, env.boxes if self.use_boxes else None)


class B3ObsN(B3Obs):
    """B3obsN: B3obs told the true number of users (what the agent's crowd_n input gives it). Capped maps."""
    name = "B3obsN"
    true_n = True


class B3ObsUncapped(B3Obs):
    """B3obsU (rung 2): B3obs with the heatmaps UNCAPPED (true share of users per cell, not x10 capped at 1).
    The pseudo-crowd size stays obs_pseudo_users, so the ONLY difference from B3obs is the saturation cap."""
    name = "B3obsU"

    def maps(self, env):
        xy = env.user_xy()
        return cell_shares(env, xy), cell_shares(env, xy[env.rescue])


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

    def plan(self, env):
        X, Y = _grid(env)
        hx, hy, hh = self.here(env)
        levels = np.array(BCFG["altitude_levels_m"], dtype=float)
        CX, CH = np.repeat(X, len(levels)), np.tile(levels, len(X))
        CY = np.repeat(Y, len(levels))
        CX, CY, CH = np.append(CX, hx), np.append(CY, hy), np.append(CH, hh)
        cov = env.evaluate(CX, CY, CH, env.p_max_w * self.power)
        best = np.flatnonzero(cov >= cov.max() - 1e-12)
        d = np.sqrt((CX[best] - hx) ** 2 + (CY[best] - hy) ** 2 + (CH[best] - hh) ** 2)
        j = best[np.argmin(d)]                                           # ties: the closest one
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


POLICIES = {"B0": B0Fixed, "B1": B1FollowCrowd, "B2": B2KMeans, "B3": B3GridSearch, "B4": B4PSO, "B5": B5EnergyAware,
            "B6": B6GridAltitude, "B7": B7Loiter,
            "B3obs": B3Obs, "B3obsU": B3ObsUncapped, "B3obsUO": B3ObsUncappedObstacles,
            "B3obsN": B3ObsN, "B3obsUN": B3ObsUncappedN}


def make_policy(name):
    return POLICIES[name]()
