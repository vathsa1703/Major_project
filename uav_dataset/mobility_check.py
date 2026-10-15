"""H1 sanity check: does a FIXED drone lose coverage as crowds move, vs the best position at each time?
Run: python mobility_check.py [n_scenarios] [power_dbm]   (fixed drone = area centre, 200 m, NOMA, obstacles on)
The 'best position' is an oracle over the sweep grid at that time (an upper bound, not a real controller)."""
import sys

import numpy as np
import pandas as pd

import make_dataset as md

N_SC = int(sys.argv[1]) if len(sys.argv) > 1 else 15
H, PDBM = 200.0, float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
noise = 10 ** ((md.CFG["noise_density_dbm_hz"] + md.CFG["noise_figure_db"] - 30) / 10)
pw = 10 ** ((PDBM - 30) / 10)
gx = np.arange(0, md.CFG["area_m"] + 1, md.CFG["sweep"]["xy_step_m"])
GX, GY = [a.ravel() for a in np.meshgrid(gx, gx, indexing="ij")]
centre = md.CFG["area_m"] / 2

rows = []
for s in md.seeds("train")[:N_SC]:
    sc = md.make_scenario(s); u = md.make_users(s, sc); tr = md.simulate(s, sc, u)
    boxes = md.obstacle_array(md.make_obstacles(s, sc))
    rng = np.random.default_rng([s, 2])
    minr = u["min_rate_bps"].values
    for t, d in tr.groupby("t"):
        d = d.sort_values("user_id")
        ux, uy = d.x.values, d.y.values
        cov = lambda X, Y: np.array([(md.noma_rates(g, pw, noise, sc["bandwidth_hz"], sc["pairing"], rng)[0] >= minr).mean()
                                     for g in md.channel_gain(ux, uy, X, Y, np.full(len(X), H), boxes)])
        fixed = cov(np.array([centre]), np.array([centre]))[0]
        rows.append((s, sc["mobility"], t, fixed, cov(GX, GY).max()))
df = pd.DataFrame(rows, columns=["seed", "mobility", "t", "fixed_cov", "best_cov"])
df["gap"] = df.best_cov - df.fixed_cov
print(f"{PDBM:g} dBm, {N_SC} scenarios. Fixed drone (centre, {H:g} m) vs oracle-best position, mean over all snapshots:")
print(df.groupby("mobility")[["fixed_cov", "best_cov", "gap"]].mean().round(3).assign(scenarios=df.groupby("mobility").seed.nunique()).to_string())
print("\nbiggest gap at any snapshot, per mobility:")
print(df.groupby("mobility").gap.max().round(3).to_string())
