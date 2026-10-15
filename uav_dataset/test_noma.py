"""Sanity tests for the NOMA / channel code in make_dataset.py. Run: python -m pytest test_noma.py"""
import numpy as np
import pytest

import make_dataset as md

N0 = 10 ** ((md.CFG["noise_density_dbm_hz"] + md.CFG["noise_figure_db"] - 30) / 10)


def _gains(seed=0, h=150.0, pos=(500.0, 500.0)):
    u = md.make_users(seed)
    G = md.channel_gain(u["x"].values, u["y"].values, np.array([pos[0]]), np.array([pos[1]]), np.array([h]))
    return G[0]


def test_gain_falls_with_horizontal_distance():
    ux, uy = np.array([500.0]), np.array([500.0])
    near = md.channel_gain(ux, uy, np.array([500.0]), np.array([500.0]), np.array([100.0]))[0, 0]
    far = md.channel_gain(ux, uy, np.array([900.0]), np.array([500.0]), np.array([100.0]))[0, 0]
    assert far < near


def test_sum_rate_rises_with_power():
    g = _gains()
    rates = [md.noma_rates(g, 10 ** ((p - 30) / 10), N0)[0].sum() for p in [0, 10, 20, 30]]
    assert all(b > a for a, b in zip(rates, rates[1:]))


def test_more_power_to_weak_user_lowers_strong_rate():
    g = _gains()
    p_w = 1.0
    old = md.CFG["noma_alpha_weak"]
    try:
        strong_rates = []
        for aw in [0.6, 0.8, 0.95]:
            md.CFG["noma_alpha_weak"] = aw
            r, _ = md.noma_rates(g, p_w, N0)
            order = np.argsort(g)
            strong = order[::-1][: len(g) // 2]
            strong_rates.append(r[strong].sum())
    finally:
        md.CFG["noma_alpha_weak"] = old
    assert strong_rates[0] > strong_rates[1] > strong_rates[2]


def test_sic_check_flags_a_forced_failure():
    # strong user with LOWER gain than the weak user cannot decode the weak message -> infeasible
    assert not md.sic_feasible(0.8, 1.0, gs=1e-12, gw=1e-9, N0=N0)
    assert md.sic_feasible(0.8, 1.0, gs=1e-9, gw=1e-12, N0=N0)


def test_pairings_always_assign_roles_by_gain_so_sic_holds():
    g = _gains()
    rng = np.random.default_rng(0)
    for pairing in ["extreme", "random"]:
        weak, strong = md.pair_users(g, pairing, rng)
        assert (g[strong] >= g[weak]).all()
        assert len(set(weak) | set(strong)) == 2 * (len(g) // 2)   # every user in exactly one pair


def test_random_pairing_is_reproducible_and_differs_from_extreme():
    g = _gains()
    w1, _ = md.pair_users(g, "random", np.random.default_rng(5))
    w2, _ = md.pair_users(g, "random", np.random.default_rng(5))
    we, _ = md.pair_users(g, "extreme")
    assert (w1 == w2).all() and not (np.sort(w1) == np.sort(we)).all()


def test_scenarios_vary_and_are_reproducible():
    a, b = md.make_scenario(3), md.make_scenario(3)
    assert a == b
    assert len({md.make_scenario(s)["n_users"] for s in range(30)}) > 1
    for s in range(30):
        sc = md.make_scenario(s)
        assert sc["bandwidth_hz"] == sc["n_users"] * md.CFG["bandwidth_per_user_hz"]
        assert len(md.make_users(s, sc)) == sc["n_users"]


def test_class_mix_roughly_matches_config():
    u = md.make_users(0, {**md.make_scenario(0), "n_users": 1000})
    share = u["class"].value_counts(normalize=True)
    for c, v in md.CFG["classes"].items():
        assert abs(share[c] - v["share"]) < 0.06


def test_rates_nonnegative_and_finite():
    g = _gains()
    for arr in md.noma_rates(g, 0.1, N0):
        assert np.isfinite(arr).all() and (arr >= 0).all()
