"""Stage 5, the "sim-to-sim gap": the same pilots on the same scenarios, flown (a) in the point-mass game and (b) by the
simulated quadcopter + autopilot (quadsim.py), in calm air and in wind (config quad.wind_on). A short check, not a
full evaluation: 5 scenarios per cell (validation seeds 100-104 by default; test seeds untouched).

    python sim2sim_exp.py run                 # all cells, one process; appends to results/sim2sim/episodes.csv
    python sim2sim_exp.py run --seeds 100-101 # fewer scenarios
    python sim2sim_exp.py report              # table -> results/sim2sim/summary.md (and printed)

Cells: B6 on `hard`, B6 on `sites_d20_t0_ann` (G5 settings: a_max 4, noma_opt), and the committed showcase AI
(models/e0_best_ai, trained on `rl_static`) on `rl_static`. Finished episodes are skipped on a re-run (resume).
"""
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

import make_dataset as md
from baselines import make_policy
from evalstats import mean_ci, paired_diff
from quadsim import wind_overrides
from uav_env import UAVEnv

HERE = Path(__file__).parent
OUT = HERE / "results" / "sim2sim"
AI_MODEL = HERE / "models" / "e0_best_ai" / "model.zip"
CELLS = [("hard", "B6"), ("sites_d20_t0_ann", "B6"), ("rl_static", "AI_E0")]
CONDITIONS = {"point": ("point", None), "quad_calm": ("quad", False), "quad_wind": ("quad", True)}


def make_pilot(name):
    if name == "AI_E0":
        from rl_utils import load_policy  # needs stable-baselines3 (requirements-rl.txt)
        return load_policy(str(AI_MODEL))
    return make_policy(name)


def episode(profile, pilot, condition, seed):
    """One episode -> one row of metrics."""
    md.apply_profile(profile)
    dyn, wind = CONDITIONS[condition]
    env = UAVEnv(dynamics=dyn, quad_overrides=wind_overrides(wind) if dyn == "quad" else None)
    pol = make_pilot(pilot)
    env.reset(seed=seed)
    pol.reset(env)
    t0, done, cov, tilt, path, prev = time.time(), False, [], 0.0, 0.0, (env.x, env.y)
    while not done:
        _, _, term, trunc, info = env.step(pol.act(env))
        cov.append(info["coverage"])
        path += float(np.hypot(env.x - prev[0], env.y - prev[1]))
        prev = (env.x, env.y)
        if "quad" in info:
            tilt = max(tilt, info["quad"]["tilt_peak_deg"])
        done = term or trunc
    return dict(profile=profile, pilot=pilot, condition=condition, seed=seed, steps=len(cov),
                survived=len(cov) >= env.T, coverage_full=float(np.sum(cov) / env.T),
                people_served=env.served_user_s / (env.T * env.dt), n_users=int(env.sc["n_users"]),
                energy_wh=env.energy_used_j / 3600.0, battery_left_wh=env.energy_left_j / 3600.0,
                path_km=path / 1000.0, tilt_max_deg=tilt, run_s=time.time() - t0)


def run(seeds):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "episodes.csv"
    done = set()
    if path.exists():
        old = pd.read_csv(path)
        done = set(zip(old.profile, old.pilot, old.condition, old.seed, strict=True))
    for profile, pilot in CELLS:
        for seed in seeds:
            for cond in CONDITIONS:
                if (profile, pilot, cond, seed) in done:
                    continue
                row = episode(profile, pilot, cond, seed)
                pd.DataFrame([row]).to_csv(path, mode="a", header=not path.exists(), index=False)
                print(f"{profile:18s} {pilot:6s} {cond:10s} seed {seed}: coverage {row['coverage_full']:.4f}, "
                      f"energy {row['energy_wh']:.3f} Wh, {row['run_s']:.1f} s", flush=True)


def fmt(m_h, k=3):
    return f"{m_h[0]:.{k}f} +/- {m_h[1]:.{k}f}"


def report():
    df = pd.read_csv(OUT / "episodes.csv")
    lines = ["| cell | flown by | n | coverage | people served (avg) | energy (Wh) | path (km) | max tilt (deg) | "
             "coverage gap vs point | energy gap vs point (Wh) |", "|" + "---|" * 10]
    for (profile, pilot), g in df.groupby(["profile", "pilot"], sort=False):
        base = g[g.condition == "point"].set_index("seed")
        for cond in CONDITIONS:
            c = g[g.condition == cond].set_index("seed").reindex(base.index).dropna(subset=["coverage_full"])
            if c.empty:
                continue
            b = base.loc[c.index]
            gap_c = "-" if cond == "point" else fmt(paired_diff(c.coverage_full, b.coverage_full))
            gap_e = "-" if cond == "point" else fmt(paired_diff(c.energy_wh, b.energy_wh), 2)
            tilt = "-" if cond == "point" else f"{c.tilt_max_deg.max():.1f}"
            lines.append(f"| {pilot} on {profile} | {cond} | {len(c)} | {fmt(mean_ci(c.coverage_full))} | "
                         f"{fmt(mean_ci(c.people_served), 1)} | {fmt(mean_ci(c.energy_wh), 2)} | "
                         f"{c.path_km.mean():.2f} | {tilt} | {gap_c} | {gap_e} |")
    text = "\n".join(lines)
    (OUT / "summary.md").write_text(text + "\n", encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=["run", "report"])
    ap.add_argument("--seeds", default="100-104", help="inclusive range, e.g. 100-104")
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.seeds.split("-"))
    if a.what == "run":
        run(range(lo, hi + 1))
    report()


if __name__ == "__main__":
    main()
