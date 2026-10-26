"""Tests for the simulated quadcopter (quadsim.py), its hook into UAVEnv (dynamics="quad") and the 3D-flight data.
Run: python -m pytest test_quadsim.py"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import dashboard_core as dc
import make_dataset as md
import quadsim
from baselines import POLICIES, make_policy
from quadsim import QuadSim, wind_overrides
from rl_utils import RandomPolicy
from uav_env import UAVEnv

HERE = Path(__file__).parent
BOUNDS = (0.0, 2000.0, 0.0, 2000.0, 50.0, 300.0)
SMALL = {"n_users": 100}
CALM = wind_overrides(False)
WINDY = wind_overrides(True)


@pytest.fixture(autouse=True)
def back_to_default():
    md.apply_profile("default")
    yield
    md.apply_profile("default")                      # a profile must never leak into other tests


def sim(seed=1, **over):
    s = QuadSim(seed=seed, bounds=BOUNDS, overrides=over or CALM)
    s.reset(1000.0, 1000.0, 150.0)
    return s


def fly(s, v, seconds):
    outs = [s.fly(v, 1.0) for _ in range(int(seconds))]
    return outs


# ---------------------------------------------------------------- the model on its own
def test_config_is_off_by_default_and_mass_comes_from_the_energy_section():
    assert md.CFG["quad"]["enabled"] is False
    assert UAVEnv().dynamics == "point" and UAVEnv().quad is None
    s = QuadSim()
    assert s.m == pytest.approx(md.CFG["energy"]["weight_n"] / md.CFG["energy"]["g_mps2"])     # 2.04 kg
    assert s.c2 == pytest.approx(0.5 * 0.6 * 1.225 * 0.05 * 0.503)                             # Zeng's fuselage drag
    assert md.CFG["quad"]["wind"]["mean_mps"] == 0.0 and md.CFG["quad"]["wind"]["gust_std_mps"] == 0.0


def test_hover_holds_position_and_altitude_in_calm_air():
    s = sim()
    outs = fly(s, (0.0, 0.0, 0.0), 60)
    P = np.array([o["pos"] for o in outs])
    assert np.abs(P - [1000.0, 1000.0, 150.0]).max() < 1e-6          # trimmed start: it just stays
    assert outs[-1]["thrust_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert max(o["tilt_peak"] for o in outs) < 1e-6


def test_returns_after_a_kick():
    """A sudden push (as from a gust front): it drifts, the position loop brings it back, without wild overshoot."""
    s = sim()
    s.vx, s.vy, s.vz = 4.0, -3.0, 1.5
    outs = fly(s, (0.0, 0.0, 0.0), 20)
    P = np.array([o["pos"] for o in outs])
    dev = np.hypot(P[:, 0] - 1000.0, P[:, 1] - 1000.0)
    assert dev.max() > 0.5                                             # it really was pushed away
    assert dev.max() < 15.0 and abs(P[:, 2] - 150.0).max() < 5.0       # leash-bounded excursion
    assert dev[-1] < 0.1 and abs(P[-1, 2] - 150.0) < 0.05              # and it came back


@pytest.mark.parametrize("v", [5.0, 10.0, 15.0])
def test_velocity_step_settles_with_bounded_overshoot(v):
    s = sim()
    outs = fly(s, (v, 0.0, 0.0), 15)
    vx = np.array([o["vel"][0] for o in outs])
    assert abs(vx[-1] - v) < 0.05 and abs(outs[-1]["vel"][1]) < 1e-6
    assert max(o["speed_peak"] for o in outs) <= v * 1.05 + 0.02       # overshoot <= 5% (measured 3.3%)
    assert abs(outs[-1]["pos"][2] - 150.0) < 0.2                       # altitude held while accelerating
    # acceleration is limited (setpoint shaping): it cannot reach v in the first second like the point-mass game
    assert vx[0] < min(v, md.CFG["quad"]["shape_acc_xy_mps2"] + 0.5)


def test_climb_step_reaches_the_commanded_rate():
    s = sim()
    outs = fly(s, (0.0, 0.0, 4.0), 10)
    assert abs(outs[-1]["vel"][2] - 4.0) < 0.05
    assert outs[-1]["pos"][2] > 150.0 + 4.0 * 7


@pytest.mark.parametrize("wind", [False, True])
def test_tilt_and_speed_limits_hold_under_random_commands(wind):
    """60 s of random setpoints (worse than any pilot): the tilt SETPOINT is capped at tilt_max; the real attitude
    may lag past it by a fraction of a degree (motor delay), so tilt <= tilt_max + 0.5 deg. Horizontal speed within
    3% of v_max in calm air (gusts can add their own speed in wind), climb rate bounded."""
    s = sim(seed=4, **(WINDY if wind else CALM))
    rng = np.random.default_rng(0)
    u = md.CFG["uav"]
    tilt_lim = math.radians(md.CFG["quad"]["tilt_max_deg"] + 0.5)
    for _ in range(60):
        a = rng.uniform(-1, 1, 3)
        o = s.fly((a[0] * u["v_max_mps"], a[1] * u["v_max_mps"], a[2] * u["vz_max_mps"]), 1.0)
        assert o["tilt_peak"] <= tilt_lim
        assert o["speed_peak"] <= u["v_max_mps"] * (1.03 if not wind else 1.15)
        assert abs(o["vel"][2]) <= u["vz_max_mps"] * 1.1


def test_geofence_keeps_it_inside_the_map_and_altitude_band():
    s = QuadSim(seed=2, bounds=BOUNDS, overrides=CALM)
    s.reset(60.0, 1940.0, 60.0)                                       # near a corner, low
    outs = fly(s, (-15.0, 15.0, -5.0), 20)
    P = np.array([o["pos"] for o in outs])
    assert P[:, 0].min() > -2.0 and P[:, 1].max() < 2002.0 and P[:, 2].min() > 48.0
    s.reset(1000.0, 1000.0, 290.0)
    P = np.array([o["pos"] for o in fly(s, (0.0, 0.0, 5.0), 10)])
    assert P[:, 2].max() < 302.0


def test_wind_drift_is_only_transient():
    """Mean wind 5 m/s + gusts: the drone holds its spot within a metre. A sudden wind change (calm -> 8 m/s) pushes
    it away briefly; the integrator learns the new drag and it returns."""
    s = sim(seed=3, **WINDY)
    P = np.array([o["pos"] for o in fly(s, (0.0, 0.0, 0.0), 120)])
    dev = np.hypot(P[:, 0] - 1000.0, P[:, 1] - 1000.0)
    assert dev.max() < 1.0 and abs(P[:, 2] - 150.0).max() < 0.5
    s = sim()
    s.w_mean = (8.0, 0.0, 0.0)                                         # sudden wind change
    P = np.array([o["pos"] for o in fly(s, (0.0, 0.0, 0.0), 30)])
    dev = np.hypot(P[:, 0] - 1000.0, P[:, 1] - 1000.0)
    assert dev.max() > 0.3 and dev[-1] < 0.05


def test_gusts_are_seeded_and_have_the_configured_size():
    a, b = sim(seed=9, **WINDY), sim(seed=9, **WINDY)
    oa, ob = fly(a, (3.0, 1.0, 0.0), 30), fly(b, (3.0, 1.0, 0.0), 30)
    assert all(x["pos"] == y["pos"] for x, y in zip(oa, ob, strict=True))
    s = QuadSim(seed=5, bounds=BOUNDS, overrides=WINDY)
    s.reset(1000.0, 1000.0, 150.0)
    gx = [s.fly((0.0, 0.0, 0.0), 1.0)["wind"][0] - s.w_mean[0] for _ in range(600)]
    std = md.CFG["quad"]["wind_on"]["gust_std_mps"]
    assert 0.5 * std < np.std(gx) < 1.5 * std                          # stationary std (correlated: rough check)


def test_integration_step_does_not_change_the_answer():
    def run(dt):
        s = QuadSim(seed=1, bounds=BOUNDS, overrides={**CALM, "dt_s": dt})
        s.reset(1000.0, 1000.0, 150.0)
        for v in [(15, 0, 3), (15, 0, 3), (15, 0, 3), (0, 10, -2), (0, 10, -2), (0, 0, 0), (0, 0, 0), (0, 0, 0)] * 3:
            o = s.fly(v, 1.0)
        return np.array(o["pos"])
    assert np.abs(run(0.01) - run(0.005)).max() < 0.5


# ---------------------------------------------------------------- energy follows the flown speed
def test_energy_matches_zeng_at_the_flown_airspeed():
    p_w = 0.1
    env = UAVEnv(dynamics="quad", quad_overrides=CALM, scenario_overrides=SMALL)
    env.reset(seed=3)
    for _ in range(3):
        _, _, _, _, info = env.step(np.array([0.0, 0.0, 0.0, 2 * p_w / env.p_max_w - 1]))
    assert info["energy_step_j"] == pytest.approx(float(md.energy_step_j(0.0, 0.0, p_w)), rel=1e-9)   # hover
    for _ in range(20):                                                 # steady cruise at 10 m/s east
        _, _, _, _, info = env.step(np.array([10.0 / env.uav["v_max_mps"], 0.0, 0.0, 2 * p_w / env.p_max_w - 1]))
    assert np.hypot(env.vx, env.vy) == pytest.approx(10.0, abs=0.02)
    assert info["energy_step_j"] == pytest.approx(float(md.energy_step_j(10.0, 0.0, p_w)), rel=2e-3)
    # in a steady wind the rotors see the AIRSPEED: hovering in 5 m/s wind costs Zeng's power at 5 m/s
    env = UAVEnv(dynamics="quad", quad_overrides={"wind": {"mean_mps": 5.0}}, scenario_overrides=SMALL)
    env.reset(seed=3)
    _, _, _, _, info = env.step(np.array([0.0, 0.0, 0.0, 2 * p_w / env.p_max_w - 1]))
    assert info["energy_step_j"] == pytest.approx(float(md.energy_step_j(5.0, 0.0, p_w)), rel=1e-6)


def test_energy_includes_climb_and_the_acceleration_term_when_enabled():
    md.CFG["uav"]["a_max_mps2"] = 4.0                                   # switches the turning-energy term on
    env = UAVEnv(dynamics="quad", quad_overrides=CALM, scenario_overrides=SMALL)
    env.reset(seed=3)
    _, _, _, _, info = env.step(np.array([1.0, 0.0, 1.0, 1.0]))       # speeding up + climbing
    steady = md.energy_step_j(np.hypot(env.vx, env.vy), 0.0, env.p_max_w)
    assert info["energy_step_j"] > steady + 0.5 * md.CFG["energy"]["weight_n"] * 0.5


# ---------------------------------------------------------------- the env hook
FINGERPRINTS = {   # computed with the code BEFORE Stage 5 (commit ea840a5): the point-mass game must not change
    ("default", "random"): (222, 273366.4358534013, 703238.8758272924, 0.0),
    ("sites_d20_t0_ann", "random"): (300, 638759.04163829, 1382800.6344608637, 5943.11361286759),
    ("default", "B6"): (191, 241974.1740258155, 651594.4624499278, 0.0),
}


def stored(*key):
    """The stored fingerprint, compared to 1e-12 relative: numpy's exp/log kernels differ by CPU type (CI runners vary)
    in the last bits; any real change to the game is many orders of magnitude larger."""
    return pytest.approx(FINGERPRINTS[key], rel=1e-12, abs=1e-9)


def fingerprint(env, act, seed):
    env.reset(seed=seed)
    rows, done = [], False
    while not done:
        _, r, te, tr, info = env.step(act(env))
        rows.append((env.x, env.y, env.h, env.vx, env.vy, env.vz, info["coverage"], info["energy_step_j"], r))
        done = te or tr
    a = np.array(rows)
    return len(rows), float(a.sum()), float((a * np.arange(1, a.shape[1] + 1)).sum()), env.energy_left_j


@pytest.mark.parametrize("dynamics", [None, "point"])
def test_dynamics_off_is_bit_exact(dynamics):
    acts = np.random.default_rng(11).uniform(-1, 1, (400, 4))
    for prof in ("default", "sites_d20_t0_ann"):
        md.apply_profile(prof)
        assert fingerprint(UAVEnv(dynamics=dynamics), lambda e: acts[e.t], 3) == stored(prof, "random")
    md.apply_profile("default")
    p = make_policy("B6")
    env = UAVEnv(dynamics=dynamics)
    env.reset(seed=4)
    p.reset(env)
    assert fingerprint(env, p.act, 4) == stored("default", "B6")


def test_quad_mode_logs_the_flight_and_leaves_the_env_rng_alone():
    acts = np.random.default_rng(2).uniform(-1, 1, (30, 4))
    pt = UAVEnv(scenario_overrides=SMALL)
    qd = UAVEnv(dynamics="quad", quad_overrides=WINDY, scenario_overrides=SMALL)
    pt.reset(seed=6)
    qd.reset(seed=6)
    for a in acts:
        pt.step(a)
        _, _, _, _, info = qd.step(a)
    assert pt.rng.bit_generator.state == qd.rng.bit_generator.state     # gusts use their own stream
    assert len(qd.flight) == 1 + 30 * 5                                  # 5 Hz log incl. the start
    assert set(info["quad"]) >= {"roll_deg", "pitch_deg", "tilt_peak_deg", "wind_mps", "airspeed_mps"}
    assert "quad" not in pt.step(acts[0])[4]
    assert (pt.x, pt.y) != (qd.x, qd.y)                                  # it really flew differently


def test_quad_lags_behind_the_point_mass():
    pt, qd = UAVEnv(scenario_overrides=SMALL), UAVEnv(dynamics="quad", quad_overrides=CALM, scenario_overrides=SMALL)
    pt.reset(seed=1)
    qd.reset(seed=1)
    pt.step(np.array([1.0, 0.0, 0.0, 1.0]))
    qd.step(np.array([1.0, 0.0, 0.0, 1.0]))
    assert pt.x - 500.0 == pytest.approx(15.0) and 0.5 < qd.x - 500.0 < 5.0


def test_every_pilot_and_random_fly_the_quad():
    for name in [*POLICIES, "random"]:
        env = UAVEnv(dynamics="quad", quad_overrides=WINDY, scenario_overrides=SMALL)
        env.reset(seed=2)
        pol = RandomPolicy("goto") if name == "random" else make_policy(name)
        pol.reset(env)
        for _ in range(12):
            _, r, term, trunc, info = env.step(pol.act(env))
            assert np.isfinite([env.x, env.y, env.h, r]).all()
        assert -2.0 <= env.x <= env.L + 2.0 and env.uav["h_min_m"] - 2.0 <= env.h <= env.uav["h_max_m"] + 2.0


def test_the_showcase_ai_flies_the_quad():
    pytest.importorskip("stable_baselines3")
    from rl_utils import load_policy
    md.apply_profile("rl_static")
    pol = load_policy(str(HERE / "models" / "e0_best_ai" / "model.zip"))
    env = UAVEnv(dynamics="quad", quad_overrides=WINDY)
    env.reset(seed=100)
    pol.reset(env)
    for _ in range(25):
        _, r, _, _, info = env.step(pol.act(env))
    assert np.isfinite(r) and info["coverage"] >= 0.0


# ---------------------------------------------------------------- 3D flight data and page
def test_flight3d_is_json_serialisable_and_bounded():
    s = dc.Settings(profile="default", seed=3, n_users=1000, mobility="surge")
    d = dc.flight3d(s, "B3", wind=True, max_users=400)
    text = json.dumps(d)
    assert len(text) < 1_500_000
    assert d["users"]["n_drawn"] == 400 and all(len(f["s"]) == 400 for f in d["users"]["frames"])
    assert "xy" in d["users"]["frames"][0] and len(d["users"]["frames"][0]["xy"]) == 800
    assert len(d["drone"]["t"]) == 1 + d["steps_flown"] * 5                     # 5 Hz
    assert len(d["sec"]["coverage"]) == d["steps_flown"] and d["wind"]["on"] is True
    assert all(15.0 <= b[4] <= 30.0 for b in d["buildings"])                    # display-only heights
    assert d["summary"]["max_tilt_deg"] <= md.CFG["quad"]["tilt_max_deg"] + 0.5
    assert dc.flight3d(s, "B3", wind=True, max_users=400) is d                  # cached
    calm = dc.flight3d(s, "B3", wind=False, max_users=400)
    assert calm["wind"]["mean_mps"] == 0.0 and calm is not d


def test_flight3d_marks_inactive_users_on_competing_sites():
    s = dc.Settings(profile="sites_d20_t0_ann", seed=1, n_users=100)
    d = dc.flight3d(s, "B0", wind=False)
    codes = "".join(f["s"] for f in d["users"]["frames"])
    assert "2" in codes and set(codes) <= {"0", "1", "2"}
    assert max(d["sec"]["n_active"]) <= d["users"]["n_pool"]


def test_viewer_html_embeds_the_data_and_only_pinned_scripts():
    d = dc.flight3d(dc.Settings(profile="default", seed=2, n_users=100), "B0")
    html = dc.viewer3d_html(d, "dark")
    assert "__FLIGHT_JSON__" not in html and "__THEME__" not in html and 'data-theme="dark"' in html
    srcs = [line.split('src="')[1].split('"')[0] for line in html.splitlines() if "<script src=" in line]
    assert srcs == ["https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
                    "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"]
    tag = '<script id="flight" type="application/json">'
    start = html.index(tag) + len(tag)
    assert json.loads(html[start:html.index("</script>", start)])["seed"] == 2
    with pytest.raises(AssertionError):
        dc.viewer3d_html(d, "purple")


def test_dashboard_core_still_does_not_import_streamlit():
    code = "import sys, dashboard_core, quadsim; assert 'streamlit' not in sys.modules"
    r = subprocess.run([sys.executable, "-c", code], cwd=HERE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_quadsim_has_no_ui_or_rl_imports():
    src = (HERE / "quadsim.py").read_text(encoding="utf-8")
    for lib in ("streamlit", "matplotlib", "gymnasium", "stable_baselines3", "torch"):
        assert f"import {lib}" not in src and f"from {lib}" not in src
    assert quadsim.QuadSim is QuadSim
