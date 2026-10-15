"""Pipeline and config sanity tests. Run: python -m pytest test_pipeline.py"""
import numpy as np
import pandas as pd
import pytest

import make_dataset as md

CFG = md.CFG


def _small_scenario(seed=3):
    sc = {**md.make_scenario(seed), "n_users": 100, "bandwidth_hz": 100 * CFG["bandwidth_per_user_hz"]}
    return sc, md.make_users(seed, sc), md.obstacle_array(md.make_obstacles(seed, sc))


# ---------------------------------------------------------------- splits and config
def test_splits_have_the_documented_sizes_and_never_overlap():
    tr, va, te = (set(md.seeds(s)) for s in ("train", "val", "test"))
    assert (len(tr), len(va), len(te)) == (100, 20, 20)
    assert not (tr & va) and not (tr & te) and not (va & te)


def test_config_is_self_consistent():
    assert all(n % 2 == 0 for n in CFG["n_users_choices"])
    assert sum(c["share"] for c in CFG["classes"].values()) == pytest.approx(1.0)
    assert all(c["min_rate_bps"] > 0 for c in CFG["classes"].values())
    assert CFG["noma_alpha_weak"] > 0.5                                  # the weak user must get the larger share
    assert CFG["uav"]["h_min_m"] < CFG["uav"]["h_max_m"]
    assert CFG["uav"]["start_h_m"] >= CFG["uav"]["h_min_m"] and CFG["uav"]["start_h_m"] <= CFG["uav"]["h_max_m"]
    assert CFG["energy"]["battery_wh"] > 0 and CFG["mobility"]["episode_steps"] > 0
    assert CFG["mobility"]["episode_steps"] % CFG["mobility"]["store_every_steps"] == 0
    assert set(CFG["mobility"]["choices"]) <= {"random_waypoint", "group_drift", "attraction", "hotspot_jump", "surge"}


# ---------------------------------------------------------------- users and scenarios
def test_users_are_inside_the_area_with_valid_classes():
    sc, u, _ = _small_scenario()
    assert u.x.between(0, CFG["area_m"]).all() and u.y.between(0, CFG["area_m"]).all()
    assert set(u["class"]) <= set(CFG["classes"])
    assert (u.min_rate_bps == u["class"].map(lambda c: CFG["classes"][c]["min_rate_bps"])).all()
    assert u.user_id.is_unique and u.cluster_id.between(-1, sc["n_clusters"] - 1).all()


def test_all_scenario_fields_stay_in_their_configured_ranges():
    for s in range(60):
        sc = md.make_scenario(s)
        assert sc["n_users"] in CFG["n_users_choices"]
        assert CFG["n_clusters_range"][0] <= sc["n_clusters"] <= CFG["n_clusters_range"][1]
        assert CFG["cluster_radius_range_m"][0] <= sc["cluster_radius_m"] <= CFG["cluster_radius_range_m"][1]
        assert CFG["scatter_fraction_range"][0] <= sc["scatter_fraction"] <= CFG["scatter_fraction_range"][1]
        assert sc["mobility"] in CFG["mobility"]["choices"]


# ---------------------------------------------------------------- the sweep
def test_sweep_has_the_expected_shape_and_valid_values():
    sc, u, boxes = _small_scenario()
    rows = md.sweep_one(u, sc, boxes)
    n_xy = len(np.arange(0, CFG["area_m"] + 1, CFG["sweep"]["xy_step_m"])) ** 2
    assert len(rows) == n_xy * len(CFG["sweep"]["altitudes_m"]) * len(CFG["tx_power_dbm_levels"])
    df = pd.DataFrame(rows, columns=md.COLS)
    assert df.notna().all().all()
    for col in ("coverage", "coverage_oma", "fairness", "outage_rescue"):
        assert df[col].between(0, 1).all(), col
    assert (df.sum_rate_mbps > 0).all() and (df.sum_rate_oma_mbps > 0).all()
    assert (df.seed == sc["seed"]).all() and set(df.p_dbm) == set(CFG["tx_power_dbm_levels"])


def test_sweep_is_reproducible_and_more_power_never_lowers_total_rate():
    sc, u, boxes = _small_scenario()
    a = pd.DataFrame(md.sweep_one(u, sc, boxes), columns=md.COLS)
    b = pd.DataFrame(md.sweep_one(u, sc, boxes), columns=md.COLS)
    assert a.equals(b)
    by_power = a.groupby("p_dbm").sum_rate_mbps.mean()
    assert by_power.is_monotonic_increasing


def test_sweep_energy_grows_with_transmit_power():
    sc, u, boxes = _small_scenario()
    df = pd.DataFrame(md.sweep_one(u, sc, boxes), columns=md.COLS)
    e = df.groupby("p_dbm").energy_j_per_step.first()
    assert e.is_monotonic_increasing and e.iloc[0] > CFG["energy"]["P0_w"] + CFG["energy"]["Pi_w"]


def test_noma_beats_oma_on_total_rate_at_high_power():
    sc, u, boxes = _small_scenario()
    df = pd.DataFrame(md.sweep_one(u, sc, boxes), columns=md.COLS)
    hi = df[df.p_dbm == max(CFG["tx_power_dbm_levels"])]
    assert hi.sum_rate_mbps.mean() > hi.sum_rate_oma_mbps.mean()


def test_jain_fairness_edge_cases():
    assert md.jain(np.ones(10)) == pytest.approx(1.0)
    assert md.jain(np.array([1.0, 0, 0, 0])) == pytest.approx(0.25)
    assert md.jain(np.zeros(5)) == 0.0
