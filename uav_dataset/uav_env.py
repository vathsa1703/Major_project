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


class UAVEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, reward=None, fading=None, battery_wh=None):
        super().__init__()
        self.L = CFG["area_m"]
        self.T = CFG["mobility"]["episode_steps"]
        self.dt = CFG["energy"]["dt_s"]
        self.uav = CFG["uav"]
        self.grid = CFG["env"]["grid"]
        self.reward_version = reward or CFG["env"]["reward"]
        self.fading = CFG["fading"]["enabled"] if fading is None else fading
        self.battery_j = (battery_wh if battery_wh is not None else CFG["energy"]["battery_wh"]) * 3600.0
        self.p_max_w = 10 ** ((self.uav["p_max_dbm"] - 30) / 10)
        self.noise_psd = 10 ** ((CFG["noise_density_dbm_hz"] + CFG["noise_figure_db"] - 30) / 10)
        self.hover_step_j = md.energy_step_j(0.0, 0.0, 0.0)
        self.action_space = spaces.Box(-1.0, 1.0, shape=(4,), dtype=np.float32)
        self.observation_space = spaces.Box(-1.0, 1.0, shape=(11 + 2 * self.grid**2,), dtype=np.float32)

    # ------------------------------------------------------------------ episode
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        ss = (options or {}).get("scenario_seed")
        if ss is None:
            ss = seed if seed is not None else int(self.np_random.integers(0, 2**31 - 1))
        self.scenario_seed = int(ss)
        self.sc = md.make_scenario(self.scenario_seed)
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

    def user_xy(self, t=None):
        return self.P[self.t if t is None else t]

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
        rate, _ = md.noma_rates(g, p_w, self.noise_psd, self.sc["bandwidth_hz"], self.sc["pairing"], self.rng)
        served = rate >= self.min_rate
        coverage = float(served.mean())
        self.prev = dict(
            coverage=coverage,
            throughput=float(min(1.0, rate.sum() / (2.0 * self.min_rate.sum()))),
            fairness=md.jain(rate))

        e_step = float(md.energy_step_j(np.hypot(self.vx, self.vy), self.vz, p_w))
        self.energy_left_j = max(0.0, self.energy_left_j - e_step)
        self.energy_used_j += e_step
        self.served_user_s += float(served.sum()) * self.dt

        reward = coverage
        if self.reward_version == "v2":
            reward -= CFG["env"]["lambda_energy"] * e_step / self.hover_step_j
        terminated = self.energy_left_j <= 0.0
        if terminated:
            reward -= CFG["env"]["terminal_penalty"] * (1.0 - coverage)
        truncated = (not terminated) and self.t >= self.T
        info = self._info(served, rate=rate, energy_step_j=e_step, p_tx_w=p_w)
        return self._obs(), float(reward), bool(terminated), bool(truncated), info

    # ------------------------------------------------------------------ helpers
    def _heatmap(self, xy):
        if len(xy) == 0:
            return np.zeros(self.grid**2)
        h, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=self.grid, range=[[0, self.L], [0, self.L]])
        return np.minimum(1.0, h.ravel() / len(xy) * 10.0)      # share of users per cell x10, capped at 1

    def _obs(self):
        u = self.uav
        xy = self.user_xy()
        scalars = [
            self.x / self.L, self.y / self.L, (self.h - u["h_min_m"]) / (u["h_max_m"] - u["h_min_m"]),
            self.vx / u["v_max_mps"], self.vy / u["v_max_mps"], self.vz / u["vz_max_mps"],
            self.energy_left_j / self.battery_j, self.t / self.T,
            self.prev["coverage"], self.prev["throughput"], self.prev["fairness"]]
        o = np.concatenate([scalars, self._heatmap(xy), self._heatmap(xy[self.rescue])])
        return np.clip(o, -1.0, 1.0).astype(np.float32)

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
