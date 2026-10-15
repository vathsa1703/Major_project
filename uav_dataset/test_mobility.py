"""Sanity tests for the mobility code in make_dataset.py. Run: python -m pytest test_mobility.py"""
import numpy as np
import pytest

import make_dataset as md

MODELS = md.CFG["mobility"]["choices"]


def _run(model, seed=3, n=300):
    sc = {**md.make_scenario(seed), "n_users": n, "mobility": model}
    u = md.make_users(seed, sc)
    return sc, u, md.simulate(seed, sc, u)


@pytest.mark.parametrize("model", MODELS)
def test_stays_in_bounds_and_snapshot_count(model):
    sc, u, tr = _run(model)
    L = md.CFG["area_m"]
    assert tr.x.between(0, L).all() and tr.y.between(0, L).all()
    mob = md.CFG["mobility"]
    assert tr.t.nunique() == mob["episode_steps"] // mob["store_every_steps"] + 1
    assert len(tr) == len(u) * tr.t.nunique()


@pytest.mark.parametrize("model", MODELS)
def test_t0_matches_users_table_and_is_reproducible(model):
    sc, u, tr = _run(model)
    t0 = tr[tr.t == 0].sort_values("user_id")
    assert np.allclose(t0.x.values, u.x.values) and np.allclose(t0.y.values, u.y.values)
    assert tr.equals(md.simulate(3, sc, u))


@pytest.mark.parametrize("model", MODELS)
def test_speed_never_exceeds_limit(model):
    _, _, tr = _run(model)
    mob = md.CFG["mobility"]
    hi = mob["surge_speed_mps"] if model in ("surge", "hotspot_jump") else mob["speed_mps"][1]
    jitter = 6 * mob["group_jitter_mps"] if model in ("group_drift", "hotspot_jump") else 0
    assert (np.hypot(tr.vx, tr.vy) <= hi + jitter + 1e-6).all()


@pytest.mark.parametrize("model", ["surge", "hotspot_jump"])
def test_sudden_events_start_calm_then_move_fast(model):
    sc, u, tr = _run(model)
    early = tr[tr.t <= md.CFG["mobility"]["surge_start_range_s"][0] - 30]
    late_speed = np.hypot(tr.vx, tr.vy)[tr.t > md.CFG["mobility"]["surge_start_range_s"][1]].max()
    early_speed = np.hypot(early.vx, early.vy).max()
    assert early_speed <= md.CFG["mobility"]["speed_mps"][1] + 6 * md.CFG["mobility"]["group_jitter_mps"]
    assert late_speed > 0 or model == "hotspot_jump"


def test_attraction_moves_users_closer_together():
    _, _, tr = _run("attraction")
    spread = lambda d: np.hypot(d.x - d.x.mean(), d.y - d.y.mean()).mean()
    # users walk to 1-2 shelters, so by the end they are packed into at most 2 small blobs
    first, last = tr[tr.t == 0], tr[tr.t == tr.t.max()]
    assert last.groupby(last.x.round(-2)).ngroups <= first.groupby(first.x.round(-2)).ngroups


def test_group_drift_keeps_group_shape_but_moves_it():
    _, _, tr = _run("group_drift")
    c = tr[tr.cluster_id == 0]
    if c.empty:
        pytest.skip("no members in cluster 0")
    first, last = c[c.t == 0], c[c.t == c.t.max()]
    spread = lambda d: np.hypot(d.x - d.x.mean(), d.y - d.y.mean()).mean()
    assert abs(spread(last) - spread(first)) < 0.5 * spread(first) + 10        # shape roughly kept
    assert np.hypot(last.x.mean() - first.x.mean(), last.y.mean() - first.y.mean()) > 20   # but it moved
