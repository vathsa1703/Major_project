"""Tests for the value-of-information pilots (contribution 2): ReportsView, B6rep, B3rep.
Run: python -m pytest test_voi.py"""
import hashlib

import numpy as np
import pytest

import baselines as bl
import make_dataset as md
from baselines import B6GridAltitude, ReportsView, make_policy
from uav_env import UAVEnv

SMALL = {"n_users": 100}
SMALL_GRID = {"grid_n": 4, "altitude_levels_m": [100, 200]}
PROFILES = ("hard", "sites_d20_t60_ann")


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    md.apply_profile("default")


def profile(name, small_grid=True):
    md.apply_profile(name)
    if small_grid:
        md.CFG["baselines"].update(SMALL_GRID)


def play(env, pol, seed, n=None):
    """Actions and per-step coverage of one episode (or its first n steps)."""
    env.reset(seed=seed)
    pol.reset(env)
    acts, cov = [], []
    for _ in range(n or env.T):
        a = pol.act(env)
        _, _, term, trunc, info = env.step(a)
        acts.append(a)
        cov.append(info["coverage"])
        if term or trunc:
            break
    return np.array(acts), np.array(cov)


def fresh(seed, overrides=SMALL):
    env = UAVEnv(scenario_overrides=overrides)
    env.reset(seed=seed)
    return env


# ---------------------------------------------------------------- full information = the old pilots, bit for bit
@pytest.mark.parametrize("prof", PROFILES)
@pytest.mark.parametrize("pair", [("B6", "B6rep:f=1,sigma=0,age=0"), ("B3", "B3rep:f=1,sigma=0,age=0"),
                                  ("B6", "B6rep")])
def test_full_information_reproduces_the_pilot_exactly(prof, pair):
    profile(prof)
    a_ref, c_ref = play(UAVEnv(scenario_overrides=SMALL), make_policy(pair[0]), 3)
    a_rep, c_rep = play(UAVEnv(scenario_overrides=SMALL), make_policy(pair[1]), 3)
    assert np.array_equal(a_ref, a_rep) and np.array_equal(c_ref, c_rep)


@pytest.mark.parametrize("prof", PROFILES)
def test_full_information_belief_is_the_true_users(prof):
    profile(prof)
    env = fresh(5)
    v = ReportsView(env, 1.0, 0.0, 0)
    for t in (0, 100, 200, 299):
        env.t = t
        for a, b in zip(v.belief(), env.users_now(), strict=True):
            assert np.array_equal(a, b)


def test_old_pilots_unchanged():
    """The default pilot list and B6's behaviour do not move (fingerprint taken with the code before this change)."""
    assert list(bl.POLICIES) == ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B6fc", "B3obs", "B3obsU",
                                 "B3obsUO", "B3obsN", "B3obsUN"]
    profile("hard")
    acts, cov = play(UAVEnv(scenario_overrides=SMALL), B6GridAltitude(), 3)
    digest = hashlib.sha1(np.round(acts, 12).tobytes() + np.round(cov, 12).tobytes()).hexdigest()
    assert digest == B6_FINGERPRINT


B6_FINGERPRINT = "cb0499668f8dbd4b3dac358fd35f08d29bd65690"   # baselines.py at a2147dd (before ReportsView)


# ---------------------------------------------------------------- reports: seeded, deterministic, nested
def test_reports_are_seeded_and_deterministic():
    profile("hard")
    env = fresh(7)
    a, b = ReportsView(env, 0.2, 10.0, 30), ReportsView(env, 0.2, 10.0, 30)
    for t in (0, 37, 250):
        env.t = t
        for x, y in zip(a.belief(), b.belief(), strict=True):
            assert np.array_equal(x, y)
    c = ReportsView(env, 0.2, 10.0, 30, rep=1)
    assert not np.array_equal(a.reports, c.reports)
    other = ReportsView(fresh(8), 0.2, 10.0, 30)
    assert not np.array_equal(a.reports[:50], other.reports[:50])


def test_reporters_are_nested_across_f_and_share_is_about_f():
    profile("hard")
    env = fresh(9, {"n_users": 1000})
    sets = [ReportsView(env, f, 0.0, 0).reports for f in (0.05, 0.1, 0.2, 0.5, 1.0)]
    for small, big in zip(sets, sets[1:], strict=False):
        assert np.all(big[small])
    assert sets[-1].all()
    assert abs(sets[2].mean() - 0.2) < 0.04


# ---------------------------------------------------------------- unreported users are invisible
def test_unreported_users_are_invisible():
    profile("hard")
    env = fresh(11)
    v = ReportsView(env, 0.3, 0.0, 0)
    env.t = 50
    xy, mr, rs = v.belief()
    rep = np.flatnonzero(v.reports)
    k = len(rep)
    assert np.array_equal(xy[:k], env.P[50, rep])                 # the reporters, in user order
    assert np.array_equal(mr[:k], env.min_rate[rep]) and np.array_equal(rs[:k], env.rescue[rep])
    true_rows = {tuple(p) for p in env.P[50, rep]}
    assert all(tuple(p) in true_rows for p in xy)                  # fillers sit only at reporters' positions
    # moving the non-reporters anywhere changes neither the belief nor the plan
    a_before = make_policy("B6rep:f=0.3,sigma=0,age=0")
    a_before.reset(env)
    a_before.plan(env)
    env.P[:, ~v.reports] = env.P[:, ~v.reports][:, ::-1] * 0.5 + 3.0
    assert np.array_equal(v.belief()[0], xy)
    a_after = make_policy("B6rep:f=0.3,sigma=0,age=0")
    a_after.reset(env)
    a_after.plan(env)
    assert a_before.target == a_after.target


def test_count_scaling_and_filler_classes():
    profile("hard")
    env = fresh(12, {"n_users": 1000})
    v = ReportsView(env, 0.2, 10.0, 0)
    xy, mr, rs = v.belief()
    k = int(v.reports.sum())
    n_hat = int(round(k / 0.2))
    assert len(xy) == n_hat + n_hat % 2 and len(mr) == len(xy) and len(rs) == len(xy)
    fill = mr[k:]
    names = list(md.CFG["classes"])
    rates = np.array([md.CFG["classes"][c]["min_rate_bps"] for c in names])
    shares = np.array([np.mean(fill == r) for r in rates])
    mix = np.array([md.CFG["classes"][c]["share"] for c in names])
    assert np.allclose(shares, mix / mix.sum(), atol=2.0 / len(fill))
    assert np.array_equal(rs[k:], fill == md.CFG["classes"]["rescue"]["min_rate_bps"])


def test_gps_error_is_per_report_and_scales_with_sigma():
    profile("hard")
    env = fresh(13, {"n_users": 1000})
    env.t = 120
    rep = np.flatnonzero(ReportsView(env, 1.0, 0.0, 0).reports)
    errs = {}
    for s in (10.0, 50.0):
        xy = ReportsView(env, 1.0, s, 0).belief()[0]
        errs[s] = xy - env.P[120, rep]
    inner = (env.P[120, rep] > 200).all(axis=1) & (env.P[120, rep] < env.L - 200).all(axis=1)   # away from clipping
    assert abs(errs[10.0][inner].std() - 10.0) < 1.5
    assert np.allclose(errs[50.0][inner], 5.0 * errs[10.0][inner])                              # same Z, scaled
    env.t = 121
    assert not np.allclose(ReportsView(env, 1.0, 10.0, 0).belief()[0] - env.P[121, rep], errs[10.0])


# ---------------------------------------------------------------- report age
def test_age_planner_sees_the_last_report():
    profile("hard")
    env = fresh(14)
    age = 30
    v = ReportsView(env, 1.0, 0.0, age)
    for t in (0, 5, 29, 30, 77, 299):
        tr = v.last_report(t)
        assert np.all(tr <= t) and np.all(t - tr < age)
        assert np.all((tr == 0) | (np.mod(tr - v.phase, age) == 0))           # on schedule (or the attach report)
        env.t = t
        xy = v.belief()[0]
        assert np.array_equal(xy, env.P[tr, np.arange(env.P.shape[1])])
    assert np.array_equal(v.last_report(0), np.zeros(env.P.shape[1], int))     # attach report at t = 0


def test_sites_movers_go_stale_then_vanish_and_twins_appear_on_attach():
    profile("sites_d20_t60_ann")
    env = fresh(15)
    age = 30
    v = ReportsView(env, 1.0, 0.0, age)
    act = env.active
    movers = np.flatnonzero(~act[-1] & act[0])
    twins = np.flatnonzero(act[-1] & ~act[0])
    assert len(movers) and len(twins)
    for u in movers[:20]:
        leave = int(np.argmin(act[:, u]))                                     # first inactive second
        nxt = leave + int(np.mod(v.phase[u] - leave, age))                   # first scheduled report after leaving
        if nxt > leave and nxt <= 300:
            assert u in v.visible(leave)[0]                                   # still seen, at its stale position
        if nxt <= 300:
            assert u not in v.visible(nxt)[0]                                 # its next report says "not here"
    for u in twins[:20]:
        on = int(np.argmax(act[:, u]))
        if on > 0:
            assert u not in v.visible(on - 1)[0]
        idx, tr = v.visible(on)
        assert u in idx and tr[list(idx).index(u)] == on                      # attach report


# ---------------------------------------------------------------- the radio layer always uses the true users
@pytest.mark.parametrize("prof", PROFILES)
def test_radio_layer_uses_the_true_users(prof):
    profile(prof)
    env = UAVEnv(scenario_overrides=SMALL)
    acts, cov = play(env, make_policy("B6rep:f=0.1,sigma=50,age=30"), 4, n=80)
    P0 = fresh(4).P
    assert np.array_equal(env.P, P0)                                          # the belief never touches the truth
    replay = fresh(4)
    for a, c in zip(acts, cov, strict=True):
        info = replay.step(a)[4]
        assert info["coverage"] == c                                          # same actions -> same served users
        # and that is the TRUE users' coverage at the drone's position (no fading, extreme pairing: no rng involved)
        true_cov = replay.evaluate([replay.x], [replay.y], [replay.h], info["p_tx_w"])[0]
        assert true_cov == pytest.approx(c, abs=1e-12)


def test_empty_belief_stays_put():
    profile("hard")
    env = fresh(16)
    pol = make_policy("B6rep:f=0.001,sigma=0,age=0")
    pol.reset(env)
    pol.view.reports[:] = False
    pol.plan(env)
    assert pol.target == (env.x, env.y, env.h)


def test_parse_rep_names():
    p = make_policy("B6rep:f=0.2,sigma=10,age=30,rep=2")
    assert isinstance(p, bl.B6Reports) and p.voi == dict(f=0.2, sigma_m=10.0, age_s=30.0, rep=2)
    assert isinstance(make_policy("B3rep:f=0.5"), bl.B3Reports)
    with pytest.raises(AssertionError):
        make_policy("B6rep:x=1")
    with pytest.raises(AssertionError):
        ReportsView(fresh(1), 0.0, 0.0, 0)
