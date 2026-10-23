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
Stage 5 (opt-in, dynamics="quad" or config quad.enabled): the velocity computed above (same semantics) becomes the
setpoint of a simulated quadcopter + autopilot (quadsim.py) flown for the 1 s step; position and velocity come from the
quadcopter, energy uses its airspeed / climb rate / acceleration at every integration step, the flight is logged at
5 Hz in env.flight and info["quad"] holds attitude, wind and peaks. Default "point" = the old game, bit for bit.
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
              event_countdown seconds to the ANNOUNCED event / episode length, clipped to [0, 1] (0 once it has
                            started); 1 when the scenario has no announced event. OFF by default: the owner has not
                            decided whether the AI may use it (D-52)
  Competing sites (mobility `sites`, D-52): users carry an activity mask active[t, user] (make_dataset.activity_mask).
  Only the users active at t count: coverage denominator, radio resources (every access scheme runs on the active subset
  with the scenario's fixed total bandwidth), evaluate(t), the maps and the critic-only state. Without a mask (every
  other scenario) the arrays are the full ones, exactly as before.
  Model mismatch (config `mismatch:`, off by default): env.step serves users through the TRUE channel (user-side
  shadowing, a different building loss, hidden buildings), while evaluate(model="nominal") (the default, used by every
  planner) keeps the textbook model; evaluate(model="true") is for the B6true upper bound only. See gains().
  obs_mode="dict"           gymnasium Dict observation: "maps" (C, grid, grid) and "scalars" (vector)
  privileged=True           (dict mode only) adds "priv_maps" and "priv_n": the TRUE state, for an asymmetric critic
                            during training only. The acting policy never reads them (see rl_net.DictMapExtractor and
                            rl_utils.RLPolicy, which never even asks the env for them).
"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces

import make_dataset as md
import quadsim

CFG = md.CFG
# The default observation is built from these named groups, always in this order (scalars first, then the two maps).
OBS_GROUPS = ("pos", "vel", "battery", "time", "prev", "heat_all", "heat_rescue")
# Every group that exists, in canonical order (OBS_GROUPS keep their relative order, so the default is unchanged).
ALL_GROUPS = ("pos", "vel", "battery", "time", "prev", "crowd_n", "history", "event_countdown", "event_announce",
              "heat_all", "heat_all_u", "heat_rescue", "heat_rescue_u")
MAP_GROUPS = ("heat_all", "heat_all_u", "heat_rescue", "heat_rescue_u")
# Critic-only keys of the Dict observation (true state). Any key starting with "priv" is privileged.
PRIV_CHANNELS = ("density", "rescue", "obstacles", "demand")


class UAVEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, reward=None, fading=None, battery_wh=None, scenario_seeds=None, scenario_overrides=None,
                 obs_groups=None, access=None, obs_mode="box", privileged=False, history_every=None, sic_eps=None,
                 rescue_first=None, dynamics=None, quad_overrides=None):
        """scenario_seeds: if given, reset() without an explicit scenario_seed draws the scenario from this pool
        (used for training, so the agent only ever sees the training seeds).
        obs_mode: "box" (flat vector, the default) or "dict". privileged: add the critic-only true state (dict only).
        history_every: seconds between two entries of the `history` group (= the agent's decision rhythm).
        dynamics: "point" = the old point-mass game; "quad" = the commanded velocity is flown by the simulated
        quadcopter + autopilot (quadsim.py, Stage 5); None = config quad.enabled. quad_overrides: changes to config
        `quad:` for this env only, e.g. quadsim.wind_overrides(True) for the wind-on preset."""
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
        self.dynamics = dynamics or ("quad" if CFG.get("quad", {}).get("enabled") else "point")
        assert self.dynamics in ("point", "quad"), f"dynamics must be 'point' or 'quad', not {self.dynamics!r}"
        self.quad_cfg = quadsim.quad_config(quad_overrides) if self.dynamics == "quad" else None
        self.quad, self.flight = None, []            # QuadSim (dynamics "quad" only) and its 5 Hz flight log
        self.action_space = spaces.Box(-1.0, 1.0, shape=(4,), dtype=np.float32)
        if not self.dict_obs:
            self.observation_space = spaces.Box(-1.0, 1.0, shape=(self.obs_dim(self.obs_groups, self.grid),),
                                                dtype=np.float32)
        else:
            self.observation_space = self.dict_space(self.obs_groups, self.grid, self.privileged)

    @staticmethod
    def group_sizes(grid):
        return {"pos": 3, "vel": 3, "battery": 1, "time": 1, "prev": 3, "crowd_n": 1, "event_countdown": 1,
                "event_announce": 6,
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
        self._make_true_world()
        self.P, self.V = md.simulate_positions(self.scenario_seed, self.sc, self.users)   # (T+1, n, 2)
        self.active = md.activity_mask(self.users, self.T, self.dt)    # (T+1, n) bool, or None = everyone counts
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
        if self.dynamics == "quad":            # the quadcopter starts in trimmed hover at the same spot; own gust rng
            self.quad = quadsim.QuadSim(self.scenario_seed, (0.0, self.L, 0.0, self.L, self.uav["h_min_m"],
                                                             self.uav["h_max_m"]), cfg=self.quad_cfg)
            self.flight = [self.quad.reset(self.x, self.y, self.h)]
        return self._obs(), self._info(None)

    def _make_true_world(self):
        """Model mismatch (config `mismatch:`): the TRUE world's buildings, building loss and user-side shadowing
        field. Off (the default): the true world IS the nominal model (same objects), so every result is bit-exact."""
        m = md.mismatch_cfg()
        draw = int(m.get("draw", 0) or 0)
        hidden = md.hidden_obstacles(self.scenario_seed, int(m.get("hidden_obstacles", 0) or 0), draw)
        self.true_boxes = np.vstack([self.boxes, hidden]) if len(hidden) else self.boxes
        self.true_excess_db = m.get("excess_loss_db")                  # None = the nominal value
        sigma = float(m.get("shadow_sigma_db", 0.0) or 0.0)
        self.shadow_sigma_db = sigma
        self.shadow_field = (md.ShadowField(self.scenario_seed, self.L, m["shadow_corr_m"],
                                            m.get("shadow_res_frac", 0.25), draw) if sigma > 0 else None)
        self.mismatch = md.mismatch_on()

    def gains(self, ux, uy, X, Y, H, model="true", rng=None, fading=None):
        """Channel gains (P, N) from drones (X, Y, H) to users (ux, uy). model="nominal" = the textbook model the
        planners use (known buildings, obstacles.excess_loss_db, no shadowing); "true" = the world env.step serves
        (with the mismatch, if any). Identical when the mismatch is off."""
        assert model in ("nominal", "true"), f"model must be 'nominal' or 'true', not {model!r}"
        if model == "nominal" or not self.mismatch:
            return md.channel_gain(ux, uy, X, Y, H, self.boxes, rng, fading)
        shadow = None
        if self.shadow_field is not None:
            shadow = (self.shadow_field.at(ux, uy), self.shadow_sigma_db)
        return md.channel_gain(ux, uy, X, Y, H, self.true_boxes, rng, fading, excess_loss_db=self.true_excess_db,
                               shadow=shadow)

    def observation(self, groups=None, dict_obs=None, history_every=None, privileged=None):
        """The current observation. `groups` picks a subset of observation groups (a trained agent asks for the
        groups it was trained on); default = the groups this env was built with. dict_obs / history_every /
        privileged likewise default to this env's own settings."""
        return self._obs(groups, dict_obs, history_every, privileged)

    def user_xy(self, t=None):
        """Positions of ALL users (including the inactive ones of a competing-sites scenario; see users_now)."""
        return self.P[self.t if t is None else t]

    def active_mask(self, t=None):
        """Which users count at time index t (default now): bool (n,), or None when everyone always counts."""
        return None if self.active is None else self.active[self.t if t is None else int(t)]

    def users_now(self, t=None):
        """(xy, min_rate, rescue) of the users that count at time index t (default now). Without an activity mask
        these are exactly the full arrays (old behaviour)."""
        xy, m = self.user_xy(t), self.active_mask(t)
        if m is None:
            return xy, self.min_rate, self.rescue
        return xy[m], self.min_rate[m], self.rescue[m]

    def event_countdown(self):
        """Seconds to the announced event / episode length, in [0, 1] (0 once it started); 1 if none is announced."""
        t0 = self.sc.get("event_t0_s")
        if t0 is None or not self.sc.get("announced", False):
            return 1.0
        return float(np.clip((t0 - self.t * self.dt) / (self.T * self.dt), 0.0, 1.0))

    def event_announce(self):
        """The rest of the announcement message (owner's decision D-54: the AI may use it, like B6fc): where people
        move from (site A) and to (site B) as x/L, y/L, the share that moves, and the switch duration / episode
        length. All zeros when nothing is announced (the countdown then reads 1)."""
        if self.sc.get("event_t0_s") is None or not self.sc.get("announced", False):
            return [0.0] * 6
        T = self.T * self.dt
        return [self.sc["site_x"][0] / self.L, self.sc["site_y"][0] / self.L, self.sc["site_x"][1] / self.L,
                self.sc["site_y"][1] / self.L, float(self.sc["event_share"]), float(self.sc["tau_s"]) / T]

    def evaluate(self, X, Y, H, p_w, t=None, model="nominal"):
        """Coverage the drone WOULD get at each candidate position (X, Y, H arrays) with transmit power p_w (W),
        for the user positions at time index t (default: now, env.t). Average channel (no fading). Does not change
        env state or the env rng. Used by the search baselines (B3, B4, B5, B6) and, with a future t, by the
        clairvoyant oracle (oracle.py).
        model: "nominal" (default) = the textbook model a planner has; "true" = the world env.step serves (with the
        model mismatch, if any; only the B6true upper bound may use it). The same thing when the mismatch is off."""
        t = self.t if t is None else int(t)
        xy, min_rate, rescue = self.users_now(t)          # only the users active at t (all, without a mask)
        return self.evaluate_users(xy, min_rate, rescue, X, Y, H, p_w, t, model=model)

    def evaluate_users(self, xy, min_rate, rescue, X, Y, H, p_w, t, model="nominal"):
        """env.evaluate for a GIVEN user set (positions xy (n, 2), min rates, rescue flags) instead of the users at
        time index t: the same physics, access scheme, bandwidth and rng recipe (seeded by (scenario, t); used only by
        the fixed schemes with random pairing). evaluate(..., t) == evaluate_users(*users_now(t), ..., t). Used by B6fc
        to score a FORECAST user set (baselines.B6Forecast)."""
        ux, uy = np.asarray(xy, dtype=float).T
        X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
        gains = self.gains(ux, uy, X, Y, H, model=model)
        rng = np.random.default_rng([self.scenario_seed, t])
        if self.access in md.QOS_SCHEMES:                 # vectorised over all candidates at once
            return self.access_rates(gains, p_w, return_info=True, min_rate=min_rate,
                                     rescue=rescue)[1]["served"].mean(axis=1)
        pick = 0 if self.access == "noma" else 1
        return np.array([
            (md.noma_rates(g, p_w, self.noise_psd, self.sc["bandwidth_hz"], self.sc["pairing"], rng)[pick]
             >= min_rate).mean() for g in gains])

    def access_rates(self, gains, p_w, return_info=False, min_rate=None, rescue=None):
        """Rates under this env's QoS-aware scheme (oma_opt / noma_opt) for gains (N,) or (P, N).
        min_rate / rescue default to the users that count now when the gains are for them (competing sites), else
        to all users (every other scenario: the same thing)."""
        if min_rate is None:
            _, min_rate, rescue = self.users_now()
            if np.shape(gains)[-1] != len(min_rate):
                min_rate, rescue = self.min_rate, self.rescue
        return md.access_rates(gains, p_w, self.noise_psd, self.sc["bandwidth_hz"], min_rate, self.access,
                               eps=self.sic_eps, rescue=rescue, rescue_first=self.rescue_first,
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

        use_accel_energy = a_max is not None and CFG["energy"]["accel_power"]
        quad_info, e_quad = None, None
        if self.quad is None:                      # the point-mass game (unchanged)
            nx, ny = np.clip(self.x + vh[0] * self.dt, 0, self.L), np.clip(self.y + vh[1] * self.dt, 0, self.L)
            nh = np.clip(self.h + vz * self.dt, self.uav["h_min_m"], self.uav["h_max_m"])
            # the stored velocity is the REALISED one: at the map edge or an altitude limit the drone stops on that
            # axis (a hard geofence stop; the only case where the realised change can exceed a_max * dt)
            self.vx, self.vy, self.vz = (nx - self.x) / self.dt, (ny - self.y) / self.dt, (nh - self.h) / self.dt
            accel = float(np.hypot(self.vx - v_prev[0], self.vy - v_prev[1])) / self.dt   # realised horizontal accel.
        else:
            # Stage 5: the commanded velocity is the autopilot's setpoint for this step; position and velocity are
            # the quadcopter's own (it lags, overshoots, drifts in gusts; the autopilot's geofence keeps it in the map)
            fl = self.quad.fly((float(vh[0]), float(vh[1]), float(vz)), self.dt)
            (nx, ny, nh), (self.vx, self.vy, self.vz) = fl["pos"], fl["vel"]
            accel = float(np.hypot(self.vx - v_prev[0], self.vy - v_prev[1])) / self.dt
            # energy: Zeng's power at every integration step's AIRSPEED (= ground speed in calm air) and climb rate,
            # averaged over the step; the turning/acceleration term uses the actual horizontal acceleration
            e_quad = float(np.mean(md.energy_step_j(fl["airspeed_h"], fl["vz"], p_w,
                                                    fl["a_h"] if use_accel_energy else None)))
            self.flight.extend(fl["samples"])
            r, pch, yw = fl["att"]
            quad_info = dict(roll_deg=float(np.degrees(r)), pitch_deg=float(np.degrees(pch)),
                             yaw_deg=float(np.degrees(yw)), tilt_peak_deg=float(np.degrees(fl["tilt_peak"])),
                             speed_peak_mps=float(fl["speed_peak"]), airspeed_mps=float(fl["airspeed_h"][-1]),
                             wind_mps=tuple(float(w) for w in fl["wind"]), thrust_ratio=float(fl["thrust_ratio"]),
                             commanded_mps=(float(vh[0]), float(vh[1]), float(vz)))
        self.x, self.y, self.h = float(nx), float(ny), float(nh)
        self.t += 1

        xy, min_rate, rescue = self.users_now()           # only the users that count now (all, without a mask)
        ux, uy = xy.T
        # the TRUE channel (= the nominal one when the mismatch is off); the radio layer below allocates with these
        # true gains (a base station measures its channels), only the planners' placement uses the nominal model
        g = self.gains(ux, uy, np.array([self.x]), np.array([self.y]), np.array([self.h]), "true", self.rng,
                       self.fading)[0]
        rate_noma, rate_oma = md.noma_rates(g, p_w, self.noise_psd, self.sc["bandwidth_hz"], self.sc["pairing"],
                                            self.rng)
        extra = {}
        if self.access in md.QOS_SCHEMES:
            rate, acc = self.access_rates(g, p_w, return_info=True, min_rate=min_rate, rescue=rescue)
            served = acc["served"]
            extra = dict(pairs=int(acc["pairs"]), noma_pairs=int(acc["noma_pairs"]),
                         alpha_lt_half=int(acc["alpha_lt_half"]))
        else:
            rate = rate_noma if self.access == "noma" else rate_oma
            served = rate >= min_rate
        # the fixed schemes are always reported, so every run also shows what they would have given
        both = dict(coverage_noma=float((rate_noma >= min_rate).mean()),
                    coverage_oma=float((rate_oma >= min_rate).mean()),
                    sum_rate_noma_mbps=float(rate_noma.sum() / 1e6), sum_rate_oma_mbps=float(rate_oma.sum() / 1e6))
        coverage = float(served.mean())
        both.update(coverage_access=coverage, sum_rate_access_mbps=float(rate.sum() / 1e6),
                    fairness_served=md.jain(rate[served]) if served.any() else 0.0, **extra)
        self.prev = dict(
            coverage=coverage,
            throughput=float(min(1.0, rate.sum() / (2.0 * min_rate.sum()))),
            fairness=md.jain(rate))

        if e_quad is None:
            e_step = float(md.energy_step_j(np.hypot(self.vx, self.vy), self.vz, p_w,
                                            accel if use_accel_energy else None))
        else:
            e_step = e_quad
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
        info = self._info(served, rate=rate, energy_step_j=e_step, p_tx_w=p_w, rescue=rescue)
        mask = self.active_mask()
        if mask is not None:                       # report per user of the whole pool: inactive users are not served
            full = np.zeros(len(mask), bool)
            full[mask] = served
            info.update(served=full, active=mask.copy(), n_active=int(mask.sum()))
        # each reward part is reported separately, so reward hacking can be spotted
        info.update(reward_coverage=coverage, reward_energy=energy_term, reward_terminal=terminal_term,
                    accel_mps2=accel)
        if quad_info is not None:
            info["quad"] = quad_info
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
        xy, _, rescue = self.users_now()          # maps count only the users active now
        if g == "heat_all":
            return self._heatmap(xy)
        if g == "heat_rescue":
            return self._heatmap(xy[rescue])
        # uncapped: sqrt(share per cell). In [0, 1] (1 only if everyone stands in one cell) and invertible, so it
        # carries exactly the true share without the x10 cap; sqrt spreads small shares (1% -> 0.1, 25% -> 0.5).
        return np.sqrt(self._shares(xy if g == "heat_all_u" else xy[rescue], self.grid))

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
        if g == "event_countdown":
            return [self.event_countdown()]
        if g == "event_announce":
            return self.event_announce()
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
        p = self.priv_grid
        xy, min_rate, rescue = self.users_now()
        top = max(c["min_rate_bps"] for c in CFG["classes"].values())
        count = self._shares(xy, p) * len(xy)
        demand = np.divide(self._shares(xy, p, weights=min_rate / top) * len(xy), count,
                           out=np.zeros(p * p), where=count > 0)
        chans = {"density": np.sqrt(self._shares(xy, p)), "rescue": np.sqrt(self._shares(xy[rescue], p)),
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

    def _info(self, served, rate=None, energy_step_j=0.0, p_tx_w=0.0, rescue=None):
        rescue = self.rescue if rescue is None else rescue
        used_wh = self.energy_used_j / 3600.0
        info = dict(
            scenario_seed=self.scenario_seed, t=self.t, mobility=self.sc["mobility"], n_users=self.sc["n_users"],
            x=self.x, y=self.y, h=self.h, battery_wh=self.energy_left_j / 3600.0,
            coverage=self.prev["coverage"], fairness=self.prev["fairness"],
            sum_rate_mbps=float(rate.sum() / 1e6) if rate is not None else 0.0,
            outage_rescue=float(1 - served[rescue].mean()) if served is not None and rescue.any() else 0.0,
            energy_step_j=energy_step_j, p_tx_w=p_tx_w,
            served_user_s_per_wh=self.served_user_s / used_wh if used_wh > 0 else 0.0)
        if served is not None:
            info["served"] = served
        return info
