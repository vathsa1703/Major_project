"""Put several pilots on the SAME scenario and compare them in one picture.

    python compare_run.py --seed 5 --profile hard --policies B0,B2,B3,B4
    python compare_run.py --seed 105 --profile rl_static --policies random,B0,B2,B3,ppo --model <model.zip>
    python compare_run.py --seed 21 --users 800 --clusters 5 --mobility surge --obstacles 5 --policies B0,B1,B3,B4

Output: a PNG with (top) coverage over time for every pilot and (bottom) a map of each pilot's flight path with who is
served at the last step, plus a table in the terminal. Same flags as view_run.py for the scenario and the pilots.
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

import make_dataset as md
from rl_utils import CONTROLS
from view_run import OVERRIDE_FLAGS, build_policy, run


def summarize_run(env, frames):
    cov = np.array([f[3]["coverage"] for f in frames])
    return {
        "coverage_full": float(cov.sum() / env.T),     # a dead drone counts as 0 for the rest of the horizon
        "coverage_alive": float(cov.mean()),
        "rescue_outage": float(np.mean([f[3]["outage_rescue"] for f in frames])),
        "steps": len(frames),
        "survived": len(frames) >= env.T,
        "battery_left_wh": frames[-1][3]["battery_wh"],
    }


def compare(seed, names, model_path=None, controls=None, overrides=None, battery_wh=None, hold=None):
    """Run every pilot on the same scenario. Returns {name: (env, frames, summary)}."""
    out = {}
    for n in names:
        env, frames = run(seed, build_policy(n, model_path, controls, hold), battery_wh, overrides)
        out[n] = (env, frames, summarize_run(env, frames))
    return out


def draw(results, seed, title, path):
    names = list(results)
    first_env = results[names[0]][0]
    L = md.CFG["area_m"]
    fig = plt.figure(figsize=(3.4 * len(names), 8))
    gs = fig.add_gridspec(2, len(names), height_ratios=[1, 1.5])
    ax = fig.add_subplot(gs[0, :])
    for n in names:
        _, frames, s = results[n]
        ax.plot([f[3]["t"] for f in frames], [f[3]["coverage"] for f in frames], lw=1.8,
                label=f"{n}  (mean {s['coverage_full']:.2f})")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("share of people with a good signal")
    ax.set_ylim(0, 1.02)
    ax.set_xlim(0, first_env.T)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title(title, fontsize=10)
    for i, n in enumerate(names):
        env, frames, s = results[n]
        m = fig.add_subplot(gs[1, i])
        for x0, y0, x1, y1 in env.boxes:
            m.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color="0.6", alpha=0.7))
        xy, served = frames[-1][0], frames[-1][1]
        m.scatter(xy[:, 0], xy[:, 1], s=5, c=np.where(served, "tab:green", "tab:red"))
        trail = np.array([f[2][:2] for f in frames])
        m.plot(trail[:, 0], trail[:, 1], "b-", lw=1)
        m.plot(*trail[0], "o", color="blue", ms=5)
        m.plot(*trail[-1], "^", color="blue", ms=11)
        m.set_xlim(0, L)
        m.set_ylim(0, L)
        m.set_aspect("equal")
        m.set_xticks([])
        m.set_yticks([])
        life = "alive at the end" if s["survived"] else f"battery died at {s['steps']} s"
        m.set_title(f"{n}: {s['coverage_full']:.2f}\n{life}", fontsize=9)
    fig.text(0.5, 0.005, f"seed {seed}. Maps show the last step: green = served, red = not served, blue line = "
             "flight path (circle = start, triangle = end), grey = collapsed buildings.", ha="center", fontsize=8)
    plt.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--policies", default="B0,B2,B3,B4", help="comma list of B0..B6, random, ppo")
    ap.add_argument("--model", default=None)
    ap.add_argument("--controls", default=None, choices=list(CONTROLS), help="default: read from the model's settings")
    ap.add_argument("--hold", type=int, default=None, help="seconds each decision is held (default: from the model)")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--battery_wh", type=float, default=None)
    ap.add_argument("--users", type=int)
    ap.add_argument("--clusters", type=int)
    ap.add_argument("--mobility", choices=["static", "random_waypoint", "group_drift", "attraction", "hotspot_jump",
                                           "surge"])
    ap.add_argument("--obstacles", type=int)
    ap.add_argument("--radius", type=float)
    ap.add_argument("--scatter", type=float)
    ap.add_argument("--out", default=str(md.OUT / "compare.png"))
    a = ap.parse_args()
    md.apply_profile(a.profile)
    overrides = {field: getattr(a, flag) for flag, field in OVERRIDE_FLAGS.items() if getattr(a, flag) is not None}
    results = compare(a.seed, a.policies.split(","), a.model, a.controls, overrides, a.battery_wh, a.hold)
    env0 = results[next(iter(results))][0]
    title = (f"Scenario seed {a.seed}, profile {a.profile}: {env0.sc['n_users']} users, "
             f"{env0.sc['n_clusters']} crowds, movement '{env0.sc['mobility']}', {len(env0.boxes)} obstacles, "
             f"{md.CFG['area_m']:g} m map")
    draw(results, a.seed, title, a.out)
    print(title)
    print(f"{'pilot':8s} {'coverage':>9s} {'alive-only':>10s} {'rescue out.':>11s} {'steps':>6s} {'battery left':>12s}")
    for n, (_, _, s) in results.items():
        print(f"{n:8s} {s['coverage_full']:9.3f} {s['coverage_alive']:10.3f} {s['rescue_outage']:11.3f} "
              f"{s['steps']:6d} {s['battery_left_wh']:10.2f} Wh")
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
