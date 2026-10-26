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
*(Update 2026-10-21: items 1 and 4 (imperfect SIC) are done, see 13.9.)*
1. **Choose the power split per pair** instead of a fixed 80/20: for example a closed-form split that gives each weak user just
   its minimum rate and the rest to the strong user, and later the AI choosing it. Expected to remove the 232 kbps ceiling and the
   coverage loss at full power.
2. **Better pairing:** k-means on channel gain, and need-aware pairing (avoid putting a high-rate user in the weak role).
3. **The AI decides the NOMA settings** together with position, altitude and power (curriculum step 6): the joint problem
   studied in the literature.
4. **Imperfect SIC** (a residual factor) and **bit-error rate** as ablations. Only then do real SIC failures appear.
5. Report H3 with all of the above, with 5 seeds for any AI result.

## 13.9 Adaptive NOMA vs equally optimised OMA (Track 1, 2026-10-21)
**Plain words.** Until now every pair of users got the same power and the same fixed 80/20 split, whatever they needed. Now the
drone works out, for every person, the *least* power that still gives them the speed they need, serves the cheapest people
first until the power runs out, and only then pairs them up for NOMA. To be fair, OMA gets exactly the same treatment. The
question becomes: when both are run as well as possible, does NOMA still serve more people?

**How it works (`access_rates()` in `make_dataset.py`, D-39).** Two new access schemes; the old `noma` and `oma` are unchanged
(byte-identical code, and the old numbers reproduce exactly).
- `oma_opt`: every user has its own slice b = B/N. Minimum power for user i: p_i = (2^(R_i/b) - 1) x noise x b / g_i. Users are
  admitted cheapest-first while the total stays within the drone's power P (this is provably the best way to maximise the number
  served). Leftover power is shared by scaling every admitted user's power by the same factor.
- `noma_opt`: the same cheapest-first order, but the admitted users are paired strongest-with-weakest on a double slice 2b,
  and each pair gets its **minimum NOMA power** in closed form, with an imperfect-SIC residual eps (the share of the removed
  signal that stays behind):
  ```
  p_s = gamma_s N (eps gamma_w / g_w + 1 / g_s) / (1 - eps gamma_s gamma_w)      (strong user)
  p_w = gamma_w (p_s + N / g_w)                                                (weak user)
  gamma = 2^(R / 2b) - 1,  N = noise power on 2b
  ```
  If NOMA would cost more than serving the two users separately (possible only when eps > 0), the pair uses OMA inside its slot.
  The largest number of users that fits is found by binary search. Unserved users' slots are wasted in **both** schemes.
- Options: `sic_eps` (0 or 0.05, engineering assumption) and `rescue_first` (admit rescue users before everyone else).
- Checks: 45 new tests, including brute force on small crowds (`oma_opt` exact; `noma_opt` within one user), every rate
  recomputed from the returned powers, SIC decoding always possible, more power never serves fewer people. I also re-derived the
  closed form independently: rates come out exact to 1e-15 over 2,000 random pairs.

**Results in the game** (100 scenarios, 16 Wh, every pilot survives; `*` = significant after Holm correction over all 60
comparisons of the table):

| Profile, pilot | OMA | NOMA (fixed) | OMA optimised | **NOMA adaptive** | adaptive NOMA minus optimised OMA |
|---|---|---|---|---|---|
| lowpower (20 dBm), B0 | 0.745 | 0.797 | 0.893 | **0.944** | +0.051* |
| lowpower, B2 | 0.769 | 0.835 | 0.924 | **0.962** | +0.039* |
| lowpower, B3 | 0.808 | 0.865 | 0.945 | **0.983** | +0.038* |
| hard (2 x 2 km, 20 dBm), B0 | 0.420 | 0.428 | 0.658 | **0.690** | +0.032* |
| hard, B2 | 0.568 | 0.633 | 0.777 | **0.811** | +0.034* |
| hard, B3 | 0.616 | 0.675 | 0.808 | **0.849** | +0.041* |

Same runs, other measures (B3 shown; B0 and B2 behave the same way):

| B3 | total speed (Mbps) | fairness (Jain) | rescue users not served |
|---|---|---|---|
| lowpower: NOMA fixed / OMA opt / **NOMA adaptive** | 218.4 / 71.3 / **93.1** | 0.751 / 0.409 / **0.472** | 0.190 / 0.030 / **0.004** |
| hard: NOMA fixed / OMA opt / **NOMA adaptive** | 155.8 / 45.9 / **54.0** | 0.592 / 0.340 / **0.356** | 0.506 / 0.287 / **0.203** |

Against optimised OMA, adaptive NOMA is better on **every** measure in every case (coverage +0.03 to +0.05, total speed +5 to
+23 Mbps, fairness and rescue outage better, all significant). One snapshot at 30 dBm (default scenarios, 20 validation maps):
adaptive NOMA 1.000 vs optimised OMA 0.989, while fixed NOMA still trails OMA (0.913 vs 0.933). **The 232 kbps ceiling of
13.6 is gone.**

Charts: [8_access_schemes_hard.png](figures/8_access_schemes_hard.png),
[9_access_schemes_lowpower.png](figures/9_access_schemes_lowpower.png).

**Imperfect SIC (eps = 0.05, hard).** Adaptive NOMA loses 0.014-0.024 coverage and 16-36% of pairs switch to OMA inside the
pair, but it still beats optimised OMA by +0.016 to +0.018*. **Rescue first (hard).** With adaptive NOMA, rescue outage drops
sharply (B3 0.203 to 0.117, B2 0.258 to 0.169) for a small coverage loss (0.011-0.029); with optimised OMA the same rule costs
0.11-0.20 coverage, because a far rescue user is very expensive alone, while in NOMA the pairing absorbs that cost.

**The honest trade-off.** The optimised schemes give everyone just their minimum speed and spend the rest of the power reaching
far, expensive users. So compared with the old fixed schemes they **serve far more people (+0.12 to +0.26) but deliver about
55-65% less total speed and lower fairness**. This is a property of the goal "serve as many people as possible", not of NOMA.
In a disaster that goal is the right one (a survivor with a working connection matters more than a fast connection for
someone already served), but the report must say "more people served, less total speed", not "better on every metric".

**What is not verified.** The binary search can miss a few users at single candidate spots (up to 4% of N measured, mean about
0.1%, and 0 at every best spot); it can only under-count adaptive NOMA, so its advantage is if anything understated. "Within
one user of the optimum" is shown on small crowds, not proven. About 10-17% of NOMA pairs give the weak user less than half the
power (fine in theory; practical receivers sometimes assume otherwise; no clamp tested). sic_eps and the minimum rates are
engineering assumptions. The game runs use seeds 0-99 like the earlier H3 runs.

**Reproduce:** `python noma_vs_oma.py --profile hard --schemes oma,oma_opt,noma,noma_opt` (also `--profile lowpower`,
`--eps 0.05`, `--rescue_first`), and `python access_benchmark.py`.

## 13.10 How to explain it to an examiner
"NOMA lets two users share one frequency slice by splitting power; the strong user removes the weak user's signal with SIC. In our
simulator NOMA always increases total throughput by about 20-27%, and it serves more users when transmit power is limited. With a
fixed 80/20 split the weak user's SINR is capped at 4, so its rate cannot exceed 232 kbps, which is why OMA can cover slightly more
users at full power. That is why the next step is adaptive power allocation per pair."

Since Track 1: "When both schemes allocate power optimally to serve as many users as possible, NOMA still serves 3-5
more users per 100 than OMA, with more throughput and fewer unserved rescue users; imperfect SIC halves but does not
remove that gain. The price of the coverage objective, for both schemes, is lower total throughput."

## 13.11 NOMA vs OMA in the final studies (2026-10-24)
**Plain words.** Every study since G5 ran the same pilot or AI twice: once with adaptive NOMA and once with equally optimised
OMA (same bandwidth, same power, both with the G5 settings: SIC residual 0.05, rescue users first). NOMA wins everywhere, and
by more than on the synthetic maps of 13.9.

| Study (book section) | Who flies | NOMA | OMA | NOMA - OMA (paired, 95% CI) | Source |
|---|---|---|---|---|---|
| Hybrid timing AI, 2 km sudden (8.10) | hybrid AI, 3 seeds | 0.752 | 0.620 | +0.132 ± 0.034* | `uav_dataset/results/hybrid/summary.md` |
| Hybrid timing AI, 2 km over 1 min (8.10) | hybrid AI, 3 seeds | 0.734 | 0.606 | +0.128 ± 0.031* | same |
| Wrong physics, 8 hidden buildings (8.11) | AI, 3 seeds | 0.756 | - | +0.111 [+0.078, +0.143] | `docs/prereg/model_mismatch_results.md` |
| Wrong physics, all errors (8.11) | AI, 3 seeds | 0.700 | - | +0.078 [+0.053, +0.103] | same |
| Wrong physics, textbook right (8.11) | AI, 3 seeds | 0.817 | - | +0.076 [+0.051, +0.100] | same |
| Kathmandu case (7.16) | B6 | 0.781 | 0.654 | +0.127 ± 0.008* | `docs/case_nepal/results.md` |
| Kathmandu case (7.16) | B7 | 0.774 | 0.626 | +0.148 ± 0.007* | same |
| Synthetic `hard_g5`, same seeds (7.16) | B6 | 0.837 | 0.773 | +0.064 ± 0.021* | same |

("-": the results file gives the difference, not the OMA mean.) Two caveats: the AIs were trained with NOMA, so their OMA runs
are outside what they learned (the gain may be overstated for the AI rows); on the real map the larger gain for the searching
pilots (+0.127 vs +0.064 for B6) is explained by a hypothesis (the 3-D line of sight splits users into two groups about 19 dB
apart, and NOMA pairs gain most from unequal channels) that was not tested separately.
