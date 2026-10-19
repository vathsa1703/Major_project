"""Pins the parameters that were checked against the papers (see docs/assumptions.md).
Run: python -m pytest test_parameters.py"""
from pathlib import Path

import numpy as np
import pytest

import make_dataset as md

CFG = md.CFG
E = CFG["energy"]
ROOT = Path(__file__).resolve().parent.parent

# Values read in Zeng, Xu, Zhang (arXiv:1804.02238): notation table and Table I
ZENG = {"delta": 0.012, "k": 0.1, "rho": 1.225, "s": 0.05}
# Our drone (engineering choice, see docs/assumptions.md): a small ~2 kg UAV
OUR_DRONE = {"W": 20.0, "R": 0.4, "Omega": 300.0}


def _zeng_hover(W, R, Omega, A):
    """Zeng Appendix A Eq. 61 and the v0 definition."""
    z = ZENG
    P0 = z["delta"] / 8 * z["rho"] * z["s"] * A * Omega**3 * R**3
    Pi = (1 + z["k"]) * W**1.5 / np.sqrt(2 * z["rho"] * A)
    v0 = np.sqrt(W / (2 * z["rho"] * A))
    return P0, Pi, v0


def test_config_drone_follows_from_the_papers_formulas():
    P0, Pi, v0 = _zeng_hover(OUR_DRONE["W"], OUR_DRONE["R"], OUR_DRONE["Omega"], E["A_m2"])
    assert E["P0_w"] == pytest.approx(P0, rel=2e-3)
    assert E["Pi_w"] == pytest.approx(Pi, rel=2e-3)
    assert E["v0_mps"] == pytest.approx(v0, rel=2e-3)
    assert E["Utip_mps"] == pytest.approx(OUR_DRONE["Omega"] * OUR_DRONE["R"])
    assert E["A_m2"] == pytest.approx(np.pi * OUR_DRONE["R"] ** 2, rel=1e-3)
    assert E["weight_n"] == OUR_DRONE["W"]


def test_config_uses_the_papers_constants():
    assert E["rho_kg_m3"] == ZENG["rho"] and E["s"] == ZENG["s"]


def test_propulsion_power_matches_the_papers_equation():
    V = np.array([0.0, 5.0, 10.0, 20.0])
    paper = (E["P0_w"] * (1 + 3 * V**2 / E["Utip_mps"] ** 2)
             + E["Pi_w"] * np.sqrt(np.sqrt(1 + V**4 / (4 * E["v0_mps"] ** 4)) - V**2 / (2 * E["v0_mps"] ** 2))
             + 0.5 * E["d0"] * E["rho_kg_m3"] * E["s"] * E["A_m2"] * V**3)
    assert md.propulsion_power_w(V) == pytest.approx(paper)


def test_the_papers_own_drone_is_a_much_bigger_aircraft():
    # Zeng Table I: W = 100 N, R = 0.5 m, Omega = 400 rad/s. Hover is about 1.37 kW, not our 168 W.
    P0, Pi, _ = _zeng_hover(100.0, 0.5, 400.0, np.pi * 0.5**2)
    assert 1300 < P0 + Pi < 1450


def test_free_space_path_loss_reference_value():
    # 1 km at 2 GHz = 98.46 dB; a user right below a drone 1 km up is (almost) pure LoS
    d = 1000.0
    pl = 20 * np.log10(4 * np.pi * CFG["fc_hz"] * d / md.C)
    assert pl == pytest.approx(98.46, abs=0.01)
    a2g = CFG["a2g"]
    p_los = 1 / (1 + a2g["a"] * np.exp(-a2g["b"] * (90.0 - a2g["a"])))
    expect = 10 ** (-(pl + p_los * a2g["eta_los_db"] + (1 - p_los) * a2g["eta_nlos_db"]) / 10)
    got = md.channel_gain(np.array([500.0]), np.array([500.0]), np.array([500.0]), np.array([500.0]), np.array([d]))
    assert got[0, 0] == pytest.approx(expect, rel=1e-9)


def test_los_probability_rises_with_elevation_angle():
    a2g = CFG["a2g"]
    theta = np.linspace(1, 90, 90)
    p = 1 / (1 + a2g["a"] * np.exp(-a2g["b"] * (theta - a2g["a"])))
    assert (np.diff(p) > 0).all() and p[0] < 0.2 and p[-1] > 0.99


def test_assumptions_doc_covers_every_physical_parameter():
    text = (ROOT / "docs" / "assumptions.md").read_text(encoding="utf-8")
    keys = ["a2g.a", "a2g.b", "eta_los_db", "eta_nlos_db", "fc_hz", "bandwidth_per_user_hz",
            "noise_density_dbm_hz", "noise_figure_db", "tx_power_dbm_levels", "obstacles.excess_loss_db",
            "fading.rician_k_db", "noma_alpha_weak", "weight_n", "P0_w", "Pi_w", "Utip_mps", "v0_mps", "d0",
            "P_circuit_w", "pa_efficiency", "battery_wh", "v_max_mps", "h_max_m", "surge_speed_mps",
            "min_rate_bps", "lambda_energy", "terminal_penalty"]
    missing = [k for k in keys if k not in text]
    assert not missing, f"docs/assumptions.md has no entry for: {missing}"
