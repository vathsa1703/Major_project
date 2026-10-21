# Chapter 4. The simulator

Everything here is in `uav_dataset/make_dataset.py` (physics and scenarios) and is configured only in
`uav_dataset/config.yaml`. The Gymnasium game (Chapter 6) and the dataset (Chapter 5) call the same functions, so they cannot
disagree. Parameter sources and their verification status are in Chapter 10 and `docs/assumptions.md`.

## 4.1 Scenarios and seeds
**Plain words.** A scenario is one invented disaster area: how many people, how many crowds, how big, where the collapsed
buildings are, how people move. A seed is the scenario's ID number; the same seed always produces exactly the same scenario.

**Technically.** `make_scenario(seed)` draws, with a NumPy generator seeded by `[seed, 0]` (domain randomisation):
- number of users from {100, 300, 600, 1000} (must be even, because NOMA works in pairs);
- number of clusters 2-5, cluster radius 50-200 m, share of scattered users 5-10%;
- the mobility model from the profile's list, the number of obstacles from its range;
- bandwidth = number of users x 50 kHz (D-03); pairing method from the config.
New draws are always appended at the end, so adding a field never changes the earlier draws.

Seeds are split and never mixed: **train 0-99, validation 100-119, test 120-139.** Profiles (Chapter 3, D-15) override config
values; `apply_profile(name)` merges them in place and always starts from an untouched copy of the base config.

| Profile | Changes |
|---|---|
| default | 1 x 1 km, 30 dBm, 0-5 obstacles, five mobility models, 10 Wh |
| `lowpower` | 20 dBm |
| `bigarea` | 2 x 2 km |
| `hard` | 2 x 2 km, 20 dBm, 3-8 obstacles of 60-200 m, mobility only hotspot jump / surge / group drift / attraction, 16 Wh, baseline grid 14 x 14 |
| `rl_static` | as `hard` but the crowd never moves (RL curriculum step 1) |
| `rl_static_g20` | as `rl_static` with a 20 x 20 heatmap for the agent |

## 4.2 People
**Plain words.** Crowds are blobs of people around random centres, plus a few people scattered alone over the map. Every person
belongs to a class (rescue, video, voice, iot, normal) that decides how much data speed they need to count as "served".

**Technically.** `make_users(seed, sc)` with generator `[seed, 1]`:
- cluster centres uniform in [radius, L - radius]; users split between clusters with Dirichlet(3) weights and a multinomial draw;
- positions: 2D Gaussian around the centre with standard deviation radius / 2, truncated at the radius (redrawn if outside);
- scattered users uniform over the map; everything clipped to the map;
- class drawn per user with the configured shares; `min_rate_bps` from the class.

| Class | Share | Minimum rate | Status |
|---|---|---|---|
| rescue | 10% | 200 kbps | engineering assumption, not signed off |
| video | 20% | 500 kbps | same |
| voice | 30% | 50 kbps | same |
| iot | 20% | 10 kbps | same |
| normal | 20% | 100 kbps | same |

## 4.3 Movement
`simulate_positions(seed, sc, users)` (generator `[seed, 3]`) moves everyone for 300 steps of 1 s, vectorised over users (no
loop over people). It returns every position and velocity; `simulate()` keeps a snapshot every 30 s for the dataset.

| Model | Behaviour |
|---|---|
| `static` | nobody moves (used for RL step 1) |
| `random_waypoint` | each person walks (0.5-1.5 m/s) to a random point, then picks a new one |
| `group_drift` | each crowd drifts together with its own heading and speed, bouncing off the edges; members wobble (0.3 m/s); scattered people walk alone |
| `attraction` | everyone walks to the nearest of 1-2 shelters and stops within 20 m of it |
| `hotspot_jump` | as group drift, but at a random moment between 60 and 180 s one crowd heads to a new place at 3 m/s |
| `surge` | everyone stands still until a random moment (60-180 s), then all run at 3 m/s to one point and pile up within 60 m |

Speeds are engineering assumptions. An evacuation model (social-force-lite) is planned, not built.

## 4.4 Collapsed buildings (obstacles)
**Plain words.** Grey rectangles on the map. If the straight line from the drone to a person crosses one, that person's signal
is weaker.

**Technically.** `make_obstacles(seed, sc)` (generator `[seed, 4]`) draws `n_obstacles` axis-aligned rectangles with sides
40-150 m (60-200 m in `hard`). `link_blocked()` tests every drone-user segment against every rectangle with the slab
(Liang-Barsky) method, vectorised over drones and users. A blocked link gets **15 dB** extra loss (engineering assumption,
sensitivity range 10-25 dB). The test is 2D (no building heights): a user inside a rectangle counts as blocked.

## 4.5 The radio channel (air to ground)
**Plain words.** The higher the drone flies, the more likely it has a clear line of sight to a person, but the farther away it
is. That trade-off creates a best height. Line-of-sight links lose a little extra signal; blocked links lose a lot.

**Technically.** `channel_gain()` for drone positions (X, Y, H) and users (x, y), following Al-Hourani et al.:

```
d       = sqrt((x - X)^2 + (y - Y)^2 + H^2)                      3D distance (m)
theta   = (180 / pi) * arcsin(H / d)                              elevation angle in degrees
P_LoS   = 1 / (1 + a * exp(-b * (theta - a)))                     a = 9.61, b = 0.16
FSPL    = 20 * log10(4 * pi * fc * d / c)                         fc = 2 GHz
PL_dB   = FSPL + P_LoS * eta_LoS + (1 - P_LoS) * eta_NLoS         eta_LoS = 1 dB, eta_NLoS = 20 dB
        + 15 dB if the link crosses an obstacle
gain    = 10^(-PL_dB / 10)
```
The architecture document's version of this formula omits the NLoS term; we use the full mean path loss.

**Fading (optional).** With fading on, each link is drawn LoS with probability P_LoS and then gets Rician fading (K = 10 dB) if
LoS or Rayleigh fading if NLoS, both with unit mean power. Off in the dataset and for the baselines (deterministic average).

**Noise.** Noise power = -174 dBm/Hz + 7 dB noise figure, times the bandwidth of each user's resource.

## 4.6 NOMA (and the OMA reference)
**Plain words.** Instead of giving every person their own slice of frequency, NOMA puts two people on the same slice: a person
with a strong signal and a person with a weak one. The weak person gets most of the power. The strong person first removes the
weak person's message from what they receive (successive interference cancellation, SIC) and then reads their own. NOMA is
inside every coverage number in this project, but nobody chooses its settings yet: pairing and the 80/20 split are fixed.

**Technically.** `noma_rates(g, P, N0_density, B, pairing)` for one drone position:
1. **Pairing** (`pair_users`): `extreme` sorts users by gain and pairs the weakest with the strongest, the second weakest with
   the second strongest, and so on; `random` pairs at random and makes the lower-gain user of each pair the "weak" one.
2. **Resources:** N users, N/2 pairs; each pair gets bandwidth b = B / (N/2) and power p = P / (N/2) (total power and bandwidth
   are shared by everyone). Noise per pair N0 = noise density x b.
3. **Power split:** the weak user gets a_w = 0.8, the strong user a_s = 0.2.
4. **Rates:**
   ```
   SINR_weak         = a_w p g_w / (a_s p g_w + N0)
   SINR_strong->weak = a_w p g_s / (a_s p g_s + N0)        the strong user decoding the weak message
   SINR_strong       = a_s p g_s / N0                       after SIC
   R = b * log2(1 + SINR)
   ```
5. **SIC check** (`sic_feasible`): SIC works only if SINR_strong->weak >= SINR_weak; otherwise the strong user's rate is 0.
   Because roles are assigned by gain, this always holds in our pairings; a real failure needs imperfect SIC or need-based
   pairing (planned).
6. **OMA reference (FDMA):** every user gets bandwidth B / N and power P / N; R = (B / N) log2(1 + (P / N) g / (N0_density B / N)).
   Same total bandwidth and power as NOMA, which makes the comparison fair (hypothesis H3).

A user is **covered** if their NOMA rate is at least their class's minimum rate. **Coverage** is the share of users covered.
Fairness is Jain's index (sum R)^2 / (N sum R^2).

## 4.7 Energy and the battery
**Plain words.** Keeping a drone in the air costs far more energy than its radio. Our drone is a small one (about 2 kg) that
needs about 168 W just to hover. A surprising and important fact from the model: flying forward at about 10 m/s costs *less*
than hovering (134 J/s against 176 J/s including radio and electronics), as with real helicopters.

**Technically.** Rotary-wing propulsion power (Zeng, Xu, Zhang, verified, Chapter 10):
```
P(V) = P0 (1 + 3 V^2 / Utip^2) + Pi * sqrt( sqrt(1 + V^4 / (4 v0^4)) - V^2 / (2 v0^2) ) + 0.5 d0 rho s A V^3
hover = P(0) = P0 + Pi = 79.86 + 88.63 = 168.49 W
```
with Utip = 120 m/s, v0 = 4.03 m/s, d0 = 0.6, rho = 1.225 kg/m^3, s = 0.05, A = 0.503 m^2 (our 20 N drone, D-13).
Energy per 1 s step = P(V_horizontal) + 20 N x max(climb rate, 0) + P_tx / 0.4 + 5 W.
Climbing term, amplifier efficiency 0.4 and circuit power 5 W are engineering assumptions. Battery 10 Wh by default (D-07),
16 Wh in `hard` and `rl_static`.

| Situation | Energy per second |
|---|---|
| Hover, 30 dBm | 176.0 J |
| 5 m/s, 30 dBm | 151.1 J |
| 10 m/s, 30 dBm | 133.5 J |
| 15 m/s, 30 dBm | 146.0 J |

10 Wh lasts about 205 s of hovering; 300 s needs 14.7 Wh.

## 4.8 The drone position sweep (dataset)
`sweep_one()` evaluates every grid position (11 x 11 at 100 m steps), every altitude (12 levels, 50-1,000 m) and every power
level (0, 10, 20, 30 dBm) for the users at t = 0, with obstacles and the average channel, and records coverage, sum rate,
spectral efficiency, fairness, rescue outage, OMA coverage and sum rate, and the hover energy per step. Chapter 5 has the table
layout.

## 4.9 What the simulator does not model yet
Fading in the dataset, building heights, terrain, wind, GPS error, control delays, real battery behaviour, the drone's own
backhaul link, interference from other cells, more than one drone, imperfect SIC, bit-error rate, NOMA settings as decisions,
and not knowing where people are. All are in the roadmap (Chapter 11).
