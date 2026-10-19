"""Baseline controllers B0-B5, plus B6 (B3 with altitude search).
Each one drives the SAME UAVEnv through env.step(), so comparisons are fair.

    policy = make_policy("B2")
    obs, info = env.reset(seed=3); policy.reset(env)
    action = policy.act(env)          # numpy array of 4 numbers in [-1, 1]

Baselines may look at the true user positions (privileged information); the RL agent only sees heatmaps.
That makes them a strong test: RL has to beat them, not B0 (a drone that does nothing).
All settings are in config.yaml under `baselines:`.
"""
import numpy as np

import make_dataset as md

BCFG = md.CFG["baselines"]


# ---------------------------------------------------------------- shared helpers
def go_to(env, tx, ty, th, power_frac):
    """Action that flies toward (tx, ty, th) as fast as allowed and sets the transmit power."""
    u = env.uav
    d = np.array([tx - env.x, ty - env.y]) / (u["v_max_mps"] * env.dt)
    n = np.linalg.norm(d)
    if n > 1.0:
        d = d / n
    az = np.clip((th - env.h) / (u["vz_max_mps"] * env.dt), -1.0, 1.0)
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

    def plan(self, env):
        X, Y = _grid(env)
        X, Y = np.append(X, env.x), np.append(Y, env.y)
        p_w = env.p_max_w * self.power
        cov = env.evaluate(X, Y, np.full(len(X), BCFG["altitude_m"]), p_w)
        best = np.flatnonzero(cov >= cov.max() - 1e-12)
        j = best[np.argmin(np.hypot(X[best] - env.x, Y[best] - env.y))]      # ties: the closest one
        self.target = (X[j], Y[j], BCFG["altitude_m"])


class B6GridAltitude(Policy):
    """B6 (B3 plus altitude): every K steps, score every grid position at every altitude level (plus the current
    spot), go to the best. Added so B4's lead over B3 can be split into 'chooses altitude' and 'places better'.
    Power stays at full, like B3."""
    name = "B6"

    def plan(self, env):
        X, Y = _grid(env)
        levels = np.array(BCFG["altitude_levels_m"], dtype=float)
        CX, CH = np.repeat(X, len(levels)), np.tile(levels, len(X))
        CY = np.repeat(Y, len(levels))
        CX, CY, CH = np.append(CX, env.x), np.append(CY, env.y), np.append(CH, env.h)
        cov = env.evaluate(CX, CY, CH, env.p_max_w * self.power)
        best = np.flatnonzero(cov >= cov.max() - 1e-12)
        d = np.sqrt((CX[best] - env.x) ** 2 + (CY[best] - env.y) ** 2 + (CH[best] - env.h) ** 2)
        j = best[np.argmin(d)]                                           # ties: the closest one
        self.target = (CX[j], CY[j], CH[j])


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
            "B6": B6GridAltitude}


def make_policy(name):
    return POLICIES[name]()
