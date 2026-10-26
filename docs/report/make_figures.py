"""Charts for the report and the guide brief, drawn from numbers copied from the project book (no new runs).

    python docs/report/make_figures.py       # writes docs/report/figures/*.png

- circling_vs_hovering.png: book 7.10 (B6 hovers vs B7 circles; 5-minute missions at 12/13/14/16 Wh on `hard`, and the
  run-to-empty test on still crowds at 10 Wh).
- room_fresh_seeds.png: book 7.13 (room for an anticipating pilot on 20 fresh scenarios per design; two bars).
The 3D-flight screenshot (fig_3d_flight.png) is made separately from the dashboard's 3D page (see report Figure 5.14).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

OUT = Path(__file__).parent / "figures"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d9d8d4"
HOVER, CIRCLE = "#2a78d6", "#eb6834"         # categorical slots 1 and 2 of the reference palette

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.facecolor": "white"})


def circling():
    wh = ["12 Wh", "13 Wh", "14 Wh", "16 Wh"]
    b6 = [0.596, 0.652, 0.707, 0.739]                    # book 7.10, hard, 100 scenarios
    b7 = [0.716, 0.730, 0.731, 0.731]
    fig, (a, b) = plt.subplots(1, 2, figsize=(8.2, 3.2), gridspec_kw={"width_ratios": [2.2, 1]})
    x, w = np.arange(len(wh)), 0.36
    a.bar(x - w / 2 - 0.01, b6, w, color=HOVER, label="B6 hovers")
    a.bar(x + w / 2 + 0.01, b7, w, color=CIRCLE, label="B7 circles (50 m)")
    for xi, v in zip(x, b6, strict=True):
        a.text(xi - w / 2, v + 0.01, f"{v:.3f}", ha="center", fontsize=7.5, color=INK)
    for xi, v in zip(x, b7, strict=True):
        a.text(xi + w / 2, v + 0.01, f"{v:.3f}", ha="center", fontsize=7.5, color=INK)
    a.set_xticks(x, wh)
    a.set_ylim(0.5, 0.8)
    a.set_ylabel("coverage over the 5-minute mission")
    a.set_title("5-minute mission, hard profile (100 scenarios)", fontsize=9, color=INK, loc="left")
    a.grid(axis="y", color=GRID, lw=0.6)
    a.set_axisbelow(True)
    a.legend(frameon=False, fontsize=8, loc="upper left")
    a.set_xlabel("battery (B6 never lasts the 5 minutes at 12-13 Wh)")
    vals = [67682, 85033]                                 # book 7.10, still crowds, 10 Wh, 50 scenarios
    b.bar([0, 1], vals, 0.6, color=[HOVER, CIRCLE])
    for xi, v in zip([0, 1], vals, strict=True):
        b.text(xi, v + 1500, f"{v:,}", ha="center", fontsize=7.5, color=INK)
    b.text(1, vals[1] * 0.5, "+25.6%", ha="center", fontsize=9, color="white", weight="bold")
    b.set_xticks([0, 1], ["B6 hovers", "B7 circles"])
    b.set_ylim(0, 100000)
    b.set_ylabel("people-seconds served per battery")
    b.set_title("Fly until empty (10 Wh)", fontsize=9, color=INK, loc="left")
    b.grid(axis="y", color=GRID, lw=0.6)
    b.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "circling_vs_hovering.png", dpi=200)
    plt.close(fig)


def room():
    rows, cols = ["1.0 km", "1.5 km", "2.0 km"], ["sudden", "over 1 min", "over 3 min"]
    plain = np.array([[0.016, 0.005, 0.004], [0.056, 0.029, 0.012], [0.091, 0.071, 0.029]])     # book 7.13
    fc = np.array([[0.013, 0.005, 0.004], [0.038, 0.029, 0.012], [0.046, 0.047, 0.029]])
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.1))
    titles = ["Bar: best of B6, B7, B8", "Bar: also the forecasting pilot B6fc (announced)"]
    for ax, data, title in zip(axes, [plain, fc], titles, strict=True):
        im = ax.imshow(data, cmap="Blues", vmin=0, vmax=0.10)
        for i in range(3):
            for j in range(3):
                v = data[i, j]
                ok = "✓" if v >= 0.02 else "✗"
                ax.text(j, i, f"{v:+.3f}\n{ok}", ha="center", va="center", fontsize=8.5,
                        color="white" if v > 0.055 else INK)
        ax.set_xticks(range(3), cols)
        ax.set_yticks(range(3), rows)
        ax.set_xlabel("how fast the demand switches")
        if ax is axes[0]:
            ax.set_ylabel("distance between sites")
        ax.set_title(title, fontsize=9, color=INK, loc="left")
        for s in ax.spines.values():
            s.set_visible(False)
    cb = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.02)
    cb.set_label("room (coverage), pass mark 0.02")
    cb.outline.set_visible(False)
    fig.suptitle("Room for a pilot that thinks ahead: 20 fresh scenarios per design", fontsize=9.5, color=INK, x=0.02,
                 ha="left")
    fig.savefig(OUT / "room_fresh_seeds.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    circling()
    room()
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
