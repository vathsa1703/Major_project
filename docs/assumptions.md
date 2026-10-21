# Assumptions and parameter sources

Every parameter in `uav_dataset/config.yaml` has a value, a unit, a source or the label "engineering assumption",
and a sensitivity range (the plan requires all four). Checked on 2026-10-16.

**Status key**
- **VERIFIED**: the formula or value was read in the cited paper.
- **DERIVED**: follows from VERIFIED formulas for a drone we chose. The choice itself is an assumption.
- **CONSISTENT**: appears in secondary papers that cite the original; the original was **not** read.
- **STANDARD**: physical constant or textbook convention.
- **ASSUMPTION**: engineering choice with no source. Report results with the sensitivity range.

The sensitivity ranges are proposals for experiment E13. They are not measured yet.

## Sources
- **[Zeng]** Y. Zeng, J. Xu, R. Zhang, "Energy Minimization for Wireless Communication with Rotary-Wing UAV",
  IEEE Trans. Wireless Commun., 2019. arXiv:1804.02238 (read: Eq. 6, Appendix A Eq. 61, Table I).
- **[Hourani]** A. Al-Hourani, S. Kandeepan, S. Lardner, "Optimal LAP Altitude for Maximum Coverage",
  IEEE Wireless Commun. Lett., vol. 3, no. 6, pp. 569-572, 2014, DOI 10.1109/LWC.2014.2342736.
  **Original not read.** The formulas were checked in arXiv:1802.01117 and arXiv:1705.03304, which cite it.

## Channel (air-to-ground)
| Parameter | Value | Unit | Status and source | Sensitivity range |
|---|---|---|---|---|
| P_LoS formula `1/(1+a*exp(-b*(theta-a)))`, theta in degrees | n/a | n/a | CONSISTENT: same form and 180/pi degree conversion in arXiv:1802.01117 and 1705.03304 (citing [Hourani]) | n/a |
| Mean path loss `FSPL + P_LoS*eta_LoS + (1-P_LoS)*eta_NLoS` | n/a | dB | CONSISTENT: same form in both secondary papers. (The architecture doc omits the NLoS term.) | n/a |
| a2g.a | 9.61 | none | CONSISTENT: appears with b, eta values below in two papers' simulation tables (fc = 2 GHz), **environment label not stated there**. "Urban" is unconfirmed. | other [Hourani] environments (suburban, dense urban, high-rise): fill from the original |
| a2g.b | 0.16 | 1/deg | as above | as above |
| a2g.eta_los_db | 1.0 | dB | as above | 0 to 2.5 |
| a2g.eta_nlos_db | 20.0 | dB | as above | 15 to 35 |
| fc_hz | 2e9 | Hz | ASSUMPTION (matches the secondary papers; must match the MATLAB reference for parity) | 1e9 to 6e9 |
| FSPL `20*log10(4*pi*fc*d/c)` | n/a | dB | STANDARD (98.46 dB at 1 km, 2 GHz, checked in tests) | n/a |
| bandwidth_per_user_hz | 50000 | Hz | ASSUMPTION (total B = n_users x this; 200 users = 10 MHz) | 25000 to 100000 |
| noise_density_dbm_hz | -174 | dBm/Hz | STANDARD (thermal noise at about 290 K) | n/a |
| noise_figure_db | 7 | dB | ASSUMPTION (spec range 5 to 9) | 5 to 9 |
| tx_power_dbm_levels, uav.p_max_dbm | 0,10,20,30 / 30 | dBm | ASSUMPTION (typical UAV base-station range) | 20 to 30 max |
| obstacles.excess_loss_db | 15 | dB | ASSUMPTION (extra loss on a link whose 2D segment crosses a rectangle; no height test) | 10 to 25 |
| obstacles.n_range, size_range_m | 0 to 5, 40 to 150 | count, m | ASSUMPTION | 0 to 10 |
| fading.rician_k_db | 10 | dB | ASSUMPTION (LoS links Rician, NLoS Rayleigh, unit mean power; off in the dataset) | 3 to 15 |

## NOMA
| Parameter | Value | Unit | Status and source | Sensitivity range |
|---|---|---|---|---|
| noma_alpha_weak | 0.8 | none | ASSUMPTION (fixed split; weak user gets the larger share) | 0.6 to 0.95, then optimized per pair |
| pairing | extreme / random | n/a | Architecture doc 6.2 (strongest with weakest); k-means and QoS-aware not built | all strategies |
| SIC feasibility rule | n/a | n/a | Architecture doc 6.2 step 5 (always holds when roles are set by gain; fails only with imperfect SIC or QoS rules) | imperfect SIC residual 0 to 0.1 |

## UAV energy (rotary wing)
Formula and equations VERIFIED in [Zeng]: `P(V) = P0(1+3V^2/Utip^2) + Pi*(sqrt(1+V^4/(4 v0^4)) - V^2/(2 v0^2))^(1/2)
+ 0.5*d0*rho*s*A*V^3`, hover = P0 + Pi, `P0 = (delta/8) rho s A Omega^3 R^3`, `Pi = (1+k) W^(3/2) / sqrt(2 rho A)`,
`v0 = sqrt(W/(2 rho A))`.

| Parameter | Value | Unit | Status and source | Sensitivity range |
|---|---|---|---|---|
| delta (profile drag) | 0.012 | none | VERIFIED [Zeng] notation table (used in tests, not in config) | n/a |
| k (induced power correction) | 0.1 | none | VERIFIED [Zeng] Table I (used in tests) | n/a |
| rho_kg_m3 | 1.225 | kg/m^3 | VERIFIED [Zeng] Table I | 1.1 to 1.3 |
| s (solidity) | 0.05 | none | VERIFIED [Zeng] Table I | n/a |
| weight_n | 20 | N | ASSUMPTION: a small UAV (about 2 kg). **[Zeng]'s own table uses W = 100 N.** | 10 to 40 |
| R and Omega behind Utip, A | R = 0.4 m, Omega = 300 rad/s | m, rad/s | ASSUMPTION (small-drone choice). [Zeng] uses R = 0.5 m, Omega = 400 rad/s. | n/a |
| A_m2 | 0.503 | m^2 | DERIVED: pi * 0.4^2 | n/a |
| Utip_mps | 120 | m/s | DERIVED: Omega * R = 300 * 0.4 | n/a |
| P0_w, Pi_w | 79.86, 88.63 | W | DERIVED: the formulas above for W = 20 N, R = 0.4 m, Omega = 300 give 79.80 and 88.66 (within 0.1%, rounding of A) | follows W |
| v0_mps | 4.03 | m/s | DERIVED: sqrt(W/(2 rho A)) | follows W |
| d0 | 0.6 | none | UNVERIFIED: [Zeng] uses 0.3 for its own drone. 0.6 implies a fuselage flat-plate area of 0.0151 m^2 (d0 = S_FP/(s A)). | 0.3 to 0.6 |
| hover power | 168.49 | W | DERIVED (P0 + Pi). For comparison, [Zeng]'s own 100 N drone would hover at about 1370 W. | follows W |
| P_circuit_w | 5 | W | ASSUMPTION | 2 to 10 |
| pa_efficiency | 0.4 | none | ASSUMPTION (comm power = P_tx / this) | 0.2 to 0.6 |
| climbing term `W * vz` (no recovery on descent) | n/a | W | ASSUMPTION (the spec asks for a climb term; this form is ours) | with or without recovery |
| battery_wh | 10 | Wh | ASSUMPTION (about 3.5 min of hover, so the battery binds in a 300 s episode) | 5 to 20 (experiment E7) |

## UAV limits, users and reward
| Parameter | Value | Unit | Status and source | Sensitivity range |
|---|---|---|---|---|
| v_max_mps, vz_max_mps | 15, 5 | m/s | ASSUMPTION (spec says 10 to 20 m/s) | 10 to 20 |
| h_min_m, h_max_m, start_h_m | 50, 300, 150 | m | ASSUMPTION (spec: h_max 300 to 500). The sweep goes to 1000 m for diagnostics only. | h_max 300 to 500 |
| area_m, episode_steps, dt_s | 1000, 300, 1 | m, steps, s | Spec defaults | area up to 2000 |
| mobility.speed_mps | 0.5 to 1.5 | m/s | ASSUMPTION (typical walking, spec range) | 0.5 to 2 |
| mobility.surge_speed_mps | 3 | m/s | ASSUMPTION (panicked or running) | 2 to 5 |
| classes.share | rescue 0.10, video 0.20, voice 0.30, iot 0.20, normal 0.20 | none | Spec example mix (the plan says to state it) | vary rescue 0.05 to 0.2 |
| classes.min_rate_bps | rescue 200k, video 500k, voice 50k, iot 10k, normal 100k | bit/s | ASSUMPTION: **not signed off.** Video and rescue coverage is very low at low power. | each +/- 50% |
| env.lambda_energy | 0.05 | none | ASSUMPTION (reward weight on energy) | 0.01 to 0.2 |
| env.terminal_penalty | 1.0 | none | ASSUMPTION | 0 to 2 |

## Acceleration and turning (added 2026-10-21, D-44..D-46)
| Parameter | Value | Unit | Status and source | Sensitivity range |
|---|---|---|---|---|
| `uav.a_max_mps2` (horizontal acceleration limit) | null = off (old behaviour, bit-exact); 4 when on | m/s^2 | ENGINEERING ASSUMPTION | 2, 4, 8 (tested: result unchanged) |
| `uav.az_max_mps2` (vertical) | 3 (only with the limit on) | m/s^2 | ENGINEERING ASSUMPTION | 2, 4 (not yet run) |
| `energy.accel_power` (load-factor term) | true | flag | OUR EXTENSION of Zeng-Xu-Zhang (whose rotary-wing model covers steady straight flight): kappa = sqrt(1 + (a_h/g)^2), induced power x kappa^1.5, v0 x sqrt(kappa), quasi-steady; not validated against measurements | on / off |
| `energy.g_mps2` | 9.81 | m/s^2 | standard | - |
| `baselines.loiter_radius_m` (B7) | 50 | m | ENGINEERING ASSUMPTION | 50, 100 (tested) |
| v* (minimum-power speed) | 10.21 | m/s | DERIVED from the Zeng formula with our parameters; P(v*) = 126.0 W vs hover 168.5 W | 9.6-12.0 over d0 and Pi ranges |
| B7 loiter speed (r 50 / r 100) | 9.84 / 10.11 | m/s | DERIVED (minimum of P(V, kappa(V^2/r))) | follows d0, Pi, r |

## Still to do
1. Read [Hourani] itself and confirm the (a, b, eta_LoS, eta_NLoS) rows and which environment is which.
   (Get the PDF via IEEE Xplore or your library and drop it in this repo's `docs/papers/`, which is gitignored.)
2. Confirm where d0 = 0.6 and the small-drone values (W = 20 N, R = 0.4 m, Omega = 300 rad/s) come from, or
   choose the drone openly as an engineering assumption (the numbers are self-consistent with [Zeng]).
3. MATLAB parity (Gate G1): needs the reference vectors from the MATLAB code.
4. Run the sensitivity ranges above (experiment E13).
