"""Watch one episode: top-down map of users (green = served, red = not, black ring = rescue), obstacles and the drone.
Run: python view_run.py [--seed 3] [--policy fixed|follow|random] [--out data/run.gif]
The 'policies' here are DEMO policies only (to see the env move); real baselines come later."""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Rectangle

import make_dataset as md
from uav_env import UAVEnv


def policy(name, env, rng):
    if name == "fixed":
        return np.array([0.0, 0.0, 0.0, 1.0])
    if name == "random":
        return rng.uniform(-1, 1, 4)
    c = env.user_xy().mean(axis=0)                      # follow: fly toward the crowd centroid, full power
    d = c - np.array([env.x, env.y])
    return np.array([*(d / max(np.linalg.norm(d), 1.0)), 0.0, 1.0])


def run(seed, name, battery_wh):
    env = UAVEnv(battery_wh=battery_wh)
    env.reset(seed=seed)
    rng = np.random.default_rng(0)
    frames, done = [], False
    while not done:
        _, r, term, trunc, info = env.step(policy(name, env, rng))
        frames.append((env.user_xy().copy(), info["served"].copy(), (env.x, env.y, env.h), dict(info), r))
        done = term or trunc
    return env, frames


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--policy", default="follow", choices=["fixed", "follow", "random"])
    ap.add_argument("--battery_wh", type=float, default=None)
    ap.add_argument("--out", default=str(md.OUT / "run.gif"))
    a = ap.parse_args()
    env, frames = run(a.seed, a.policy, a.battery_wh)
    L = md.CFG["area_m"]
    rescue = env.rescue
    fig, ax = plt.subplots(figsize=(6.2, 6.2))

    def draw(i):
        ax.clear()
        xy, served, (x, y, h), info, r = frames[i]
        for x0, y0, x1, y1 in env.boxes:
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color="0.6", alpha=0.7))
        ax.scatter(xy[:, 0], xy[:, 1], s=6, c=np.where(served, "tab:green", "tab:red"))
        ax.scatter(xy[rescue, 0], xy[rescue, 1], s=24, facecolors="none", edgecolors="k", linewidths=0.6)
        trail = np.array([f[2][:2] for f in frames[: i + 1]])
        ax.plot(trail[:, 0], trail[:, 1], "b-", lw=1)
        ax.plot([x], [y], marker="^", color="blue", markersize=14)
        ax.set_xlim(0, L); ax.set_ylim(0, L); ax.set_aspect("equal")
        ax.set_title(f"seed {a.seed} ({info['mobility']}, {info['n_users']} users)  policy={a.policy}\n"
                     f"t={info['t']}s  coverage={info['coverage']:.2f}  battery={info['battery_wh']:.1f} Wh  h={h:.0f} m",
                     fontsize=9)

    idx = list(range(0, len(frames), 5)) + [len(frames) - 1]
    FuncAnimation(fig, lambda k: draw(idx[k]), frames=len(idx)).save(a.out, writer=PillowWriter(fps=6))
    draw(len(frames) - 1); fig.savefig(a.out.replace(".gif", "_last.png"), dpi=100)
    cov = np.mean([f[3]["coverage"] for f in frames])
    print(f"{len(frames)} steps, mean coverage {cov:.3f}, battery left {frames[-1][3]['battery_wh']:.2f} Wh, saved {a.out}")
