"""Plan step 5 experiments: acceleration limit (uav.a_max_mps2) and the loiter pilot B7 vs the hover pilot B6.

    python accel_loiter_exp.py run a        # B6, B3 on `hard` (100 scenarios), limit off vs on (a_max 4)
    python accel_loiter_exp.py run c        # B7 (r 50) on `hard`, limit on; batteries 12/13/14/16 Wh in the report
    python accel_loiter_exp.py run b        # MAIN: run-to-empty on rl_static, 10 Wh, 600 s horizon: B6 vs B7 r50/r100
    python accel_loiter_exp.py run d        # sensitivity (30 scenarios): d0, Pi, a_max, r
    python accel_loiter_exp.py report       # all tables -> results/accel_loiter/summary.md
One process, sequential (no worker pool). Every finished episode is appended to results/accel_loiter/episodes.csv
and its per-step log saved, so an interrupted run resumes where it stopped.

Battery sweep (exp c): B6/B7 never look at the battery, so their trajectory until the battery is empty does not
depend on its size. A run with the 16 Wh battery therefore gives every smaller battery exactly: the episode ends at
the first step where the cumulative energy reaches the battery (the env's own rule), and coverage_full is the sum of
the coverage up to and including that step / 300. `check-truncation` verifies this against real env runs.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import make_dataset as md
from baselines import make_policy
from evalstats import holm, mean_ci, paired_diff, paired_p
from uav_env import UAVEnv

OUT = Path(__file__).parent / "results" / "accel_loiter"
STEPS = OUT / "steps"
A_ON = 4.0                     # a_max when the limit is on (engineering assumption, sensitivity {2, 4, 8})
SEEDS_HARD = list(range(0, 100))
SEEDS_B = list(range(100, 120)) + list(range(0, 30))         # val 100-119 + train 0-29 (50 scenarios)
SEEDS_D = SEEDS_B[:30]

# setting name -> (profile, config overrides {(section, key): value}, battery_wh)
SETTINGS = {
    "hard_off": ("hard", {}, None),
    "hard_on": ("hard", {("uav", "a_max_mps2"): A_ON}, None),
    "rte_base": ("rl_static", {("uav", "a_max_mps2"): A_ON, ("mobility", "episode_steps"): 600}, 10.0),
}
_B = SETTINGS["rte_base"][1]
SETTINGS.update({
    "rte_r100": ("rl_static", {**_B, ("baselines", "loiter_radius_m"): 100}, 10.0),
    "rte_d0_0.3": ("rl_static", {**_B, ("energy", "d0"): 0.3}, 10.0),
    "rte_Pi_x1.2": ("rl_static", {**_B, ("energy", "Pi_w"): None}, 10.0),        # None = scale, see apply()
    "rte_Pi_x0.8": ("rl_static", {**_B, ("energy", "Pi_w"): None}, 10.0),
    "rte_a2": ("rl_static", {**_B, ("uav", "a_max_mps2"): 2.0}, 10.0),
    "rte_a8": ("rl_static", {**_B, ("uav", "a_max_mps2"): 8.0}, 10.0),
})
EXPS = {
    "a": [(s, p, seed) for s in ("hard_off", "hard_on") for p in ("B6", "B3") for seed in SEEDS_HARD],
    "c": [("hard_on", "B7", seed) for seed in SEEDS_HARD],
    "b": [(s, p, seed) for s, p in (("rte_base", "B6"), ("rte_base", "B7"), ("rte_r100", "B7")) for seed in SEEDS_B],
    "d": [(s, p, seed) for s in ("rte_d0_0.3", "rte_Pi_x1.2", "rte_Pi_x0.8", "rte_a2", "rte_a8")
          for p in ("B6", "B7") for seed in SEEDS_D],
}


def apply(setting):
    """Switch the in-process config to a setting (profile + overrides)."""
    profile, over, _ = SETTINGS[setting]
    md.apply_profile(profile)
    for (sec, key), val in over.items():
        if sec == "energy" and key == "Pi_w":
            val = md.BASE_CFG["energy"]["Pi_w"] * float(setting.split("_x")[1])
        md.CFG[sec][key] = val


def run_logged(setting, policy, seed, battery_wh=None):
    """One episode with a per-step log. Returns (row dict, steps dict of arrays)."""
    apply(setting)
    bat = battery_wh if battery_wh is not None else SETTINGS[setting][2]
    env = UAVEnv(battery_wh=bat)
    env.reset(seed=seed)
    pol = make_policy(policy)
    pol.reset(env)
    log = {k: [] for k in ("x", "y", "h", "speed", "vz", "accel", "energy", "coverage", "served")}
    done = False
    while not done:
        _, _, term, trunc, info = env.step(pol.act(env))
        for k, v in (("x", env.x), ("y", env.y), ("h", env.h), ("speed", np.hypot(env.vx, env.vy)), ("vz", env.vz),
                     ("accel", info["accel_mps2"]), ("energy", info["energy_step_j"]),
                     ("coverage", info["coverage"]), ("served", float(info["served"].sum()))):
            log[k].append(v)
        done = term or trunc
    steps = {k: np.asarray(v, dtype=float) for k, v in log.items()}
    used_wh = env.energy_used_j / 3600.0
    row = dict(setting=setting, policy=policy, seed=seed, mobility=env.sc["mobility"], n_users=env.sc["n_users"],
               battery_wh=env.battery_j / 3600.0, horizon=env.T, steps=len(steps["energy"]),
               survived=bool(not term), coverage_full=float(steps["coverage"].sum() / env.T),
               coverage_alive=float(steps["coverage"].mean()), served_user_s=env.served_user_s,
               energy_used_wh=used_wh, served_per_wh=env.served_user_s / used_wh,
               mean_power_w=float(steps["energy"].mean() / env.dt),
               v_loiter=float(getattr(pol, "v_loiter", np.nan)), loiter_r=float(getattr(pol, "r", np.nan)))
    return row, steps


def run(exp):
    OUT.mkdir(parents=True, exist_ok=True)
    STEPS.mkdir(exist_ok=True)
    csv = OUT / "episodes.csv"
    done = set()
    if csv.exists():
        old = pd.read_csv(csv)
        done = set(zip(old.setting, old.policy, old.seed, strict=True))
    jobs = [j for j in EXPS[exp] if j not in done]
    print(f"exp {exp}: {len(jobs)} episodes to run ({len(EXPS[exp]) - len(jobs)} already done), 1 process")
    t0 = time.time()
    for i, (s, p, seed) in enumerate(jobs, 1):
        row, steps = run_logged(s, p, seed)
        np.savez_compressed(STEPS / f"{s}__{p}__{seed}.npz", **steps)
        pd.DataFrame([row]).to_csv(csv, mode="a", header=not csv.exists(), index=False)
        if i % 10 == 0 or i == len(jobs):
            el = time.time() - t0
            print(f"  {i}/{len(jobs)}  {el / 60:.1f} min, {el / i:.1f} s/episode", flush=True)


def truncate(steps, battery_wh, horizon):
    """coverage_full and survival for a smaller battery, from a run with a larger one (see module doc)."""
    cum = np.cumsum(steps["energy"])
    dead = np.flatnonzero(cum >= battery_wh * 3600.0)
    n = int(dead[0]) + 1 if len(dead) else len(cum)
    return float(steps["coverage"][:n].sum() / horizon), bool(len(dead) == 0 and n >= horizon)


def check_truncation():
    """Real env runs at 12 Wh vs truncation of the 16 Wh logs (must be identical)."""
    for p in ("B6", "B7"):
        for seed in (0, 1):
            row, _ = run_logged("hard_on", p, seed, battery_wh=12.0)
            st = dict(np.load(STEPS / f"hard_on__{p}__{seed}.npz"))
            cov, surv = truncate(st, 12.0, 300)
            print(p, seed, "real", row["coverage_full"], row["survived"], "truncated", cov, surv,
                  "EQUAL" if (cov == row["coverage_full"] and surv == row["survived"]) else "DIFFERENT")


# ---------------------------------------------------------------- report
def fmt(v, k=3):
    m, h = mean_ci(v)
    return f"{m:.{k}f} +/- {h:.{k}f}"


def paired_rows(pairs):
    """pairs: list of (label, a, b). Returns markdown rows with mean diff, CI, p, Holm-adjusted p."""
    ps = [paired_p(a, b) for _, a, b in pairs]
    adj = holm(ps) if ps else []
    out = []
    for (label, a, b), p, q in zip(pairs, ps, adj, strict=True):
        m, h = paired_diff(a, b)
        rel = m / np.mean(b) if np.mean(b) != 0 else np.nan
        out.append(f"| {label} | {m:+.4g} +/- {h:.3g} | {rel:+.1%} | {p:.2g} | {q:.2g}{' *' if q < 0.05 else ''} |")
    return out


PAIR_HEAD = ["| comparison (a - b) | mean diff +/- 95% CI | relative to b | p | Holm p |", "|---|---|---|---|---|"]


def loiter_power(setting, r):
    """(v*, P(v*)/P(0), v_loiter, P_loiter step, hover step) under a setting (20 dBm comm power, profile rl_static)."""
    apply(setting)
    u, e = md.CFG["uav"], md.CFG["energy"]
    vs = md.min_power_speed(u["v_max_mps"])
    a = u["a_max_mps2"]
    vl = md.min_power_speed(u["v_max_mps"], r, a)
    comm = 10 ** ((u["p_max_dbm"] - 30) / 10) / e["pa_efficiency"] + e["P_circuit_w"]
    p_loiter = md.propulsion_power_w(vl, md.load_factor(vl * vl / r)) + comm
    p_hover = md.propulsion_power_w(0.0) + comm
    return vs, md.propulsion_power_w(vs) / md.propulsion_power_w(0.0), vl, p_loiter, p_hover


def report():
    df = pd.read_csv(OUT / "episodes.csv")
    L = []

    def piv(setting, pol, col):
        d = df[(df.setting == setting) & (df.policy == pol)].set_index("seed")[col]
        return d.sort_index()

    # ---- a
    if {"hard_off", "hard_on"} <= set(df.setting):
        L += ["## (a) Does the acceleration limit change the G3 numbers? Profile hard, 100 scenarios, 16 Wh, 300 s", "",
              "| policy | limit | coverage_full | survived | served-user-s per Wh | mean power W |",
              "|---|---|---|---|---|---|"]
        for p in ("B3", "B6"):
            for s, lab in (("hard_off", "off"), ("hard_on", "on (a_max 4)")):
                d = df[(df.setting == s) & (df.policy == p)]
                if len(d):
                    L.append(f"| {p} | {lab} | {fmt(d.coverage_full)} | {d.survived.mean():.0%} | "
                             f"{fmt(d.served_per_wh, 1)} | {fmt(d.mean_power_w, 1)} |")
        pairs = [(f"{p} on - off", piv("hard_on", p, "coverage_full"), piv("hard_off", p, "coverage_full"))
                 for p in ("B3", "B6")
                 if len(piv("hard_on", p, "coverage_full")) == len(piv("hard_off", p, "coverage_full")) > 0]
        L += ["", "Paired, coverage_full:", "", *PAIR_HEAD, *paired_rows(pairs), ""]

    # ---- c
    on = df[df.setting == "hard_on"]
    if (on.policy == "B7").sum() == (on.policy == "B6").sum() == len(SEEDS_HARD):           # exp c complete
        L += ["## (c) Fixed 300 s game on hard, 100 scenarios, limit on: B6 (hover) vs B7 (loiter r 50)", "",
              "Smaller batteries by exact truncation of the 16 Wh logs (see module doc; verified by check-truncation).",
              "", "| battery Wh | B6 coverage_full | B6 survived | B7 coverage_full | B7 survived |",
              "|---|---|---|---|---|"]
        res = {}
        for bat in (12.0, 13.0, 14.0, 16.0):
            for p in ("B6", "B7"):
                seeds = sorted(df[(df.setting == "hard_on") & (df.policy == p)].seed)
                vals = [truncate(dict(np.load(STEPS / f"hard_on__{p}__{s}.npz")), bat, 300) for s in seeds]
                res[(bat, p)] = pd.Series([v[0] for v in vals], index=seeds), np.mean([v[1] for v in vals])
            L.append(f"| {bat:g} | {fmt(res[(bat, 'B6')][0])} | {res[(bat, 'B6')][1]:.0%} | "
                     f"{fmt(res[(bat, 'B7')][0])} | {res[(bat, 'B7')][1]:.0%} |")
        pairs = [(f"B7 - B6 at {bat:g} Wh", res[(bat, "B7")][0], res[(bat, "B6")][0])
                 for bat in (12.0, 13.0, 14.0, 16.0)]
        L += ["", "Paired, coverage_full (Holm over the 4 batteries):", "", *PAIR_HEAD, *paired_rows(pairs), ""]

    # ---- b
    if "rte_base" in set(df.setting):
        L += ["## (b) MAIN: run-to-empty, profile rl_static (still crowds), 10 Wh, horizon 600 s, a_max 4, "
              f"{len(SEEDS_B)} scenarios (val 100-119 + train 0-29)", "",
              "| pilot | served user-s | user-s per Wh | flight time s | coverage while alive | mean power W |",
              "|---|---|---|---|---|---|"]
        groups = [("B6 hover", "rte_base", "B6"), ("B7 r 50", "rte_base", "B7"), ("B7 r 100", "rte_r100", "B7")]
        for lab, s, p in groups:
            d = df[(df.setting == s) & (df.policy == p)]
            if len(d):
                L.append(f"| {lab} | {fmt(d.served_user_s, 0)} | {fmt(d.served_per_wh, 0)} | {fmt(d.steps, 1)} | "
                         f"{fmt(d.coverage_alive)} | {fmt(d.mean_power_w, 1)} |")
        b6 = piv("rte_base", "B6", "served_user_s")
        pairs, tpairs = [], []
        for lab, s, p in groups[1:]:
            a = piv(s, p, "served_user_s")
            if len(a) == len(b6) > 0:
                pairs.append((f"{lab} - B6, served user-s", a, b6))
                tpairs.append((f"{lab} - B6, flight time s", piv(s, p, "steps"), piv("rte_base", "B6", "steps")))
                tpairs.append((f"{lab} - B6, coverage while alive", piv(s, p, "coverage_alive"),
                               piv("rte_base", "B6", "coverage_alive")))
        if len(pairs) == 2:
            pairs.append(("B7 r 50 - B7 r 100, served user-s", piv("rte_base", "B7", "served_user_s"),
                          piv("rte_r100", "B7", "served_user_s")))
        L += ["", "Paired (Holm over the user-seconds rows; the flight-time and coverage rows are Holm-adjusted "
                  "separately):", "", *PAIR_HEAD, *paired_rows(pairs), *paired_rows(tpairs), ""]
        L += ["Arithmetic prediction: US_B7 / US_B6 ~ (cov_B7 / cov_B6) x (T_B7 / T_B6), with T ~ E_bat / P "
              "(transit and climb ignored), so T_B7 / T_B6 ~ P_hover_step / P_loiter_step.", "",
              "| pilot | P_loiter step W (analytic) | P_hover step W | predicted T ratio | measured T ratio "
              "(mean of per-scenario) | predicted US ratio (x measured cov ratio) | measured US ratio |",
              "|---|---|---|---|---|---|---|"]
        for lab, s, p in groups[1:]:
            d, d6 = piv(s, p, "steps"), piv("rte_base", "B6", "steps")
            if len(d) != len(d6) or len(d) == 0:
                continue
            r = SETTINGS[s][1].get(("baselines", "loiter_radius_m"), md.BASE_CFG["baselines"]["loiter_radius_m"])
            _, _, vl, pl, ph = loiter_power(s, r)
            cov_ratio = (piv(s, p, "coverage_alive") / piv("rte_base", "B6", "coverage_alive")).mean()
            us_ratio = (piv(s, p, "served_user_s") / b6).mean()
            L.append(f"| {lab} (v {vl:.2f} m/s) | {pl:.2f} | {ph:.2f} | {ph / pl:.3f} | {(d / d6).mean():.3f} | "
                     f"{ph / pl * cov_ratio:.3f} | {us_ratio:.3f} |")
        L.append("")

    # ---- d
    if any(s.startswith("rte_") and s not in ("rte_base", "rte_r100") for s in df.setting):
        L += [f"## (d) Sensitivity, run-to-empty on rl_static, first {len(SEEDS_D)} scenarios of (b) "
              "(one change at a time from the base: a_max 4, r 50, d0 0.6, Pi 88.63 W)", "",
              "| setting | v* m/s | P(v*)/P(0) | v_loiter m/s | P_loiter/P_hover (with comm+circuit) | "
              "B7 - B6 served user-s (mean +/- CI) | relative | p | Holm p |", "|---|---|---|---|---|---|---|---|---|"]
        rows = []
        for s, b7s in (("rte_base", "rte_base"), ("rte_r100", "rte_r100"), ("rte_d0_0.3", "rte_d0_0.3"),
                       ("rte_Pi_x1.2", "rte_Pi_x1.2"), ("rte_Pi_x0.8", "rte_Pi_x0.8"), ("rte_a2", "rte_a2"),
                       ("rte_a8", "rte_a8")):
            b6s = "rte_base" if s == "rte_r100" else s
            a, b = piv(b7s, "B7", "served_user_s"), piv(b6s, "B6", "served_user_s")
            a, b = a[a.index.isin(SEEDS_D)], b[b.index.isin(SEEDS_D)]
            if len(a) != len(SEEDS_D) or len(b) != len(SEEDS_D):
                continue
            r = SETTINGS[s][1].get(("baselines", "loiter_radius_m"), md.BASE_CFG["baselines"]["loiter_radius_m"])
            vs, ratio, vl, pl, ph = loiter_power(s, r)
            rows.append((s, vs, ratio, vl, pl / ph, a, b))
        ps = holm([paired_p(a, b) for *_, a, b in rows]) if rows else []
        for (s, vs, ratio, vl, pr, a, b), q in zip(rows, ps, strict=True):
            m, h = paired_diff(a, b)
            L.append(f"| {s} | {vs:.2f} | {ratio:.3f} | {vl:.2f} | {pr:.3f} | {m:+.0f} +/- {h:.0f} | "
                     f"{m / b.mean():+.1%} | {paired_p(a, b):.2g} | {q:.2g}{' *' if q < 0.05 else ''} |")
        L.append("")
    md.apply_profile("default")
    text = "\n".join(L)
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report", "check-truncation"])
    ap.add_argument("exp", nargs="?", choices=list(EXPS))
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.exp)
    elif a.cmd == "report":
        report()
    else:
        check_truncation()


if __name__ == "__main__":
    sys.exit(main())
