"""Tests for obstacles, fading and the energy model. Run: python -m pytest test_phase45.py"""
import numpy as np
import pytest

import make_dataset as md

E = md.CFG["energy"]


# ---------------------------------------------------------------- obstacles
def test_link_blocked_basic_geometry():
    box = np.array([[400.0, 400.0, 600.0, 600.0]])
    X, Y = np.array([0.0]), np.array([500.0])
    ux, uy = np.array([1000.0, 1000.0, 500.0, 300.0]), np.array([500.0, 900.0, 500.0, 500.0])
    got = md.link_blocked(ux, uy, X, Y, box)[0]
    # through the box / passes above it / ends inside the box / stops short of the box
    assert got.tolist() == [True, False, True, False]


def test_vertical_segments_are_handled():
    box = np.array([[400.0, 400.0, 600.0, 600.0]])
    top = np.array([1000.0]), np.array([1000.0])
    thru = md.link_blocked(np.array([500.0]), top[1], np.array([500.0]), np.array([0.0]), box)[0, 0]
    beside = md.link_blocked(np.array([700.0]), top[1], np.array([700.0]), np.array([0.0]), box)[0, 0]
    assert thru and not beside               # straight up through the box / straight up beside it


def test_blocked_link_loses_exactly_the_excess():
    ux, uy = np.array([1000.0]), np.array([500.0])
    X, Y, H = np.array([0.0]), np.array([500.0]), np.array([100.0])
    box = np.array([[400.0, 400.0, 600.0, 600.0]])
    free = md.channel_gain(ux, uy, X, Y, H)[0, 0]
    blocked = md.channel_gain(ux, uy, X, Y, H, box)[0, 0]
    assert blocked == pytest.approx(free * 10 ** (-md.CFG["obstacles"]["excess_loss_db"] / 10))


def test_obstacles_are_reproducible_and_inside_area():
    sc = {**md.make_scenario(5), "n_obstacles": 4}
    a, b = md.make_obstacles(5, sc), md.make_obstacles(5, sc)
    assert a.equals(b) and len(a) == 4
    L = md.CFG["area_m"]
    assert (a[["x_min", "y_min"]].values >= 0).all() and (a[["x_max", "y_max"]].values <= L).all()
    assert (a.x_max >= a.x_min).all() and (a.y_max >= a.y_min).all()


def test_obstacles_lower_coverage_on_average():
    ux, uy = np.random.default_rng(0).uniform(0, 1000, (2, 300))
    X = Y = np.array([500.0]); H = np.array([150.0])
    boxes = np.array([[300.0, 300.0, 700.0, 700.0]])
    assert md.channel_gain(ux, uy, X, Y, H, boxes).mean() < md.channel_gain(ux, uy, X, Y, H).mean()


# ---------------------------------------------------------------- fading
def test_fading_off_gives_the_average_channel(monkeypatch):
    ux, uy = np.array([300.0, 700.0]), np.array([300.0, 700.0])
    X, Y, H = np.array([500.0]), np.array([500.0]), np.array([150.0])
    base = md.channel_gain(ux, uy, X, Y, H)
    monkeypatch.setitem(md.CFG["fading"], "enabled", False)
    assert np.allclose(md.channel_gain(ux, uy, X, Y, H, rng=np.random.default_rng(0)), base)


def test_fading_on_is_random_but_reproducible(monkeypatch):
    monkeypatch.setitem(md.CFG["fading"], "enabled", True)
    ux, uy = np.random.default_rng(1).uniform(0, 1000, (2, 50))
    X, Y, H = np.array([500.0]), np.array([500.0]), np.array([150.0])
    a = md.channel_gain(ux, uy, X, Y, H, rng=np.random.default_rng(3))
    b = md.channel_gain(ux, uy, X, Y, H, rng=np.random.default_rng(3))
    c = md.channel_gain(ux, uy, X, Y, H, rng=np.random.default_rng(4))
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_fading_has_unit_mean_power(monkeypatch):
    # LoS-only geometry (user right below the drone): mean gain over many draws ~ the no-fading LoS gain
    monkeypatch.setitem(md.CFG["fading"], "enabled", True)
    n = 20000
    ux, uy = np.full(n, 500.0), np.full(n, 500.0)
    X, Y, H = np.array([500.0]), np.array([500.0]), np.array([300.0])
    g = md.channel_gain(ux, uy, X, Y, H, rng=np.random.default_rng(0))[0]
    d = 300.0
    fspl = 20 * np.log10(4 * np.pi * md.CFG["fc_hz"] * d / md.C)
    p_los = 1 / (1 + md.CFG["a2g"]["a"] * np.exp(-md.CFG["a2g"]["b"] * (90 - md.CFG["a2g"]["a"])))
    expect = p_los * 10 ** (-(fspl + md.CFG["a2g"]["eta_los_db"]) / 10) + (1 - p_los) * 10 ** (-(fspl + md.CFG["a2g"]["eta_nlos_db"]) / 10)
    assert g.mean() == pytest.approx(expect, rel=0.1)


# ---------------------------------------------------------------- energy
def test_hover_power_is_p0_plus_pi():
    assert md.propulsion_power_w(0.0) == pytest.approx(E["P0_w"] + E["Pi_w"])
    assert md.propulsion_power_w(0.0) == pytest.approx(168.49, abs=0.01)


def test_power_curve_has_a_minimum_below_hover_then_rises():
    v = np.linspace(0, 30, 301)
    p = md.propulsion_power_w(v)
    assert p.min() < p[0]                    # flying forward is cheaper than hovering at moderate speed
    assert p[-1] > p.min()
    assert (p > 0).all()


def test_energy_step_adds_comm_climb_and_circuit():
    base = md.energy_step_j(0.0, 0.0, 0.0)
    assert base == pytest.approx((E["P0_w"] + E["Pi_w"] + E["P_circuit_w"]) * E["dt_s"])
    assert md.energy_step_j(0.0, 0.0, 1.0) > base                       # transmitting costs energy
    assert md.energy_step_j(0.0, 3.0, 0.0) > base                       # climbing costs energy
    assert md.energy_step_j(0.0, -3.0, 0.0) == pytest.approx(base)      # descending gives nothing back (assumption)


def test_flying_dominates_the_battery():
    p_comm = md.CFG["uav"]["p_max_dbm"]
    comm = 10 ** ((p_comm - 30) / 10) / E["pa_efficiency"]
    assert comm < 0.05 * md.propulsion_power_w(0.0)


def test_scenarios_carry_obstacle_counts():
    lo, hi = md.CFG["obstacles"]["n_range"]
    assert all(lo <= md.make_scenario(s)["n_obstacles"] <= hi for s in range(40))
