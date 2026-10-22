"""All the logic behind the dashboard (dashboard.py). NO streamlit here, so everything is testable without it.

    import dashboard_core as dc
    s = dc.Settings(profile="hard", seed=5, access="noma_opt")
    ep = dc.run_pilot(s, "B3")                 # one episode: ep.trace (per second), ep.summary, ep.env, ep.frames
    fig = dc.render_frame(ep, 120)             # matplotlib Figure of the map at t = 120 s
    res = dc.compare_pilots(s, ["B0", "B3"])   # {label: Episode} on the SAME scenario
    plan = dc.recommend(s)                     # where to put the drone, NOMA vs OMA, battery advice

It is a simulation-based planning tool: it re-uses the simulator (uav_env.py), the pilots (baselines.py, view_run.py)
and the statistics (evalstats.py) unchanged. It never changes physics. The config is switched by profile inside a lock
(`configured`), because make_dataset.CFG is one shared dictionary and the web app serves several users from threads.
Expensive results are kept in small in-memory caches keyed by the settings.
"""
from __future__ import annotations

import contextlib
import importlib.util
import os
import tempfile
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import make_dataset as md
from baselines import POLICIES, B6GridAltitude
from compare_run import summarize_run
from evalstats import mean_ci, paired_diff
from rl_utils import model_settings
from run_baselines import run_episode
from uav_env import UAVEnv
from view_run import animate, build_policy, run

HERE = Path(__file__).parent
REPO = HERE.parent
BOOK = REPO / "docs" / "book"
AI_PREFIX = "AI: "
MAX_BATCH = 20

# ---------------------------------------------------------------- plain-language labels (one place for the whole app)
PROFILE_INFO = {
    "default": "Town: 1 x 1 km, strong radio (30 dBm), 0-5 collapsed buildings, 10 Wh battery",
    "lowpower": "Weak radio: 1 x 1 km, 20 dBm transmitter",
    "bigarea": "Big area: 2 x 2 km, 30 dBm",
    "hard": "Hard: 2 x 2 km, weak radio (20 dBm), 3-8 collapsed buildings, crowds that move suddenly, 16 Wh",
    "rl_static": "Still crowd (where the AI was trained): like hard, but people stand still",
    "rl_static_g20": "Still crowd, AI map 20 x 20 (same scenarios as rl_static)",
}
MOBILITY_INFO = {
    "static": "Standing still",
    "random_waypoint": "Everyone wanders to random spots",
    "group_drift": "Groups drift together",
    "attraction": "People walk to a shelter",
    "hotspot_jump": "Groups suddenly jump to a new spot",
    "surge": "Panic: everyone runs to one new point",
}
ACCESS_INFO = {
    "noma_opt": "NOMA, adaptive: pairs share a channel, power tuned per pair",
    "noma": "NOMA, fixed: pairs share a channel, fixed 80/20 power split",
    "oma_opt": "OMA, optimised: everyone gets their own channel, power tuned",
    "oma": "OMA, equal: everyone gets their own channel, equal power",
}
PILOT_INFO = {
    "B0": "Parked: stays over the map centre at 150 m",
    "B1": "Follows the biggest crowd",
    "B2": "Crowd centres (k-means): goes to the heaviest group",
    "B3": "Grid search: tries every spot of a grid every 10 s",
    "B4": "Swarm search (PSO): also picks altitude and power (slow)",
    "B5": "Energy-aware grid search: moves only if it is worth the energy",
    "B6": "Grid search + 5 altitudes (slow)",
    "B7": "Circling pilot: loiters around the best spot to save energy",
    "B3obs": "Grid search seeing only the AI's crowd maps",
    "B3obsN": "Grid search, AI's maps + true crowd size",
    "B3obsU": "Grid search, uncapped crowd maps",
    "B3obsUO": "Grid search, uncapped maps + buildings",
    "B3obsUN": "Grid search, exactly the AI's information",
    "random": "Random waypoints (the floor every pilot must beat)",
}
SLOW_PILOTS = ("B4", "B6")
# Consistent colours (dataviz reference palette, categorical slots in fixed order; served/not served = status colours)
COLORS = {"served": "#008300", "unserved": "#e34948", "drone": "#2a78d6", "building": "#9e9e9e", "pair": "#8a8a8a"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
METRICS = {   # name -> (plain label, higher is better)
    "coverage_full": ("share of people served over the whole episode (dead drone = 0)", True),
    "outage_rescue": ("share of rescue users NOT served", False),
    "sum_rate_mbps": ("total data speed (Mbps)", True),
    "served_user_s_per_wh": ("people-seconds served per Wh of battery", True),
}

# ---------------------------------------------------------------- headline results (hard-coded from the project book)
HEADLINES = [
    dict(title="Moving the drone pays off (H1)", value="0.741 vs 0.428",
         detail="Share of people served on the hard scenarios: grid search + altitude (B6) vs a drone parked in the "
                "middle (B0). 100 scenarios, 16 Wh.",
         source="Book ch. 7.8 (profile hard, all 7 pilots); journal 02, B6 entry"),
    dict(title="Adaptive NOMA beats optimised OMA (H3)", value="+0.03 to +0.05",
         detail="More people served than equally optimised OMA in every case; e.g. weak radio, grid search: "
                "0.983 vs 0.945. Rescue users not served: 0.004.",
         source="Book ch. 13.9 (Track 1 tables)"),
    dict(title="Circling saves battery (B7)", value="+25.6%",
         detail="More people-seconds served per battery when the drone circles the best spot at its cheapest speed "
                "instead of hovering (forward flight costs less than hovering in the energy model).",
         source="B7 loiter-pilot branch (circling experiment, decision D-45); book entry pending"),
    dict(title="The AI learns by itself (H2, Gate G4)", value="0.576",
         detail="Best AI (E0) on still crowds vs k-means B2 0.610 and random 0.430. It learns from raw measurements "
                "only, no hints. Gate G4 not met (pass mark 0.580).",
         source="Book ch. 8.8 (Track 2 results, G4 verdict D-47)"),
]
FIGURE_CAPTIONS = {
    "1_hard_moving_crowds.png": "Hard scenarios with moving crowds: pilots compared",
    "2_still_crowd_AI_vs_pilots.png": "Still crowd: the AI against the pilots",
    "3_surge_custom.png": "A panic surge: the crowd runs to a new point",
    "4_goto_checkpoint.png": "AI choosing waypoints (a training checkpoint)",
    "5_goto_hold10.png": "AI deciding every 10 s: no more circling",
    "6_noma_pairs_default.png": "NOMA pairs at 30 dBm (who shares a channel with whom)",
    "7_noma_pairs_lowpower.png": "NOMA pairs with a weak radio (20 dBm)",
    "8_access_schemes_hard.png": "Four ways to share the radio, hard scenarios",
    "9_access_schemes_lowpower.png": "Four ways to share the radio, weak radio",
    "10_e0_vs_b3_seed105.png": "Best AI (E0) vs grid search (B3) on scenario 105",
}


# ---------------------------------------------------------------- settings and config
@dataclass(frozen=True)
class Settings:
    """Everything that defines one disaster scenario. None = let the profile / the scenario seed decide."""
    profile: str = "default"
    seed: int = 5
    n_users: int | None = None
    n_clusters: int | None = None
    mobility: str | None = None
    n_obstacles: int | None = None
    cluster_radius_m: float | None = None
    scatter_fraction: float | None = None
    battery_wh: float | None = None
    access: str | None = None
    p_max_dbm: float | None = None

    def __post_init__(self):
        assert self.profile == "default" or self.profile in md.BASE_CFG["profiles"], f"unknown profile {self.profile}"
        assert self.access is None or self.access in md.ACCESS_SCHEMES, f"unknown access scheme {self.access!r}"
        assert self.mobility is None or self.mobility in MOBILITY_INFO, f"unknown movement model {self.mobility!r}"
        assert self.n_users is None or (self.n_users >= 2 and self.n_users % 2 == 0), "n_users must be even (pairs)"
        assert self.battery_wh is None or self.battery_wh > 0, "battery must be positive"

    def overrides(self):
        keys = ("n_users", "n_clusters", "mobility", "n_obstacles", "cluster_radius_m", "scatter_fraction")
        return {k: getattr(self, k) for k in keys if getattr(self, k) is not None}


_LOCK = threading.RLock()


@contextlib.contextmanager
def configured(settings):
    """Apply the settings' profile (and transmit-power override) to the shared config for the duration of the block,
    then restore the profile that was active before. Holds a lock so two app users cannot mix configs."""
    with _LOCK:
        before = md.CFG.get("active_profile", "default")
        md.apply_profile(settings.profile)
        if settings.p_max_dbm is not None:
            md.CFG["uav"]["p_max_dbm"] = float(settings.p_max_dbm)
        try:
            yield md.CFG
        finally:
            md.apply_profile(before)


def profiles():
    return ["default", *md.BASE_CFG["profiles"]]


def profile_defaults(profile):
    """The values a profile uses when nothing is overridden (shown next to the controls)."""
    with configured(Settings(profile=profile)):
        c = md.CFG
        return dict(area_m=c["area_m"], p_max_dbm=c["uav"]["p_max_dbm"], battery_wh=c["energy"]["battery_wh"],
                    obstacles=tuple(c["obstacles"]["n_range"]), mobility=tuple(c["mobility"]["choices"]),
                    access=c["env"]["access"], episode_s=c["mobility"]["episode_steps"],
                    tx_levels=tuple(c["tx_power_dbm_levels"]))


def _env(settings):
    """A UAVEnv for the settings. Call inside `configured(settings)`."""
    return UAVEnv(battery_wh=settings.battery_wh, scenario_overrides=settings.overrides(), access=settings.access)


def build_scenario(settings):
    """The scenario the settings produce (deterministic: same settings -> same crowd, buildings, movement)."""
    with configured(settings):
        env = _env(settings)
        env.reset(seed=settings.seed)
        return dict(sc=dict(env.sc), users_xy=env.user_xy(0).copy(), positions=env.P.copy(), boxes=env.boxes.copy(),
                    rescue=env.rescue.copy(), classes=env.users["class"].to_numpy(), area_m=env.L, steps=env.T,
                    p_max_dbm=md.CFG["uav"]["p_max_dbm"], battery_wh=env.battery_j / 3600.0, access=env.access,
                    hover_w=float(env.hover_step_j / env.dt))


def describe(scn):
    """One plain sentence about a scenario from build_scenario / Episode.scenario."""
    sc = scn["sc"]
    return (f"{sc['n_users']} people in {sc['n_clusters']} crowds, movement: "
            f"{MOBILITY_INFO.get(sc['mobility'], sc['mobility']).lower()}, {len(scn['boxes'])} collapsed buildings, "
            f"{scn['area_m'] / 1000:g} x {scn['area_m'] / 1000:g} km, radio {scn['p_max_dbm']:g} dBm, "
            f"battery {scn['battery_wh']:g} Wh, {ACCESS_INFO[scn['access']].split(':')[0]}")


# ---------------------------------------------------------------- pilots (baselines, random, any trained AI)
def default_models_dir():
    """UAV_MODELS_DIR if set; else the local training output (results/rl, not in git) if it holds any model; else the
    small set of showcase models committed in uav_dataset/models (used by the online deployment)."""
    if os.environ.get("UAV_MODELS_DIR"):
        return Path(os.environ["UAV_MODELS_DIR"])
    local = HERE / "results" / "rl"
    if local.is_dir() and any(p.joinpath("model.zip").is_file() for p in local.iterdir()):
        return local
    return HERE / "models"


def ai_available():
    """True if the RL libraries are installed (needed only to FLY a trained model, not to list it)."""
    return importlib.util.find_spec("stable_baselines3") is not None


def list_models(models_dir=None):
    """{name: path to model.zip} for every <models_dir>/<name>/model.zip. Empty if the folder does not exist."""
    d = Path(models_dir) if models_dir else default_models_dir()
    if not d.is_dir():
        return {}
    return {p.name: p / "model.zip" for p in sorted(d.iterdir()) if (p / "model.zip").is_file()}


def model_info(path):
    """A short description of a trained model from its saved config.json."""
    s = model_settings(path)
    if not s:
        return "trained AI (no saved settings)"
    return (f"trained AI ({s.get('algo', 'PPO')}, trained on profile {s.get('profile', '?')}, "
            f"controls {s.get('controls', '?')}, decides every {s.get('hold_steps', 1)} s)")


def pilot_options(models_dir=None):
    """{pilot id: plain description}: the baselines (B7 too if that branch is merged), random, and every AI found."""
    out = {name: PILOT_INFO.get(name, f"pilot {name}") for name in POLICIES}
    out["random"] = PILOT_INFO["random"]
    for name, path in list_models(models_dir).items():
        out[AI_PREFIX + name] = model_info(path)
    return out


def make_pilot(pilot, models_dir=None):
    """A pilot object by id. Call inside `configured(...)` (random/AI read the config)."""
    if pilot.startswith(AI_PREFIX):
        models = list_models(models_dir)
        name = pilot[len(AI_PREFIX):]
        if name not in models:
            raise ValueError(f"no trained model {name!r} in {models_dir or default_models_dir()}")
        if not ai_available():
            raise RuntimeError("flying a trained AI needs the RL libraries: pip install -r requirements-rl.txt")
        return build_policy("ppo", str(models[name]))
    return build_policy(pilot)


# ---------------------------------------------------------------- small caches
class _Cache:
    def __init__(self, size):
        self.size, self.d = size, OrderedDict()

    def get(self, key):
        if key in self.d:
            self.d.move_to_end(key)
            return self.d[key]
        return None

    def put(self, key, value):
        self.d[key] = value
        self.d.move_to_end(key)
        while len(self.d) > self.size:
            self.d.popitem(last=False)
        return value

    def clear(self):
        self.d.clear()


_EPISODES, _BATCHES, _PLANS = _Cache(12), _Cache(16), _Cache(16)


def clear_caches():
    for c in (_EPISODES, _BATCHES, _PLANS):
        c.clear()


def _model_key(pilot, models_dir):
    if not pilot.startswith(AI_PREFIX):
        return None
    p = list_models(models_dir).get(pilot[len(AI_PREFIX):])
    return (str(p), p.stat().st_mtime) if p else None


# ---------------------------------------------------------------- one episode
TRACE_COLUMNS = ["t", "x", "y", "h", "coverage", "served_users", "rescue_served", "rescue_outage", "sum_rate_mbps",
                 "battery_wh", "fairness", "coverage_noma", "coverage_oma", "energy_step_j", "p_tx_w"]


@dataclass
class Episode:
    settings: Settings
    pilot: str
    env: UAVEnv = field(repr=False)
    frames: list = field(repr=False)        # view_run.run frames: (user xy, served, (x, y, h), info, reward)
    trace: pd.DataFrame = field(repr=False)
    summary: dict
    scenario: dict = field(repr=False)

    @property
    def steps(self):
        return len(self.frames)


def _trace(frames):
    rows = []
    for _, served, (x, y, h), info, _ in frames:
        rows.append(dict(t=info["t"], x=x, y=y, h=h, coverage=info["coverage"], served_users=int(served.sum()),
                         rescue_served=1.0 - info["outage_rescue"], rescue_outage=info["outage_rescue"],
                         sum_rate_mbps=info["sum_rate_mbps"], battery_wh=info["battery_wh"],
                         fairness=info["fairness"], coverage_noma=info["coverage_noma"],
                         coverage_oma=info["coverage_oma"], energy_step_j=info["energy_step_j"],
                         p_tx_w=info["p_tx_w"]))
    return pd.DataFrame(rows, columns=TRACE_COLUMNS)


def run_pilot(settings, pilot, models_dir=None):
    """Fly one pilot on the settings' scenario for one episode (cached). Returns an Episode."""
    key = (settings, pilot, _model_key(pilot, models_dir))
    hit = _EPISODES.get(key)
    if hit is not None:
        return hit
    with configured(settings):
        env, frames = run(settings.seed, make_pilot(pilot, models_dir), settings.battery_wh, settings.overrides(),
                          settings.access)
        s = summarize_run(env, frames)
        trace = _trace(frames)
        s.update(sum_rate_mbps=float(trace.sum_rate_mbps.mean()), fairness=float(trace.fairness.mean()),
                 served_user_s_per_wh=frames[-1][3]["served_user_s_per_wh"], access=env.access)
        scenario = dict(sc=dict(env.sc), boxes=env.boxes, area_m=env.L, steps=env.T, rescue=env.rescue,
                        p_max_dbm=md.CFG["uav"]["p_max_dbm"], battery_wh=env.battery_j / 3600.0, access=env.access)
    return _EPISODES.put(key, Episode(settings, pilot, env, frames, trace, s, scenario))


def metrics_at(ep, t):
    """The live numbers at second t (1..steps) of an episode."""
    i = int(np.clip(t, 1, ep.steps)) - 1
    r = ep.trace.iloc[i]
    return dict(t=int(r.t), coverage=float(r.coverage), served_users=int(r.served_users),
                n_users=int(ep.scenario["sc"]["n_users"]), rescue_served=float(r.rescue_served),
                sum_rate_mbps=float(r.sum_rate_mbps), battery_wh=float(r.battery_wh), h=float(r.h),
                power_w=float(r.p_tx_w), alive=bool(r.battery_wh > 0))


# ---------------------------------------------------------------- drawing
def _pairs(ep, i, max_pairs):
    """NOMA pairs at frame i (average channel): (weak, strong) index arrays of the pairs nearest the drone.
    noma: the fixed scheme's pairing (md.pair_users); noma_opt: the partners the adaptive scheme actually forms;
    OMA schemes: no pairs."""
    env = ep.env
    if env.access not in ("noma", "noma_opt"):
        return np.array([], int), np.array([], int)
    xy, _, (x, y, h), info, _ = ep.frames[i]
    with configured(ep.settings):
        g = md.channel_gain(xy[:, 0], xy[:, 1], np.array([x]), np.array([y]), np.array([h]), env.boxes)[0]
        if env.access == "noma":
            weak, strong = md.pair_users(g, env.sc["pairing"], np.random.default_rng(0))
        else:
            partner = env.access_rates(g, max(info["p_tx_w"], 1e-3), return_info=True)[1]["partner"]
            a = np.flatnonzero(partner >= 0)
            a = a[a < partner[a]]
            weak, strong = a, partner[a]
    near = np.argsort(np.hypot(xy[weak, 0] - x, xy[weak, 1] - y))[:max_pairs]
    return weak[near], strong[near]


def _draw_map(ax, env, xy, served, drone=None, trail=None, start=None, pairs=None, compact=False):
    L = env.L
    for x0, y0, x1, y1 in env.boxes:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color=COLORS["building"], alpha=0.75, lw=0))
    if pairs is not None:
        for w, s in zip(*pairs, strict=True):
            ax.plot([xy[w, 0], xy[s, 0]], [xy[w, 1], xy[s, 1]], color=COLORS["pair"], lw=0.6, alpha=0.7, zorder=1)
    size = 5 if compact else 9
    ax.scatter(xy[:, 0], xy[:, 1], s=size, c=np.where(served, COLORS["served"], COLORS["unserved"]), zorder=2,
               linewidths=0)
    r = env.rescue
    ax.scatter(xy[r, 0], xy[r, 1], s=size * 4, facecolors="none", edgecolors="black", linewidths=0.6, zorder=3)
    if trail is not None and len(trail):
        ax.plot(trail[:, 0], trail[:, 1], "-", color=COLORS["drone"], lw=1.4, alpha=0.8, zorder=4)
    if start is not None:
        ax.plot(*start, "o", color=COLORS["drone"], ms=5, zorder=5)
    if drone is not None:
        ax.plot(drone[0], drone[1], marker="^", color=COLORS["drone"], ms=11 if compact else 15,
                markeredgecolor="white", markeredgewidth=1.2, zorder=6)
    ax.set_xlim(0, L)
    ax.set_ylim(0, L)
    ax.set_aspect("equal")
    if compact:
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        ax.set_xlabel("east (m)")
        ax.set_ylabel("north (m)")
    for sp in ax.spines.values():
        sp.set_color("0.8")


def _legend(ax, pairs=False):
    items = [Line2D([], [], ls="", marker="o", color=COLORS["served"], label="served (good signal)"),
             Line2D([], [], ls="", marker="o", color=COLORS["unserved"], label="not served"),
             Line2D([], [], ls="", marker="o", mfc="none", mec="black", label="rescue user"),
             Rectangle((0, 0), 1, 1, color=COLORS["building"], label="collapsed building"),
             Line2D([], [], color=COLORS["drone"], marker="^", label="drone + flight path")]
    if pairs:
        items.append(Line2D([], [], color=COLORS["pair"], label="NOMA pair (shares a channel)"))
    ax.legend(handles=items, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, frameon=False)


def render_frame(ep, t, show_pairs=False, max_pairs=60):
    """The map at second t (1..steps): users served/not served, rescue rings, buildings, drone and its trail."""
    i = int(np.clip(t, 1, ep.steps)) - 1
    xy, served, (x, y, h), info, _ = ep.frames[i]
    trail = np.array([f[2][:2] for f in ep.frames[: i + 1]])
    pairs = _pairs(ep, i, max_pairs) if show_pairs else None
    fig = Figure(figsize=(7.6, 5.6), layout="constrained")
    ax = fig.add_subplot()
    _draw_map(ax, ep.env, xy, served, drone=(x, y), trail=trail, start=(ep.env.L / 2, ep.env.L / 2), pairs=pairs)
    ax.set_title(f"t = {info['t']} s   |   {info['coverage']:.0%} served   |   altitude {h:.0f} m   |   "
                 f"battery {info['battery_wh']:.1f} Wh", fontsize=10)
    _legend(ax, pairs is not None and len(pairs[0]) > 0)
    return fig


def render_maps(episodes, t=None):
    """Small multiples: one map per episode at second t (default: each one's last second)."""
    names = list(episodes)
    fig = Figure(figsize=(3.3 * len(names), 3.9), layout="constrained")
    for k, n in enumerate(names):
        ep = episodes[n]
        i = (ep.steps if t is None else int(np.clip(t, 1, ep.steps))) - 1
        xy, served, (x, y, _), info, _ = ep.frames[i]
        ax = fig.add_subplot(1, len(names), k + 1)
        trail = np.array([f[2][:2] for f in ep.frames[: i + 1]])
        _draw_map(ax, ep.env, xy, served, drone=(x, y), trail=trail, start=(ep.env.L / 2, ep.env.L / 2),
                  compact=True)
        life = "alive at the end" if ep.summary["survived"] else f"battery died at {ep.steps} s"
        ax.set_title(f"{n}\n{ep.summary['coverage_full']:.0%} served on average, {life}", fontsize=9)
    return fig


def make_gif(ep, every=5, fps=6):
    """The episode as an animated GIF (view_run.animate). Returns the bytes."""
    with configured(ep.settings), tempfile.TemporaryDirectory() as d:
        out = Path(d) / "run.gif"
        animate(ep.env, ep.frames, str(out), f"seed {ep.settings.seed}", ep.pilot, every=every, fps=fps)
        return out.read_bytes()


# ---------------------------------------------------------------- comparisons on one scenario
def _unique(labels):
    seen, out = {}, []
    for lab in labels:
        seen[lab] = seen.get(lab, 0) + 1
        out.append(lab if seen[lab] == 1 else f"{lab} ({seen[lab]})")
    return out


def compare_pilots(settings, pilots, models_dir=None, progress=None):
    """Several pilots on the SAME scenario. Returns {pilot: Episode}."""
    out = {}
    for k, (lab, p) in enumerate(zip(_unique(pilots), pilots, strict=True)):
        out[lab] = run_pilot(settings, p, models_dir)
        if progress:
            progress((k + 1) / len(pilots), lab)
    return out


def compare_access(settings, pilot, schemes=("noma_opt", "oma_opt"), models_dir=None, progress=None):
    """One pilot on the SAME scenario with different radio-sharing schemes. Returns {scheme: Episode}."""
    out = {}
    for k, s in enumerate(schemes):
        out[s] = run_pilot(replace(settings, access=s), pilot, models_dir)
        if progress:
            progress((k + 1) / len(schemes), s)
    return out


def summary_table(episodes):
    """One row per episode with plain-language column names."""
    rows = []
    for name, ep in episodes.items():
        s = ep.summary
        rows.append({"pilot / scheme": name,
                     "people served, average over the episode": round(s["coverage_full"], 3),
                     "people served while flying": round(s["coverage_alive"], 3),
                     "rescue users not served": round(s["rescue_outage"], 3),
                     "total data speed (Mbps)": round(s["sum_rate_mbps"], 1),
                     "fairness (Jain, 0-1)": round(s["fairness"], 3),
                     "flight time (s)": s["steps"],
                     "battery left (Wh)": round(s["battery_left_wh"], 2),
                     "people-seconds per Wh": round(s["served_user_s_per_wh"], 0)})
    return pd.DataFrame(rows)


def long_trace(episodes, column):
    """Tidy (t, value, name) table of one trace column for overlaid charts."""
    return pd.concat([pd.DataFrame({"t": ep.trace.t, "value": ep.trace[column], "name": name})
                      for name, ep in episodes.items()], ignore_index=True)


# ---------------------------------------------------------------- comparison over several scenarios
@dataclass
class Batch:
    per_seed: pd.DataFrame
    a: str
    b: str
    metric: str
    mean_a: tuple
    mean_b: tuple
    diff: tuple
    significant: bool
    verdict: str


def batch_compare(settings, a, b, n, kind="pilots", pilot="B3", metric="coverage_full", models_dir=None,
                  progress=None):
    """Run a vs b on n scenarios (seeds settings.seed .. settings.seed + n - 1, same overrides), in ONE process.
    kind="pilots": a and b are pilots; kind="access": a and b are schemes flown by `pilot`.
    Returns a Batch with per-scenario values and the paired difference a - b with its 95% CI (evalstats)."""
    assert 2 <= n <= MAX_BATCH, f"choose between 2 and {MAX_BATCH} scenarios"
    assert kind in ("pilots", "access") and metric in METRICS
    key = (settings, a, b, n, kind, pilot, metric, _model_key(a, models_dir), _model_key(b, models_dir),
           _model_key(pilot, models_dir))
    hit = _BATCHES.get(key)
    if hit is not None:
        return hit
    rows = []
    for k, seed in enumerate(range(settings.seed, settings.seed + n)):
        row = {"scenario seed": seed}
        for side in (a, b):
            s = replace(settings, seed=seed, access=side) if kind == "access" else replace(settings, seed=seed)
            who = pilot if kind == "access" else side
            with configured(s):
                r = run_episode(_env(s), make_pilot(who, models_dir), seed)
            row[side] = r[metric]
            row.setdefault("people", r["n_users"])
            row.setdefault("movement", r["mobility"])
        rows.append(row)
        if progress:
            progress((k + 1) / n, f"scenario {k + 1}/{n}")
    df = pd.DataFrame(rows)
    df["difference (A - B)"] = df[a] - df[b]
    ma, mb, d = mean_ci(df[a]), mean_ci(df[b]), paired_diff(df[a], df[b])
    sig = abs(d[0]) > d[1]
    return _BATCHES.put(key, Batch(df, a, b, metric, ma, mb, d, sig, verdict(a, b, metric, d, sig, n)))


def verdict(a, b, metric, d, significant, n):
    """A plain-words sentence for a paired difference (mean, half-width)."""
    label, higher = METRICS[metric]
    m, h = d
    better = a if (m > 0) == higher else b
    worse = b if better == a else a
    txt = f"{a} minus {b}, {label}: {m:+.3f} +/- {h:.3f} (95% CI, paired over {n} scenarios). "
    if m == 0 and h == 0:
        txt += "They give exactly the same result on every scenario."
    elif significant:
        txt += f"{better} is better than {worse}, and the interval excludes 0, so this is unlikely to be luck."
    else:
        txt += (f"{better} is ahead on average, but the interval includes 0: on these scenarios the difference "
                "could be luck. Try more scenarios.")
    if n < 10:
        txt += f" With only {n} scenarios the interval is rough; the book uses 100."
    return txt


# ---------------------------------------------------------------- plan: where to put the drone
def _served_at(env, x, y, h, p_w):
    """Who would be served with the drone at (x, y, h) and power p_w, right now (average channel). Same physics and
    rng recipe as UAVEnv.evaluate, but returns the per-user flags (to count rescue users too)."""
    ux, uy = env.user_xy().T
    g = md.channel_gain(ux, uy, np.array([x]), np.array([y]), np.array([h]), env.boxes)[0]
    if env.access in md.QOS_SCHEMES:
        return env.access_rates(g, p_w, return_info=True)[1]["served"]
    rng = np.random.default_rng([env.scenario_seed, env.t])
    rates = md.noma_rates(g, p_w, env.noise_psd, env.sc["bandwidth_hz"], env.sc["pairing"], rng)
    return rates[0 if env.access == "noma" else 1] >= env.min_rate


def battery_advice(battery_wh, hover_w, steps, cheapest=None):
    """(ok, text): can the battery hover for the whole episode? cheapest = (speed m/s, power W) of the cheapest
    forward flight, if it costs less than hovering."""
    need_wh = hover_w * steps / 3600.0
    endurance = battery_wh * 3600.0 / hover_w
    if battery_wh >= need_wh:
        return True, (f"{battery_wh:.1f} Wh >= {need_wh:.1f} Wh needed to hover {steps} s: the battery lasts the whole "
                      f"mission (about {endurance:.0f} s of hovering in total).")
    text = (f"{battery_wh:.1f} Wh < {need_wh:.1f} Wh needed to hover {steps} s: expect the drone to die at "
            f"~{endurance:.0f} s. Consider a bigger battery or circling")
    if cheapest is not None:
        v, p = cheapest
        text += (f" (flying slow circles at about {v:.0f} m/s draws {p:.0f} W instead of {hover_w:.0f} W for "
                 f"hovering, which would last ~{battery_wh * 3600.0 / p:.0f} s)")
    text += ". Try pilot B7, which circles the spot." if "B7" in POLICIES else "."
    return False, text


@dataclass
class Plan:
    settings: Settings
    scenario: str
    x_m: float
    y_m: float
    altitude_m: float
    power_dbm: float
    power_w: float
    coverage: dict              # scheme -> share of people served at the spot (t = 0)
    rescue_served: dict         # scheme -> share of rescue users served at the spot
    centre_coverage: float      # parked at the map centre (B0's spot), with the chosen scheme
    battery_wh: float
    hover_w: float
    hover_wh_needed: float
    hover_endurance_s: float
    cheapest_speed_mps: float
    cheapest_power_w: float
    battery_ok: bool
    battery_advice: str
    flown: dict | None = None   # optional: B6 flown for the whole episode (summary)
    env: UAVEnv = field(default=None, repr=False)
    served: np.ndarray = field(default=None, repr=False)

    def table(self):
        rows = [("Recommended spot, east", f"{self.x_m:.0f}", "m"), ("Recommended spot, north", f"{self.y_m:.0f}", "m"),
                ("Altitude", f"{self.altitude_m:.0f}", "m"),
                ("Transmit power", f"{self.power_dbm:.0f} ({self.power_w:g} W)", "dBm"),
                ("Parked at the centre instead (same scheme)", f"{self.centre_coverage:.3f}", "share served")]
        for s in md.ACCESS_SCHEMES:
            rows.append((f"People served at the spot: {ACCESS_INFO[s]}", f"{self.coverage[s]:.3f}", "share"))
            rows.append((f"Rescue users served: {ACCESS_INFO[s]}", f"{self.rescue_served[s]:.3f}", "share"))
        rows += [("Battery", f"{self.battery_wh:.1f}", "Wh"), ("Hover power", f"{self.hover_w:.0f}", "W"),
                 ("Energy to hover the whole mission", f"{self.hover_wh_needed:.1f}", "Wh"),
                 ("Hover endurance", f"{self.hover_endurance_s:.0f}", "s"),
                 ("Cheapest flight speed", f"{self.cheapest_speed_mps:.1f}", "m/s"),
                 ("Power at the cheapest speed", f"{self.cheapest_power_w:.0f}", "W")]
        if self.flown:
            rows.append(("B6 flown for the whole mission: people served", f"{self.flown['coverage_full']:.3f}",
                         "share"))
        return pd.DataFrame(rows, columns=["item", "value", "unit"])

    def markdown(self):
        s = self.settings
        gain = self.coverage["noma_opt"] - self.coverage["oma_opt"]
        lines = [f"# Drone deployment plan (scenario seed {s.seed}, profile {s.profile})", "",
                 "Simulation-based planning tool: a recommendation from the simulator, not a guarantee.", "",
                 f"**Scenario.** {self.scenario}.", "",
                 f"**Where to fly.** Go to ({self.x_m:.0f} m east, {self.y_m:.0f} m north) at {self.altitude_m:.0f} m "
                 f"altitude, transmitting at {self.power_dbm:.0f} dBm ({self.power_w:g} W). This is the best spot of "
                 "pilot B6's search (every grid spot at 5 altitudes) for the crowd as it stands at the start.", "",
                 f"**Expected service at the start.** Adaptive NOMA serves {self.coverage['noma_opt']:.1%} of the "
                 f"people vs {self.coverage['oma_opt']:.1%} with optimised OMA ({gain * 100:+.1f} "
                 "percentage points); rescue users served "
                 f"{self.rescue_served['noma_opt']:.1%} vs {self.rescue_served['oma_opt']:.1%}. Parked at the map "
                 f"centre instead: {self.centre_coverage:.1%}.", "",
                 f"**Battery.** {self.battery_advice}", ""]
        if self.flown:
            lines += [f"**If B6 keeps re-planning every 10 s for the whole mission:** "
                      f"{self.flown['coverage_full']:.1%} served on average, flight time {self.flown['steps']} s.", ""]
        lines += ["Crowds move: re-plan as they do (pilots B3/B6 re-plan every 10 s). All numbers come from the "
                  "simulator and its engineering assumptions (see the dashboard's About page)."]
        return "\n".join(lines)


def recommend(settings, fly=False):
    """The plan for one disaster: B6's search at t = 0 (spot, altitude, power), expected service there under every
    access scheme (adaptive NOMA vs optimised OMA in particular), and battery advice. fly=True also flies B6 for the
    whole episode (slow on big maps: 10-40 s)."""
    key = (settings, fly)
    hit = _PLANS.get(key)
    if hit is not None:
        return hit
    s = settings if settings.access else replace(settings, access="noma_opt")
    with configured(s):
        env = _env(s)
        env.reset(seed=s.seed)
        pilot = B6GridAltitude()
        pilot.reset(env)
        pilot.plan(env)
        x, y, h = (float(v) for v in pilot.target)
        p_w = env.p_max_w * pilot.power
        cov, resc, served_main = {}, {}, None
        for scheme in md.ACCESS_SCHEMES:
            e = env if scheme == env.access else _env(replace(s, access=scheme))
            if e is not env:
                e.reset(seed=s.seed)
            sv = _served_at(e, x, y, h, p_w)
            cov[scheme] = float(sv.mean())
            resc[scheme] = float(sv[e.rescue].mean()) if e.rescue.any() else 1.0
            if e is env:
                served_main = sv
        centre = float(_served_at(env, env.L / 2, env.L / 2, md.CFG["baselines"]["altitude_m"], p_w).mean())
        hover_w = float(md.energy_step_j(0.0, 0.0, p_w) / env.dt)
        v = np.linspace(0.0, env.uav["v_max_mps"], 301)
        pw = md.energy_step_j(v, 0.0, p_w) / env.dt
        j = int(np.argmin(pw))
        cheapest = (float(v[j]), float(pw[j])) if pw[j] < hover_w * 0.99 else None
        battery_wh = env.battery_j / 3600.0
        ok, advice = battery_advice(battery_wh, hover_w, env.T, cheapest)
        scn = describe(dict(sc=env.sc, boxes=env.boxes, area_m=env.L, p_max_dbm=md.CFG["uav"]["p_max_dbm"],
                            battery_wh=battery_wh, access=env.access))
        plan = Plan(s, scn, x, y, h, md.CFG["uav"]["p_max_dbm"] + 10 * np.log10(pilot.power), p_w, cov, resc, centre,
                    battery_wh, hover_w, hover_w * env.T / 3600.0, battery_wh * 3600.0 / hover_w, float(v[j]),
                    float(pw[j]), ok, advice, env=env, served=served_main)
    if fly:
        plan.flown = run_pilot(s, "B6").summary
    return _PLANS.put(key, plan)


def render_plan(plan):
    """Map of the crowd at t = 0, served/not served with the drone at the recommended spot (star)."""
    env = plan.env
    fig = Figure(figsize=(7.6, 5.6), layout="constrained")
    ax = fig.add_subplot()
    _draw_map(ax, env, env.user_xy(0), plan.served)
    ax.plot(plan.x_m, plan.y_m, "*", color=COLORS["drone"], ms=22, markeredgecolor="white", zorder=7)
    ax.plot(env.L / 2, env.L / 2, "x", color="0.3", ms=9, zorder=7)
    ax.set_title(f"Recommended spot (star) at {plan.altitude_m:.0f} m: {plan.coverage[env.access]:.0%} served "
                 f"({ACCESS_INFO[env.access].split(':')[0]}); x = map centre", fontsize=10)
    _legend(ax)
    return fig


# ---------------------------------------------------------------- showcase and about
def gallery():
    """(pictures, animations): lists of (path, caption) from docs/book/figures (numbered book figures first)."""
    figs = BOOK / "figures"
    if not figs.is_dir():
        return [], []

    def order(p):
        head = p.name.split("_")[0]
        return (0, int(head)) if head.isdigit() else (1, p.name)

    def caption(p):
        return FIGURE_CAPTIONS.get(p.name, p.stem.replace("_", " "))

    pics = [(p, caption(p)) for p in sorted(figs.glob("*.png"), key=order)]
    gifs = [(p, caption(p)) for p in sorted((figs / "gifs").glob("*.gif"))]
    return pics, gifs


def book_pdf():
    p = BOOK / "UAV-NOMA-Project-Book.pdf"
    return p if p.is_file() else None


def assumptions_table():
    """Key parameters with their value, unit and status (from config.yaml; status per CLAUDE.md / docs/assumptions)."""
    c = md.BASE_CFG
    e, u = c["energy"], c["uav"]
    rows = [
        ("Minimum data speed per class (rescue/video/voice/iot/normal)",
         " / ".join(f"{v['min_rate_bps'] / 1e3:g}" for v in c["classes"].values()), "kbps",
         "engineering assumption (not signed off)"),
        ("Class mix", " / ".join(f"{v['share']:.0%}" for v in c["classes"].values()), "share", "project spec example"),
        ("Air-to-ground channel a, b, eta LoS, eta NLoS",
         f"{c['a2g']['a']}, {c['a2g']['b']}, {c['a2g']['eta_los_db']}, {c['a2g']['eta_nlos_db']}", "-, -, dB, dB",
         "Al-Hourani model; values seen in secondary papers, 'urban' label not yet confirmed"),
        ("Extra loss through a collapsed building", c["obstacles"]["excess_loss_db"], "dB",
         "engineering assumption (range 10-25)"),
        ("Rotor energy model P0, Pi, tip speed, v0", f"{e['P0_w']}, {e['Pi_w']}, {e['Utip_mps']}, {e['v0_mps']}",
         "W, W, m/s, m/s", "derived from Zeng-Xu-Zhang formulas for a 20 N drone; d0 unverified"),
        ("Electronics power", e["P_circuit_w"], "W", "engineering assumption"),
        ("Power-amplifier efficiency", e["pa_efficiency"], "-", "engineering assumption"),
        ("Battery (default / hard)", f"{e['battery_wh']} / {c['profiles']['hard']['energy']['battery_wh']}", "Wh",
         "engineering assumption"),
        ("Drone limits: speed, climb, altitude", f"{u['v_max_mps']}, {u['vz_max_mps']}, {u['h_min_m']}-{u['h_max_m']}",
         "m/s, m/s, m", "engineering assumption (spec values)"),
        ("Walking speed / panic speed", f"{c['mobility']['speed_mps']} / {c['mobility']['surge_speed_mps']}", "m/s",
         "engineering assumption"),
        ("Bandwidth per user", c["bandwidth_per_user_hz"] / 1e3, "kHz", "engineering assumption"),
        ("Fixed NOMA power split (weak user)", c["noma_alpha_weak"], "share", "engineering assumption"),
        ("Imperfect SIC residual (adaptive NOMA)", c["access"]["sic_eps"], "share",
         "engineering assumption (0 = perfect; 0.05 tested)"),
        ("Mission length", c["mobility"]["episode_steps"], "s", "engineering assumption"),
    ]
    return pd.DataFrame(rows, columns=["parameter", "value", "unit", "status / source"]).astype(str)


def settings_dict(settings):
    return {k: v for k, v in asdict(settings).items() if v is not None}
