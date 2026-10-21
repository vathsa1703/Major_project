"""Show NOMA at work at one moment: who is paired with whom, and who is served with NOMA vs with OMA.

    python noma_picture.py                         # scenario 1 (300 users), drone at the spot grid search (B3) picks
    python noma_picture.py --seed 7 --profile hard
    python noma_picture.py --seed 1 --x 400 --y 600 --h 150

Left: the map. Every line joins the two users of one NOMA pair (a strong-signal user and a weak-signal user who
share one frequency slice). Colours: served by both schemes, only by NOMA, only by OMA, or by neither.
Right: every user's data speed under NOMA and under OMA (sorted), with each class's minimum speed.
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

import make_dataset as md
from baselines import B3GridSearch
from uav_env import UAVEnv

COLOURS = {"both": "tab:green", "NOMA only": "tab:blue", "OMA only": "tab:orange", "neither": "tab:red"}


def snapshot(seed, x=None, y=None, h=None, max_pairs=60):
    """The NOMA and OMA situation at t = 0 for a drone at (x, y, h), or at B3's chosen spot."""
    env = UAVEnv()
    env.reset(seed=seed)
    if x is None:
        b3 = B3GridSearch()
        b3.reset(env)
        b3.plan(env)
        x, y, h = b3.target
    h = h or md.CFG["baselines"]["altitude_m"]
    ux, uy = env.user_xy().T
    g = md.channel_gain(ux, uy, np.array([x]), np.array([y]), np.array([h]), env.boxes)[0]
    weak, strong = md.pair_users(g, env.sc["pairing"], np.random.default_rng(0))
    noma, oma = md.noma_rates(g, env.p_max_w, env.noise_psd, env.sc["bandwidth_hz"], env.sc["pairing"])
    sn, so = noma >= env.min_rate, oma >= env.min_rate
    status = np.where(sn & so, "both", np.where(sn, "NOMA only", np.where(so, "OMA only", "neither")))
    shown = np.argsort(np.hypot(ux[weak] - x, uy[weak] - y))[:max_pairs]          # the pairs nearest the drone
    return dict(env=env, x=x, y=y, h=h, ux=ux, uy=uy, weak=weak, strong=strong, shown=shown, noma=noma, oma=oma,
                status=status, cov_noma=sn.mean(), cov_oma=so.mean())


def draw(s, title, path):
    env = s["env"]
    fig, (m, r) = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={"width_ratios": [1, 1.1]})
    for x0, y0, x1, y1 in env.boxes:
        m.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color="0.75"))
    for i in s["shown"]:
        w, st = s["weak"][i], s["strong"][i]
        m.plot([s["ux"][w], s["ux"][st]], [s["uy"][w], s["uy"][st]], color="0.4", lw=0.6, alpha=0.6)
    for k, c in COLOURS.items():
        sel = s["status"] == k
        m.scatter(s["ux"][sel], s["uy"][sel], s=10, color=c, label=f"{k} ({sel.sum()})")
    m.plot(s["x"], s["y"], "*", color="black", ms=18, label=f"drone ({s['h']:.0f} m)")
    m.set_xlim(0, env.L)
    m.set_ylim(0, env.L)
    m.set_aspect("equal")
    m.legend(fontsize=8, loc="upper right")
    m.set_title(f"NOMA pairs (lines: the {len(s['shown'])} pairs nearest the drone)", fontsize=10)
    order = np.argsort(s["noma"])
    r.semilogy(s["noma"][order] / 1e3, ".", ms=3, label="NOMA speed per user")
    r.semilogy(s["oma"][order] / 1e3, ".", ms=3, label="OMA speed per user")
    for c, v in md.CFG["classes"].items():
        r.axhline(v["min_rate_bps"] / 1e3, color="0.6", lw=0.7, ls="--")
        r.text(0, v["min_rate_bps"] / 1e3 * 1.08, f"{c} minimum", fontsize=7, color="0.4")
    r.set_xlabel("users, sorted by NOMA speed")
    r.set_ylabel("data speed (kbps, log scale)")
    r.legend(fontsize=8)
    r.set_title(f"coverage: NOMA {s['cov_noma']:.2f}  vs  OMA {s['cov_oma']:.2f};  total speed: NOMA "
                f"{s['noma'].sum() / 1e6:.0f} Mbps vs OMA {s['oma'].sum() / 1e6:.0f} Mbps", fontsize=9)
    fig.suptitle(title, fontsize=11)
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--profile", default="default")
    ap.add_argument("--x", type=float)
    ap.add_argument("--y", type=float)
    ap.add_argument("--h", type=float)
    ap.add_argument("--out", default=str(md.OUT / "noma_picture.png"))
    a = ap.parse_args()
    md.apply_profile(a.profile)
    s = snapshot(a.seed, a.x, a.y, a.h)
    env = s["env"]
    title = (f"Scenario {a.seed} ({a.profile}): {env.sc['n_users']} users, {md.CFG['uav']['p_max_dbm']:g} dBm, "
             f"{env.sc['bandwidth_hz'] / 1e6:g} MHz shared by both schemes")
    draw(s, title, a.out)
    print(title)
    print(f"coverage NOMA {s['cov_noma']:.3f} vs OMA {s['cov_oma']:.3f}; total speed NOMA {s['noma'].sum() / 1e6:.1f} "
          f"vs OMA {s['oma'].sum() / 1e6:.1f} Mbps; served by NOMA only {np.sum(s['status'] == 'NOMA only')}, "
          f"by OMA only {np.sum(s['status'] == 'OMA only')}; saved {a.out}")


if __name__ == "__main__":
    main()
