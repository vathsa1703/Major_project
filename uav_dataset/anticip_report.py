"""Evaluation of the pre-registered anticipation rule (docs/prereg/anticipation_rule.md): measured headroom on the 8
new cells vs the FROZEN predictions in results/anticipation/fit.json, the pre-registered criteria, the 17-cell table,
the gap decomposition on the G5 cells and the figure. Called by `python anticip_exp.py evaluate`."""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

import anticip_exp as ax
from evalstats import paired_diff

FIG = "anticipation_rule.png"
PREREG = Path(__file__).parent.parent / "docs" / "prereg"
R2_MIN, CALL_MIN = 0.7, 0.8                                   # pre-registered pass criteria


def new_table():
    df = pd.read_csv(ax.OUT / "newcells_episodes.csv", float_precision="round_trip")
    ann = ax.headroom_table(df, ax.NEW_CELLS, ax.BAR_ANN_NEW)
    una = ax.headroom_table(df, ax.NEW_CELLS, ax.BAR_UNANN_NEW).set_index("cell")
    ann["h_unann"] = una.loc[ann.cell, "h"].values
    surv = {p: df[f"{p}_survived"].mean() for p in (*ax.NEW_PILOTS, "dp")}
    return df, ann, surv


def decomp_table(g5_dirs):
    """Per G5 cell (val seeds 100-119): dp -> best simple pilot (bar: best by cell mean of B6, B7, B8, B6fc from the
    G5 evaluation, plus B6dep) -> B3 (full information, the agent's control set: fixed 150 m altitude, no forecast) ->
    B3obsUN (B3's search with only the agent's information) -> best G5 agent (by cell mean)."""
    p = ax.OUT / "decomp_episodes.csv"
    if not p.exists():
        return []
    d = pd.read_csv(p, float_precision="round_trip")
    L = ["| cell | n | dp | bar (pilot) | B3 | B3obsUN | best agent | foresight dp - bar | tools bar - B3 | information "
         "B3 - B3obsUN | learning B3obsUN - agent | total dp - agent | B6 check |", "|" + "---|" * 13]
    for cell, g5 in g5_dirs.items():
        x = d[d.cell == cell].sort_values("seed").set_index("seed")
        e = pd.read_csv(Path(g5) / "episodes.csv", float_precision="round_trip")
        e = e[e.access == "noma_opt"] if "access" in e else e
        piv = e.pivot_table(index="seed", columns="policy", values="coverage_full").loc[x.index]
        agents = [c for c in piv.columns if c.startswith("g5")]
        best_agent = max(agents, key=lambda a: piv[a].mean())
        cols = {b: piv[b] for b in ("B6", "B7", "B8", "B6fc")}
        cols["B6dep"] = x.B6dep
        bar = max(cols, key=lambda b: cols[b].mean())
        chk = float(np.max(np.abs(piv.B6 - x.B6)))
        parts = [(x.dp, cols[bar]), (cols[bar], x.B3), (x.B3, x.B3obsUN), (x.B3obsUN, piv[best_agent]),
                 (x.dp, piv[best_agent])]
        txt = [f"{m:+.3f} +/- {h:.3f}" for m, h in (paired_diff(a, b) for a, b in parts)]
        L.append(f"| {cell} | {len(x)} | {x.dp.mean():.3f} | {cols[bar].mean():.3f} ({bar}) | {x.B3.mean():.3f} | "
                 f"{x.B3obsUN.mean():.3f} | {piv[best_agent].mean():.3f} ({best_agent.replace('g5r1_', '')}) | "
                 + " | ".join(txt) + f" | {chk:.1e} |")
    return L


def figure(fit_cells, new, model, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    blue, orange, ink, muted = "#2a78d6", "#eb6834", "#0b0b0b", "#8a8984"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": muted, "axes.labelcolor": ink, "xtick.color": ink,
                         "ytick.color": ink, "axes.spines.top": False, "axes.spines.right": False})
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    # (a) h vs A, marker size ~ M
    for t, col, lab in ((fit_cells, blue, "fit cells (9, seeds 1000-1019)"), (new, orange, "new cells (8, seeds 2000-2011)")):
        axs[0].scatter(np.maximum(t.A, 1e-3), t.h, s=20 + 400 * t.M, color=col, edgecolor="white", linewidth=1.5,
                       label=lab, zorder=3)
    axs[0].set_xscale("log")
    axs[0].set_xlabel("A = (T_tr + 10 s) / (tau + 10 s)   (marker size ~ M)")
    axs[0].set_ylabel("headroom h = dp - best simple pilot")
    axs[0].set_title("(a) headroom vs A", loc="left", color=ink)
    # (b) h vs M
    for t, col in ((fit_cells, blue), (new, orange)):
        axs[1].scatter(t.M, t.h, s=40, color=col, edgecolor="white", linewidth=1.5, zorder=3)
    axs[1].set_xlabel("M = T_tr / T_episode")
    axs[1].set_title("(b) headroom vs M", loc="left", color=ink)
    # (c) predicted (fitted for the fit cells, frozen predictions for the new ones) vs measured, with 95% CIs
    lim = max(fit_cells.h.max(), new.h.max(), fit_cells.h_fit.max(), new.h_pred.max()) * 1.1
    lo = min(0.0, fit_cells.h.min(), new.h.min()) - 0.005
    axs[2].plot([lo, lim], [lo, lim], color=muted, linewidth=2, zorder=1, label="prediction = measurement")
    axs[2].errorbar(fit_cells.h_fit, fit_cells.h, yerr=fit_cells.h_ci, fmt="o", color=blue, ms=6, mec="white",
                    elinewidth=1, capsize=0, zorder=3)
    axs[2].errorbar(new.h_pred, new.h, yerr=new.h_ci, fmt="o", color=orange, ms=6, mec="white", elinewidth=1,
                    capsize=0, zorder=3)
    for hp, hm, c in zip(new.h_pred, new.h, new.cell, strict=True):
        axs[2].annotate(c.replace("sites_", ""), (hp, hm), textcoords="offset points", xytext=(4, 3), fontsize=7,
                        color=muted)
    axs[2].axvline(ax.PASS_MARK, color=muted, linewidth=1, linestyle="--", zorder=0)
    axs[2].set_xlabel(f"predicted h (model '{model}'; fit cells: fitted)")
    axs[2].set_title("(c) predicted vs measured", loc="left", color=ink)
    axs[2].legend(frameon=False, loc="upper left")
    for a in axs:
        a.axhline(ax.PASS_MARK, color=muted, linewidth=1, linestyle="--", zorder=0)
        a.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    axs[0].legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def evaluate(confirm_csv, g5_dirs=None):
    fit = json.loads((ax.OUT / "fit.json").read_text(encoding="utf-8"))
    model = fit["model"]
    fit_cells = pd.DataFrame(fit["fit_cells"])
    pred = pd.DataFrame(fit["predictions"]).set_index("cell")
    df, ann, surv = new_table()
    new = ann.set_index("cell").join(pred[["D_m", "tau_s", "v_max", "T_s", "rho_m", "T_tr_s", "A", "M", "h_pred",
                                           "call"]]).reset_index()
    r2 = ax.r2(new.h_pred, new.h)
    right = (new.h_pred >= ax.PASS_MARK) == (new.h >= ax.PASS_MARK)
    ok_r2, ok_call = r2 >= R2_MIN, right.mean() >= CALL_MIN
    corr = float(np.corrcoef(new.h_pred, new.h)[0, 1])
    L = ["# Anticipation rule: pre-registered test on 8 new cells", "",
         f"Frozen fit (9 cells): model {model}, params {fit['params']}, fit R^2 = {fit['r2_fit']:.3f}. "
         "Predictions from fit.json, unchanged.", "",
         "## Verdict", "",
         f"- R^2 (1 - SS_res/SS_tot, predicted vs measured h, 8 new cells) = **{r2:.3f}** (pass >= {R2_MIN}): "
         f"**{'PASS' if ok_r2 else 'FAIL'}**  (Pearson r = {corr:.3f}, r^2 = {corr ** 2:.3f}, for information)",
         f"- correct room / no-room call at h >= {ax.PASS_MARK}: **{int(right.sum())}/8 = {right.mean():.0%}** (pass >= "
         f"{CALL_MIN:.0%}): **{'PASS' if ok_call else 'FAIL'}**",
         f"- overall: **{'RULE CONFIRMED' if ok_r2 and ok_call else 'RULE NOT CONFIRMED'}**", "",
         "## All 17 cells", "",
         "Announced bar: fit cells best of B6, B7, B8, B6fc_u, B6fc_a, B6dep; new cells best of B6, B6fc_u, B6fc_a, "
         "B6dep (by cell mean). h = paired mean dp - bar (95% CI). Unannounced bar: without B6fc_a and B6dep.", "",
         "| cell | set | D m | tau s | v_max | T s | rho m | T_tr s | A | M | bar pilot | bar | dp | h ann. (95% CI) | "
         "h unann. | predicted / fitted h | call right |", "|" + "---|" * 17]
    for r in fit_cells.itertuples():
        L.append(f"| {r.cell} | fit | {r.D_m:.0f} | {r.tau_s:.0f} | {r.v_max:.0f} | {r.T_s:.0f} | {r.rho_m:.0f} | "
                 f"{r.T_tr_s:.1f} | {r.A:.3f} | {r.M:.4f} | {r.bar_pilot} | {r.bar:.3f} | {r.dp:.3f} | "
                 f"{r.h:+.4f} +/- {r.h_ci:.4f} | {r.h_unann:+.4f} | {r.h_fit:.4f} (fit) | - |")
    for r, ok in zip(new.itertuples(), right, strict=True):
        L.append(f"| {r.cell} | NEW | {r.D_m:.0f} | {r.tau_s:.0f} | {r.v_max:.0f} | {r.T_s:.0f} | {r.rho_m:.0f} | "
                 f"{r.T_tr_s:.1f} | {r.A:.3f} | {r.M:.4f} | {r.bar_pilot} | {r.bar:.3f} | {r.dp:.3f} | "
                 f"{r.h:+.4f} +/- {r.h_ci:.4f} | {r.h_unann:+.4f} | {r.h_pred:.4f} | {'yes' if ok else 'NO'} |")
    L += ["", "### New cells: pilot means", "", "| cell | n | B6 | B6fc_u | B6fc_a | B6dep | dp | teleport | secs/scenario |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in ax.NEW_CELLS:
        d = df[df.cell == c]
        L.append(f"| {c} | {len(d)} | " + " | ".join(f"{d[p].mean():.3f}" for p in (*ax.NEW_PILOTS, "dp", "teleport"))
                 + f" | {d.secs_total.mean():.0f} |")
    L += ["", "Survival (share of new-cell scenarios lasting the episode): "
          + ", ".join(f"{p} {v:.0%}" for p, v in surv.items()) + ".", ""]
    dec = decomp_table(g5_dirs or {})
    if dec:
        L += ["## Gap decomposition on the G5 cells (val seeds 100-119, announced)", "",
              "Chain dp -> best simple pilot -> B3 (full information, the goto agent's controls: 150 m, no forecast) "
              "-> B3obsUN (same search, only the agent's information) -> best G5 round-1 agent. Paired means +/- 95% "
              "CI; the four parts add up to the total.", ""] + dec + [""]
    L += [f"![figure]({FIG})", ""]
    text = "\n".join(L)
    (ax.OUT / "summary.md").write_text(text, encoding="utf-8")
    figure(fit_cells, new, model, ax.OUT / FIG)
    PREREG.mkdir(parents=True, exist_ok=True)
    shutil.copy(ax.OUT / FIG, PREREG / FIG)
    print(text)
