"""Gate G2 diagnostic: does coverage-vs-altitude have an optimum, for each user class?
Run: python altitude_by_class.py [n_scenarios]   -> data/altitude_by_class.png + a printed table
Uses a sample of train scenarios, NOMA only, one power level per curve."""
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import make_dataset as md

N_SC = int(sys.argv[1]) if len(sys.argv) > 1 else 20
POWERS = [0, 10]
noise = 10 ** ((md.CFG["noise_density_dbm_hz"] + md.CFG["noise_figure_db"] - 30) / 10)
alts = np.array(md.CFG["sweep"]["altitudes_m"], float)
gx = np.arange(0, md.CFG["area_m"] + 1, md.CFG["sweep"]["xy_step_m"])
X, Y, H = [a.ravel() for a in np.meshgrid(gx, gx, alts, indexing="ij")]

rows = []
for s in md.seeds("train")[:N_SC]:
    sc = md.make_scenario(s)
    u = md.make_users(s, sc)
    G = md.channel_gain(u["x"].values, u["y"].values, X, Y, H)
    rng = np.random.default_rng([s, 2])
    minr, cls = u["min_rate_bps"].values, u["class"].values
    for p in POWERS:
        pw = 10 ** ((p - 30) / 10)
        cov = np.array([md.noma_rates(G[i], pw, noise, sc["bandwidth_hz"], sc["pairing"], rng)[0] >= minr
                        for i in range(len(X))])                       # (positions, users)
        for c in np.unique(cls):
            per_pos = cov[:, cls == c].mean(axis=1)
            for h in alts:
                rows.append((s, p, c, h, per_pos[H == h].mean()))
df = pd.DataFrame(rows, columns=["seed", "p_dbm", "class", "h", "coverage"])
m = df.groupby(["p_dbm", "class", "h"]).coverage.mean().unstack("h").round(3)
print(m.to_string())
print("\nbest altitude per (power, class):")
print(m.idxmax(axis=1).unstack("class").to_string())

fig, ax = plt.subplots(1, len(POWERS), figsize=(11, 4), sharey=True)
for a, p in zip(ax, POWERS):
    for c, row in m.loc[p].iterrows():
        a.plot(row.index, row.values, "-o", label=f"{c} ({md.CFG['classes'][c]['min_rate_bps']/1e3:.0f} kbps)")
    a.set_title(f"{p} dBm, NOMA"); a.set_xlabel("altitude (m)")
ax[0].set_ylabel("mean coverage"); ax[0].legend(fontsize=7)
plt.tight_layout(); plt.savefig(md.OUT / "altitude_by_class.png", dpi=110)
print("saved altitude_by_class.png")
