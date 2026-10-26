"""Real-place case study: a scenario based on the September 2024 Kathmandu (Bagmati river) floods. No training.
Map data (c) OpenStreetMap contributors, ODbL 1.0.

    python nepal_case.py run --shard 0/2      # (and 1/2 in a second process) pilots x access x seeds, place + hard_g5
    python nepal_case.py sens --shard 0/2     # sensitivity: LoS model `statistical`, flood band 150 / 300 m
    python nepal_case.py report               # tables -> results/nepal/summary.md (+ docs/case_nepal/results.md)
    python nepal_case.py figures              # figures -> results/nepal/ and docs/case_nepal/figures/
    python nepal_case.py timing               # speed of the height-aware LoS test

Profiles: `place` = place_kathmandu_bagmati (G5 settings, D-48); `hard_g5` = the synthetic `hard` profile with the SAME
G5 settings (noma_opt / oma_opt, imperfect SIC 0.05, rescue first, a_max 4 m/s^2), so the comparison isolates the
geometry and the crowd. Seeds 0-19 (crowd draws). Each pilot runs with noma_opt and oma_opt (equal bandwidth/power).
One process per shard, seed-major; every finished episode is appended to a CSV (an interrupted run resumes).
"""
import argparse
import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PolyCollection

import baselines as bl
import make_dataset as md
from baselines import make_policy
from evalstats import mean_ci, paired_diff
from uav_env import UAVEnv

HERE = Path(__file__).parent
OUT = HERE / "results" / "nepal"
DOC = HERE.parent / "docs" / "case_nepal"
SEEDS = list(range(20))
PILOTS = ("B0", "B2", "B3", "B6", "B7", "B8", "B6fc")
ACCESS = ("noma_opt", "oma_opt")
PROFILES = ("place", "hard_g5")
GROUPS = ("stranded", "shelter", "dry", "scatter", "evacuee")
SENS = {"los_statistical": ({"los_model": "statistical"}, ("B0", "B2", "B6")),
        "band150": ({"flood_band_m": 150}, ("B0", "B6")),
        "band300": ({"flood_band_m": 300}, ("B0", "B6"))}
CREDIT = "Map data © OpenStreetMap contributors (ODbL)"
NOMA_C, OMA_C = "#2a78d6", "#eb6834"                 # categorical slots 1, 2 (dataviz reference palette)
GROUP_C = {"stranded": "#eb6834", "shelter": "#2a78d6", "evacuee": "#2a78d6", "dry": "#1baf7a", "scatter": "#8a8984"}


def setup(profile, place_over=None):
    """Switch the config to a case-study profile."""
    if profile == "place":
        md.apply_profile("place_kathmandu_bagmati")
        md.CFG["place"].update(place_over or {})
    elif profile == "hard_g5":
        md.apply_profile("hard")
        md.CFG["uav"]["a_max_mps2"] = 4
        md.CFG["env"]["access"] = "noma_opt"
        md.CFG["access"].update(sic_eps=0.05, rescue_first=True)
    else:
        raise ValueError(profile)


def episode(env, policy, seed):
    """One episode; per-step logs -> one row of metrics + the flight path (T+1, 3)."""
    env.reset(seed=seed)
    policy.reset(env)
    group = env.users["group"].values if "group" in env.users else None
    rescue = env.rescue
    path = [(env.x, env.y, env.h)]
    cov, rate, resc, resc_n, dist = [], [], [], 0.0, 0.0
    gs = {g: [] for g in GROUPS}
    done, info = False, {}
    while not done:
        x0, y0 = env.x, env.y
        _, _, term, trunc, info = env.step(policy.act(env))
        done = term or trunc
        dist += float(np.hypot(env.x - x0, env.y - y0))
        path.append((env.x, env.y, env.h))
        cov.append(info["coverage"]); rate.append(info["sum_rate_mbps"])
        served = info["served"]
        act = info.get("active", np.ones(len(served), bool))
        r = act & rescue
        resc.append(served[r].mean() if r.any() else np.nan)
        resc_n += float(served[r].sum())
        if group is not None:
            for g in GROUPS:
                m = act & (group == g)
                if m.any():
                    gs[g].append(served[m].mean())
    T = env.T
    row = dict(seed=seed, n_users=info["n_users"], steps=len(cov), survived=len(cov) >= T,
               coverage_full=float(np.sum(cov) / T), coverage_alive=float(np.mean(cov)),
               rescue_served=float(np.nansum(resc) / T), rescue_user_s=resc_n,
               sum_rate_mbps=float(np.sum(rate) / T), battery_left_wh=info["battery_wh"],
               energy_used_wh=env.energy_used_j / 3600.0, served_user_s_per_wh=info["served_user_s_per_wh"],
               flown_m=dist, mean_h=float(np.mean([p[2] for p in path[1:]])))
    for g in GROUPS:
        row[f"cov_{g}"] = float(np.mean(gs[g])) if gs[g] else np.nan
    return row, np.array(path)


def shard_of(spec):
    if not spec:
        return 0, 1
    k, n = spec.split("/")
    return int(k), int(n)


def done_keys(csv, cols):
    if not csv.exists():
        return set()
    d = pd.read_csv(csv)
    return set(map(tuple, d[cols].astype(str).values))


def append(csv, row):
    pd.DataFrame([row]).to_csv(csv, mode="a", header=not csv.exists(), index=False)


def run(shard, variant=None):
    k, n = shard_of(shard)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "paths").mkdir(exist_ok=True)
    tag = "sens" if variant else "episodes"
    csv = OUT / f"{tag}_shard{k}.csv"
    cols = ["variant", "profile", "access", "policy", "seed"]
    done = done_keys(csv, cols)
    seeds = [s for i, s in enumerate(SEEDS) if i % n == k]
    t_start = time.time()
    for s in seeds:
        jobs = []
        if variant:
            for v, (over, pilots) in SENS.items():
                jobs += [(v, "place", over, a, p) for a in ACCESS for p in pilots]
        else:
            jobs = [("base", prof, None, a, p) for prof in PROFILES for a in ACCESS for p in PILOTS]
        bl.FC_MEMO = {}                                   # forecasts shared only within one seed
        for v, prof, over, acc, pol in jobs:
            if (v, prof, acc, pol, str(s)) in done:
                continue
            setup(prof, over)
            t = time.time()
            row, path = episode(UAVEnv(access=acc), make_policy(pol), s)
            row = dict(variant=v, profile=prof, access=acc, policy=pol, **row, secs=time.time() - t)
            append(csv, row)
            if not variant:
                np.save(OUT / "paths" / f"{prof}_{acc}_{pol}_s{s}.npy", path.astype(np.float32))
            print(f"[{(time.time() - t_start) / 60:5.1f} min] {v} {prof} {acc} {pol} seed {s}: "
                  f"cov {row['coverage_full']:.3f}  {row['secs']:.0f}s", flush=True)
        bl.FC_MEMO = None


# ---------------------------------------------------------------- report
def load(tag):
    fs = sorted(OUT.glob(f"{tag}_shard*.csv"))
    assert fs, f"no {tag} CSVs in {OUT}"
    d = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    key = ["variant", "profile", "access", "policy", "seed"]
    assert not d.duplicated(key).any(), "duplicate episodes"
    return d


def f3(mci, signed=False):
    m, h = mci
    return (f"{m:+.3f}" if signed else f"{m:.3f}") + f" +/- {h:.3f}" + ("*" if signed and abs(m) > h else "")


def table_main(d, prof):
    x = d[(d.profile == prof)]
    lines = ["| pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | rescue served NOMA | rescue served OMA "
             "| total speed NOMA (Mbit/s) | total speed OMA | battery left NOMA (Wh) | flown NOMA (m) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for p in PILOTS:
        a = x[(x.policy == p) & (x.access == "noma_opt")].set_index("seed").sort_index()
        b = x[(x.policy == p) & (x.access == "oma_opt")].set_index("seed").sort_index()
        if a.empty or b.empty:
            continue
        lines.append(f"| {p} | {f3(mean_ci(a.coverage_full))} | {f3(mean_ci(b.coverage_full))} | "
                     f"{f3(paired_diff(a.coverage_full, b.coverage_full), True)} | {f3(mean_ci(a.rescue_served))} | "
                     f"{f3(mean_ci(b.rescue_served))} | {mean_ci(a.sum_rate_mbps)[0]:.1f} | "
                     f"{mean_ci(b.sum_rate_mbps)[0]:.1f} | {mean_ci(a.battery_left_wh)[0]:.2f} | "
                     f"{mean_ci(a.flown_m)[0]:.0f} |")
    return "\n".join(lines)


def table_paired(d, prof, ref="B6"):
    x = d[(d.profile == prof)]
    out = [f"| pilot | access | minus {ref} (paired, 95% CI) |", "|---|---|---|"]
    for acc in ACCESS:
        piv = x[x.access == acc].pivot(index="seed", columns="policy", values="coverage_full")
        for p in PILOTS:
            if p != ref and p in piv:
                out.append(f"| {p} | {acc} | {f3(paired_diff(piv[p], piv[ref]), True)} |")
    return "\n".join(out)


def ranking(d, prof, acc="noma_opt"):
    m = d[(d.profile == prof) & (d.access == acc)].groupby("policy").coverage_full.mean()
    return " > ".join(f"{p} {m[p]:.3f}" for p in m.sort_values(ascending=False).index)


def report():
    d = load("episodes")
    n = d.groupby(["profile", "access", "policy"]).seed.nunique()
    lines = ["# Kathmandu (Bagmati) case study: results", "",
             "A scenario based on the September 2024 Kathmandu (Bagmati river) floods. The crowd is RECONSTRUCTED from "
             "the map with engineering assumptions (not real data). " + CREDIT + ".", "",
             f"Seeds 0-19 (crowd draws); episodes per (profile, access, pilot): {n.min()}-{n.max()}. Values: mean "
             "+/- 95% CI over scenarios; paired differences per scenario; * = the CI excludes 0. Coverage = mean share "
             "of the active users served over the 300 s horizon (dead drone = 0). Rescue served = the same for the "
             "rescue class. Total speed = mean sum rate. G5 settings in both profiles (noma_opt vs oma_opt, SIC "
             "residual 0.05, rescue first, a_max 4 m/s^2, 20 dBm, 16 Wh).", ""]
    for prof, title in (("place", "Kathmandu place profile (place_kathmandu_bagmati)"),
                        ("hard_g5", "Synthetic `hard` with the same G5 settings")):
        lines += [f"## {title}", "", table_main(d, prof), "", "Paired difference to B6:", "",
                  table_paired(d, prof), "", f"Ranking (noma_opt): {ranking(d, prof)}", "",
                  f"Ranking (oma_opt): {ranking(d, prof, 'oma_opt')}", ""]
    # NOMA gain: place vs hard (per pilot, unpaired across profiles: different scenarios)
    lines += ["## NOMA gain: real geometry vs synthetic", "",
              "| pilot | NOMA - OMA, place | NOMA - OMA, hard_g5 | difference of the gains (Welch-style CI) |",
              "|---|---|---|---|"]
    for p in PILOTS:
        gains = []
        for prof in PROFILES:
            x = d[(d.profile == prof) & (d.policy == p)].pivot(index="seed", columns="access", values="coverage_full")
            gains.append((x["noma_opt"] - x["oma_opt"]).values)
        m = gains[0].mean() - gains[1].mean()
        h = 1.96 * np.sqrt(gains[0].var(ddof=1) / len(gains[0]) + gains[1].var(ddof=1) / len(gains[1]))
        lines.append(f"| {p} | {f3(mean_ci(gains[0]), True)} | {f3(mean_ci(gains[1]), True)} | "
                     f"{m:+.3f} +/- {h:.3f}{'*' if abs(m) > h else ''} |")
    x = d[(d.profile == "place")]
    lines += ["", "## Who is served (place profile, mean share of each group's active users served)", "",
              "| pilot | access | stranded (roofs, flood band) | at shelters | dry ground | scattered | evacuees "
              "(at shelters after rescue) |", "|---|---|---|---|---|---|---|"]
    for acc in ACCESS:
        for p in PILOTS:
            y = x[(x.policy == p) & (x.access == acc)]
            lines.append(f"| {p} | {acc} | " + " | ".join(f"{y[f'cov_{g}'].mean():.3f}" for g in GROUPS) + " |")
    lines += ["", "Run time per episode (s, mean): " + ", ".join(
        f"{prof} {p} {d[(d.profile == prof) & (d.policy == p)].secs.mean():.0f}" for prof in PROFILES
        for p in ("B6", "B6fc"))]
    for prof in PROFILES:
        b6, fc = (d[(d.policy == p) & (d.profile == prof)].set_index(["access", "seed"]).coverage_full
                  for p in ("B6", "B6fc"))
        lines += ["", f"{prof}: B6fc equals B6 (to 1e-12) in {int((np.abs(b6 - fc) < 1e-12).sum())} of {len(b6)} "
                  "episodes" + (" (the evacuation is unannounced and people stand still, so B6fc's forecast is the "
                                "present)." if prof == "place" else ".")]
    s = sorted(OUT.glob("sens_shard*.csv"))
    if s:
        sd = load("sens")
        base = d[(d.profile == "place")]
        lines += ["", "## Sensitivity (place profile)", "",
                  "| variant | pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | base coverage NOMA |",
                  "|---|---|---|---|---|---|"]
        for v, (_, pilots) in SENS.items():
            for p in pilots:
                y = sd[(sd.variant == v) & (sd.policy == p)].pivot(index="seed", columns="access",
                                                                    values="coverage_full")
                b = base[(base.policy == p) & (base.access == "noma_opt")].coverage_full
                if y.empty:
                    continue
                lines.append(f"| {v} | {p} | {f3(mean_ci(y['noma_opt']))} | {f3(mean_ci(y['oma_opt']))} | "
                             f"{f3(paired_diff(y['noma_opt'], y['oma_opt']), True)} | {f3(mean_ci(b))} |")
    text = "\n".join(lines) + "\n"
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    DOC.mkdir(parents=True, exist_ok=True)
    (DOC / "results.md").write_text(text, encoding="utf-8")
    print(text)


# ---------------------------------------------------------------- figures
def _credit(ax):
    ax.text(0.995, 0.005, CREDIT, transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="#52514e",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=1.5))


def draw_city(ax, S, alpha=1.0, band=True, cmap="Greys"):
    polys = [b["xy"] for b in S.buildings]
    pc = PolyCollection(polys, array=S.heights, cmap=cmap, edgecolor="none", alpha=alpha)
    pc.set_clim(0, 30)
    ax.add_collection(pc)
    if band:
        cc = (np.arange(S.n) + 0.5) * S.cell
        W = md.CFG["place"]["flood_band_m"]
        ax.contourf(cc, cc, (S.dist.T <= W).astype(float), levels=[0.5, 1.5], colors=["#9cc3f0"], alpha=0.35)
        ax.contour(cc, cc, S.dist.T, levels=[W], colors=["#2a78d6"], linewidths=0.8, linestyles="--")
    for r in S.other_rivers:
        ax.plot(r[:, 0], r[:, 1], color="#7fb0e8", lw=1.0)
    for r in S.rivers:
        ax.plot(r[:, 0], r[:, 1], color="#1f5fae", lw=2.2)
    ax.set_xlim(0, S.side); ax.set_ylim(0, S.side); ax.set_aspect("equal")
    ax.set_xlabel("x (m, east)"); ax.set_ylabel("y (m, north)")
    _credit(ax)
    return pc


def fig_map(S, env, seed):
    fig, ax = plt.subplots(figsize=(9, 8.2))
    pc = draw_city(ax, S)
    cb = fig.colorbar(pc, ax=ax, shrink=0.7, pad=0.01)
    cb.set_label("building height (m; 94% filled from the tagged ones)")
    sh = [s for s in S.shelters if s["kind"] in md.CFG["place"]["shelter_kinds"]]
    ax.scatter([s["x"] for s in sh], [s["y"] for s in sh], marker="^", s=18, facecolor="white", edgecolor="#0b0b0b",
               lw=0.6, label="shelter candidates (schools, hospitals, temples, parks)", zorder=3)
    u = env.users
    for g, mk in (("stranded", "o"), ("shelter", "s"), ("dry", "o"), ("scatter", "."), ("evacuee", "s")):
        m = (u.group == g).values
        lab = {"stranded": "stranded on roofs (flood band)", "shelter": "at a shelter", "dry": "on dry ground",
               "scatter": "scattered", "evacuee": "evacuees (appear at the shelter after rescue)"}[g]
        ax.scatter(u.x[m], u.y[m], s=7 if g != "scatter" else 14, marker=mk, color=GROUP_C[g],
                   alpha=0.35 if g == "evacuee" else 0.9, lw=0, label=lab, zorder=4)
    sc = env.sc
    ax.scatter(sc["shelter_x"], sc["shelter_y"], marker="^", s=120, facecolor="none", edgecolor="#0b0b0b", lw=1.5,
               zorder=5, label="shelters used in this scenario")
    ax.plot([], [], color="#1f5fae", lw=2.2, label="Bagmati river (OSM centreline)")
    ax.fill([], [], color="#9cc3f0", alpha=0.5, label=f"assumed flood band ({md.CFG['place']['flood_band_m']:g} m)")
    ax.legend(loc="upper left", fontsize=7, framealpha=0.9)
    ax.set_title(f"Kathmandu, Teku / Kuleshwor reach of the Bagmati: a scenario based on the Sept 2024 floods\n"
                 f"seed {seed}: {sc['n_users']} people (reconstructed, not real data)", fontsize=10)
    return fig


def fig_paths(S, seed, d):
    from matplotlib.colors import Normalize
    fig, axs = plt.subplots(2, 3, figsize=(13, 9.6))
    norm = Normalize(-100, 300)                         # light (start) -> dark (end); no near-white marks
    sca = None
    for ax, p in zip(axs.ravel(), ("B0", "B2", "B3", "B6", "B7", "B8"), strict=True):
        draw_city(ax, S, alpha=0.5)
        f = OUT / "paths" / f"place_noma_opt_{p}_s{seed}.npy"
        if f.exists():
            path = np.load(f)
            sca = ax.scatter(path[:, 0], path[:, 1], c=np.arange(len(path)), cmap="Blues", norm=norm, s=4, zorder=4)
            ax.plot(path[-1, 0], path[-1, 1], marker="*", ms=14, color="#eb6834", mec="#0b0b0b", zorder=5)
            r = d[(d.profile == "place") & (d.access == "noma_opt") & (d.policy == p) & (d.seed == seed)]
            cov = r.coverage_full.iloc[0] if len(r) else np.nan
            ax.set_title(f"{p}: coverage {cov:.3f}\nfinal spot ({path[-1, 0]:.0f}, {path[-1, 1]:.0f}) m at "
                         f"{path[-1, 2]:.0f} m", fontsize=9)
        ax.set_xlabel(""); ax.set_ylabel("")
    cb = fig.colorbar(sca, ax=axs, shrink=0.6, label="time along the flight (s)")
    cb.ax.set_ylim(0, 300)
    fig.suptitle(f"Flight paths (noma_opt), seed {seed}; star = final spot", fontsize=11)
    return fig


def fig_coverage(S, env, seed, panels):
    """Coverage the drone would get at each position (noma_opt), per panel (altitude h, time index t)."""
    n = 41
    g = np.linspace(0, S.side, n)
    X, Y = np.meshgrid(g, g, indexing="ij")
    covs = [env.evaluate(X.ravel(), Y.ravel(), np.full(n * n, float(h)), env.p_max_w, t=t).reshape(n, n)
            for h, t in panels]
    top = max(c.max() for c in covs)
    fig, axs = plt.subplots(1, len(panels), figsize=(6.2 * len(panels), 6.4))
    for ax, (h, t), cov in zip(axs, panels, covs, strict=True):
        im = ax.imshow(cov.T, origin="lower", extent=(0, S.side, 0, S.side), cmap="Blues", vmin=0, vmax=top,
                       interpolation="bilinear")
        polys = [b["xy"] for b in S.buildings]
        ax.add_collection(PolyCollection(polys, facecolor="none", edgecolor="#52514e", lw=0.15, alpha=0.6))
        for r in S.rivers:
            ax.plot(r[:, 0], r[:, 1], color="#1f5fae", lw=1.8)
        xy, _, _ = env.users_now(t)
        ax.scatter(xy[:, 0], xy[:, 1], s=4, color="#eb6834", lw=0, label="people counted now")
        i = np.unravel_index(np.argmax(cov), cov.shape)
        ax.plot(g[i[0]], g[i[1]], marker="*", ms=16, color="#eda100", mec="#0b0b0b",
                label=f"best spot: {cov.max():.3f} served")
        ax.set_xlim(0, S.side); ax.set_ylim(0, S.side); ax.set_aspect("equal")
        ax.legend(loc="upper left", fontsize=8)
        ev = "before the evacuation" if t < (env.sc["event_t0_s"] or 0) else "after the evacuation"
        ax.set_title(f"drone at {h:g} m, t = {t} s ({ev})", fontsize=10)
        _credit(ax)
    fig.colorbar(im, ax=axs, shrink=0.7, label="share of the people counted now that would be served")
    fig.suptitle(f"Coverage map, seed {seed} (noma_opt, 20 dBm, height-aware line of sight)", fontsize=11)
    return fig


def fig_bars(d):
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, prof, title in zip(axs, PROFILES, ("Kathmandu place profile", "synthetic hard (same G5 settings)"),
                               strict=True):
        xs = np.arange(len(PILOTS))
        for k, (acc, col, lab) in enumerate((("noma_opt", NOMA_C, "NOMA (noma_opt)"), ("oma_opt", OMA_C,
                                                                                        "OMA (oma_opt)"))):
            st = [mean_ci(d[(d.profile == prof) & (d.access == acc) & (d.policy == p)].coverage_full)
                  for p in PILOTS]
            ax.bar(xs + (k - 0.5) * 0.38, [s[0] for s in st], width=0.36, yerr=[s[1] for s in st], color=col,
                   capsize=3, label=lab, error_kw=dict(lw=1, ecolor="#52514e"))
        ax.set_xticks(xs, PILOTS)
        ax.set_ylim(0, 1)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", color="#e4e3df", lw=0.6); ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axs[0].set_ylabel("coverage over 300 s (mean, 95% CI, 20 seeds)")
    axs[0].legend(fontsize=8, loc="upper left", ncol=2)
    fig.suptitle("NOMA vs OMA at equal bandwidth and power", fontsize=11)
    fig.text(0.99, 0.005, CREDIT + " (place profile)", ha="right", va="bottom", fontsize=7, color="#52514e")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def figures(seed=0):
    setup("place")
    import place
    S = place.scene()
    d = load("episodes")
    env = UAVEnv(access="noma_opt")
    env.reset(seed=seed)
    targets = []
    for name, fig in (("map", fig_map(S, env, seed)), ("paths", fig_paths(S, seed, d)), ("bars", fig_bars(d))):
        targets.append((name, fig))
    p6 = OUT / "paths" / f"place_noma_opt_B6_s{seed}.npy"
    h = float(np.load(p6)[-1, 2]) if p6.exists() else 100.0
    targets.append(("coverage", fig_coverage(S, env, seed, [(100.0, 0), (h, 0), (h, env.T - 1)])))
    DOC.joinpath("figures").mkdir(parents=True, exist_ok=True)
    for name, fig in targets:
        for folder in (OUT, DOC / "figures"):
            fig.savefig(folder / f"nepal_{name}.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        print("saved", f"nepal_{name}.png")


def timing():
    setup("place")
    import place
    t = time.time(); S = place.scene(); t_scene = time.time() - t
    env = UAVEnv(access="noma_opt")
    rows = []
    for seed in (0, 1, 2):
        env.reset(seed=seed)
        b6 = make_policy("B6"); b6.reset(env)
        CX, CY, CH = b6.candidates(env)
        pool = env.links.pool
        t = time.time()
        place.ray_clear(S, pool[:, 0], pool[:, 1], env.links.pool_z, CX, CY, CH)
        t_full = time.time() - t
        t = time.time()
        for k in range(50):
            place.ray_clear(S, pool[:, 0], pool[:, 1], env.links.pool_z, np.array([900.0 + k]), np.array([1000.0]),
                            np.array([120.0]))
        t_one = (time.time() - t) / 50
        rows.append(dict(seed=seed, n_pool=len(pool), candidates=len(CX), links=len(CX) * len(pool),
                         secs_all_candidates=round(t_full, 2), ms_one_position=round(1000 * t_one, 2)))
    df = pd.DataFrame(rows)
    text = (f"Scene build (load + rasterise {len(S.buildings)} footprints at {S.cell:g} m + river distance): "
            f"{t_scene:.1f} s, once per process.\n\n" + df.to_string(index=False))
    print(text)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "timing.csv", index=False)
    (OUT / "timing.json").write_text(json.dumps(dict(scene_s=t_scene, rows=rows)), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "sens", "report", "figures", "timing"])
    ap.add_argument("--shard", default=None)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.what == "run":
        run(a.shard)
    elif a.what == "sens":
        run(a.shard, variant=True)
    elif a.what == "report":
        report()
    elif a.what == "figures":
        figures(a.seed)
    else:
        timing()
