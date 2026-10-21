"""Plan step 5: acceleration limit, the accelerating-flight energy term (our extension) and the loiter pilot B7.
Run: python -m pytest test_accel_loiter.py"""
import numpy as np
import pytest

import make_dataset as md
from baselines import B7Loiter, brake_speed, go_to, make_policy
from run_baselines import run_episode
from uav_env import UAVEnv

A_MAX = 4.0          # the value the experiments use when the limit is on


@pytest.fixture
def limit_on(monkeypatch):
    monkeypatch.setitem(md.CFG["uav"], "a_max_mps2", A_MAX)


def _env(seed=3, **kw):
    env = UAVEnv(**kw)
    env.reset(seed=seed)
    return env


def _flat_landscape(best_xyh):
    """A fake env.evaluate: coverage falls with distance from best_xyh, so B6/B7 choose it (fast, no radio)."""
    bx, by, bh = best_xyh

    def evaluate(X, Y, H, p_w):
        X, Y, H = (np.atleast_1d(np.asarray(a, dtype=float)) for a in (X, Y, H))
        return 1.0 / (1.0 + np.hypot(X - bx, Y - by) / 100.0 + np.abs(H - bh) / 100.0)
    return evaluate


# ---------------------------------------------------------------- limit OFF = the old model, bit for bit
def _old_step_kinematics(state, action, uav, L, dt):
    """The ORIGINAL UAVEnv.step kinematics and energy (copied before plan step 5)."""
    x, y, h = state
    a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
    vh = a[:2] * uav["v_max_mps"]
    norm = np.linalg.norm(vh)
    if norm > uav["v_max_mps"]:
        vh *= uav["v_max_mps"] / norm
    vz = a[2] * uav["vz_max_mps"]
    p_w = max(1e-3, 10 ** ((uav["p_max_dbm"] - 30) / 10) * (a[3] + 1) / 2)
    nx, ny = np.clip(x + vh[0] * dt, 0, L), np.clip(y + vh[1] * dt, 0, L)
    nh = np.clip(h + vz * dt, uav["h_min_m"], uav["h_max_m"])
    vx, vy, vzr = (nx - x) / dt, (ny - y) / dt, (nh - h) / dt
    e = md.CFG["energy"]
    v = np.hypot(vx, vy)
    prop = (e["P0_w"] * (1 + 3 * v**2 / e["Utip_mps"] ** 2)
            + e["Pi_w"] * np.sqrt(np.sqrt(1 + v**4 / (4 * e["v0_mps"] ** 4)) - v**2 / (2 * e["v0_mps"] ** 2))
            + 0.5 * e["d0"] * e["rho_kg_m3"] * e["s"] * e["A_m2"] * v**3)
    energy = (prop + e["weight_n"] * max(vzr, 0.0) + p_w / e["pa_efficiency"] + e["P_circuit_w"]) * e["dt_s"]
    return (float(nx), float(ny), float(nh)), (vx, vy, vzr), float(energy)


def test_limit_off_reproduces_the_old_trajectory_and_energy_exactly():
    assert md.CFG["uav"]["a_max_mps2"] is None                         # the default is OFF
    env = _env(seed=7)
    rng = np.random.default_rng(0)
    state = (env.x, env.y, env.h)
    for t in range(120):
        act = rng.uniform(-1.3, 1.3, 4) if t % 7 else np.array([1.0, 1.0, 1.0, 1.0])   # hits walls too
        state, vel, energy = _old_step_kinematics(state, act, env.uav, env.L, env.dt)
        info = env.step(act)[4]
        assert (env.x, env.y, env.h) == state and (env.vx, env.vy, env.vz) == vel
        assert info["energy_step_j"] == energy                       # exact, not approx


def test_go_to_is_unchanged_when_the_limit_is_off():
    env = _env()
    rng = np.random.default_rng(1)
    u = env.uav
    for _ in range(50):
        tx, ty, th = rng.uniform(0, env.L), rng.uniform(0, env.L), rng.uniform(50, 300)
        d = np.array([tx - env.x, ty - env.y]) / (u["v_max_mps"] * env.dt)
        n = np.linalg.norm(d)
        if n > 1.0:
            d = d / n
        old = np.array([d[0], d[1], np.clip((th - env.h) / (u["vz_max_mps"] * env.dt), -1, 1), 1.0])
        assert np.array_equal(go_to(env, tx, ty, th, 1.0), old)
        env.step(rng.uniform(-1, 1, 4))


def test_energy_step_without_acceleration_is_zengs_value():
    for v in (0.0, 5.0, 10.2, 15.0):
        assert md.energy_step_j(v, 1.0, 0.1) == md.energy_step_j(v, 1.0, 0.1, None)
        assert md.energy_step_j(v, 1.0, 0.1, 0.0) == pytest.approx(md.energy_step_j(v, 1.0, 0.1), rel=1e-12)


# ---------------------------------------------------------------- load factor (our extension)
def test_load_factor_is_one_at_rest_and_monotone():
    assert md.load_factor(0.0) == 1.0
    a = np.linspace(0, 20, 201)
    k = md.load_factor(a)
    assert np.all(np.diff(k) > 0)
    assert md.load_factor(md.CFG["energy"]["g_mps2"]) == pytest.approx(np.sqrt(2.0))
    # more load = more induced power at every speed
    for v in (0.0, 5.0, 10.0, 15.0):
        p = md.propulsion_power_w(v, k)
        assert np.all(np.diff(p) > 0)


def test_load_factor_scales_hover_induced_power_by_kappa_to_1_5():
    e = md.CFG["energy"]
    kappa = 1.3
    assert md.propulsion_power_w(0.0, kappa) == pytest.approx(e["P0_w"] + e["Pi_w"] * kappa**1.5)


def test_min_power_speed_is_the_minimum_of_the_power_curve():
    vs = md.min_power_speed(15.0)
    v = np.linspace(0, 15, 3001)
    assert vs == pytest.approx(v[np.argmin(md.propulsion_power_w(v))], abs=0.01)
    assert 9.5 < vs < 11.0                                            # 10.2 m/s for this drone
    # on a circle the turn load lowers the best speed a little, and a_max caps it at sqrt(a_max r)
    assert md.min_power_speed(15.0, 50.0, 4.0) < vs
    assert md.min_power_speed(15.0, 20.0, 2.0) <= np.sqrt(2.0 * 20.0) + 1e-9


# ---------------------------------------------------------------- limit ON
def test_velocity_change_never_exceeds_a_max_dt(limit_on):
    env = _env(seed=5, battery_wh=1000.0)
    rng = np.random.default_rng(2)
    for _ in range(200):
        vx0, vy0, vz0 = env.vx, env.vy, env.vz
        info = env.step(rng.uniform(-1, 1, 4))[4]
        if 0 < env.x < env.L and 0 < env.y < env.L:                  # no geofence stop at the map edge
            assert np.hypot(env.vx - vx0, env.vy - vy0) <= A_MAX * env.dt + 1e-9
            assert info["accel_mps2"] <= A_MAX + 1e-9
        if env.uav["h_min_m"] < env.h < env.uav["h_max_m"]:
            assert abs(env.vz - vz0) <= env.uav["az_max_mps2"] * env.dt + 1e-9
        assert np.hypot(env.vx, env.vy) <= env.uav["v_max_mps"] + 1e-9


def _oscillate(env, pattern, n=100):
    vs = md.min_power_speed(env.uav["v_max_mps"])
    x0, y0, e = env.x, env.y, 0.0
    for t in range(n):
        s = pattern[t % len(pattern)]
        e += env.step(np.array([s * vs / env.uav["v_max_mps"], 0.0, 0.0, 1.0]))[4]["energy_step_j"]
    return np.hypot(env.x - x0, env.y - y0), e / n


def test_without_the_limit_the_oscillation_exploit_exists():
    env = _env(battery_wh=1000.0)
    moved, e = _oscillate(env, [1, -1])
    assert moved < 1e-9 and e < 0.85 * md.energy_step_j(0.0, 0.0, env.p_max_w)      # the old loophole


def test_the_limit_closes_the_oscillation_exploit(limit_on):
    hover = md.energy_step_j(0.0, 0.0, UAVEnv().p_max_w)
    # strict +v*, -v* alternation: from rest the velocity only swings 0 <-> +a_max*dt, so the drone drifts
    # (it no longer stays put) and pays at least hover power
    env = _env(battery_wh=1000.0)
    _, e = _oscillate(env, [1, -1])
    assert e >= 0.97 * hover
    # the symmetric pattern that DOES keep it in place (+, -, -, +): velocity 4, 0, -4, 0 m/s
    env = _env(battery_wh=1000.0)
    moved, e = _oscillate(env, [1, -1, -1, 1])
    assert moved < 10.0 and e >= 0.97 * hover


def test_energy_per_step_is_turn_power_plus_comm_plus_circuit(limit_on):
    env = _env(battery_wh=1000.0)
    e = md.CFG["energy"]
    rng = np.random.default_rng(3)
    for _ in range(40):
        vx0, vy0 = env.vx, env.vy
        act = np.append(rng.uniform(-1, 1, 2), [0.0, rng.uniform(-1, 1)])
        info = env.step(act)[4]
        a = np.hypot(env.vx - vx0, env.vy - vy0) / env.dt
        expect = (md.propulsion_power_w(np.hypot(env.vx, env.vy), md.load_factor(a)) + e["weight_n"] * max(env.vz, 0)
                  + info["p_tx_w"] / e["pa_efficiency"] + e["P_circuit_w"]) * e["dt_s"]
        assert info["energy_step_j"] == pytest.approx(expect, rel=1e-12)


def test_accel_energy_flag_off_keeps_the_limit_but_not_the_energy_term(limit_on, monkeypatch):
    monkeypatch.setitem(md.CFG["energy"], "accel_power", False)
    env = _env(battery_wh=1000.0)
    info = env.step(np.array([1.0, 0.0, 0.0, 1.0]))[4]
    assert env.vx == pytest.approx(A_MAX)
    assert info["energy_step_j"] == pytest.approx(md.energy_step_j(A_MAX, 0.0, info["p_tx_w"]))


def test_brake_speed_is_below_the_continuous_braking_curve():
    d = np.linspace(0, 500, 501)
    assert np.all(brake_speed(d, A_MAX, 1.0) <= np.sqrt(2 * A_MAX * d) + 1e-12)
    assert brake_speed(4.0, 4.0, 1.0) == pytest.approx(4.0)


@pytest.mark.parametrize("dist", [3.0, 37.0, 150.0, 600.0])
def test_go_to_reaches_the_target_without_overshoot(limit_on, dist):
    env = _env(battery_wh=1000.0)
    x0, y0, h0 = env.x, env.y, env.h
    ux, uy = 0.6, -0.8                                                 # a diagonal direction (stays in the map)
    tx, ty, th = x0 + ux * dist, y0 + uy * dist, h0 + 40.0
    along = []
    for _ in range(int(dist / 4) + 60):
        env.step(go_to(env, tx, ty, th, 1.0))
        along.append((env.x - x0) * ux + (env.y - y0) * uy)
    assert max(along) - dist <= 5.0                                    # overshoot <= 5 m
    assert np.hypot(env.x - tx, env.y - ty) < 0.5 and abs(env.h - th) < 0.5
    assert np.hypot(env.vx, env.vy) < 0.5


# ---------------------------------------------------------------- B7 loiter
GRID = np.linspace(0, md.CFG["area_m"], md.CFG["baselines"]["grid_n"])     # B6/B7 candidate grid
BEST = (float(GRID[5]), float(GRID[4]), 150.0)                                # a grid point


def _b7_run(env, steps, monkeypatch, best=BEST):
    monkeypatch.setattr(env, "evaluate", _flat_landscape(best))
    pol = make_policy("B7")
    pol.reset(env)
    rows = []
    for _ in range(steps):
        info = env.step(pol.act(env))[4]
        rows.append([env.x, env.y, env.h, np.hypot(env.vx, env.vy), info["energy_step_j"], info["accel_mps2"]])
        if info["battery_wh"] <= 0:
            break
    return pol, np.array(rows)


def test_b7_is_registered_but_not_in_the_default_run():
    import run_baselines
    assert "B7" in run_baselines.POLICIES and isinstance(make_policy("B7"), B7Loiter)
    import inspect
    assert 'p != "B7"' in inspect.getsource(run_baselines.main)


def test_b7_flies_a_circle_of_radius_r_at_the_loiter_speed(limit_on, monkeypatch):
    env = _env(battery_wh=1000.0)
    pol, R = _b7_run(env, 200, monkeypatch)
    cx, cy = pol.centre(env)
    assert (cx, cy) == pytest.approx(BEST[:2])
    tail = R[-60:]                                                     # established
    rad = np.hypot(tail[:, 0] - cx, tail[:, 1] - cy)
    assert np.all(np.abs(rad - pol.r) <= 0.1 * pol.r)
    vs = md.min_power_speed(env.uav["v_max_mps"])
    assert np.all(np.abs(tail[:, 3] - vs) <= 0.5)
    assert np.all(np.abs(tail[:, 3] - pol.v_loiter) <= 1e-6)
    assert np.all(tail[:, 5] <= A_MAX + 1e-9)
    assert np.all(np.abs(tail[:, 2] - 150.0) < 1e-6)
    # loitering costs less than hovering, and exactly P(v, kappa(v^2 / r)) + comm + circuit
    e = md.CFG["energy"]
    p_loiter = md.propulsion_power_w(pol.v_loiter, md.load_factor(pol.v_loiter**2 / pol.r))
    expect = (p_loiter + env.p_max_w / e["pa_efficiency"] + e["P_circuit_w"]) * e["dt_s"]
    assert tail[:, 4] == pytest.approx(np.full(len(tail), expect), rel=1e-9)
    assert expect < 0.8 * md.energy_step_j(0.0, 0.0, env.p_max_w)


@pytest.mark.parametrize("corner", [(0.0, 0.0, 300.0), (1000.0, 1000.0, 50.0), (0.0, 1000.0, 100.0)])
def test_b7_stays_inside_the_map_and_altitude_limits(limit_on, monkeypatch, corner):
    env = _env(battery_wh=1000.0)
    pol, R = _b7_run(env, 250, monkeypatch, best=corner)
    u = env.uav
    assert np.all((R[:, 0] >= 0) & (R[:, 0] <= env.L) & (R[:, 1] >= 0) & (R[:, 1] <= env.L))
    assert np.all((R[:, 2] >= u["h_min_m"]) & (R[:, 2] <= u["h_max_m"]))
    cx, cy = pol.centre(env)
    assert pol.r <= cx <= env.L - pol.r and pol.r <= cy <= env.L - pol.r
    rad = np.hypot(R[-60:, 0] - cx, R[-60:, 1] - cy)
    assert np.all(np.abs(rad - pol.r) <= 0.1 * pol.r)


def test_b7_works_without_the_limit_too(monkeypatch):
    env = _env(battery_wh=1000.0)
    pol, R = _b7_run(env, 150, monkeypatch)
    assert pol.v_loiter == pytest.approx(md.min_power_speed(env.uav["v_max_mps"]))
    rad = np.hypot(R[-40:, 0] - BEST[0], R[-40:, 1] - BEST[1])
    assert np.all(np.abs(rad - pol.r) <= 0.1 * pol.r)


def test_b7_is_deterministic(limit_on):
    rows = [run_episode(UAVEnv(battery_wh=1.0), make_policy("B7"), 4) for _ in range(2)]
    assert rows[0] == rows[1]


def test_run_to_empty_matches_the_arithmetic_prediction(limit_on, monkeypatch):
    """Seed 3, a still crowd (static mobility), 3 Wh. Prediction:
        US_pred = US(t_e) + N * c_lap * E_left(t_e) / E_loiter
    t_e = first step on the established circle (after transit and climb), US(t_e) = user-seconds served until then,
    c_lap = mean coverage over the first full lap after t_e, E_left(t_e) = battery left then,
    E_loiter = P(v, kappa(v^2/r)) + comm + circuit (J per step, analytic). Must be within +-5% of the env's total."""
    monkeypatch.setitem(md.CFG["mobility"], "choices", ["static"])
    env = UAVEnv(battery_wh=3.0)
    env.reset(seed=3)
    monkeypatch.setattr(env, "evaluate", _flat_landscape(BEST))
    pol = make_policy("B7")
    pol.reset(env)
    e = md.CFG["energy"]
    e_loiter = (md.propulsion_power_w(pol.v_loiter, md.load_factor(pol.v_loiter**2 / pol.r))
                + env.p_max_w / e["pa_efficiency"] + e["P_circuit_w"]) * e["dt_s"]
    cov, est, us_e, left_e, done = [], None, 0.0, 0.0, False
    while not done:
        _, _, term, trunc, info = env.step(pol.act(env))
        cov.append(info["coverage"])
        done = term or trunc
        if est is None and info["energy_step_j"] == pytest.approx(e_loiter, rel=1e-9):
            est, us_e, left_e = env.t, env.served_user_s, env.energy_left_j
    assert term and not trunc and est is not None
    lap = int(np.ceil(2 * np.pi / pol.dtheta))
    c_lap = float(np.mean(cov[est:est + lap]))
    pred = us_e + env.sc["n_users"] * c_lap * left_e / e_loiter
    assert env.served_user_s == pytest.approx(pred, rel=0.05)
