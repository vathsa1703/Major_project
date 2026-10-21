"""Play ONE scenario with ANY pilot and watch it: top-down map of users (green = served, red = not, black ring =
rescue), obstacles (grey) and the drone (blue triangle with its trail). Saves a GIF and a picture of the last frame.

    python view_run.py --seed 5 --policy B3                         # grid search on scenario 5
    python view_run.py --seed 5 --profile hard --policy B4          # the hard profile (2x2 km, 20 dBm, obstacles...)
    python view_run.py --policy ppo --model results/rl/<name>/model.zip --profile rl_static --controls xy
    python view_run.py --seed 9 --users 600 --clusters 4 --mobility surge --obstacles 6 --policy B2   # your own

Any seed is a new scenario. --users/--clusters/--mobility/--obstacles/--radius/--scatter replace those settings.
Pilots: B0..B5 (the baselines), random, ppo (needs --model). `fixed` and `follow` are old names for B0 and B1.
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Rectangle

import make_dataset as md
from baselines import POLICIES, make_policy
from rl_utils import CONTROLS, RandomPolicy, load_policy, model_settings
from uav_env import UAVEnv

ALIASES = {"fixed": "B0", "follow": "B1"}
OVERRIDE_FLAGS = {"users": "n_users", "clusters": "n_clusters", "mobility": "mobility", "obstacles": "n_obstacles",
                  "radius": "cluster_radius_m", "scatter": "scatter_fraction"}


def build_policy(name, model_path=None, controls=None, hold=None):
    """A pilot by name: a baseline (B0..), 'random', or 'ppo' (a trained model)."""
    name = ALIASES.get(name, name)
    saved = model_settings(model_path) if (name == "ppo" and model_path) else {}
    controls = controls or saved.get("controls") or md.CFG["rl"]["controls"]
    hold = hold or saved.get("hold_steps", 1)                 # old models were trained deciding every second
    if name in POLICIES:
        return make_policy(name)
    if name == "random":
        return RandomPolicy(controls)
    if name == "ppo":
        if not model_path:
            raise ValueError("--policy ppo needs --model path/to/model.zip")
        return load_policy(model_path, controls, hold)              # PPO or SAC, from the model's saved settings
    raise ValueError(f"unknown policy {name!r}; choose from {sorted(POLICIES)} + random, ppo")


def run(seed, pilot, battery_wh=None, overrides=None):
    """Play one episode. Returns the env and one frame per step."""
    env = UAVEnv(battery_wh=battery_wh, scenario_overrides=overrides)
    env.reset(seed=seed)
    pilot.reset(env)
    frames, done = [], False
    while not done:
        _, r, term, trunc, info = env.step(pilot.act(env))
        frames.append((env.user_xy().copy(), info["served"].copy(), (env.x, env.y, env.h), dict(info), r))
        done = term or trunc
    return env, frames


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--policy", default="B1")
    ap.add_argument("--model", default=None, help="model.zip for --policy ppo")
    ap.add_argument("--controls", default=None, choices=list(CONTROLS),
                    help="controls of the model/random (default: read from the model's saved settings)")
    ap.add_argument("--hold", type=int, default=None, help="seconds each decision is held (default: from the model)")
    ap.add_argument("--profile", default="default", help="default, lowpower, bigarea, hard, rl_static")
    ap.add_argument("--battery_wh", type=float, default=None)
    ap.add_argument("--users", type=int)
    ap.add_argument("--clusters", type=int)
    ap.add_argument("--mobility", choices=["static", "random_waypoint", "group_drift", "attraction", "hotspot_jump",
                                           "surge"])
    ap.add_argument("--obstacles", type=int)
    ap.add_argument("--radius", type=float)
    ap.add_argument("--scatter", type=float)
    ap.add_argument("--out", default=str(md.OUT / "run.gif"))
    a = ap.parse_args()
    md.apply_profile(a.profile)
    overrides = {field: getattr(a, flag) for flag, field in OVERRIDE_FLAGS.items() if getattr(a, flag) is not None}
    env, frames = run(a.seed, build_policy(a.policy, a.model, a.controls, a.hold), a.battery_wh, overrides)

    L = md.CFG["area_m"]
    rescue = env.rescue
    fig, ax = plt.subplots(figsize=(6.2, 6.2))

    def draw(i):
        ax.clear()
        xy, served, (x, y, h), info, _ = frames[i]
        for x0, y0, x1, y1 in env.boxes:
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color="0.6", alpha=0.7))
        ax.scatter(xy[:, 0], xy[:, 1], s=6, c=np.where(served, "tab:green", "tab:red"))
        ax.scatter(xy[rescue, 0], xy[rescue, 1], s=24, facecolors="none", edgecolors="k", linewidths=0.6)
        trail = np.array([f[2][:2] for f in frames[: i + 1]])
        ax.plot(trail[:, 0], trail[:, 1], "b-", lw=1)
        ax.plot([x], [y], marker="^", color="blue", markersize=14)
        ax.set_xlim(0, L)
        ax.set_ylim(0, L)
        ax.set_aspect("equal")
        ax.set_title(f"seed {a.seed} ({info['mobility']}, {info['n_users']} users) pilot={a.policy}\n"
                     f"t={info['t']}s  coverage={info['coverage']:.2f}  battery={info['battery_wh']:.1f} Wh "
                     f"h={h:.0f} m", fontsize=9)

    idx = list(range(0, len(frames), 5)) + [len(frames) - 1]
    FuncAnimation(fig, lambda k: draw(idx[k]), frames=len(idx)).save(a.out, writer=PillowWriter(fps=6))
    draw(len(frames) - 1)
    fig.savefig(a.out.replace(".gif", "_last.png"), dpi=100)
    cov = np.mean([f[3]["coverage"] for f in frames])
    left = frames[-1][3]["battery_wh"]
    print(f"{len(frames)} steps, mean coverage {cov:.3f}, battery left {left:.2f} Wh, saved {a.out}")


if __name__ == "__main__":
    main()
