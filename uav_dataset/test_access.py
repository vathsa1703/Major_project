"""Tests for the QoS-aware access schemes oma_opt / noma_opt (make_dataset.access_rates, book 14.6 step 2).
Run: python -m pytest test_access.py"""
import itertools

import numpy as np
import pytest

import make_dataset as md
from uav_env import UAVEnv

NOISE = 10 ** ((-174 + 7 - 30) / 10)          # W/Hz, as in the config (noise density + noise figure)
BPU = 50e3                                     # Hz per user, as in the config
RATES = np.array([c["min_rate_bps"] for c in md.CFG["classes"].values()], dtype=float)


@pytest.fixture(autouse=True)
def default_profile():
    md.apply_profile("default")
    yield
    md.apply_profile("default")


def draw(rng, n, budget=(0.2, 1.0)):
    """Random gains (realistic range), class min rates, and a power that admits only part of the users."""
    g = 10 ** rng.uniform(-13.5, -10.5, n)
    R = rng.choice(RATES, n)
    full = md.oma_min_power(g, R, NOISE, BPU).sum()
    return g, R, rng.uniform(*budget) * full


def served(g, R, P, scheme, **kw):
    return md.access_rates(g, P, NOISE, len(g) * BPU, R, scheme, return_info=True, **kw)


# ---------------------------------------------------------------- 1-4: the pair closed form
@pytest.mark.parametrize("eps", [0.0, 0.01, 0.05])
def test_closed_form_gives_exactly_the_min_rates(eps):
    rng = np.random.default_rng(1)
    for _ in range(200):
        g = np.sort(10 ** rng.uniform(-13, -10, 2))
        gw, gs = g
        rw, rs = rng.choice(RATES, 2)
        p_s, p_w = md.noma_pair_power(gs, gw, rs, rw, NOISE, 2 * BPU, eps)
        if not np.isfinite(p_s):
            continue
        r_s, r_w = md.noma_pair_rates(p_s, p_w, gs, gw, NOISE, 2 * BPU, eps)
        assert r_s == pytest.approx(rs, rel=1e-9) and r_w == pytest.approx(rw, rel=1e-9)


def test_imperfect_sic_can_make_noma_infeasible_and_the_pair_falls_back_to_oma():
    bp = 2 * BPU
    gam = 2 ** (500e3 / bp) - 1                     # two video users: gamma = 31 each
    eps = 1.0 / (gam * gam)                         # eps * gamma_s * gamma_w = 1 exactly
    p_s, p_w = md.noma_pair_power(1e-11, 1e-12, 500e3, 500e3, NOISE, bp, eps)
    assert np.isinf(p_s) and np.isinf(p_w)
    g, R = np.array([1e-10, 1e-9]), np.array([500e3, 500e3])
    rates, info = md.access_rates(g, 1.0, NOISE, 2 * BPU, R, "noma_opt", eps=0.05, return_info=True)
    assert info["pairs"] == 1 and info["noma_pairs"] == 0             # paired, but OMA inside the pair
    assert info["served"].all() and (rates >= R).all()
    assert (info["partner"] == -1).all()


def test_noma_pair_never_needs_more_power_than_oma_with_perfect_sic():
    rng = np.random.default_rng(2)
    g = np.sort(10 ** rng.uniform(-13.5, -10, (5000, 2)), axis=1)
    rw, rs = rng.choice(RATES, (2, 5000))
    p_s, p_w = md.noma_pair_power(g[:, 1], g[:, 0], rs, rw, NOISE, 2 * BPU, 0.0)
    oma = md.oma_min_power(g[:, 1], rs, NOISE, BPU) + md.oma_min_power(g[:, 0], rw, NOISE, BPU)
    assert (p_s + p_w <= oma * (1 + 1e-12)).all()


@pytest.mark.parametrize("eps", [0.0, 0.05])
def test_strong_user_decodes_the_weak_message_at_least_as_well_as_the_weak_user(eps):
    rng = np.random.default_rng(3)
    g = np.sort(10 ** rng.uniform(-13.5, -10, (2000, 2)), axis=1)
    gw, gs = g[:, 0], g[:, 1]
    rw, rs = rng.choice(RATES, (2, 2000))
    p_s, p_w = md.noma_pair_power(gs, gw, rs, rw, NOISE, 2 * BPU, eps)
    ok = np.isfinite(p_s)
    assert ok.mean() > 0.5
    p_s, p_w, gs, gw = p_s[ok], p_w[ok], gs[ok], gw[ok]
    n0 = NOISE * 2 * BPU
    for f in (1.0, 3.7):                            # also after the common leftover-power scaling
        at_strong = f * p_w * gs / (f * p_s * gs + n0)
        at_weak = f * p_w * gw / (f * p_s * gw + n0)
        assert (at_strong >= at_weak * (1 - 1e-12)).all()


# ---------------------------------------------------------------- 5-6: optimality against brute force
def brute_oma(g, R, P):
    c = md.oma_min_power(g, R, NOISE, BPU)
    return max(len(s) for k in range(len(g) + 1) for s in itertools.combinations(range(len(g)), k)
               if c[list(s)].sum() <= P)


def brute_noma(g, R, P, eps=0.0):
    """Most users that fit, over every subset and every split of it into pairs (NOMA or OMA inside) and singles."""
    n = len(g)
    c = md.oma_min_power(g, R, NOISE, BPU)
    best = {0: 0.0}

    def cover(mask):                                # min power to serve exactly the users in mask
        if mask in best:
            return best[mask]
        i = (mask & -mask).bit_length() - 1
        rest = mask & ~(1 << i)
        v = c[i] + cover(rest)
        for j in range(n):
            if rest >> j & 1:
                s, w = (i, j) if g[i] >= g[j] else (j, i)
                p_s, p_w = md.noma_pair_power(g[s], g[w], R[s], R[w], NOISE, 2 * BPU, eps)
                v = min(v, min(p_s + p_w, c[i] + c[j]) + cover(rest & ~(1 << j)))
        best[mask] = v
        return v

    return max(bin(m).count("1") for m in range(1 << n) if cover(m) <= P)


@pytest.mark.parametrize("n", [1, 2, 5, 8, 10])
def test_oma_opt_equals_brute_force(n):
    rng = np.random.default_rng(10 + n)
    for _ in range(40):
        g, R, P = draw(rng, n)
        assert served(g, R, P, "oma_opt")[1]["served"].sum() == brute_oma(g, R, P)


@pytest.mark.parametrize("n", [2, 3, 6, 8])
def test_noma_opt_is_within_one_user_of_brute_force(n):
    rng = np.random.default_rng(20 + n)
    gaps = []
    for _ in range(40):
        g, R, P = draw(rng, n)
        got = served(g, R, P, "noma_opt")[1]["served"].sum()
        best = brute_noma(g, R, P)
        assert got <= best
        gaps.append(best - got)
    assert max(gaps) <= 1


# ---------------------------------------------------------------- 7-11: properties on random draws
def test_noma_opt_covers_at_least_oma_opt_and_oma_opt_at_least_oma():
    rng = np.random.default_rng(7)
    for _ in range(100):
        n = int(rng.choice([10, 50, 100, 300]))
        g, R, _ = draw(rng, n)
        P = 10 ** rng.uniform(-3, 0)
        cov = {s: served(g, R, P, s)[1]["served"].mean() for s in md.ACCESS_SCHEMES}
        assert cov["noma_opt"] >= cov["oma_opt"] - 1.0 / n
        assert cov["oma_opt"] >= cov["oma"]


@pytest.mark.parametrize("scheme", ["oma_opt", "noma_opt"])
@pytest.mark.parametrize("eps", [0.0, 0.05])
def test_power_budget_and_min_rates_hold_and_rates_follow_from_the_powers(scheme, eps):
    rng = np.random.default_rng(8)
    for _ in range(60):
        n = int(rng.choice([7, 20, 100]))
        g, R, P = draw(rng, n)
        rates, info = served(g, R, P, scheme, eps=eps)
        s, pw, mate = info["served"], info["power_w"], info["partner"]
        assert pw.sum() <= P * (1 + 1e-9) and (pw[~s] == 0).all() and (rates[~s] == 0).all()
        if s.any():
            assert pw.sum() == pytest.approx(P, rel=1e-9)               # leftover power is spread, none wasted
        assert (rates[s] >= R[s]).all()
        # independent recomputation of every served user's rate from its own power (and its partner's)
        alone = s & (mate < 0)
        assert np.allclose(rates[alone], BPU * np.log2(1 + pw[alone] * g[alone] / (NOISE * BPU)), rtol=1e-9)
        for i in np.flatnonzero(mate >= 0):
            j = mate[i]
            st, wk = (i, j) if g[i] >= g[j] else (j, i)
            r_s, r_w = md.noma_pair_rates(pw[st], pw[wk], g[st], g[wk], NOISE, 2 * BPU, eps)
            assert rates[i] == pytest.approx(r_s if i == st else r_w, rel=1e-9) and mate[j] == i


@pytest.mark.parametrize("scheme", ["oma_opt", "noma_opt"])
def test_coverage_never_falls_when_power_grows(scheme):
    rng = np.random.default_rng(9)
    for _ in range(30):
        g, R, _ = draw(rng, int(rng.choice([9, 40, 200])))
        powers = np.logspace(-4, 0.5, 25)
        cov = [served(g, R, P, scheme)[1]["served"].sum() for P in powers]
        assert (np.diff(cov) >= 0).all()


@pytest.mark.parametrize("n", [1, 3, 7, 9, 101])
def test_odd_number_of_users(n):
    rng = np.random.default_rng(n)
    g, R, _ = draw(rng, n)
    for P in (1e-6, 1e-3, 10.0):
        for scheme in md.QOS_SCHEMES:
            rates, info = served(g, R, P, scheme)
            assert rates.shape == (n,) and info["served"].sum() <= n and info["pairs"] <= n // 2
            assert (rates[info["served"]] >= R[info["served"]]).all()
    # with plenty of power every user is served, including the one left over after pairing
    assert served(g, R, 1e6, "noma_opt")[1]["served"].all()
    assert served(g, R, 1e6, "oma_opt")[1]["served"].all()


def test_binary_search_matches_the_full_linear_scan_within_two_percent():
    rng = np.random.default_rng(11)
    gaps = []
    for _ in range(40):
        n = int(rng.choice([20, 100, 300]))
        G = 10 ** rng.uniform(-13.5, -10.5, (8, n))
        R = rng.choice(RATES, n)
        P = 10 ** rng.uniform(-3, -0.5)
        kw = dict(return_info=True)
        a = md.access_rates(G, P, NOISE, n * BPU, R, "noma_opt", **kw)[1]["served"].sum(axis=1)
        b = md.access_rates(G, P, NOISE, n * BPU, R, "noma_opt", search="linear", **kw)[1]["served"].sum(axis=1)
        assert (b >= a).all()                         # the scan finds the largest feasible number of pairs
        gaps += list((b - a) / n)
    assert max(gaps) <= 0.02


def test_rescue_first_serves_at_least_as_many_rescue_users():
    rng = np.random.default_rng(12)
    for _ in range(50):
        g, R, P = draw(rng, 60)
        rescue = R == md.CFG["classes"]["rescue"]["min_rate_bps"]
        for scheme in md.QOS_SCHEMES:
            plain = served(g, R, P, scheme, rescue=rescue)[1]["served"]
            first = served(g, R, P, scheme, rescue=rescue, rescue_first=True)[1]["served"]
            assert first[rescue].sum() >= plain[rescue].sum()
            if scheme == "oma_opt":                # lexicographic optimum: most rescue users, then most users
                c = md.oma_min_power(g, R, NOISE, BPU)
                assert first[rescue].sum() == (np.cumsum(np.sort(c[rescue])) <= P).sum()


def test_vectorised_rows_equal_one_position_at_a_time():
    rng = np.random.default_rng(13)
    G = 10 ** rng.uniform(-13.5, -10.5, (6, 50))
    R = rng.choice(RATES, 50)
    for scheme in md.ACCESS_SCHEMES:
        many = md.access_rates(G, 0.05, NOISE, 50 * BPU, R, scheme)
        one = np.array([md.access_rates(g, 0.05, NOISE, 50 * BPU, R, scheme) for g in G])
        assert np.array_equal(many, one)


# ---------------------------------------------------------------- 12: old schemes unchanged, env integration
def test_noma_and_oma_schemes_reproduce_noma_rates_exactly():
    rng = np.random.default_rng(14)
    G = 10 ** rng.uniform(-13.5, -10.5, (4, 100))
    R = rng.choice(RATES, 100)
    for pairing in ("extreme", "random"):
        for pick, scheme in enumerate(("noma", "oma")):
            got = md.access_rates(G, 0.1, NOISE, 100 * BPU, R, scheme, pairing, np.random.default_rng(5))
            r2 = np.random.default_rng(5)
            want = np.array([md.noma_rates(g, 0.1, NOISE, 100 * BPU, pairing, r2)[pick] for g in G])
            assert np.array_equal(got, want)


def _episode(access, seed=3, steps=12, **kw):
    env = UAVEnv(access=access, battery_wh=1000.0, **kw)
    env.reset(seed=seed)
    out = []
    for t in range(steps):
        info = env.step(np.array([np.sin(t), np.cos(t), 0.1, 1.0]))[4]
        out.append((info["coverage"], info["sum_rate_mbps"], info["fairness"], info["coverage_noma"],
                    info["coverage_oma"], info["fairness_served"], info["outage_rescue"]))
    return env, info, out


@pytest.mark.parametrize("access", md.ACCESS_SCHEMES)
def test_env_runs_with_every_scheme_and_is_deterministic(access):
    env, info, a = _episode(access)
    _, _, b = _episode(access)
    assert a == b
    assert info["access"] == access and info["coverage_access"] == info["coverage"]
    assert info["sum_rate_access_mbps"] == info["sum_rate_mbps"]
    if access == "noma":
        assert info["coverage"] == info["coverage_noma"]
    if access == "oma":
        assert info["coverage"] == info["coverage_oma"]
    if access == "noma_opt":
        assert 0 <= info["alpha_lt_half"] <= info["noma_pairs"] <= info["pairs"]


def test_default_access_is_still_noma_and_old_info_is_unchanged():
    env, info, _ = _episode(None)
    assert env.access == "noma" and env.sic_eps == 0.0 and env.rescue_first is False
    _, info2, _ = _episode("noma_opt")
    # the fixed schemes are reported whatever the active scheme (same world, same moves)
    assert (info["coverage_noma"], info["coverage_oma"]) == (info2["coverage_noma"], info2["coverage_oma"])


@pytest.mark.parametrize("access", md.QOS_SCHEMES)
def test_env_evaluate_uses_the_qos_scheme(access):
    env = UAVEnv(access=access)
    env.reset(seed=4)
    X, Y, H = np.array([300.0, 700.0, 500.0]), np.array([300.0, 500.0, 500.0]), np.full(3, 150.0)
    got = env.evaluate(X, Y, H, env.p_max_w)
    ux, uy = env.user_xy().T
    G = md.channel_gain(ux, uy, X, Y, H, env.boxes)
    want = [md.access_rates(g, env.p_max_w, env.noise_psd, env.sc["bandwidth_hz"], env.min_rate, access,
                            return_info=True)[1]["served"].mean() for g in G]
    assert np.allclose(got, want)
    old = UAVEnv(access=access.replace("_opt", ""))
    old.reset(seed=4)
    assert (got >= old.evaluate(X, Y, H, old.p_max_w) - 1e-12).all()


def test_env_passes_eps_and_rescue_first_through():
    env = UAVEnv(access="noma_opt", sic_eps=0.05, rescue_first=True)
    env.reset(seed=4)
    G = md.channel_gain(*env.user_xy().T, np.array([500.0]), np.array([500.0]), np.array([150.0]), env.boxes)
    want = md.access_rates(G, 0.01, env.noise_psd, env.sc["bandwidth_hz"], env.min_rate, "noma_opt", eps=0.05,
                           rescue=env.rescue, rescue_first=True, return_info=True)[1]["served"].mean(axis=1)
    assert np.allclose(env.evaluate(500.0, 500.0, 150.0, 0.01), want)


# ---------------------------------------------------------------- B3obs with QoS-aware schemes
def test_explicit_classes_follow_the_mix_and_keep_certain_classes():
    from baselines import explicit_classes
    names = list(md.CFG["classes"])
    shares = np.array([md.CFG["classes"][c]["share"] for c in names])
    prior = shares.copy(); prior[0] = 0; prior /= prior.sum()
    probs = np.vstack([np.tile(np.eye(len(names))[0], (5, 1)), np.tile(prior, (45, 1))])
    cls = explicit_classes(probs)
    assert (cls[:5] == 0).all() and (cls[5:] != 0).all()
    assert np.array_equal(np.bincount(cls[5:], minlength=len(names))[1:], np.round(prior[1:] * 45).astype(int))
    assert np.array_equal(cls, explicit_classes(probs))
    # interleaved: every block of 10 consecutive users holds at least 3 different classes
    assert all(len(set(cls[5 + i: 15 + i])) >= 3 for i in range(0, 35, 10))


@pytest.mark.parametrize("access", md.QOS_SCHEMES)
def test_b3obs_plans_with_qos_schemes(access):
    from baselines import make_policy
    env = UAVEnv(access=access)
    env.reset(seed=3)
    pol = make_policy("B3obs")
    pol.reset(env)
    pol.plan(env)
    x, y, h = pol.target
    assert 0 <= x <= env.L and 0 <= y <= env.L
    from baselines import B3Obs, expected_coverage, pseudo_population
    xy, probs = pseudo_population(env, *B3Obs().maps(env))
    cov = expected_coverage(env, xy, probs, np.array([x, 100.0]), np.array([y, 900.0]), np.full(2, 150.0),
                            env.p_max_w)
    assert ((0 <= cov) & (cov <= 1)).all()


# ---------------------------------------------------------------- statistics and the H3 runner
def test_holm_and_paired_p():
    from evalstats import holm, paired_p
    assert np.allclose(holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
    assert paired_p([1, 2, 3], [1, 2, 3]) == 1.0
    assert paired_p(np.arange(50) * 0.01 + 1, np.arange(50) * 0.01) < 1e-6


def test_four_scheme_runner_and_tables():
    from noma_vs_oma import comparison_table, run, scheme_table
    df = run(["B0"], [2, 3], battery_wh=1000.0, workers=1, schemes=("oma", "oma_opt", "noma", "noma_opt"))
    assert sorted(df.scheme.unique()) == ["noma", "noma_opt", "oma", "oma_opt"] and df.survived.all()
    assert "| B0 | noma_opt |" in scheme_table(df)
    text = comparison_table(df)
    assert "noma_opt - oma_opt" in text and "Holm" in text
    eps = run(["B0"], [2], battery_wh=1000.0, workers=1, schemes=("noma_opt",), env_kw={"sic_eps": 0.05})
    assert list(eps.scheme) == ["noma_opt[eps=0.05]"]
