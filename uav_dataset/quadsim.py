"""A simulated quadcopter that really flies (roadmap Stage 5): our own rigid-body model + autopilot, plain Python/NumPy.

Plain words: the old game moves the drone like a chess piece (the commanded velocity is applied at once). Here the
command goes to an AUTOPILOT, like a real flight controller in velocity-setpoint mode (ArduPilot GUIDED velocity /
PX4 offboard velocity). The autopilot tilts the drone to accelerate, the motors react with a small delay, wind and gusts
push it around, and it can only tilt so far (30 deg) and push so hard (2x its weight). The drone therefore lags,
overshoots and drifts a little, as a real one does.

    sim = QuadSim(seed=3, bounds=(0, 2000, 0, 2000, 50, 300))
    sim.reset(1000, 1000, 150)
    out = sim.fly((15.0, 0.0, 0.0), duration=1.0)      # velocity setpoint (m/s, east/north/up) held for 1 s
    out["pos"], out["vel"], out["att"]                   # state at the end; out["samples"] = 5 Hz log for the 3D view

Model (world frame x east, y north, z up; ZYX Euler angles roll phi, pitch theta, yaw psi):
  translational   m dv/dt = T z_b(phi, theta, psi) - m g e_z - c1 v_air - c2 |v_air| v_air,   v_air = v - wind
  rotational      I dw/dt = tau - w x (I w)                         (w = body rates p, q, r; I diagonal)
  kinematics      phi' = p + tan(theta)(q sin(phi) + r cos(phi)),  theta' = q cos(phi) - r sin(phi),
                  psi' = (q sin(phi) + r cos(phi)) / cos(theta)
  motors          T' = (T_cmd - T) / tau_m,  tau' = (tau_cmd - tau) / tau_m  (first-order lag; collective thrust and
                  body torques saturate independently: a simplification of a per-motor mixer)
  wind            mean vector + gusts: one first-order Gauss-Markov process per axis (Dryden-lite), exact
                  discretisation g[k+1] = a g[k] + sigma sqrt(1 - a^2) n[k], a = exp(-dt / tau_g), seeded
Autopilot (cascade, every integration step dt):
  1 setpoint shaping   geofence first: the command toward a fence (map edges, h_min/h_max) is cut to sqrt(2 (a/2) d).
                       The target velocity then moves toward it with acceleration <= shape_acc and jerk <= shape_jerk
                       (horizontal vector norm; vertical separately), the acceleration easing off on a sqrt(2 j dv)
                       curve (like ArduPilot's sqrt controller); target position = its integral (leash-limited).
  2 position + velocity  v_cmd = v_tgt + Kp (p_tgt - p)  (|v_cmd_h| <= v_max, |v_cmd_z| <= vz_max)
                       a_cmd = a_ff + Kv (v_cmd - v) + Ki * integral(v_cmd - v)  (integral clamped, frozen if saturated)
                       a_ff = target acceleration + (1 / ang_p) x target jerk (horizontal lead for the attitude lag)
  3 thrust vector      F = m (a_cmd + g e_z); tilt <= tilt_max (vertical first), |F| <= T_max; attitude setpoint from
                       the direction of F at yaw 0; collective T_cmd = F . z_b (thrust along the current body axis)
  4 attitude           an attitude TARGET follows the setpoint (sqrt controller with gain ang_p and angular acceleration
                       <= ang_acc_max); desired Euler rates = ang_p (target - angle) + target rate (feed-forward)
                       -> body rates, each |rate| <= rate_max (rate_ff false: ang_p (setpoint - angle) only)
  5 rates              tau_cmd = I K_rate (w_sp - w) + w x (I w), clipped to the torque the rotors can make
Energy is NOT computed here: the env passes the per-integration-step airspeed, climb rate and horizontal acceleration
to make_dataset.energy_step_j (Zeng's model, the same code path as the point-mass game).

Every parameter is in config.yaml `quad:` with its source or "ENGINEERING ASSUMPTION" and a sensitivity range.
Scalar Python floats in the inner loop on purpose: one drone, a short sequential time loop (100 steps per second);
small NumPy arrays would be ~10x slower here. Nothing loops over users.
"""
import copy
import math

import numpy as np

import make_dataset as md


def quad_config(overrides=None):
    """A copy of config `quad:` with `overrides` deep-merged (e.g. {"wind": {"mean_mps": 5}})."""
    q = copy.deepcopy(md.CFG["quad"])
    if overrides:
        md.deep_update(q, overrides)
    return q


def wind_overrides(on):
    """{"wind": ...} for the wind-on preset (quad.wind_on) or calm air; None keeps the configured wind."""
    if on is None:
        return {}
    if not on:
        return {"wind": {"mean_mps": 0.0, "gust_std_mps": 0.0, "gust_std_z_mps": 0.0}}
    return {"wind": copy.deepcopy(md.CFG["quad"]["wind_on"])}


class QuadSim:
    """One quadrotor + autopilot. bounds = (x_lo, x_hi, y_lo, y_hi, h_lo, h_hi) = the geofence (the env's map and
    altitude limits). seed seeds the gust process only (its own stream; the env's rng is never touched)."""

    def __init__(self, seed=0, bounds=None, cfg=None, overrides=None):
        q = quad_config(overrides) if cfg is None else cfg
        e, u = md.CFG["energy"], md.CFG["uav"]
        self.q = q
        self.g = float(e["g_mps2"])
        self.m = float(e["weight_n"]) / self.g                       # 20 N / g = 2.04 kg (Zeng's weight)
        self.W = self.m * self.g
        self.T_max = float(q["thrust_to_weight"]) * self.W
        self.T_min = float(q["min_thrust_frac"]) * self.W
        self.I = [float(v) for v in q["inertia_kg_m2"]]
        self.tau_rp_max = float(q["arm_m"]) * self.T_max / 4.0           # roll/pitch torque at full differential
        self.tau_yaw_max = float(q["yaw_torque_m"]) * self.T_max / 2.0
        self.c1 = float(q["drag_lin_n_s_m"])
        # quadratic drag = the fuselage drag of Zeng's parasite power, 0.5 d0 rho s A (same numbers as the energy model)
        self.c2 = 0.5 * e["d0"] * e["rho_kg_m3"] * e["s"] * e["A_m2"]
        self.tilt_max = math.radians(float(q["tilt_max_deg"]))
        self.rate_max = math.radians(float(q["rate_max_dps"]))
        self.v_max, self.vz_max = float(u["v_max_mps"]), float(u["vz_max_mps"])
        self.dt = float(q["dt_s"])
        self.sample_every = max(1, int(round(float(q["sample_every_s"]) / self.dt)))
        w = q["wind"]
        th = math.radians(float(w["dir_deg"]))
        self.w_mean = (float(w["mean_mps"]) * math.cos(th), float(w["mean_mps"]) * math.sin(th), 0.0)
        self.g_std = (float(w["gust_std_mps"]), float(w["gust_std_mps"]), float(w["gust_std_z_mps"]))
        self.g_a = math.exp(-self.dt / float(w["gust_tau_s"]))
        self.bounds = bounds if bounds is not None else (-math.inf, math.inf, -math.inf, math.inf,
                                                         float(u["h_min_m"]), float(u["h_max_m"]))
        self.rng = np.random.default_rng([int(seed), 7])

    # ------------------------------------------------------------------ state
    def wind(self):
        return tuple(m + gg for m, gg in zip(self.w_mean, self.gust, strict=True))

    def reset(self, x, y, h):
        """Start in TRIMMED hover at (x, y, h): at rest over the ground, tilted into the mean wind, the velocity
        integrator already holding the mean-wind drag (the drone took off and settled before the mission). The
        gust state starts from its stationary distribution."""
        self.t = 0.0
        self.px, self.py, self.pz = float(x), float(y), float(h)
        self.vx = self.vy = self.vz = 0.0
        self.p = self.qr = self.r = 0.0
        self.gust = tuple(float(s * n) for s, n in zip(self.g_std, self.rng.standard_normal(3).tolist(), strict=True))
        wx, wy, _ = self.w_mean
        sp = math.hypot(wx, wy)
        # drag on a drone at rest in the mean wind pushes it downwind: F = c1 w + c2 |w| w; the integrator cancels it
        self.ix = -(self.c1 * wx + self.c2 * sp * wx) / self.m
        self.iy = -(self.c1 * wy + self.c2 * sp * wy) / self.m
        self.iz = 0.0
        fx, fy, fz = self.m * self.ix, self.m * self.iy, self.W
        self.roll, self.pitch = self._attitude_from_force(fx, fy, fz, 0.0)
        self.roll_t, self.pitch_t = self.roll, self.pitch                   # shaped attitude target ...
        self.wr_t = self.wp_t = 0.0                                         # ... and its rate (the feed-forward)
        self.yaw = 0.0
        self.T = math.sqrt(fx * fx + fy * fy + fz * fz)
        self.tx = self.ty = self.tz = 0.0
        self.tpx, self.tpy, self.tpz = self.px, self.py, self.pz            # autopilot target position
        self.tvx = self.tvy = self.tvz = 0.0                                # autopilot target velocity
        self.tax = self.tay = self.taz = 0.0                                # autopilot target acceleration
        return self.sample()

    def sample(self):
        """One row of the 5 Hz flight log: t, x, y, h, vx, vy, vz, roll, pitch, yaw (rad), thrust/weight, wind xyz."""
        wx, wy, wz = self.wind()
        return (self.t, self.px, self.py, self.pz, self.vx, self.vy, self.vz, self.roll, self.pitch, self.yaw,
                self.T / self.W, wx, wy, wz)

    def tilt(self):
        return math.acos(max(-1.0, min(1.0, math.cos(self.roll) * math.cos(self.pitch))))

    @staticmethod
    def _attitude_from_force(fx, fy, fz, yaw):
        """Roll and pitch that point the body z axis along (fx, fy, fz) at heading yaw (ZYX Euler)."""
        n = math.sqrt(fx * fx + fy * fy + fz * fz)
        nx, ny, nz = fx / n, fy / n, fz / n
        cy, sy = math.cos(yaw), math.sin(yaw)
        n1, n2 = cy * nx + sy * ny, -sy * nx + cy * ny
        return math.asin(max(-1.0, min(1.0, -n2))), math.atan2(n1, nz)

    # ------------------------------------------------------------------ one flight segment
    def fly(self, v_sp, duration=1.0):
        """Hold the velocity setpoint v_sp = (vx, vy, vz) (m/s) for `duration` seconds. Returns the state at the end
        and per-integration-step arrays for the energy model (airspeed, vz, a_h), plus the 5 Hz samples."""
        q, dt, m, g = self.q, self.dt, self.m, self.g
        n = max(1, int(round(duration / dt)))
        noise = self.rng.standard_normal((n, 3)).tolist()            # gusts for the whole segment, drawn at once
        k_ga = math.sqrt(1.0 - self.g_a * self.g_a)
        x_lo, x_hi, y_lo, y_hi, h_lo, h_hi = self.bounds
        sxy, sz = float(q["shape_acc_xy_mps2"]), float(q["shape_acc_z_mps2"])
        jxy, jz = float(q["shape_jerk_xy_mps3"]), float(q["shape_jerk_z_mps3"])
        kp_xy, kv_xy, ki_xy = float(q["pos_p_xy"]), float(q["vel_p_xy"]), float(q["vel_i_xy"])
        kp_z, kv_z, ki_z = float(q["pos_p_z"]), float(q["vel_p_z"]), float(q["vel_i_z"])
        imax_xy, imax_z = float(q["vel_i_max_xy_mps2"]), float(q["vel_i_max_z_mps2"])
        leash_xy, leash_z = float(q["leash_xy_m"]), float(q["leash_z_m"])
        k_ang, k_rate = [float(v) for v in q["ang_p"]], float(q["rate_p"])
        rate_ff = bool(q["rate_ff"])
        alpha = math.radians(float(q["ang_acc_max_dps2"]))
        lead_xy = 1.0 / k_ang[0]                     # attitude lag ~ 1 / ang_p (s); derived, not a parameter
        a_m = dt / float(q["motor_tau_s"])
        Ixx, Iyy, Izz = self.I
        tan_tilt = math.tan(self.tilt_max)
        # the commanded velocity, limited like the env's (horizontal norm v_max, vertical vz_max)
        cvx, cvy, cvz = (float(v) for v in v_sp)
        sp = math.hypot(cvx, cvy)
        if sp > self.v_max:
            cvx, cvy = cvx * self.v_max / sp, cvy * self.v_max / sp
        cvz = max(-self.vz_max, min(self.vz_max, cvz))
        air_h, vz_log, ah_log, samples = np.empty(n), np.empty(n), np.empty(n), []
        tilt_peak = speed_peak = 0.0

        for k in range(n):
            # ---- wind (gust process)
            gx, gy, gz = self.gust
            nk = noise[k]
            gx = self.g_a * gx + self.g_std[0] * k_ga * nk[0]
            gy = self.g_a * gy + self.g_std[1] * k_ga * nk[1]
            gz = self.g_a * gz + self.g_std[2] * k_ga * nk[2]
            self.gust = (gx, gy, gz)
            wx, wy, wz = self.w_mean[0] + gx, self.w_mean[1] + gy, gz

            # ---- 1 setpoint shaping (geofence, then jerk- and acceleration-limited target velocity)
            # geofence on the COMMAND: toward a fence, only what can still stop in time (braking at half the shaping
            # acceleration leaves room for the jerk ramp)
            fvx = _fence(cvx, self.tpx, x_lo, x_hi, 0.5 * sxy)
            fvy = _fence(cvy, self.tpy, y_lo, y_hi, 0.5 * sxy)
            fvz = _fence(cvz, self.tpz, h_lo, h_hi, 0.5 * sz)
            dvx, dvy = fvx - self.tvx, fvy - self.tvy
            dn = math.hypot(dvx, dvy)
            amag = min(sxy, math.sqrt(2.0 * jxy * dn), dn / dt)          # sqrt controller: brake the acceleration
            ax_d, ay_d = (dvx * amag / dn, dvy * amag / dn) if dn > 0.0 else (0.0, 0.0)
            jx, jy = ax_d - self.tax, ay_d - self.tay
            jn = math.hypot(jx, jy)
            if jn > jxy * dt:
                jx, jy = jx * jxy * dt / jn, jy * jxy * dt / jn
            dvz = fvz - self.tvz
            az_d = math.copysign(min(sz, math.sqrt(2.0 * jz * abs(dvz)), abs(dvz) / dt), dvz)
            jzz = max(-jz * dt, min(jz * dt, az_d - self.taz))
            afx, afy, afz = self.tax + jx, self.tay + jy, self.taz + jzz
            nvx, nvy, nvz = self.tvx + afx * dt, self.tvy + afy * dt, self.tvz + afz * dt
            # safety net: never let the target itself run through a fence; a clamped axis simply stops there (no
            # acceleration kick, which would make the jerk-limited shaper bounce off the fence)
            cx = _fence(nvx, self.tpx, x_lo, x_hi, sxy)
            cy = _fence(nvy, self.tpy, y_lo, y_hi, sxy)
            cz = _fence(nvz, self.tpz, h_lo, h_hi, sz)
            if cx != nvx:
                nvx, afx, jx = cx, 0.0, 0.0
            if cy != nvy:
                nvy, afy, jy = cy, 0.0, 0.0
            if cz != nvz:
                nvz, afz = cz, 0.0
            self.tvx, self.tvy, self.tvz = nvx, nvy, nvz
            self.tax, self.tay, self.taz = afx, afy, afz
            # lead on the feed-forward: the tilt follows its target about 1/ang_p seconds late, so ask now for the
            # acceleration the target will need that much later (target jerk x lag; bounded by the jerk limit)
            if rate_ff:
                afx, afy = afx + lead_xy * jx / dt, afy + lead_xy * jy / dt
            self.tpx = min(x_hi, max(x_lo, self.tpx + nvx * dt))
            self.tpy = min(y_hi, max(y_lo, self.tpy + nvy * dt))
            self.tpz = min(h_hi, max(h_lo, self.tpz + nvz * dt))
            ex, ey, ez = self.tpx - self.px, self.tpy - self.py, self.tpz - self.pz
            el = math.hypot(ex, ey)
            if el > leash_xy:                                     # leash: the target never runs far ahead
                self.tpx, self.tpy = self.px + ex * leash_xy / el, self.py + ey * leash_xy / el
                ex, ey = ex * leash_xy / el, ey * leash_xy / el
            if abs(ez) > leash_z:
                ez = math.copysign(leash_z, ez)
                self.tpz = self.pz + ez

            # ---- 2 position + velocity loops
            ux, uy = self.tvx + kp_xy * ex, self.tvy + kp_xy * ey
            un = math.hypot(ux, uy)
            if un > self.v_max:
                ux, uy = ux * self.v_max / un, uy * self.v_max / un
            uz = max(-self.vz_max, min(self.vz_max, self.tvz + kp_z * ez))
            evx, evy, evz = ux - self.vx, uy - self.vy, uz - self.vz
            ax = afx + kv_xy * evx + self.ix
            ay = afy + kv_xy * evy + self.iy
            az = afz + kv_z * evz + self.iz

            # ---- 3 thrust vector with tilt and thrust limits (vertical first)
            fz = min(self.T_max, max(self.T_min, m * (az + g)))
            fx, fy = m * ax, m * ay
            fh = math.hypot(fx, fy)
            fh_max = min(fz * tan_tilt, math.sqrt(max(0.0, self.T_max * self.T_max - fz * fz)))
            sat_h = fh > fh_max
            if sat_h:
                fx, fy = fx * fh_max / fh, fy * fh_max / fh
            sat_z = fz != m * (az + g)
            # integrators (clamped; frozen on the saturated axis = anti-windup)
            if not sat_h:
                self.ix = max(-imax_xy, min(imax_xy, self.ix + ki_xy * evx * dt))
                self.iy = max(-imax_xy, min(imax_xy, self.iy + ki_xy * evy * dt))
            if not sat_z:
                self.iz = max(-imax_z, min(imax_z, self.iz + ki_z * evz * dt))
            roll_sp, pitch_sp = self._attitude_from_force(fx, fy, fz, 0.0)
            cr, sr = math.cos(self.roll), math.sin(self.roll)
            cp, s_p = math.cos(self.pitch), math.sin(self.pitch)
            cyw, syw = math.cos(self.yaw), math.sin(self.yaw)
            zbx, zby, zbz = cyw * s_p * cr + syw * sr, syw * s_p * cr - cyw * sr, cp * cr
            T_cmd = min(self.T_max, max(self.T_min, fx * zbx + fy * zby + fz * zbz))

            # ---- 4 attitude loop: Euler-angle errors (+ shaped target-rate feed-forward) -> Euler rates -> body rates
            if rate_ff:        # the attitude TARGET follows the setpoint smoothly (sqrt controller, accel-limited)
                self.roll_t, self.wr_t = _shape_angle(self.roll_t, self.wr_t, roll_sp, k_ang[0], alpha, dt)
                self.pitch_t, self.wp_t = _shape_angle(self.pitch_t, self.wp_t, pitch_sp, k_ang[1], alpha, dt)
                d_roll = k_ang[0] * (self.roll_t - self.roll) + self.wr_t
                d_pitch = k_ang[1] * (self.pitch_t - self.pitch) + self.wp_t
            else:
                d_roll = k_ang[0] * (roll_sp - self.roll)
                d_pitch = k_ang[1] * (pitch_sp - self.pitch)
            d_yaw = k_ang[2] * math.remainder(0.0 - self.yaw, 2.0 * math.pi)
            rmax = self.rate_max
            p_sp = max(-rmax, min(rmax, d_roll - s_p * d_yaw))
            q_sp = max(-rmax, min(rmax, cr * d_pitch + sr * cp * d_yaw))
            r_sp = max(-rmax, min(rmax, -sr * d_pitch + cr * cp * d_yaw))

            # ---- 5 rate loop -> torques (gyroscopic feed-forward), rotor limits
            p, qq, r = self.p, self.qr, self.r
            gyx, gyy, gyz = (Izz - Iyy) * qq * r, (Ixx - Izz) * r * p, (Iyy - Ixx) * p * qq     # w x (I w)
            tx_c = max(-self.tau_rp_max, min(self.tau_rp_max, Ixx * k_rate * (p_sp - p) + gyx))
            ty_c = max(-self.tau_rp_max, min(self.tau_rp_max, Iyy * k_rate * (q_sp - qq) + gyy))
            tz_c = max(-self.tau_yaw_max, min(self.tau_yaw_max, Izz * k_rate * (r_sp - r) + gyz))

            # ---- motors (first-order lag)
            self.T += (T_cmd - self.T) * a_m
            self.tx += (tx_c - self.tx) * a_m
            self.ty += (ty_c - self.ty) * a_m
            self.tz += (tz_c - self.tz) * a_m

            # ---- rigid body: rates, then angles (semi-implicit Euler)
            p += (self.tx - gyx) / Ixx * dt
            qq += (self.ty - gyy) / Iyy * dt
            r += (self.tz - gyz) / Izz * dt
            self.p, self.qr, self.r = p, qq, r
            t_th = math.tan(self.pitch)
            self.roll += (p + t_th * (qq * sr + r * cr)) * dt
            self.pitch += (qq * cr - r * sr) * dt
            self.yaw += (qq * sr + r * cr) / cp * dt

            # ---- translation
            cr, sr = math.cos(self.roll), math.sin(self.roll)
            cp, s_p = math.cos(self.pitch), math.sin(self.pitch)
            cyw, syw = math.cos(self.yaw), math.sin(self.yaw)
            zbx, zby, zbz = cyw * s_p * cr + syw * sr, syw * s_p * cr - cyw * sr, cp * cr
            rx, ry, rz = self.vx - wx, self.vy - wy, self.vz - wz
            ra = math.sqrt(rx * rx + ry * ry + rz * rz)
            dx = -(self.c1 + self.c2 * ra)
            accx = (self.T * zbx + dx * rx) / m
            accy = (self.T * zby + dx * ry) / m
            accz = (self.T * zbz + dx * rz) / m - g
            self.vx += accx * dt
            self.vy += accy * dt
            self.vz += accz * dt
            self.px += self.vx * dt
            self.py += self.vy * dt
            self.pz += self.vz * dt
            if self.pz < 0.0:                                      # the ground
                self.pz, self.vz = 0.0, max(0.0, self.vz)
            self.t += dt

            air_h[k] = math.hypot(self.vx - wx, self.vy - wy)
            vz_log[k] = self.vz
            ah_log[k] = math.hypot(accx, accy)
            tilt_peak = max(tilt_peak, self.tilt())
            speed_peak = max(speed_peak, math.hypot(self.vx, self.vy))
            if (k + 1) % self.sample_every == 0:
                samples.append(self.sample())

        return dict(pos=(self.px, self.py, self.pz), vel=(self.vx, self.vy, self.vz),
                    att=(self.roll, self.pitch, self.yaw), airspeed_h=air_h, vz=vz_log, a_h=ah_log,
                    samples=samples, tilt_peak=tilt_peak, speed_peak=speed_peak, wind=self.wind(),
                    thrust_ratio=self.T / self.W)


def _shape_angle(ang, rate, sp, k, alpha, dt):
    """One step of attitude-target shaping (like ArduPilot's input shaping with ATC_ACCEL_*_MAX): the target angle
    moves toward the setpoint sp with the rate of a sqrt controller (P gain k near the setpoint, constant
    deceleration alpha farther away), and that rate changes by at most alpha * dt. Returns (angle, rate)."""
    err = sp - ang
    lin = alpha / (k * k)                         # error below which the controller is linear
    if abs(err) <= lin:
        want = k * err
    else:
        want = math.copysign(math.sqrt(2.0 * alpha * (abs(err) - 0.5 * lin)), err)
    rate += max(-alpha * dt, min(alpha * dt, want - rate))
    return ang + rate * dt, rate


def _fence(v, p, lo, hi, a):
    """Limit the target velocity v (one axis) at target position p so it can still stop inside [lo, hi] with
    deceleration a: outward speed <= sqrt(2 a distance-to-the-fence)."""
    if v > 0.0 and hi < math.inf:
        return min(v, math.sqrt(2.0 * a * max(0.0, hi - p)))
    if v < 0.0 and lo > -math.inf:
        return max(v, -math.sqrt(2.0 * a * max(0.0, p - lo)))
    return v
