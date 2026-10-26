"""Tests for the model-mismatch experiment: the true world vs the planners' nominal model, B6r / B6true / B6meas.
Run: python -m pytest test_mismatch.py"""
import numpy as np
import pytest

import make_dataset as md
from baselines import MeasuredView, make_policy, refine_spot
from mismatch_exp import CachedEnv
from run_baselines import run_episode
from uav_env import UAVEnv

SMALL = {"n_users": 100}
TINY = {"grid_n": 4, "altitude_levels_m": [100, 200]}          # small B6 grid for fast tests
MM_PROFILES = [p for p in md.BASE_CFG["profiles"] if p.startswith("mm_")]


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    md.apply_profile("default")


def prof(name, tiny=True, **mm):
    md.apply_profile(name)
    md.CFG["mismatch"].update(mm)
    if tiny:
        md.CFG["baselines"].update(TINY)


def grid_xyz(L, n=6, h=(60.0, 150.0, 300.0)):
    g = np.linspace(0, L, n)
    X, Y, H = np.meshgrid(g, g, np.asarray(h), indexing="ij")
    return X.ravel(), Y.ravel(), H.ravel()


# ---------------------------------------------------------------- off = the old game
def test_mismatch_is_off_by_default_and_in_every_old_profile():
    for p in [None] + [q for q in md.BASE_CFG["profiles"] if not q.startswith("mm_")] + ["mm_none"]:
        md.apply_profile(p)
        assert not md.mismatch_on(), p
    md.apply_profile(None)
    env = UAVEnv()
    env.reset(seed=3)
    assert env.true_boxes is env.boxes and env.shadow_field is None and env.true_excess_db is None


@pytest.mark.parametrize("profile", ["default", "rl_static", "mm_none"])
def test_off_true_equals_nominal_exactly(profile):
    prof(profile, tiny=False)
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=4)
    X, Y, H = grid_xyz(env.L)
    ux, uy = env.user_xy().T
    assert np.array_equal(env.gains(ux, uy, X, Y, H, "true"), md.channel_gain(ux, uy, X, Y, H, env.boxes))
    assert np.array_equal(env.evaluate(X, Y, H, env.p_max_w, model="true"), env.evaluate(X, Y, H, env.p_max_w))


def test_channel_gain_defaults_are_unchanged():
    md.apply_profile("rl_static")
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=2)
    X, Y, H = grid_xyz(env.L)
    ux, uy = env.user_xy().T
    a = md.channel_gain(ux, uy, X, Y, H, env.boxes)
    b = md.channel_gain(ux, uy, X, Y, H, env.boxes, excess_loss_db=md.CFG["obstacles"]["excess_loss_db"],
                        shadow=(np.zeros(len(ux)), 8.0))
    assert np.array_equal(a, b)


# ---------------------------------------------------------------- the perturbations
def test_shadow_field_is_seeded_and_redrawn_by_draw():
    a = md.ShadowField(7, 2000.0, 50.0).z
    assert np.array_equal(a, md.ShadowField(7, 2000.0, 50.0).z)
    assert not np.allclose(a, md.ShadowField(7, 2000.0, 50.0, draw=1).z)
    assert not np.allclose(a, md.ShadowField(8, 2000.0, 50.0).z)


@pytest.mark.parametrize("corr", [25.0, 50.0, 150.0])
def test_shadow_field_has_unit_variance_and_the_configured_correlation(corr):
    zs = [md.ShadowField(s, 2000.0, corr).z for s in range(6)]
    z = np.concatenate([q.ravel() for q in zs])
    assert abs(z.mean()) < 0.1 and 0.9 < z.std() < 1.1
    # correlation at lag = corr (grid spacing corr/4 -> 4 cells): exp(-1) = 0.37 for the Gaussian kernel
    lag = 4
    r = np.mean([np.corrcoef(q[:-lag].ravel(), q[lag:].ravel())[0, 1] for q in zs])
    assert 0.25 < r < 0.5, r
    far = np.mean([np.corrcoef(q[:-4 * lag].ravel(), q[4 * lag:].ravel())[0, 1] for q in zs])
    assert abs(far) < 0.1


def test_shadowing_adds_sigma_times_field_at_grazing_and_nothing_overhead():
    md.apply_profile("rl_static")
    f = md.ShadowField(3, 2000.0, 50.0)
    ux, uy = np.array([500.0, 900.0]), np.array([700.0, 1300.0])
    z = f.at(ux, uy)
    X, Y, H = np.array([ux[0], 1e5]), np.array([uy[0], 1e5]), np.array([100.0, 1.0])   # overhead user 0; grazing
    g0 = md.channel_gain(ux, uy, X, Y, H)
    g1 = md.channel_gain(ux, uy, X, Y, H, shadow=(z, 8.0))
    extra = 10 * np.log10(g0 / g1)
    assert abs(extra[0, 0]) < 1e-9                                   # straight overhead: no shadowing
    assert np.allclose(extra[1], z * 8.0, atol=0.01)                 # near-grazing: the full sigma * z
    assert np.all(np.diff(md.shadow_sigma(np.array([0.0, 30.0, 60.0, 90.0]), 8.0)) < 0)


def test_each_perturbation_has_its_own_rng_stream():
    prof("mm_none", hidden_obstacles=3)
    e1 = UAVEnv()
    e1.reset(seed=5)
    prof("mm_none", hidden_obstacles=3, shadow_sigma_db=8.0, excess_loss_db=25.0)
    e2 = UAVEnv()
    e2.reset(seed=5)
    assert np.array_equal(e1.true_boxes, e2.true_boxes)              # switching shadowing on changes nothing else
    assert len(e1.true_boxes) == len(e1.boxes) + 3
    assert np.array_equal(e1.true_boxes[: len(e1.boxes)], e1.boxes)
    prof("mm_none", hidden_obstacles=3, draw=1)
    e3 = UAVEnv()
    e3.reset(seed=5)
    assert np.array_equal(e3.boxes, e1.boxes) and not np.array_equal(e3.true_boxes, e1.true_boxes)
    assert np.array_equal(e3.user_xy(), e1.user_xy())               # the scenario itself is the same


@pytest.mark.parametrize("mm", [dict(shadow_sigma_db=8.0), dict(excess_loss_db=25.0), dict(hidden_obstacles=4)])
def test_nominal_is_unchanged_and_true_differs_when_on(mm):
    prof("mm_none", tiny=False)
    base = UAVEnv(scenario_overrides=SMALL)
    base.reset(seed=6)
    prof("mm_none", tiny=False, **mm)
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=6)
    assert md.mismatch_on()
    X, Y, H = grid_xyz(env.L, n=8)
    nom = env.evaluate(X, Y, H, env.p_max_w)
    assert np.array_equal(nom, base.evaluate(X, Y, H, env.p_max_w))
    assert np.array_equal(nom, env.evaluate(X, Y, H, env.p_max_w, model="nominal"))
    true = env.evaluate(X, Y, H, env.p_max_w, model="true")
    assert not np.array_equal(true, nom)
    if "shadow_sigma_db" not in mm:                                  # more loss only: never more coverage
        ux, uy = env.user_xy().T
        assert np.all(env.gains(ux, uy, X, Y, H, "true") <= env.gains(ux, uy, X, Y, H, "nominal"))


@pytest.mark.parametrize("mm", [dict(shadow_sigma_db=8.0), dict(excess_loss_db=25.0), dict(hidden_obstacles=4)])
def test_step_serves_through_the_true_channel_and_allocates_with_true_gains(mm):
    """Amendment 4: the radio layer (admission, pairing, power) runs on the TRUE gains; env.step's coverage is
    evaluate(model="true") at the new spot, and its served set is access_rates on the true gains."""
    prof("mm_none", tiny=False, **mm)
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=6)
    for a in np.random.default_rng(0).uniform(-1, 1, (5, 4)):
        _, _, _, _, info = env.step(a)
        p_w = info["p_tx_w"]
        x, y, h = [env.x], [env.y], [env.h]
        assert info["coverage"] == pytest.approx(env.evaluate(x, y, h, p_w, model="true")[0], abs=1e-12)
        ux, uy = env.user_xy().T
        g = env.gains(ux, uy, np.array(x), np.array(y), np.array(h), "true")[0]
        served = env.access_rates(g, p_w, return_info=True)[1]["served"]
        assert np.array_equal(served, info["served"])


# ---------------------------------------------------------------- pilots
def test_refine_never_loses_and_b6true_equals_b6r_without_mismatch():
    prof("mm_none")
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=1)
    v0 = env.evaluate([700.0], [900.0], [150.0], env.p_max_w)[0]
    *_, v = refine_spot(env, 700.0, 900.0, 150.0, env.p_max_w)
    assert v >= v0
    a = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6r"), 1)
    b = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6true"), 1)
    assert a == b


@pytest.mark.parametrize("mm", [dict(excess_loss_db=25.0), dict(hidden_obstacles=4), dict(shadow_sigma_db=8.0)])
def test_b6true_plans_at_least_as_well_as_b6_on_the_true_channel(mm):
    """Plan level (a guarantee): B6true maximises the TRUE coverage over B6's candidates and then only improves, so
    its target's true coverage is >= that of B6's target, scenario by scenario."""
    prof("mm_none", **mm)
    for seed in range(4):
        env = UAVEnv(scenario_overrides=SMALL)
        env.reset(seed=seed)
        b6, bt = make_policy("B6"), make_policy("B6true")
        for p in (b6, bt):
            p.reset(env)
            p.plan(env)
        true = env.evaluate(*np.array([b6.target, bt.target]).T, env.p_max_w, model="true")
        assert true[1] >= true[0] - 1e-12


def test_b6true_beats_b6_in_expectation_on_a_fixed_set():
    prof("mm_none", excess_loss_db=25.0, hidden_obstacles=4)
    d = [run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6true"), s)["coverage_full"]
         - run_episode(UAVEnv(scenario_overrides=SMALL), make_policy("B6"), s)["coverage_full"] for s in range(4)]
    assert np.mean(d) >= 0


def test_b6meas_only_sees_the_measured_view():
    prof("mm_none", shadow_sigma_db=8.0)
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=2)
    v = MeasuredView(env)
    for k in ("boxes", "true_boxes", "shadow_field", "P", "users", "gains", "sc", "prev", "true_excess_db", "rescue"):
        with pytest.raises(AttributeError):
            getattr(v, k)
    assert v.x == env.x and v.measured_coverage() == env.prev["coverage"]


def test_b6meas_never_uses_the_true_model(monkeypatch):
    prof("mm_none", shadow_sigma_db=8.0, hidden_obstacles=2, excess_loss_db=25.0)
    env = UAVEnv(scenario_overrides=SMALL)
    models = []
    real = env.evaluate

    def spy(X, Y, H, p_w, t=None, model="nominal"):
        models.append(model)
        return real(X, Y, H, p_w, t, model)

    monkeypatch.setattr(env, "evaluate", spy)
    pol = make_policy("B6meas")
    run_episode(env, pol, 3)
    assert models and set(models) == {"nominal"}


def test_b6meas_surveys_k_spots_and_keeps_only_improving_moves():
    prof("mm_none", excess_loss_db=25.0)
    md.CFG["b6meas"].update(k=3, dwell_s=2)
    pol = make_policy("B6meas")
    row = run_episode(UAVEnv(scenario_overrides=SMALL), pol, 4)
    assert row["survived"]
    survey = [r for r in pol.log if r[1] == "survey"]
    assert len(survey) == 3
    assert pol.mode in ("refine", "hold")
    best = max(r[-1] for r in pol.log)                               # only moves better by improve_min are kept
    assert best - md.CFG["b6meas"]["improve_min"] <= pol.center_val <= best
    # the measurement is real: the drone's measured coverage at the end equals the committed value (still crowd)
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=4)
    assert env.evaluate(*np.array([pol.center]).T, env.p_max_w, model="true")[0] == pytest.approx(pol.center_val)


def test_cached_env_gives_exactly_the_same_episodes():
    prof("mm_none", shadow_sigma_db=4.0)
    for pol in ("B6", "B6true", "B3"):
        a = run_episode(UAVEnv(scenario_overrides=SMALL), make_policy(pol), 3)
        b = run_episode(CachedEnv(scenario_overrides=SMALL), make_policy(pol), 3)
        assert a == b, pol


def test_mm_profiles_change_only_the_mismatch_section():
    md.apply_profile("mm_none")
    base = {k: v for k, v in md.CFG.items() if k not in ("mismatch", "active_profile")}
    for p in MM_PROFILES:
        if "hard" in p:
            continue
        md.apply_profile(p)
        assert {k: v for k, v in md.CFG.items() if k not in ("mismatch", "active_profile")} == base, p
    md.apply_profile("mm_none")
    assert md.CFG["env"]["access"] == "noma_opt" and md.CFG["uav"]["a_max_mps2"] == 4
    assert md.CFG["access"] == {"sic_eps": 0.05, "rescue_first": True}
    assert md.CFG["mobility"]["choices"] == ["static"]
