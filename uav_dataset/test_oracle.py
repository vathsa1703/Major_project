"""Tests for the clairvoyant oracle (oracle.py) and UAVEnv.evaluate(..., t). Run: python -m pytest test_oracle.py"""
import re
from pathlib import Path

import numpy as np
import pytest

import make_dataset as md
import oracle as orc
from baselines import make_policy
from uav_env import UAVEnv

SMALL = {"n_users": 100, "mobility": "surge"}     # small, moving crowd: fast tests


@pytest.fixture(scope="module")
def small():
    """A small moving scenario (default profile) with its oracle nodes, coverage tensor and hop matrix."""
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=4)
    nodes = orc.oracle_nodes(env)
    cov = orc.coverage_tensor(env, nodes, cache=False)
    return env, nodes, cov, orc.hop_graph(nodes, len(nodes) - 1)


# ---------------------------------------------------------------- evaluate(t)
def test_evaluate_t_leaves_env_state_and_rng_untouched():
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=4)
    for _ in range(3):
        env.step(np.array([0.3, -0.2, 0.1, 1.0]))
    state = (env.x, env.y, env.h, env.t, env.energy_left_j)
    rng_before = env.rng.bit_generator.state
    env.evaluate([100.0, 500.0], [200.0, 500.0], [150.0, 100.0], env.p_max_w, t=250)
    assert (env.x, env.y, env.h, env.t, env.energy_left_j) == state
    assert env.rng.bit_generator.state == rng_before


def test_evaluate_t_defaults_to_now_and_uses_the_future_positions():
    env = UAVEnv(scenario_overrides=SMALL)
    env.reset(seed=4)
    X, Y, H = np.array([200.0, 800.0]), np.array([300.0, 700.0]), np.array([150.0, 150.0])
    assert np.array_equal(env.evaluate(X, Y, H, env.p_max_w), env.evaluate(X, Y, H, env.p_max_w, t=0))
    # the same as asking a copy of the scenario that has really reached t = 250
    later = UAVEnv(scenario_overrides=SMALL)
    later.reset(seed=4)
    later.t = 250
    assert np.array_equal(env.evaluate(X, Y, H, env.p_max_w, t=250), later.evaluate(X, Y, H, env.p_max_w))
    assert not np.array_equal(env.user_xy(0), env.user_xy(250))          # the crowd really moved (surge)


# ---------------------------------------------------------------- tensor
def test_nodes_are_b6_candidates_plus_the_start(small):
    env, nodes, cov, _ = small
    n_lv = len(md.CFG["baselines"]["altitude_levels_m"])
    assert nodes.shape == (md.CFG["baselines"]["grid_n"] ** 2 * n_lv + 1, 3)
    assert tuple(nodes[-1]) == (env.L / 2, env.L / 2, env.uav["start_h_m"])
    assert cov.shape == (len(orc.sample_times(env)), len(nodes))
    assert orc.sample_times(env)[:3].tolist() == [0, 5, 10] and orc.sample_times(env)[-1] == env.T - 5


def test_tensor_entries_equal_evaluate_at_spot_checks(small):
    env, nodes, cov, _ = small
    p_w = env.p_max_w * md.CFG["baselines"]["power_frac"]
    for i, n in [(0, 0), (7, 123), (30, len(nodes) - 1), (59, 250)]:
        t = orc.sample_times(env)[i]
        assert cov[i, n] == env.evaluate(*nodes[n], p_w, t=t)[0]


def test_tensor_cache_round_trip(small, tmp_path, monkeypatch):
    env, nodes, cov, _ = small
    monkeypatch.setattr(orc, "CACHE", tmp_path)
    first = orc.coverage_tensor(env, nodes, cache=True)
    assert len(list(tmp_path.glob("*.npz"))) == 1
    assert np.array_equal(first, cov) and np.array_equal(orc.coverage_tensor(env, nodes, cache=True), cov)


def test_segment_scores_average_the_two_samples_of_each_10s_segment(small):
    _, _, cov, _ = small
    S = orc.segment_scores(cov)
    assert S.shape == (cov.shape[0] // 2, cov.shape[1])
    assert np.allclose(S[3], (cov[6] + cov[7]) / 2)
    assert np.array_equal(orc.frozen_scores(cov)[3], cov[6])


# ---------------------------------------------------------------- planners
def test_frozen_first_decision_is_b6s(small):
    env, nodes, cov, _ = small
    env.reset(seed=4)
    b6 = make_policy("B6")
    b6.reset(env)
    b6.plan(env)
    j = orc.frozen_plan(cov, nodes, len(nodes) - 1)[0]
    assert np.allclose(nodes[j], b6.target)


def _assert_feasible(hops, graph, start, K):
    """Hops chain in time and space, each one is flyable in its number of decisions, the plan covers the horizon."""
    u, step = md.CFG["uav"], orc.decision_steps() * md.CFG["energy"]["dt_s"]
    reach_xy = u["v_max_mps"] * step * (1 + md.CFG["oracle"]["reach_slack"])
    nodes = graph.nodes
    k, node = 0, start
    for k0, i, j, t in hops:
        assert k0 == k and i == node and t >= 1 and graph.tau[i, j] == t
        assert np.hypot(*(nodes[j, :2] - nodes[i, :2])) <= t * reach_xy + 1e-9
        assert abs(nodes[j, 2] - nodes[i, 2]) <= t * u["vz_max_mps"] * step + 1e-9
        k, node = k0 + t, j
    assert k >= K and hops[-1][0] < K                     # the last hop may still be in flight at the end


def _toy():
    """3 x 3 lattice, 150 m spacing, altitudes 100 and 200 m (x-major order like oracle_nodes)."""
    g = np.array([0.0, 150.0, 300.0])
    X, Y = np.meshgrid(g, g, indexing="ij")
    return np.array([(x, y, h) for x, y in zip(X.ravel(), Y.ravel(), strict=True) for h in (100.0, 200.0)])


def test_every_dp_and_mpc_transition_is_feasible(small):
    _, nodes, cov, graph = small
    S = orc.segment_scores(cov)
    K, start = S.shape[0], len(nodes) - 1
    v, at, target, hops = orc.dp_plan(S, graph, start)
    _assert_feasible(hops, graph, start, K)
    assert v == pytest.approx(S[np.arange(K), at].sum())                   # value = the schedule's own score
    assert (target >= 0).all() and (at >= 0).all()
    for h in (3, 6):
        _, _, hops = orc.receding_plan(lambda k, H: S[k:k + H], graph, start, K, h)
        _assert_feasible(hops, graph, start, K)


def test_hop_durations_and_in_flight_waypoints():
    nodes = _toy()
    graph = orc.HopGraph(nodes)
    tau = graph.tau
    idx = {tuple(n): i for i, n in enumerate(nodes)}
    a = idx[0, 0, 100]
    assert tau[a, a] == 1                                  # staying
    assert tau[a, idx[150, 0, 100]] == 1                   # one cell: 150 m in 10 s
    assert tau[a, idx[150, 150, 100]] == 2                 # diagonal 212 m
    assert tau[a, idx[0, 0, 200]] == 2                     # 100 m climb at 5 m/s
    assert tau[a, idx[300, 0, 100]] == 2                   # two cells: 300 m
    assert tau[a, idx[300, 300, 200]] == 3                 # 424 m corner to corner
    # straight flight (0,0) -> (300,0): after 10 s the drone is ~154 m along, nearest node (150, 0)
    assert graph.path(a, idx[300, 0, 100]).tolist() == [idx[150, 0, 100], idx[300, 0, 100]]
    # climb while flying one cell: after 10 s at (150, 0, 150), equidistant altitudes -> the lower one (100)
    assert graph.path(a, idx[150, 0, 200]).tolist() == [idx[150, 0, 100], idx[150, 0, 200]]


def test_hop_graph_with_the_start_node_off_the_lattice(small):
    _, nodes, _, graph = small
    s = len(nodes) - 1
    assert graph.tau[s, s] == 1
    assert (graph.tau > 0).all()                           # no hop limit: every node reachable by a straight flight
    for j in (0, 77, s - 1):
        w = graph.path(s, j)
        assert len(w) == graph.tau[s, j] and w[-1] == j and (w[:-1] < s).all()


def _brute_force(S, graph, start):
    """Best schedule value by trying every hop sequence (same scoring as dp_plan, last hop may run past the end)."""
    K, N = S.shape

    def best(k, node):
        if k >= K:
            return 0.0
        vals = []
        for j in range(N):
            t = graph.tau[node, j]
            if t == 0:
                continue
            w = graph.path(node, j)
            vals.append(sum(S[k + m, w[m]] for m in range(min(t, K - k))) + best(k + t, j))
        return max(vals)

    return best(0, start)


@pytest.mark.parametrize("seed", range(5))
def test_dp_equals_brute_force_on_a_toy_grid(seed):
    nodes = _toy()
    graph = orc.HopGraph(nodes)
    S = np.random.default_rng(seed).uniform(size=(3, len(nodes)))
    v, at, _, hops = orc.dp_plan(S, graph, 0)
    assert v == pytest.approx(_brute_force(S, graph, 0))
    assert v == pytest.approx(S[np.arange(3), at].sum())
    _assert_feasible(hops, graph, 0, 3)
    # a receding horizon as long as the whole episode is the full DP
    at2, _, _ = orc.receding_plan(lambda k, H: S[k:k + H], graph, 0, 3, 3)
    assert orc.plan_score(S, at2) * 3 == pytest.approx(v)


def test_dp_flies_to_a_far_good_node_in_a_straight_line():
    nodes = _toy()
    graph = orc.HopGraph(nodes)
    goal = 17                                              # (300, 300, 200): 3 decisions away from node 0
    S = np.zeros((6, len(nodes)))
    S[:, goal] = 1.0
    v, at, target, hops = orc.dp_plan(S, graph, 0)
    assert v == pytest.approx(4.0) and at.tolist()[3:] == [goal] * 3 and target[0] == goal


def test_teleport_bound_is_at_least_every_plan_on_the_tensor(small):
    _, nodes, cov, graph = small
    plans, tele = orc.all_plans(cov, nodes, graph)
    assert set(plans) == {"dp", "mpc30", "mpc60", "frozen", "frozen_path"}
    for name in ("dp", "mpc30", "mpc60", "frozen_path"):
        assert tele.mean() >= plans[name]["model"] - 1e-12
        assert plans["dp"]["model"] >= plans[name]["model"] - 1e-12     # dp is optimal for the model
        assert len(plans[name]["target"]) == len(tele)


# ---------------------------------------------------------------- replay
def test_replay_is_deterministic_and_reports_env_coverage(small):
    env, nodes, cov, graph = small
    plans, _ = orc.all_plans(cov, nodes, graph)
    pol = orc.PlanPolicy(nodes, plans["dp"]["target"], "dp")
    c1, s1 = orc.episode_coverage(env, pol, 4)
    c2, s2 = orc.episode_coverage(env, pol, 4)
    assert np.array_equal(c1, c2) and s1 == s2
    assert c1.shape == (env.T,) and ((0 <= c1) & (c1 <= 1)).all()


def test_replay_counts_zero_after_battery_death():
    env = UAVEnv(scenario_overrides=SMALL, battery_wh=0.5)
    env.reset(seed=4)
    nodes = orc.oracle_nodes(env)
    pol = orc.PlanPolicy(nodes, np.full(env.T // orc.decision_steps(), len(nodes) - 1), "stay")
    c, steps = orc.episode_coverage(env, pol, 4)
    assert steps < env.T and (c[steps:] == 0).all() and c[:steps].max() > 0


def test_window_means():
    x = np.arange(300, dtype=float)
    assert orc.window_means(x, [[0, 60], [60, 180], [180, 300]]) == [29.5, 119.5, 239.5]
    assert orc.window_means(np.arange(30.0), [[0, 60]], dt=10.0) == [2.5]


def test_parse_seeds():
    assert orc.parse_seeds("0-3,100-101,7") == [0, 1, 2, 3, 100, 101, 7]


# ---------------------------------------------------------------- isolation from the AI
def test_oracle_is_not_imported_by_the_rl_code():
    here = Path(__file__).parent
    files = sorted(here.glob("rl_*.py"))
    assert files
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+oracle\b", text, re.M), f"{f.name} imports the oracle"
        assert "oracle" not in text.lower(), f"{f.name} mentions the oracle"
