# Chapter 13. NOMA in this project

NOMA is the core of the guide's idea ("a moving base station using NOMA"). This chapter collects everything about it: what it
is, exactly where it sits in the code, what we measured, where it wins, where it loses and why, and what comes next.

## 13.1 What NOMA is
**Plain words.** A tower has a fixed amount of radio bandwidth and power to share between everyone it serves. The traditional
way (**OMA**) cuts the bandwidth into separate slices, one per person. **NOMA** puts *two people on the same slice at the same
time*: one with a strong signal (usually near the drone) and one with a weak signal (far away or behind a building). The tower
sends both messages mixed together and gives most of the power to the weak person. The weak person treats the strong person's
part as noise and reads their own. The strong person first decodes the weak person's message, subtracts it, and then reads their
own clean message (successive interference cancellation, **SIC**). Each NOMA slice is twice as wide as an OMA slice, so the pair
gets more total speed.

**Technically.** Downlink power-domain NOMA with two-user pairs, superposition coding at the transmitter and SIC at the strong
user. The OMA reference is FDMA with the same total bandwidth and the same total power.

## 13.2 Where NOMA sits in the code
Every coverage number in this project is a NOMA number unless OMA is chosen.
1. `make_dataset.py: pair_users()` sorts users by channel gain and pairs the strongest with the weakest (`extreme`), or pairs at
   random (`random`); the weak and strong roles are set by gain.
2. `make_dataset.py: noma_rates()` gives each pair bandwidth B / (N/2) and power P / (N/2), splits the pair's power 0.8 to the
   weak user and 0.2 to the strong user, and computes:
   ```
   SINR_weak   = 0.8 p g_w / (0.2 p g_w + N0)
   SINR_strong = 0.2 p g_s / N0                (after SIC)
   R = (B / (N/2)) log2(1 + SINR)
   ```
   It checks SIC feasibility (`sic_feasible`) and also returns the OMA rates:
   R = (B/N) log2(1 + (P/N) g / (N0 density x B/N)).
3. `uav_env.py`: every step calls `noma_rates` for the drone's position. `access="noma"` (the default) scores with the NOMA rates,
   `access="oma"` with the OMA rates; `info` always reports both (`coverage_noma`, `coverage_oma`, `sum_rate_noma_mbps`,
   `sum_rate_oma_mbps`).
4. The dataset's `sweep` table stores NOMA and OMA coverage and total speed for every drone position, altitude and power.

Settings in `config.yaml`: `noma_alpha_weak: 0.8`, `pairing: extreme`, `env.access: noma`.
**Nobody chooses the NOMA settings yet:** the pairing and the 80/20 split are fixed. Making them decisions is roadmap stage B.

## 13.3 NOMA in the dataset (all drone positions, from the sweep)
Averaged over every drone position in the sweep, good and bad alike:

| Power | NOMA / OMA total speed, v1 | NOMA / OMA total speed, v2 | Coverage NOMA / OMA, v2 |
|---|---|---|---|
| 0 dBm | 0.894 | 0.800 | 0.146 / 0.167 |
| 10 dBm | 1.097 | 1.008 | 0.409 / 0.410 |
| 20 dBm | 1.170 | 1.144 | 0.682 / 0.654 |
| 30 dBm | 1.152 | 1.166 | 0.847 / 0.816 |

NOMA's advantage in total speed holds at every crowd size (ratio 1.13-1.15 from 100 to 1,000 users). At extremely low power
(0 dBm) OMA is better: noise dominates and the weak user is held back by the strong user's interference.
Figure: [noma_vs_oma_v1.png](figures/noma_vs_oma_v1.png).

## 13.4 NOMA measured inside the game (hypothesis H3)
`python noma_vs_oma.py --profile <name>`: every pilot plays the same 100 scenarios twice, once with NOMA and once with OMA, with a
16 Wh battery so every pilot survives the 300 s. The search pilots evaluate candidate spots with the scheme being tested, so each
scheme gets its own best decisions. Values: NOMA / OMA / paired NOMA minus OMA (95% CI); `*` = significant.

### At 30 dBm (default scenarios: 1 x 1 km, 0-5 buildings)
NOMA vs OMA (H3). Profile default, 100 scenarios, 30 dBm, battery 16 Wh. Values: NOMA / OMA / paired NOMA - OMA (95% CI); * = the CI excludes 0.

| Pilot | coverage: NOMA / OMA / NOMA-OMA | total speed (Mbps): NOMA / OMA / NOMA-OMA | fairness: NOMA / OMA / NOMA-OMA | rescue outage: NOMA / OMA / NOMA-OMA |
|---|---|---|---|---|
| B0 | 0.882 / 0.870 / +0.012* (+/-0.008) | 275.1 / 228.8 / +46.3* (+/-6.1) | 0.731 / 0.922 / -0.192* (+/-0.012) | 0.069 / 0.069 / +0.000 (+/-0.000) |
| B1 | 0.884 / 0.900 / -0.017* (+/-0.007) | 328.7 / 262.8 / +66.0* (+/-9.2) | 0.689 / 0.888 / -0.199* (+/-0.011) | 0.098 / 0.098 / +0.000 (+/-0.000) |
| B2 | 0.887 / 0.905 / -0.018* (+/-0.007) | 328.2 / 263.8 / +64.3* (+/-8.8) | 0.694 / 0.896 / -0.201* (+/-0.011) | 0.088 / 0.088 / +0.000 (+/-0.000) |
| B3 | 0.909 / 0.929 / -0.020* (+/-0.006) | 297.7 / 270.9 / +26.8* (+/-6.6) | 0.726 / 0.925 / -0.199* (+/-0.011) | 0.037 / 0.055 / -0.018* (+/-0.009) |

### At 20 dBm (profile `lowpower`)
NOMA vs OMA (H3). Profile lowpower, 100 scenarios, 20 dBm, battery 16 Wh. Values: NOMA / OMA / paired NOMA - OMA (95% CI); * = the CI excludes 0.

| Pilot | coverage: NOMA / OMA / NOMA-OMA | total speed (Mbps): NOMA / OMA / NOMA-OMA | fairness: NOMA / OMA / NOMA-OMA | rescue outage: NOMA / OMA / NOMA-OMA |
|---|---|---|---|---|
| B0 | 0.797 / 0.745 / +0.052* (+/-0.006) | 171.8 / 141.2 / +30.6* (+/-4.1) | 0.753 / 0.849 / -0.096* (+/-0.011) | 0.323 / 0.323 / +0.000 (+/-0.000) |
| B1 | 0.830 / 0.764 / +0.065* (+/-0.011) | 222.0 / 175.4 / +46.6* (+/-5.6) | 0.706 / 0.815 / -0.109* (+/-0.011) | 0.271 / 0.271 / +0.000 (+/-0.000) |
| B2 | 0.835 / 0.769 / +0.066* (+/-0.011) | 221.7 / 176.0 / +45.7* (+/-5.4) | 0.714 / 0.824 / -0.110* (+/-0.011) | 0.262 / 0.262 / +0.000 (+/-0.000) |
| B3 | 0.865 / 0.808 / +0.058* (+/-0.009) | 218.4 / 172.1 / +46.4* (+/-6.9) | 0.751 / 0.884 / -0.134* (+/-0.008) | 0.190 / 0.203 / -0.013* (+/-0.012) |

### Hard scenarios (profile `hard`: 2 x 2 km, 20 dBm, 3-8 buildings, sudden or drifting crowds)
NOMA vs OMA (H3). Profile hard, 100 scenarios, 20 dBm, battery 16 Wh. Values: NOMA / OMA / paired NOMA - OMA (95% CI); * = the CI excludes 0.

| Pilot | coverage: NOMA / OMA / NOMA-OMA | total speed (Mbps): NOMA / OMA / NOMA-OMA | fairness: NOMA / OMA / NOMA-OMA | rescue outage: NOMA / OMA / NOMA-OMA |
|---|---|---|---|---|
| B0 | 0.428 / 0.420 / +0.008 (+/-0.009) | 57.0 / 49.7 / +7.3* (+/-3.0) | 0.504 / 0.566 / -0.062* (+/-0.010) | 0.846 / 0.846 / +0.000 (+/-0.000) |
| B2 | 0.633 / 0.568 / +0.065* (+/-0.008) | 159.5 / 119.2 / +40.3* (+/-4.7) | 0.562 / 0.609 / -0.048* (+/-0.006) | 0.524 / 0.524 / +0.000 (+/-0.000) |
| B3 | 0.675 / 0.616 / +0.059* (+/-0.005) | 155.8 / 104.9 / +50.8* (+/-7.4) | 0.592 / 0.670 / -0.078* (+/-0.009) | 0.506 / 0.537 / -0.031* (+/-0.016) |

Charts: [30 dBm](figures/noma_vs_oma_in_game_default_30dBm.png), [20 dBm](figures/noma_vs_oma_in_game_lowpower_20dBm.png),
[hard](figures/noma_vs_oma_in_game_hard_20dBm.png).

## 13.5 What the measurements say
1. **NOMA always gives more total speed:** about 20-27% more for every pilot at 30 and 20 dBm, all significant.
2. **NOMA serves more people when power is scarce:** at 20 dBm it covers 5-7 more people per 100 for every pilot, all significant.
3. **At full power (30 dBm) OMA serves slightly more people** with pilots that place the drone well (B1-B3: 1.7-2.0 fewer people
   per 100 with NOMA). Only the parked drone B0 still gains coverage with NOMA.
4. **NOMA is less fair** (Jain's index 0.10-0.20 lower): strong users get much more than weak users.
5. Rescue outage is the same or slightly better with NOMA (B3: 3.1 fewer rescue users unserved per 100 in `hard`).
6. **The harder the scenario, the more NOMA helps:** in `hard` the moving pilots serve 6-7 more people per 100 with NOMA
   (B2 +0.065, B3 +0.059, significant) and get up to 48% more total speed (B3: 155.8 vs 104.9 Mbps). For the parked drone B0
   the coverage gain (+0.008) is not significant: NOMA helps most when the drone is also placed well.

## 13.6 Why NOMA loses coverage at full power: the 232 kbps ceiling
With a fixed split, the weak user always receives the strong user's signal as interference:
```
SINR_weak = 0.8 p g_w / (0.2 p g_w + N0)  <  0.8 / 0.2 = 4      however large p g_w becomes
R_weak    <  (2 x 50 kHz) x log2(1 + 4)  =  232 kbps
```
Checked numerically on scenario 1: the fastest weak user gets exactly 232 kbps at 30, 40 and even 60 dBm, while the same users
under OMA get 507, 673 and 1,005 kbps. **Video users need 500 kbps, so a video user placed in the weak half of a pair can never be
served with NOMA**, however close the drone flies. With more power OMA catches up and overtakes on coverage, while NOMA keeps its
lead in total speed. The NOMA picture shows the ceiling: the weak half of the users sits on a flat line just above 200 kbps
([7_noma_pairs_lowpower.png](figures/7_noma_pairs_lowpower.png), right panel).

This is the classic limitation of fixed power allocation in NOMA. It is a property of the model, not a bug, and it points to the
fix.

## 13.7 Pictures
- [6_noma_pairs_default.png](figures/6_noma_pairs_default.png): scenario 1 (300 users, 30 dBm). Coverage NOMA 0.927 vs OMA 0.923;
  total speed 182.5 vs 146.0 Mbps.
- [7_noma_pairs_lowpower.png](figures/7_noma_pairs_lowpower.png): scenario 7 (1,000 users, 20 dBm). Coverage NOMA 0.81 vs OMA 0.76;
  total speed 337 vs 263 Mbps; 58 users served only thanks to NOMA, none only by OMA. Lines join the 60 pairs nearest the drone.
- Make your own: `python noma_picture.py --seed <n> [--profile <name>] [--x X --y Y --h H]`.

## 13.8 Next steps for NOMA (roadmap stage B)
1. **Choose the power split per pair** instead of a fixed 80/20: for example a closed-form split that gives each weak user just
   its minimum rate and the rest to the strong user, and later the AI choosing it. Expected to remove the 232 kbps ceiling and the
   coverage loss at full power.
2. **Better pairing:** k-means on channel gain, and need-aware pairing (avoid putting a high-rate user in the weak role).
3. **The AI decides the NOMA settings** together with position, altitude and power (curriculum step 6): the joint problem
   studied in the literature.
4. **Imperfect SIC** (a residual factor) and **bit-error rate** as ablations. Only then do real SIC failures appear.
5. Report H3 with all of the above, with 5 seeds for any AI result.

## 13.9 How to explain it to an examiner
"NOMA lets two users share one frequency slice by splitting power; the strong user removes the weak user's signal with SIC. In our
simulator NOMA always increases total throughput by about 20-27%, and it serves more users when transmit power is limited. With a
fixed 80/20 split the weak user's SINR is capped at 4, so its rate cannot exceed 232 kbps, which is why OMA can cover slightly more
users at full power. That is why the next step is adaptive power allocation per pair."
