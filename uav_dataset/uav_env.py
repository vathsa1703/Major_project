"""Gymnasium environment: ONE UAV base station serving moving ground users with NOMA.

Every step (1 s): the UAV moves (vx, vy, vz), sets its transmit power, the users move, the channel (LoS/NLoS,
obstacles, optional fading) and NOMA rates are recomputed, and the battery drains by the rotary-wing energy model.

    env = UAVEnv()
    obs, info = env.reset(seed=3)          # seed = scenario seed (same seed -> same crowd, obstacles, movement)
    obs, reward, terminated, truncated, info = env.step(action)

Action (continuous, in [-1, 1]): [vx, vy, vz, power]. vx/vy scale to v_max_mps, vz to vz_max_mps,
power maps linearly to 0..P_max (never fully off). The velocity is the command itself, unless uav.a_max_mps2 is set:
then it moves toward the command by at most a_max * dt per step, and the energy adds the load-factor term
(make_dataset.load_factor; our extension).
Observation (float32, all in [-1, 1]): see _obs(). Size = 11 + 2 * grid * grid.
Reward: v1 = coverage;  v2 = coverage - lambda_energy * (energy_step / hover_energy_step).
Battery empty -> terminated, with reward -= terminal_penalty * (share of users left uncovered).
All physics lives in make_dataset.py, so the env and the dataset can never disagree.

Opt-in extras (Track 2; the default observation above is unchanged):
  obs groups  crowd_n       log(n_users) scaled to [0, 1] over the configured n_users range (a base station knows how
                            many users are connected to it)
              history       the drone's own last `history_len` (x, y, measured coverage) at decision times, oldest first
              heat_all_u    UNCAPPED map: sqrt(share of all users per cell), in [0, 1], never saturates
              heat_rescue_u the same for the rescue users
  obs_mode="dict"           gymnasium Dict observation: "maps" (C, grid, grid) and "scalars" (vector)
  privileged=True           (dict mode only) adds "priv_maps" and "priv_n": the TRUE state, for an asymmetric critic
                            during training only. The acting policy never reads them (see rl_net.DictMapExtractor and
                            rl_utils.RLPolicy, which never even asks the env for them).
"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces

import make_dataset as md

CFG = md.CFG
# The default observation is built from these named groups, always in this order (scalars first, then the two maps).
OBS_GROUPS = ("pos", "vel", "battery", "time", "prev", "heat_all", "heat_rescue")
# Every group that exists, in canonical order (OBS_GROUPS keep their relative order, so the default is unchanged).
ALL_GROUPS = ("pos", "vel", "battery", "time", "prev", "crowd_n", "history",
              "heat_all", "heat_all_u", "heat_rescue", "heat_rescue_u")
MAP_GROUPS = ("heat_all", "heat_all_u", "heat_rescue", "heat_rescue_u")
# Critic-only keys of the Dict observation (true state). Any key starting with "priv" is privileged.
PRIV_CHANNELS = ("density", "rescue", "obstacles", "demand")


class UAVEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, reward=None, fading=None, battery_wh=None, scenario_seeds=None, scenario_overrides=None,
                 obs_groups=None, access=None, obs_mode="box", privileged=False, history_every=None, sic_eps=None,
                 rescue_first=None):
        """scenario_seeds: if given, reset() without an explicit scenario_seed draws the scenario from this pool
        (used for training, so the agent only ever sees the training seeds).
        obs_mode: "box" (flat vector, the default) or "dict". privileged: add the critic-only true state (dict only).
        history_every: seconds between two entries of the `history` group (= the agent's decision rhythm)."""
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
        unknown = set(self.obs_groups) - set(ALL_GROUPS)
        assert not unknown, f"unknown observation groups {sorted(unknown)}; choose from {ALL_GROUPS}"
        assert obs_mode in ("box", "dict"), f"obs_mode must be box or dict, not {obs_mode!r}"
        assert not (privileged and obs_mode != "dict"), "the privileged (critic-only) state needs obs_mode='dict'"
        self.dict_obs, self.privileged = obs_mode == "dict", bool(privileged)
        self.history_len = CFG["env"]["history_len"]
        self.history_every = int(history_every or CFG["env"]["history_every_s"])
        self.priv_grid = CFG["env"]["priv_grid"]
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
        if not self.dict_obs:
            self.observation_space = spaces.Box(-1.0, 1.0, shape=(self.obs_dim(self.obs_groups, self.grid),),
                                                dtype=np.float32)
        else:
            self.observation_space = self.dict_space(self.obs_groups, self.grid, self.privileged)

    @staticmethod
    def group_sizes(grid):
        return {"pos": 3, "vel": 3, "battery": 1, "time": 1, "prev": 3, "crowd_n": 1,
                "history": 3 * CFG["env"]["history_len"], **{g: grid**2 for g in MAP_GROUPS}}

    @staticmethod
    def obs_dim(groups, grid):
        sizes = UAVEnv.group_sizes(grid)
        return sum(sizes[g] for g in groups)

    @staticmethod
    def dict_space(groups, grid, privileged=False):
        """The Dict observation space: maps (C, grid, grid) in [0, 1], scalars in [-1, 1], and (critic only) the
        true state as priv_maps (4, P, P) stored as uint8 0..255 (to keep a replay buffer small) and priv_n."""
        sizes, d = UAVEnv.group_sizes(grid), {}
        n_maps = sum(g in groups for g in MAP_GROUPS)
        n_scalar = sum(sizes[g] for g in groups if g not in MAP_GROUPS)
        if n_maps:
            d["maps"] = spaces.Box(0.0, 1.0, shape=(n_maps, grid, grid), dtype=np.float32)
        if n_scalar:
            d["scalars"] = spaces.Box(-1.0, 1.0, shape=(n_scalar,), dtype=np.float32)
        if privileged:
            p = CFG["env"]["priv_grid"]
            d["priv_maps"] = spaces.Box(0, 255, shape=(len(PRIV_CHANNELS), p, p), dtype=np.uint8)
            d["priv_n"] = spaces.Box(0.0, 1.0, shape=(1,), dtype=np.float32)
        return spaces.Dict(d)

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
        self.track = [(self.x / self.L, self.y / self.L, 0.0)]          # own (x, y, coverage) every second
        self._occupancy = None                                          # obstacle map, built on first use
        return self._obs(), self._info(None)

    def observation(self, groups=None, dict_obs=None, history_every=None, privileged=None):
        """The current observation. `groups` picks a subset of observation groups (a trained agent asks for the
        groups it was trained on); default = the groups this env was built with. dict_obs / history_every /
        privileged likewise default to this env's own settings."""
        return self._obs(groups, dict_obs, history_every, privileged)

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
        a_max = self.uav.get("a_max_mps2")
        v_prev = (self.vx, self.vy)
        if a_max is not None:
            # acceleration limit: the commanded velocity is only approached, by at most a_max * dt (vector norm)
            # horizontally and az_max * dt vertically. The result is a convex mix of the old and the commanded
            # velocity, so speed limits still hold.
            dv = vh - np.array(v_prev)
            n = np.linalg.norm(dv)
            if n > a_max * self.dt:
                dv *= a_max * self.dt / n
            vh = np.array(v_prev) + dv
            az = self.uav["az_max_mps2"] * self.dt
            vz = self.vz + float(np.clip(vz - self.vz, -az, az))

        nx, ny = np.clip(self.x + vh[0] * self.dt, 0, self.L), np.clip(self.y + vh[1] * self.dt, 0, self.L)
        nh = np.clip(self.h + vz * self.dt, self.uav["h_min_m"], self.uav["h_max_m"])
        # the stored velocity is the REALISED one: at the map edge or an altitude limit the drone stops on that axis
        # (a hard geofence stop; the only case where the realised change can exceed a_max * dt)
        self.vx, self.vy, self.vz = (nx - self.x) / self.dt, (ny - self.y) / self.dt, (nh - self.h) / self.dt
        accel = float(np.hypot(self.vx - v_prev[0], self.vy - v_prev[1])) / self.dt    # realised horizontal accel.
        use_accel_energy = a_max is not None and CFG["energy"]["accel_power"]
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

        e_step = float(md.energy_step_j(np.hypot(self.vx, self.vy), self.vz, p_w,
                                        accel if use_accel_energy else None))
        self.energy_left_j = max(0.0, self.energy_left_j - e_step)
        self.energy_used_j += e_step
        self.served_user_s += float(served.sum()) * self.dt
        self.track.append((self.x / self.L, self.y / self.L, coverage))

        energy_term = 0.0
        if self.reward_version == "v2":
            energy_term = -CFG["env"]["lambda_energy"] * e_step / self.hover_step_j
        terminated = self.energy_left_j <= 0.0
        terminal_term = -CFG["env"]["terminal_penalty"] * (1.0 - coverage) if terminated else 0.0
        reward = coverage + energy_term + terminal_term
        truncated = (not terminated) and self.t >= self.T
        info = self._info(served, rate=rate, energy_step_j=e_step, p_tx_w=p_w)
        # each reward part is reported separately, so reward hacking can be spotted
        info.update(reward_coverage=coverage, reward_energy=energy_term, reward_terminal=terminal_term,
                    accel_mps2=accel)
        info.update(both, access=self.access)
        return self._obs(), float(reward), bool(terminated), bool(truncated), info

    # ------------------------------------------------------------------ helpers
    def _heatmap(self, xy):
        if len(xy) == 0:
            return np.zeros(self.grid**2)
        h, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=self.grid, range=[[0, self.L], [0, self.L]])
        return np.minimum(1.0, h.ravel() / len(xy) * 10.0)      # share of users per cell x10, capped at 1

    def _shares(self, xy, grid, weights=None):
        """Share of the users (or of `weights`) in each cell of a grid x grid map; same cell order as _heatmap."""
        if len(xy) == 0:
            return np.zeros(grid**2)
        h, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=grid, range=[[0, self.L], [0, self.L]], weights=weights)
        return h.ravel() / len(xy)

    def crowd_n(self):
        """log(n_users) scaled to [0, 1] over the configured n_users range (clipped for custom crowd sizes)."""
        lo, hi = min(CFG["n_users_choices"]), max(CFG["n_users_choices"])
        if hi <= lo:
            return 0.0
        return float(np.clip((np.log(self.sc["n_users"]) - np.log(lo)) / (np.log(hi) - np.log(lo)), 0.0, 1.0))

    def _history(self, every):
        """Own (x, y, coverage) at t - (len-1)*every, ..., t - every, t (oldest first; before the start: the start)."""
        idx = [max(0, self.t - j * every) for j in range(self.history_len - 1, -1, -1)]
        return np.array([self.track[i] for i in idx], dtype=float).ravel()

    def _map(self, g):
        xy = self.user_xy()
        if g == "heat_all":
            return self._heatmap(xy)
        if g == "heat_rescue":
            return self._heatmap(xy[self.rescue])
        # uncapped: sqrt(share per cell). In [0, 1] (1 only if everyone stands in one cell) and invertible, so it
        # carries exactly the true share without the x10 cap; sqrt spreads small shares (1% -> 0.1, 25% -> 0.5).
        return np.sqrt(self._shares(xy if g == "heat_all_u" else xy[self.rescue], self.grid))

    def _scalar(self, g, every):
        u = self.uav
        if g == "pos":
            return [self.x / self.L, self.y / self.L, (self.h - u["h_min_m"]) / (u["h_max_m"] - u["h_min_m"])]
        if g == "vel":
            return [self.vx / u["v_max_mps"], self.vy / u["v_max_mps"], self.vz / u["vz_max_mps"]]
        if g == "battery":
            return [self.energy_left_j / self.battery_j]
        if g == "time":
            return [self.t / self.T]
        if g == "prev":
            return [self.prev["coverage"], self.prev["throughput"], self.prev["fairness"]]
        if g == "crowd_n":
            return [self.crowd_n()]
        return self._history(every)                                    # "history"

    def occupancy(self):
        """Share of each priv_grid x priv_grid cell covered by collapsed buildings (8 x 8 sample points per cell).
        Static within an episode, so computed once."""
        if self._occupancy is None:
            p, k = self.priv_grid, 8
            c = (np.arange(p * k) + 0.5) * self.L / (p * k)
            X, Y = np.meshgrid(c, c, indexing="ij")                  # x index major, like the maps
            inside = np.zeros(X.shape, bool)
            for x0, y0, x1, y1 in self.boxes:
                inside |= (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
            self._occupancy = inside.reshape(p, k, p, k).mean(axis=(1, 3)).ravel()
        return self._occupancy

    def privileged_state(self):
        """CRITIC-ONLY true state (raw, nothing computed by a baseline's scorer): uncapped sqrt-share maps of all
        users and of rescue users, obstacle occupancy, demand (mean min rate per cell / the largest class min rate),
        all on a priv_grid x priv_grid map, plus crowd_n. Maps are stored as uint8 (value x 255)."""
        p, xy = self.priv_grid, self.user_xy()
        top = max(c["min_rate_bps"] for c in CFG["classes"].values())
        count = self._shares(xy, p) * len(xy)
        demand = np.divide(self._shares(xy, p, weights=self.min_rate / top) * len(xy), count,
                           out=np.zeros(p * p), where=count > 0)
        chans = {"density": np.sqrt(self._shares(xy, p)), "rescue": np.sqrt(self._shares(xy[self.rescue], p)),
                 "obstacles": self.occupancy(), "demand": demand}
        maps = np.stack([chans[c].reshape(p, p) for c in PRIV_CHANNELS])
        return {"priv_maps": np.round(np.clip(maps, 0.0, 1.0) * 255).astype(np.uint8),
                "priv_n": np.array([self.crowd_n()], dtype=np.float32)}

    def _obs(self, groups=None, dict_obs=None, history_every=None, privileged=None):
        groups = self.obs_groups if groups is None else tuple(groups)
        dict_obs = self.dict_obs if dict_obs is None else dict_obs
        every = self.history_every if history_every is None else int(history_every)
        privileged = self.privileged if privileged is None else privileged
        scal = [np.asarray(self._scalar(g, every), dtype=float) for g in ALL_GROUPS
                if g in groups and g not in MAP_GROUPS]
        maps = [self._map(g) for g in ALL_GROUPS if g in groups and g in MAP_GROUPS]
        if not dict_obs:
            return np.clip(np.concatenate(scal + maps), -1.0, 1.0).astype(np.float32)
        out = {}
        if maps:
            out["maps"] = np.clip(np.stack(maps), 0.0, 1.0).reshape(len(maps), self.grid, self.grid).astype(np.float32)
        if scal:
            out["scalars"] = np.clip(np.concatenate(scal), -1.0, 1.0).astype(np.float32)
        if privileged:
            out.update(self.privileged_state())
        return out

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
