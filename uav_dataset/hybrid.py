"""HYBRID TIMING AI (owner-approved, G5 follow-up; pre-registration docs/prereg/hybrid_timing.md).

THIS IS A HYBRID, NOT AN AI THAT FLIES ON ITS OWN. A strong search pilot decides WHERE (x, y, altitude); a small RL
policy decides only WHEN to leave for the announced destination site. In plain words: B6 is a good driver that always
drives to the best spot for the people it sees now, so it only leaves site A after the people have moved. The timing
policy is a passenger who has read the announcement ("from t0, a share of the people at A will be taken to B") and
says, every 10 s, either "keep following B6" or "go to B now".

Every decision (every baselines.replan_every_steps = 10 s) the agent picks one of two actions (Discrete(2)):
  FOLLOW (0): fly to B6's choice NOW (B6's exact rule: best of its grid x altitude candidates plus the 'stay' spot,
              ties to the one closest to the drone), with go_to at B6's power.
  LEAVE  (1): fly to the B-target (go_to, B6's power): the best lattice node for the ANNOUNCED post-event demand.
Both actions are allowed at every decision (it may also go back to following B6). An agent that always answers FOLLOW
flies exactly B6 (tested, bit for bit).

What each part may know (owner decisions D-24, D-54):
  - the agent (the neural network): only the raw observation groups of G5 (own state, history, uncapped maps, crowd
    size, event countdown, the announcement). It never sees B6's choice, the B-target, the table below or the future.
  - B6 (the WHERE pilot): what B6 always uses, the users as they are NOW (it is a baseline with privileged present
    information, like every other B-pilot).
  - the B-target: built ONCE at the start of the episode from the announcement and the users active at t = 0 only,
    with B6fc's own forecast (baselines.B6Forecast.forecast at the time t0 + tau, when every announced mover has
    switched): never from the true movers, their true arrival positions or any future position (tested by scrambling
    the future).

Speed: B6's search costs ~0.1-1.6 s per decision (980 candidates, adaptive NOMA, up to 1,000 users), far too slow
inside training. So for a FIXED pool of training scenarios the B6 coverage of every lattice node at every decision
time is precomputed once (decision_table: table[k, n] = env.evaluate at t = 10 k, the same numbers as rows 0, 2, 4, ...
of oracle.py's coverage tensor). At decision k the pilot reads ONLY row k (the present) plus a live evaluation of the
'stay' spot, so its choice is exactly live B6's (tested). The table holds future rows only because it is computed
ahead of time; nothing but row k = now is ever read.
"""
import hashlib
import json
from pathlib import Path

import gymnasium as gym
import numpy as np
from gymnasium import spaces

import make_dataset as md
from baselines import B6Forecast, B6GridAltitude, _grid, go_to
from uav_env import UAVEnv

CFG = md.CFG
BCFG = CFG["baselines"]
FOLLOW, LEAVE = 0, 1
CACHE = Path(__file__).parent / "results" / "hybrid_cache"


def hcfg():
    return CFG["hybrid"]


def obs_groups():
    return tuple(hcfg()["obs_groups"])


def every():
    """Steps between two decisions (B6's own rhythm, 10 s)."""
    return int(BCFG["replan_every_steps"])


# ---------------------------------------------------------------- the precomputed B6 table
def lattice(env):
    """B6's lattice candidates (x, y, h) in B6's order (grid x-major, every altitude level), WITHOUT the 'stay' spot."""
    X, Y = _grid(env)
    levels = np.array(BCFG["altitude_levels_m"], dtype=float)
    return np.repeat(X, len(levels)), np.repeat(Y, len(levels)), np.tile(levels, len(X))


def decision_times(env):
    return np.arange(0, env.T, every())


def _cache_key(env):
    cfg = {k: v for k, v in CFG.items() if k not in ("rl", "profiles", "active_profile", "oracle", "b6fc", "hybrid")}
    blob = json.dumps([cfg, env.access, env.sic_eps, env.rescue_first, env.scenario_overrides], sort_keys=True,
                      default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def cache_path(env, cache_dir=None):
    d = Path(cache_dir) if cache_dir else CACHE
    return d / f"{CFG.get('active_profile', 'default')}_{env.access}_s{env.scenario_seed}_{_cache_key(env)}.npz"


def scenario_data(env, cache=True, cache_dir=None):
    """(table, target) for the scenario env was just reset to (call right after env.reset()).
    table (n_decisions, n_lattice): coverage of every lattice node for the users at t = 10 k (env.evaluate, B6's power).
    target (3,): the B-target (b_target). Cached on disk (results/hybrid_cache/, not committed)."""
    assert env.t == 0, "call scenario_data right after env.reset()"
    path = cache_path(env, cache_dir)
    if cache and path.exists():
        z = np.load(path)
        return z["table"], z["target"]
    X, Y, H = lattice(env)
    p_w = env.p_max_w * BCFG["power_frac"]
    table = np.stack([env.evaluate(X, Y, H, p_w, t=int(t)) for t in decision_times(env)])
    target = b_target(env)
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, table=table, target=target)
    return table, target


def b_target(env):
    """The LEAVE target: the lattice node with the best coverage for B6fc's forecast of the ANNOUNCED post-event users
    (B6Forecast.snapshot at t = 0 + B6Forecast.forecast at t0 + tau, when every announced mover has switched).
    Ties: the node horizontally closest to site A's centre (the shortest flight from where the drone waits), then the
    first in B6's order. Uses only the users active at t = 0 and the announcement. Call right after env.reset()."""
    assert env.t == 0, "the B-target is built at the start of the episode"
    fc = B6Forecast()
    fc.reset(env)
    assert fc.announced(env), "the hybrid timing AI needs an announced event (profiles sites_*_ann)"
    s = fc.snapshot(env)
    t_post = int(np.ceil((s["t0"] + s["tau"]) / env.dt))
    t_post = min(t_post, env.T - 1)
    xy, mr, rs = fc.forecast(env, s, t_post)
    X, Y, H = lattice(env)
    cov = env.evaluate_users(xy, mr, rs, X, Y, H, env.p_max_w * BCFG["power_frac"], t_post)
    best = np.flatnonzero(cov >= cov.max() - 1e-12)
    ax, ay = env.sc["site_x"][0], env.sc["site_y"][0]
    j = best[np.argmin(np.hypot(X[best] - ax, Y[best] - ay))]
    return np.array([X[j], Y[j], H[j]])


class TableB6(B6GridAltitude):
    """B6 whose lattice scores at decision k come from row k of the precomputed table (the 'stay' spot is evaluated
    live, as B6 does). Without a table (or off the decision grid) it is live B6."""
    name = "B6tab"

    def __init__(self, table=None):
        self.table = table

    def plan(self, env):
        CX, CY, CH = self.candidates(env)
        p_w = env.p_max_w * self.power
        k = env.t // every()
        if self.table is not None and env.t % every() == 0 and k < len(self.table):
            stay = env.evaluate(CX[-1:], CY[-1:], CH[-1:], p_w)
            cov = np.append(self.table[k], stay)
        else:
            cov = env.evaluate(CX, CY, CH, p_w)
        j = self.pick(env, cov, CX, CY, CH)
        self.target = (CX[j], CY[j], CH[j])


class HybridPilot:
    """The WHERE part: turns a timing action into a target and flies it (go_to at B6's power)."""

    def __init__(self, data=None, cache=True, cache_dir=None):
        """data: optional {scenario_seed: (table, target)} (training: preloaded bundle); otherwise scenario_data()."""
        self.data, self.cache, self.cache_dir = data, cache, cache_dir

    def reset(self, env):
        seed = env.scenario_seed
        if self.data is not None and seed in self.data:
            table, target = self.data[seed]
        else:
            table, target = scenario_data(env, self.cache, self.cache_dir)
        self.b6 = TableB6(table)
        self.b6.reset(env)
        self.power = BCFG["power_frac"]
        self.btarget = tuple(float(v) for v in target)
        self.target = self.b6.target
        self.actions = []

    def decide(self, env, action):
        a = int(action)
        assert a in (FOLLOW, LEAVE), f"action must be 0 (follow B6) or 1 (leave for B), not {action!r}"
        if a == FOLLOW:
            self.b6.plan(env)
            self.target = self.b6.target
        else:
            self.target = self.btarget
        self.actions.append(a)

    def act(self, env):
        return go_to(env, *self.target, self.power)


# ---------------------------------------------------------------- the training env
class HybridTimingEnv(gym.Env):
    """Gymnasium env for the timing policy: Discrete(2) action every `hold` steps, reward = sum of the env's v1
    coverage rewards over the held steps, observation = the G5 Dict observation (raw groups only)."""
    metadata = {"render_modes": []}

    def __init__(self, scenario_seeds=None, data=None, groups=None, hold=None, reward="v1", access=None,
                 cache=True, cache_dir=None, **env_kwargs):
        super().__init__()
        self.hold = int(hold or every())
        assert self.hold == every(), "the timing policy decides on B6's rhythm (B6's table is per decision)"
        self.env = UAVEnv(reward=reward, scenario_seeds=scenario_seeds, obs_groups=groups or obs_groups(),
                          obs_mode="dict", history_every=self.hold, access=access, **env_kwargs)
        self.pilot = HybridPilot(data, cache, cache_dir)
        self.observation_space = self.env.observation_space
        self.action_space = spaces.Discrete(2)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        obs, info = self.env.reset(seed=seed, options=options)
        self.pilot.reset(self.env)
        return obs, info

    def step(self, action):
        self.pilot.decide(self.env, action)
        total, obs, term, trunc, info = 0.0, None, False, False, {}
        for _ in range(self.hold):
            obs, r, term, trunc, info = self.env.step(self.pilot.act(self.env))
            total += r
            if term or trunc:
                break
        info = dict(info, hybrid_action=int(action), target=self.pilot.target)
        return obs, total, term, trunc, info


# ---------------------------------------------------------------- policies for run_baselines.run_episode
class HybridPolicy:
    """A trained timing model as a pilot (act(env) -> 4-number action), for run_baselines.run_episode."""
    name = "hybrid"

    def __init__(self, model, data=None, cache=True, cache_dir=None, groups=None):
        self.model, self.groups = model, tuple(groups or obs_groups())
        self.pilot = HybridPilot(data, cache, cache_dir)

    def observation(self, env):
        """Exactly the training observation; the env is never asked for the privileged state."""
        return env.observation(self.groups, dict_obs=True, history_every=every(), privileged=False)

    def choose(self, env):
        a, _ = self.model.predict(self.observation(env), deterministic=True)
        return int(np.asarray(a).ravel()[0])

    def reset(self, env):
        self.pilot.reset(env)

    def act(self, env):
        if env.t % every() == 0:
            self.pilot.decide(env, self.choose(env))
        return self.pilot.act(env)


class ScheduleHybrid(HybridPolicy):
    """Rule version for tests and diagnostics: FOLLOW until decision `leave_at` (None = never), then LEAVE."""
    name = "schedule"

    def __init__(self, leave_at=None, data=None, cache=True, cache_dir=None):
        super().__init__(None, data, cache, cache_dir)
        self.leave_at = leave_at

    def choose(self, env):
        k = env.t // every()
        return LEAVE if (self.leave_at is not None and k >= self.leave_at) else FOLLOW


def load_bundle(path):
    """{seed: (table, target)} from a bundle written by hybrid_tables.py bundle."""
    z = np.load(path)
    return {int(s): (z["tables"][i], z["targets"][i]) for i, s in enumerate(z["seeds"])}
