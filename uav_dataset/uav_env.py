"""Gymnasium environment: ONE UAV base station serving moving ground users with NOMA.

Every step (1 s): the UAV moves (vx, vy, vz), sets its transmit power, the users move, the channel (LoS/NLoS,
obstacles, optional fading) and NOMA rates are recomputed, and the battery drains by the rotary-wing energy model.

    env = UAVEnv()
    obs, info = env.reset(seed=3)          # seed = scenario seed (same seed -> same crowd, obstacles, movement)
    obs, reward, terminated, truncated, info = env.step(action)

Action (continuous, in [-1, 1]): [vx, vy, vz, power]. vx/vy scale to v_max_mps, vz to vz_max_mps,
power maps linearly to 0..P_max (never fully off).
Observation (float32, all in [-1, 1]): see _obs(). Size = 11 + 2 * grid * grid.
Reward: v1 = coverage;  v2 = coverage - lambda_energy * (energy_step / hover_energy_step).
Battery empty -> terminated, with reward -= terminal_penalty * (share of users left uncovered).
All physics lives in make_dataset.py, so the env and the dataset can never disagree.
"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces

import make_dataset as md

CFG = md.CFG
# The observation is built from these named groups, always in this order (scalars first, then the two maps).
OBS_GROUPS = ("pos", "vel", "battery", "time", "prev", "heat_all", "heat_rescue")


class UAVEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, reward=None, fading=None, battery_wh=None, scenario_seeds=None, scenario_overrides=None,
                 obs_groups=None, access=None, sic_eps=None, rescue_first=None):
        """scenario_seeds: if given, reset() without an explicit scenario_seed draws the scenario from this pool
        (used for training, so the agent only ever sees the training seeds)."""
        # scenario_overrides: e.g. {"n_users": 500, "n_clusters": 4, "mobility": "surge", "n_obstacles": 6} replaces
        # those fields of every scenario the seed would produce (to try your own situation)
        super().__init__()
        self.scenario_overrides = dict(scenario_overrides or {})
        self.scenario_pool = None if scenario_seeds is None else [int(s) for s in scenario_seeds]
        self.L = CFG["area_m"]
        self.T = CFG["mobility"]["episode_steps"]
        self.dt = CFG["energy"]["dt_s"]
        self.uav = CFG["uav"]
        self.grid = CFG["env"]["grid"]
        # obs_groups: which measurements the agent sees (default: all, 211 numbers). A smaller set is allowed,
        # for example without the drone's own velocity. No group reveals the answer: only what a drone could measure.
        self.obs_groups = tuple(obs_groups) if obs_groups else OBS_GROUPS
        unknown = set(self.obs_groups) - set(OBS_GROUPS)
        assert not unknown, f"unknown observation groups {sorted(unknown)}; choose from {OBS_GROUPS}"
        self.reward_version = reward or CFG["env"]["reward"]
        self.fading = CFG["fading"]["enabled"] if fading is None else fading
        # access: how the drone shares the radio. "noma" = pairs share a frequency (superposition + SIC);
        # "oma" = everyone gets a separate slice (FDMA) with the same total bandwidth and power. Used for H3.
        # "oma_opt" / "noma_opt" = QoS-aware versions: each admitted user gets just its min rate at minimum power,
        # cheapest users first (noma_opt pairs them and picks NOMA or OMA per pair); see make_dataset.access_rates.
        self.access = access or CFG["env"]["access"]
        assert self.access in md.ACCESS_SCHEMES, f"access must be one of {md.ACCESS_SCHEMES}, not {self.access!r}"
        self.sic_eps = float(CFG["access"]["sic_eps"] if sic_eps is None else sic_eps)
        self.rescue_first = bool(CFG["access"]["rescue_first"] if rescue_first is None else rescue_first)
        self.battery_j = (battery_wh if battery_wh is not None else CFG["energy"]["battery_wh"]) * 3600.0
        self.p_max_w = 10 ** ((self.uav["p_max_dbm"] - 30) / 10)
        self.noise_psd = 10 ** ((CFG["noise_density_dbm_hz"] + CFG["noise_figure_db"] - 30) / 10)
        self.hover_step_j = md.energy_step_j(0.0, 0.0, 0.0)
        self.action_space = spaces.Box(-1.0, 1.0, shape=(4,), dtype=np.float32)
        self.observation_space = spaces.Box(-1.0, 1.0, shape=(self.obs_dim(self.obs_groups, self.grid),),
                                            dtype=np.float32)

    @staticmethod
    def obs_dim(groups, grid):
        sizes = {"pos": 3, "vel": 3, "battery": 1, "time": 1, "prev": 3, "heat_all": grid**2,
                 "heat_rescue": grid**2}
        return sum(sizes[g] for g in groups)

    # ------------------------------------------------------------------ episode
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        ss = (options or {}).get("scenario_seed")
        if ss is None and self.scenario_pool is not None:
            ss = self.scenario_pool[int(self.np_random.integers(len(self.scenario_pool)))]
        if ss is None:
            ss = seed if seed is not None else int(self.np_random.integers(0, 2**31 - 1))
        self.scenario_seed = int(ss)
        self.sc = md.make_scenario(self.scenario_seed)
        self.sc.update(self.scenario_overrides)
        if "n_users" in self.scenario_overrides:
            assert self.sc["n_users"] % 2 == 0, "n_users must be even (NOMA pairs)"
            self.sc["bandwidth_hz"] = self.sc["n_users"] * CFG["bandwidth_per_user_hz"]
        self.users = md.make_users(self.scenario_seed, self.sc)
        self.boxes = md.obstacle_array(md.make_obstacles(self.scenario_seed, self.sc))
        self.P, self.V = md.simulate_positions(self.scenario_seed, self.sc, self.users)   # (T+1, n, 2)
        self.min_rate = self.users["min_rate_bps"].values
        self.rescue = (self.users["class"] == "rescue").values
        self.rng = np.random.default_rng([self.scenario_seed, 5])      # fading + random pairing, per scenario
        self.t = 0
        self.x = self.y = self.L / 2
        self.h = self.uav["start_h_m"]
        self.vx = self.vy = self.vz = 0.0
        self.energy_left_j = self.battery_j
        self.energy_used_j = 0.0
        self.served_user_s = 0.0
        self.prev = dict(coverage=0.0, throughput=0.0, fairness=0.0)
        return self._obs(), self._info(None)

    def observation(self, groups=None):
        """The current observation. `groups` picks a subset of observation groups (a trained agent asks for the
        groups it was trained on); default = the groups this env was built with."""
        return self._obs(groups)

    def user_xy(self, t=None):
        return self.P[self.t if t is None else t]

    def evaluate(self, X, Y, H, p_w):
        """Coverage the drone WOULD get at each candidate position (X, Y, H arrays) with transmit power p_w (W),
        for the current user positions. Average channel (no fading). Does not change env state or the env rng.
        Used by the search baselines (B3, B4, B5)."""
        ux, uy = self.user_xy().T
        X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
        gains = md.channel_gain(ux, uy, X, Y, H, self.boxes)
        rng = np.random.default_rng([self.scenario_seed, self.t])
        if self.access in md.QOS_SCHEMES:                 # vectorised over all candidates at once
            return self.access_rates(gains, p_w, return_info=True)[1]["served"].mean(axis=1)
        pick = 0 if self.access == "noma" else 1
        return np.array([
            (md.noma_rates(g, p_w, self.noise_psd, self.sc["bandwidth_hz"], self.sc["pairing"], rng)[pick]
             >= self.min_rate).mean() for g in gains])

    def access_rates(self, gains, p_w, return_info=False):
        """Rates under this env's QoS-aware scheme (oma_opt / noma_opt) for gains (N,) or (P, N)."""
        return md.access_rates(gains, p_w, self.noise_psd, self.sc["bandwidth_hz"], self.min_rate, self.access,
                               eps=self.sic_eps, rescue=self.rescue, rescue_first=self.rescue_first,
                               return_info=return_info)

    # ------------------------------------------------------------------ step
    def step(self, action):
        a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        vh = a[:2] * self.uav["v_max_mps"]
        norm = np.linalg.norm(vh)
        if norm > self.uav["v_max_mps"]:
            vh *= self.uav["v_max_mps"] / norm
        vz = a[2] * self.uav["vz_max_mps"]
        p_w = max(1e-3, self.p_max_w * (a[3] + 1) / 2)

        nx, ny = np.clip(self.x + vh[0] * self.dt, 0, self.L), np.clip(self.y + vh[1] * self.dt, 0, self.L)
        nh = np.clip(self.h + vz * self.dt, self.uav["h_min_m"], self.uav["h_max_m"])
        self.vx, self.vy, self.vz = (nx - self.x) / self.dt, (ny - self.y) / self.dt, (nh - self.h) / self.dt
        self.x, self.y, self.h = float(nx), float(ny), float(nh)
        self.t += 1

        ux, uy = self.user_xy().T
        g = md.channel_gain(ux, uy, np.array([self.x]), np.array([self.y]), np.array([self.h]), self.boxes,
                            self.rng, self.fading)[0]
        rate_noma, rate_oma = md.noma_rates(g, p_w, self.noise_psd, self.sc["bandwidth_hz"], self.sc["pairing"],
                                            self.rng)
        extra = {}
        if self.access in md.QOS_SCHEMES:
            rate, acc = self.access_rates(g, p_w, return_info=True)
            served = acc["served"]
            extra = dict(pairs=int(acc["pairs"]), noma_pairs=int(acc["noma_pairs"]),
                         alpha_lt_half=int(acc["alpha_lt_half"]))
        else:
            rate = rate_noma if self.access == "noma" else rate_oma
            served = rate >= self.min_rate
        # the fixed schemes are always reported, so every run also shows what they would have given
        both = dict(coverage_noma=float((rate_noma >= self.min_rate).mean()),
                    coverage_oma=float((rate_oma >= self.min_rate).mean()),
                    sum_rate_noma_mbps=float(rate_noma.sum() / 1e6), sum_rate_oma_mbps=float(rate_oma.sum() / 1e6))
        coverage = float(served.mean())
        both.update(coverage_access=coverage, sum_rate_access_mbps=float(rate.sum() / 1e6),
                    fairness_served=md.jain(rate[served]) if served.any() else 0.0, **extra)
        self.prev = dict(
            coverage=coverage,
            throughput=float(min(1.0, rate.sum() / (2.0 * self.min_rate.sum()))),
            fairness=md.jain(rate))

        e_step = float(md.energy_step_j(np.hypot(self.vx, self.vy), self.vz, p_w))
        self.energy_left_j = max(0.0, self.energy_left_j - e_step)
        self.energy_used_j += e_step
        self.served_user_s += float(served.sum()) * self.dt

        energy_term = 0.0
        if self.reward_version == "v2":
            energy_term = -CFG["env"]["lambda_energy"] * e_step / self.hover_step_j
        terminated = self.energy_left_j <= 0.0
        terminal_term = -CFG["env"]["terminal_penalty"] * (1.0 - coverage) if terminated else 0.0
        reward = coverage + energy_term + terminal_term
        truncated = (not terminated) and self.t >= self.T
        info = self._info(served, rate=rate, energy_step_j=e_step, p_tx_w=p_w)
        # each reward part is reported separately, so reward hacking can be spotted
        info.update(reward_coverage=coverage, reward_energy=energy_term, reward_terminal=terminal_term)
        info.update(both, access=self.access)
        return self._obs(), float(reward), bool(terminated), bool(truncated), info

    # ------------------------------------------------------------------ helpers
    def _heatmap(self, xy):
        if len(xy) == 0:
            return np.zeros(self.grid**2)
        h, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=self.grid, range=[[0, self.L], [0, self.L]])
        return np.minimum(1.0, h.ravel() / len(xy) * 10.0)      # share of users per cell x10, capped at 1

    def _obs(self, groups=None):
        groups = self.obs_groups if groups is None else tuple(groups)
        u, xy = self.uav, self.user_xy()
        scalar = {
            "pos": [self.x / self.L, self.y / self.L, (self.h - u["h_min_m"]) / (u["h_max_m"] - u["h_min_m"])],
            "vel": [self.vx / u["v_max_mps"], self.vy / u["v_max_mps"], self.vz / u["vz_max_mps"]],
            "battery": [self.energy_left_j / self.battery_j],
            "time": [self.t / self.T],
            "prev": [self.prev["coverage"], self.prev["throughput"], self.prev["fairness"]]}
        chunks = [np.asarray(scalar[g], dtype=float) for g in OBS_GROUPS if g in groups and g in scalar]
        if "heat_all" in groups:
            chunks.append(self._heatmap(xy))
        if "heat_rescue" in groups:
            chunks.append(self._heatmap(xy[self.rescue]))
        return np.clip(np.concatenate(chunks), -1.0, 1.0).astype(np.float32)

    def _info(self, served, rate=None, energy_step_j=0.0, p_tx_w=0.0):
        used_wh = self.energy_used_j / 3600.0
        info = dict(
            scenario_seed=self.scenario_seed, t=self.t, mobility=self.sc["mobility"], n_users=self.sc["n_users"],
            x=self.x, y=self.y, h=self.h, battery_wh=self.energy_left_j / 3600.0,
            coverage=self.prev["coverage"], fairness=self.prev["fairness"],
            sum_rate_mbps=float(rate.sum() / 1e6) if rate is not None else 0.0,
            outage_rescue=float(1 - served[self.rescue].mean()) if served is not None and self.rescue.any() else 0.0,
            energy_step_j=energy_step_j, p_tx_w=p_tx_w,
            served_user_s_per_wh=self.served_user_s / used_wh if used_wh > 0 else 0.0)
        if served is not None:
            info["served"] = served
        return info
