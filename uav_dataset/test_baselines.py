"""Tests for the baselines, the episode runner and the statistics helpers. Run: python -m pytest test_baselines.py"""
import numpy as np
import pytest

import make_dataset as md
from baselines import POLICIES, B3GridSearch, B5EnergyAware, go_to, kmeans, make_policy
from evalstats import mean_ci, paired_diff
from run_baselines import report, run_episode, summarize
from uav_env import UAVEnv

BCFG = md.CFG["baselines"]


def _env(seed=3, **kw):
    env = UAVEnv(**kw)
    env.reset(seed=seed)
    return env


# ---------------------------------------------------------------- statistics
def test_mean_ci_no_variation_means_no_uncertainty():
    assert mean_ci([10, 10, 10, 10, 10]) == (10.0, 0.0)
    assert mean_ci([4.0]) == (4.0, 0.0)


def test_mean_ci_shrinks_with_more_data():
    rng = np.random.default_rng(0)
    assert mean_ci(rng.normal(size=400))[1] < mean_ci(rng.normal(size=25))[1]


def test_paired_diff_detects_a_consistent_winner_that_unpaired_would_hide():
    easy = np.array([10.0, 50.0, 90.0, 30.0, 70.0])          # scenario difficulty varies a lot
    mean, hw = paired_diff(easy + 5, easy)
    assert mean == pytest.approx(5.0) and hw == 0.0           # always exactly +5
    assert mean_ci(easy + 5)[1] > 10                          # the unpaired CI is far wider than the 5-point gap


# ---------------------------------------------------------------- helpers
def test_go_to_moves_toward_the_target_and_saturates():
    env = _env()
    a = go_to(env, env.x + 1000, env.y, env.h, 1.0)
    assert a[0] == pytest.approx(1.0) and abs(a[1]) < 1e-9 and a[3] == 1.0
    near = go_to(env, env.x + 3, env.y, env.h, 0.5)
    assert 0 < near[0] < 1 and near[3] == 0.0
    assert go_to(env, env.x, env.y, env.h + 1000, 1.0)[2] == 1.0


def test_kmeans_finds_separated_blobs():
    rng = np.random.default_rng(0)
    pts = np.vstack([rng.normal(c, 5, size=(60, 2)) for c in ([100, 100], [800, 200], [400, 900])])
    centres, labels = kmeans(pts, np.ones(len(pts)), 3, 30, np.random.default_rng(1))
    for truth in ([100, 100], [800, 200], [400, 900]):
        assert np.hypot(*(centres - truth).T).min() < 20
    assert len(set(labels)) == 3


def test_kmeans_weights_pull_the_centre():
    pts = np.array([[0.0, 0.0], [100.0, 0.0]])
    centres, _ = kmeans(pts, np.array([1.0, 9.0]), 1, 5, np.random.default_rng(0))
    assert centres[0][0] == pytest.approx(90.0)


def test_env_evaluate_is_pure_and_matches_a_real_step():
    env = _env()
    state = (env.x, env.y, env.h, env.t)
    before = env.rng.bit_generator.state
    cov = env.evaluate([env.x, 100.0], [env.y, 100.0], [env.h, 150.0], env.p_max_w)
    assert (env.x, env.y, env.h, env.t) == state and env.rng.bit_generator.state == before
    assert cov.shape == (2,) and ((0 <= cov) & (cov <= 1)).all()
    env.fading = False
    pred = env.evaluate(env.x, env.y, env.h, env.p_max_w)[0]
    nxt = env.step(np.array([0.0, 0.0, 0.0, 1.0]))[4]["coverage"]
    assert abs(pred - nxt) < 0.1                               # users move one step in between


# ---------------------------------------------------------------- the six policies
@pytest.mark.parametrize("name", list(POLICIES))
def test_every_policy_returns_valid_actions_for_a_whole_episode(name):
    env = _env(battery_wh=1000.0)
    pol = make_policy(name)
    pol.reset(env)
    for _ in range(25):
        a = pol.act(env)
        assert env.action_space.contains(a.astype(np.float32))
        env.step(a)


@pytest.mark.parametrize("name", list(POLICIES))
def test_every_policy_is_deterministic(name):
    rows = [run_episode(UAVEnv(battery_wh=2.0), make_policy(name), 4) for _ in range(2)]
    assert rows[0] == rows[1]


def test_b0_stays_at_the_centre():
    env = _env(battery_wh=1000.0)
    pol = make_policy("B0")
    pol.reset(env)
    for _ in range(20):
        env.step(pol.act(env))
    assert (env.x, env.y) == pytest.approx((env.L / 2, env.L / 2)) and env.h == pytest.approx(BCFG["altitude_m"], abs=5)


def test_b1_moves_toward_the_biggest_cluster():
    env = _env(battery_wh=1000.0)
    cid = env.users["cluster_id"].values
    big = np.bincount(cid[cid >= 0]).argmax()
    target = env.user_xy()[cid == big].mean(axis=0)
    d0 = np.hypot(*(np.array([env.x, env.y]) - target))
    pol = make_policy("B1")
    pol.reset(env)
    for _ in range(5):
        env.step(pol.act(env))
    assert np.hypot(env.x - target[0], env.y - target[1]) < d0


def test_b3_never_picks_a_worse_spot_than_where_it_is():
    env = _env()
    pol = B3GridSearch()
    pol.reset(env)
    pol.plan(env)
    p_w = env.p_max_w
    here = env.evaluate(env.x, env.y, BCFG["altitude_m"], p_w)[0]
    chosen = env.evaluate(pol.target[0], pol.target[1], pol.target[2], p_w)[0]
    assert chosen >= here - 1e-12


def test_b5_stays_put_when_moving_gains_nothing(monkeypatch):
    env = _env()
    pol = B5EnergyAware()
    pol.reset(env)
    monkeypatch.setattr(env, "evaluate", lambda X, Y, H, p: np.full(len(np.atleast_1d(X)), 0.5))   # flat landscape
    pol.plan(env)
    assert pol.target[:2] == (env.x, env.y)


def test_b5_moves_when_the_gain_is_large(monkeypatch):
    env = _env()
    pol = B5EnergyAware()
    pol.reset(env)

    def fake(X, Y, H, p):
        X = np.atleast_1d(X)
        out = np.zeros(len(X))
        out[0] = 0.9                                            # candidate 0 (grid corner) is far better
        return out

    monkeypatch.setattr(env, "evaluate", fake)
    pol.plan(env)
    assert pol.target[:2] == (0.0, 0.0)


def test_b4_is_reproducible_and_stays_in_bounds():
    outs = []
    for _ in range(2):
        env = _env()
        pol = make_policy("B4")
        pol.reset(env)
        pol.plan(env)
        outs.append((pol.target, pol.power))
    assert outs[0] == outs[1]
    (x, y, h), p = outs[0]
    assert 0 <= x <= env.L and 0 <= y <= env.L and env.uav["h_min_m"] <= h <= env.uav["h_max_m"] and 0.05 <= p <= 1.0


# ---------------------------------------------------------------- runner
def test_run_episode_accounts_for_a_dead_drone_as_zero_coverage():
    row = run_episode(UAVEnv(battery_wh=0.5), make_policy("B0"), 3)
    assert row["steps"] < 300 and not row["survived"]
    assert row["coverage_full"] == pytest.approx(row["coverage_alive"] * row["steps"] / 300)
    assert row["battery_left_wh"] == 0.0


def test_run_episode_survives_with_a_big_battery():
    row = run_episode(UAVEnv(battery_wh=1000.0), make_policy("B0"), 3)
    assert row["survived"] and row["steps"] == 300
    assert row["coverage_full"] == pytest.approx(row["coverage_alive"])


def test_summarize_builds_a_table_with_paired_differences():
    import pandas as pd
    rows = [{"policy": p, "seed": s, "mobility": "surge", "coverage_full": c + s * 0.01, "coverage_alive": c,
             "survived": True, "served_user_s_per_wh": 1.0, "outage_rescue": 0.1, "fairness": 0.5}
            for p, c in (("B0", 0.5), ("B1", 0.6)) for s in range(5)]
    text = summarize(pd.DataFrame(rows))
    assert "| B1 |" in text and "+0.100*" in text and "-0.100*" in text


def test_report_has_both_the_settings_header_and_the_tables():
    import pandas as pd
    rows = [{"policy": p, "seed": s, "mobility": "surge", "coverage_full": 0.5, "coverage_alive": 0.5,
             "survived": True, "served_user_s_per_wh": 1.0, "outage_rescue": 0.1, "fairness": 0.5}
            for p in ("B0", "B1") for s in range(3)]
    text = report(pd.DataFrame(rows), "hard", 16.0)
    assert text.startswith("Profile: hard.") and "battery 16 Wh" in text
    assert "| Policy |" in text and "Paired difference" in text and "by mobility model" in text


# ---------------------------------------------------------------- B6 (grid search + altitude)
def _score(env, target):
    """One-step coverage at a (x, y, h) target with full power."""
    return env.evaluate(target[0], target[1], target[2], env.p_max_w)[0]


def test_b6_candidate_set_contains_b3s_so_it_can_never_score_lower_for_one_step():
    from baselines import B6GridAltitude
    assert 150 in BCFG["altitude_levels_m"] and BCFG["altitude_m"] == 150     # B3 searches at 150 m
    for seed in (2, 3, 4):
        env = _env(seed=seed)
        b3, b6 = B3GridSearch(), B6GridAltitude()
        for p in (b3, b6):
            p.reset(env)
            p.plan(env)
        assert _score(env, b6.target) >= _score(env, b3.target) - 1e-12


def test_b6_picks_the_altitude_the_landscape_rewards(monkeypatch):
    from baselines import B6GridAltitude
    env = _env()
    pol = B6GridAltitude()
    pol.reset(env)
    monkeypatch.setattr(env, "evaluate", lambda X, Y, H, p: np.where(np.atleast_1d(H) == 50.0, 0.9, 0.2))
    pol.plan(env)
    assert pol.target[2] == 50.0


def test_b6_targets_stay_inside_the_allowed_space():
    from baselines import B6GridAltitude
    env = _env()
    pol = B6GridAltitude()
    pol.reset(env)
    pol.plan(env)
    x, y, h = pol.target
    assert 0 <= x <= env.L and 0 <= y <= env.L and h in BCFG["altitude_levels_m"] + [env.h]


# ---------------------------------------------------------------- information ladder: B3obs, B3obsU, B3obsUO
LADDER = ("B3obs", "B3obsU", "B3obsUO")


def _plan(name, env):
    pol = make_policy(name)
    pol.reset(env)
    pol.plan(env)
    return pol.target


def test_allocate_is_exact_proportional_and_deterministic():
    from baselines import allocate
    c = allocate(np.array([1.0, 1.0, 2.0, 0.0]), 10)
    assert c.sum() == 10 and c[3] == 0 and c[2] == 5 and sorted(c[:2]) == [2, 3]
    assert (allocate(np.array([1.0, 1.0, 2.0, 0.0]), 10) == c).all()
    assert allocate(np.zeros(4), 10).sum() == 0


def test_pseudo_population_has_the_configured_size_and_valid_class_probabilities():
    from baselines import B3Obs, pseudo_population
    env = _env()
    xy, probs = pseudo_population(env, *B3Obs().maps(env))
    assert len(xy) == BCFG["obs_pseudo_users"] and len(xy) % 2 == 0
    assert probs.shape == (len(xy), len(md.CFG["classes"])) and np.allclose(probs.sum(axis=1), 1.0)
    r = list(md.CFG["classes"]).index("rescue")
    assert (probs[:, r] == 1).sum() == round(BCFG["obs_pseudo_users"] * md.CFG["classes"]["rescue"]["share"])
    assert ((0 <= xy) & (xy <= env.L)).all()


def test_b3obs_reads_exactly_the_agents_maps():
    from baselines import B3Obs
    env = _env()
    a, r = B3Obs().maps(env)
    obs = env.observation(("heat_all", "heat_rescue"))
    assert np.array_equal(np.concatenate([a, r]), obs.astype(float))
    assert a.max() <= 1.0                                                  # capped, like the agent's view


def test_uncapped_maps_are_true_shares_and_differ_from_the_capped_view_on_one_dominant_cell():
    from baselines import B3Obs, B3ObsUncapped
    env = _env(scenario_overrides={"n_clusters": 1, "cluster_radius_m": 20.0, "scatter_fraction": 0.1})
    capped, _ = B3Obs().maps(env)
    true, true_r = B3ObsUncapped().maps(env)
    assert true.sum() == pytest.approx(1.0) and true_r.sum() == pytest.approx(1.0)
    assert true.max() > 0.5                                                # one cell holds most users
    assert capped.max() == 1.0                                             # ... but the agent's map saturates
    # in the capped view the crowd's cell weighs far less relative to the scattered users
    assert capped.max() / capped.sum() < true.max() / true.sum() - 0.2


def _moved_within_cells(env):
    """Move every user to the centre of its heatmap cell (same maps, different exact positions)."""
    from baselines import cell_centres
    xy = env.user_xy()
    ix = np.clip((xy / (env.L / env.grid)).astype(int), 0, env.grid - 1)
    return cell_centres(env)[ix[:, 0] * env.grid + ix[:, 1]]


@pytest.mark.parametrize("name", ["B3obs", "B3obsU"])
def test_ladder_ignores_hidden_information(name):
    for seed in (2, 3, 4):
        env = _env(seed=seed)
        before = _plan(name, env)
        env.P = env.P.copy()
        env.P[env.t] = _moved_within_cells(env)                            # exact positions inside cells
        env.min_rate = np.full_like(env.min_rate, 10 ** 9)                 # every class hidden
        env.boxes = np.array([[0.0, 0.0, env.L, env.L]])                   # a wall over everything
        assert _plan(name, env) == before


def test_b3obsuo_does_see_obstacles():
    from baselines import B3ObsUncappedObstacles
    env = _env(seed=3)
    pol = B3ObsUncappedObstacles()
    pol.reset(env)
    X, Y = np.array([env.x, 100.0]), np.array([env.y, 900.0])
    H = np.full(2, BCFG["altitude_m"])
    open_sky = pol.score(env, X, Y, H, env.p_max_w)
    env.boxes = np.array([[0.0, 0.0, env.L, env.L]])
    assert (pol.score(env, X, Y, H, env.p_max_w) < open_sky).any()
    # and it still ignores exact positions inside cells and the users' classes
    env = _env(seed=3)
    before = _plan("B3obsUO", env)
    env.P = env.P.copy()
    env.P[env.t] = _moved_within_cells(env)
    env.min_rate = np.full_like(env.min_rate, 10 ** 9)
    assert _plan("B3obsUO", env) == before


def test_b3obs_does_see_the_rescue_map():
    from baselines import B3Obs
    env = _env(seed=3)
    pol = B3Obs()
    pol.reset(env)
    X, Y, H = np.array([env.x, 100.0, 900.0]), np.array([env.y, 900.0, 100.0]), np.full(3, BCFG["altitude_m"])
    before = pol.score(env, X, Y, H, env.p_max_w)
    env.rescue = ~env.rescue                                               # a different rescue map
    assert not np.allclose(pol.score(env, X, Y, H, env.p_max_w), before)


@pytest.mark.parametrize("name", ("B3",) + LADDER)
def test_with_one_tight_crowd_every_rung_goes_to_it(name):
    env = _env(seed=3, scenario_overrides={"n_clusters": 1, "cluster_radius_m": 30.0, "scatter_fraction": 0.0,
                                           "n_obstacles": 0})
    crowd = env.user_xy().mean(axis=0)
    pol = make_policy(name)
    pol.reset(env)
    pol.power = 1e-3          # 0 dBm: at full power coverage is nearly flat on the 1 km map, position barely matters
    pol.plan(env)
    x, y, _ = pol.target
    spacing = env.L / (BCFG["grid_n"] - 1)
    assert np.hypot(x - crowd[0], y - crowd[1]) < spacing                   # the nearest grid point or better


def test_b3_refactor_kept_b3_scoring_on_the_true_model():
    env = _env(seed=3)
    pol = B3GridSearch()
    pol.reset(env)
    X, Y, H = np.array([env.x, 100.0]), np.array([env.y, 900.0]), np.full(2, BCFG["altitude_m"])
    assert np.array_equal(pol.score(env, X, Y, H, env.p_max_w), env.evaluate(X, Y, H, env.p_max_w))
