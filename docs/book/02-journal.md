# Chapter 2. Journal

A dated record of everything done, in order, with the real outputs. Decisions are numbered **D-xx** and explained in
Chapter 3. Pull requests are **#n** (Chapter 9). Numbers are copied from the run outputs; "val8" means the score on the first 8
validation scenarios printed during training, "val20" the official score on all 20 validation scenarios.

---

## 2026-10-14

### 1. First run of the dataset generator
The folder `uav_dataset_generator/uav_dataset/` contained `make_dataset.py`, `config.yaml`, a README and an earlier `data/` folder.
- `python make_dataset.py all` failed: `ModuleNotFoundError: No module named 'matplotlib'`.
- Installed the README's packages (`pip install numpy pandas matplotlib pyyaml`): matplotlib 3.11.2, pandas 3.0.6, pyyaml 6.0.3.
- Second run succeeded:
  - users tables: train 20,000 rows, val 4,000, test 4,000 (200 users x 100/20/20 scenarios);
  - sweep tables: train 387,200 rows, val 77,440, test 77,440;
  - pictures `users_preview.png` and `altitude_check.png`.

### 2. The owner shared the plan
`ARCHITECTURE.md` (system design: crowd generator, mobility, obstacles, UAV and energy model, A2G channel, NOMA engine, metrics,
Gymnasium env, baselines, RL, FastAPI backend, React dashboard) and `PROJECT_PLAN.md` (pitch, objectives, hypotheses H1-H4, scope
tiers, gates G1-G7, roles, month-by-month phases, experiments E1-E14, viva questions, deliverables). Both are summarised in
Chapter 1 and `CLAUDE.md`.

### 3. Explanations given to the owner
What the project is, what RL is (agent, state, action, reward, policy, PPO vs SAC), whether a business is possible, whether
NOMA is present (yes: superposition, SIC, feasibility check, OMA reference in `noma_rates`), why there are six CSV files (two
tables x three splits) and what every column means.

### 4. Review of the owner's parameter specification
The owner pasted a full parameter list (scenario, UAV, energy, channel, NOMA, sweep). Review findings:
1. A 50-100 Wh battery never runs out in 300-600 s episodes (hover is about 170 W), so the battery would not matter.
2. A 10-20 m/s drone is 10-20 times faster than walking crowds, so following a crowd is trivial.
3. A 25 m grid sweep with 30 altitudes, 5 powers and 50 seeds is about 12-19 million rows: too big for Excel and slow.
4. With 1,000 users on 10 MHz each user gets about 10 kHz: almost everyone is in outage.
5. Moving crowds need a time column; obstacles need their own table.
6. RL does not train on this dataset; the environment generates its own experience.
Decision: go phase by phase (D-01).

### 5. Phase 1: make the existing slice trustworthy (plan approved)
1. **Pictures checked.** `users_preview.png` shows clustered crowds plus scattered users with rescue users circled.
   `altitude_check.png` shows a coverage peak at 0 dBm near 250 m: **the altitude optimum (Gate G2) is reproduced** on dataset v1.
2. **NOMA vs OMA** on `sweep_train.csv` (v1, 100 scenarios):

   | Power | NOMA / OMA sum rate | Rows where NOMA wins | Coverage NOMA / OMA | Fairness NOMA |
   |---|---|---|---|---|
   | 0 dBm | 0.894 | 5.9% | 0.081 / 0.104 | 0.525 |
   | 10 dBm | 1.097 | 64.9% | 0.456 / 0.447 | 0.658 |
   | 20 dBm | 1.170 | 97.3% | 0.838 / 0.793 | 0.772 |
   | 30 dBm | 1.152 | 100% | 0.994 / 0.994 | 0.766 |

   NOMA gives 10-17% more total rate from 10 dBm up and loses at 0 dBm (interference-limited weak user at low SNR; plausible
   physics, not proven). Figure: [noma_vs_oma_v1.png](figures/noma_vs_oma_v1.png).
3. **NOMA unit tests** (`test_noma.py`, 5 tests, all pass; pytest installed).
4. **One Excel file** (`export_excel.py`, xlsxwriter installed): `uav_noma_dataset.xlsx` with sheets `users` (28,000 rows) and
   `sweep` (542,080 rows), a `split` column, 46 MB. Row counts confirmed from the sheet dimensions in the file (D-02).
5. **`CLAUDE.md`** written for the project root.

Observations: `energy_j_per_step` was the same constant (168.5 J) in every row; at 0 dBm OMA had a higher sum rate than NOMA.

### 6. "Is this enough data?"
Answer: count scenarios, not rows (140). Enough for the altitude and NOMA-vs-OMA charts and for Gate G3 (100+ seeded scenarios);
not relevant for RL (the environment generates experience); not enough for generalisation (every scenario had 200 users and 3
clusters); no moving crowds, battery or obstacles yet. The fixes were mapped onto phases 2-5.

### 7. Phase 2: configurable scenarios (dataset v2)
Owner decisions: **bandwidth scales with users** (D-03) and **the spec's class mix** (D-04).
- `data/` copied to `data_v1/` before regenerating.
- Each seed now draws its own number of users (100, 300, 600 or 1,000), clusters (2-5), cluster radius (50-200 m) and scatter
  share (5-10%). Five user classes with their own minimum rates. Bandwidth = users x 50 kHz. Pairing `extreme` or `random`.
  The SIC check became its own function `sic_feasible`. 9 tests pass.
- **Correction of an earlier claim:** random pairing does not make SIC fail. When the "weak" and "strong" roles are assigned by
  channel gain, SIC is always feasible; a failure needs imperfect SIC or need-based rules. The test now checks the function with
  a deliberately bad pair.
- **Results (v2, train):** NOMA/OMA sum-rate ratio 0.800 / 1.008 / 1.144 / 1.166 at 0 / 10 / 20 / 30 dBm; coverage NOMA vs OMA
  0.146/0.167, 0.409/0.410, 0.682/0.654, 0.847/0.816. By user count the ratio stays 1.13-1.15 (1.145 at 100 users, 1.127 at 300,
  600 and 1,000), so NOMA's gain does not shrink with more users.
- **The altitude peak disappeared** from the mixed chart: coverage kept rising to 500 m (best altitude 400 m in 54 scenarios,
  500 m in 44, 300 m in 2). Owner approved: extend altitudes to 1,000 m and check per class (D-05).
- **Per-class check** (`altitude_by_class.py`, 20 scenarios): an optimum exists for every class. Best altitude:

  | Class (min rate) | 0 dBm | 10 dBm |
  |---|---|---|
  | iot (10 kbps) | 500 m | 600 m |
  | voice (50 kbps) | 200 m | 600 m |
  | normal (100 kbps) | 100 m | 400 m |
  | rescue (200 kbps) | 50 m | 200 m |
  | video (500 kbps) | 50 m | 50 m |

  Higher rate target means a lower best altitude. The earlier mixed curve was dominated by low-rate users. Video coverage is near
  zero at 0 dBm, which comes from the assumed minimum rates (not signed off). Figure:
  [altitude_by_class_v2.png](figures/altitude_by_class_v2.png). Sweep size: 813,120 rows.

### 8. Phase 3: time and moving crowds
- `simulate()` moves users for 300 s in 1 s steps and stores a snapshot every 30 s; models: random waypoint, group drift,
  attraction to shelters; speeds 0.5-1.5 m/s (D-06). New `trajectory` table (823,900 rows) and Excel sheet; the Excel file became
  147 MB. 20 tests pass.
- **H1 check** (`mobility_check.py`, 15 scenarios, fixed drone at the centre, 200 m, 20 dBm): a fixed drone already covered 79-89%
  and the best possible position added only 1-6 points (attraction 0.016 at t = 0 to 0.054 at t = 300; group drift 0.055/0.060;
  random waypoint 0.024/0.011). **Crowd movement barely mattered: the dynamics were too gentle.**
- Not done in this phase: evacuation model, a `demand` field, time in the sweep.

### 9. Other discussions that day
Real maps (OpenStreetMap) were first raised; the owner chose "dataset first". The owner asked what phases 4 and 5 are, what H1
is, and for the Excel file (shown in Explorer).

---

## 2026-10-15

### 10. Phases 4 and 5: questions answered by the owner
Battery **10 Wh with 300 s episodes** (D-07), UAV limits **15 m/s, 50-300 m** (D-08), **add harder dynamics** (surge, hotspot
jump, D-09), **install Gymnasium and build the environment with a simple viewer** (D-10).

### 11. Phase 4 built: obstacles and fading
- 0-5 collapsed-building rectangles per scenario (40-150 m sides). A drone-user link whose 2D segment crosses a rectangle gets
  15 dB extra loss (engineering assumption). Geometry: vectorised slab (Liang-Barsky) test.
- Optional fading: Rician (K = 10 dB) for LoS links and Rayleigh for NLoS, unit mean power, off in the dataset.
- Two harder mobility models: `surge` (everyone suddenly runs to one point) and `hotspot_jump` (one crowd suddenly relocates),
  at 3 m/s.

### 12. Phase 5 built: energy, battery and the game
- Rotary-wing energy model (Zeng-Xu-Zhang) with a climbing term (weight x climb rate, no recovery when descending),
  communication power (P_tx / 0.4) and 5 W of circuit power. Hover = 168.49 W. Battery 10 Wh.
- `uav_env.py`: Gymnasium environment with 211 observation numbers (11 scalars and two 10 x 10 heatmaps), 4 actions
  [vx, vy, vz, power], reward v1 (coverage) or v2 (coverage minus 0.05 x energy relative to hovering), episode ends when the
  battery is empty (with a penalty) or after 300 s. It passes Gymnasium's own checker.
- `view_run.py`: a top-down map viewer that saves a GIF. First demo (seed 3, surge, 1,000 users, follow-the-crowd): 247 steps,
  mean coverage 0.904, battery empty. Figure: [viewer_first_run.png](figures/viewer_first_run.png).
- **A test caught a real bug:** `UAVEnv(fading=True)` did not turn fading on (the channel only read the config switch). Fixed.
- 52 tests pass.

### 13. Dataset v3 and the H1 re-check
- The Excel export first failed with `PermissionError` because the file was open in Excel; after the owner closed it the file was
  rebuilt: `scenarios` 140, `obstacles` 341, `users` 74,900, `trajectory` 823,900, `sweep` 813,120 rows, 145 MB.
- **H1 re-check** at 10 dBm with obstacles, 30 scenarios (fixed drone vs the best position at each snapshot):

  | Mobility | Fixed | Best | Gap | Largest gap at one moment |
  |---|---|---|---|---|
  | surge | 0.527 | 0.754 | 0.227 | 0.753 |
  | attraction | 0.602 | 0.738 | 0.137 | 0.393 |
  | random waypoint | 0.614 | 0.677 | 0.063 | 0.233 |
  | group drift | 0.644 | 0.700 | 0.056 | 0.203 |
  | hotspot jump | 0.720 | 0.761 | 0.041 | 0.180 |

  Sudden events make a fixed drone fall behind; gentle drift does not. Only 3-9 scenarios per model, so this was a first sign.

### 14. The Excel file verified cell by cell
The workbook was read back with openpyxl. No empty cells; every sheet has the `split` column; ranges as expected (users 100-1,000
per scenario, bandwidth 5-50 MHz, 0-5 obstacles, mobility counts group drift 33, surge 31, hotspot jump 28, random waypoint 24,
attraction 24; class counts voice 22,639, normal 15,023, iot 14,950, video 14,899, rescue 7,389). Notable: only `extreme` pairing
appears; NOMA coverage peaks at 0.990 while OMA reaches 1.000 (not investigated); `outage_rescue` averages 0.650. Full list in
Chapter 5.

### 15. The team's task documents
The owner shared task documents for Sagar (world and environment), Arani (baselines, statistics, CI) and Harshita (RL). Finding:
most of Sagar's weeks 1-3 (crowd generator, random-waypoint movement, Gymnasium environment) already existed. A new task message
was drafted for Sagar: own, review and extend the world code, and build the evacuation model (D-31). Small errors found in the
task documents (wrong example branch names, CI missing `gymnasium` and `scikit-learn`).

### 16. GitHub repository
- Repository `vathsa1703/Major_project` (public). First commit `4cd4cc4`: 15 files, about 90 KB; the generated data (about 430 MB)
  is excluded and regenerated with one command (D-11). The commit author was set for this repository only (the machine's global
  git identity belongs to another project).
- **Strict workflow requested by the owner:** everyone works on branches, only reviewed code reaches `main` (D-12). Built:
  CI (ruff lint, pytest on Python 3.11 and 3.12, an 80% coverage gate, a smoke run of the generator), `CODEOWNERS`, a PR template,
  `CONTRIBUTING.md`, `pyproject.toml`. Ruff found 91 style findings; the real ones were fixed (a lambda capturing loop
  variables, an unused variable, `zip` without `strict`) and three style rules were relaxed. 9 pipeline tests added: 61 tests,
  87% coverage. **#1 merged.** Branch protection on `main`.
- Arani (`Arani-Acharjee`) invited with write access.

---

## 2026-10-16

### 17. Parameters checked against the papers (#2)
- **Zeng, Xu, Zhang** (arXiv:1804.02238) read: the propulsion formula (Eq. 6), the hover formulas P0 and Pi (Eq. 61), and the
  constants delta = 0.012, k = 0.1, rho = 1.225, s = 0.05 are verified. Our P0 = 79.86 W, Pi = 88.63 W, Utip = 120 m/s and
  v0 = 4.03 m/s **follow from those formulas** for a small 20 N drone (R = 0.4 m, Omega = 300 rad/s): computed 79.80 W and 88.66 W
  (within 0.1%). **The paper's own drone is much bigger** (W = 100 N, hover about 1,370 W). d0 = 0.6 is unverified (the paper
  uses 0.3).
- **Al-Hourani:** the original paper (IEEE WCL 2014, DOI 10.1109/LWC.2014.2342736) could not be read (paywalled; the RMIT
  repository returned 403). The formulas match two secondary papers (arXiv:1802.01117, 1705.03304); the values (9.61, 0.16, 1, 20)
  appear in their simulation tables without an environment label, so "urban" is unconfirmed.
- `docs/assumptions.md` (status of every parameter) and `test_parameters.py` (7 tests): 68 tests.

---

## 2026-10-19

### 18. Baselines B0-B5 and Gate G3 (#3)
- Built `baselines.py` (B0 fixed, B1 follow the biggest crowd, B2 weighted k-means, B3 grid search, B4 particle swarm, B5
  energy-aware), `UAVEnv.evaluate()` (scores candidate spots without changing the game), `run_baselines.py` (parallel runner,
  table with mean +/- 95% CI and paired differences), `evalstats.py`.
- **Finding from a 3-scenario trial:** with 10 Wh **no policy survives 300 s.** Hovering at 30 dBm uses 176 J/s, so 10 Wh lasts
  205 s and 300 s needs 14.7 Wh. **Flying at 10 m/s uses only 134 J/s** (Zeng's power curve), so moving lasts longer than
  hovering. B5's idea ("hover to save energy") does not hold, and its energy cost became negative; it was clamped at 0 (D-14).
- **Full runs (100 scenarios)** at 10 Wh and 16 Wh, tables in Chapter 7. At 16 Wh: B4 0.914, B3 0.909, B5 0.908, B2 0.887,
  B1 0.884, B0 0.882. **Headroom is small: a parked drone already covers 88%.**
- **CI caught a dependency bug:** `pandas.to_markdown()` needs `tabulate`, which was installed locally but not in
  `requirements.txt`. Replaced with a small hand-written table function. 89 tests.

### 19. Harder scenarios (#4)
Owner chose "both": harder scenarios and a battery decision with numbers. Profiles `lowpower`, `bigarea`, `hard` added (D-15).
In `hard` (2 x 2 km, 20 dBm, 3-8 obstacles, only sudden or drifting crowds, 16 Wh), B0 falls to 0.428 and B4 reaches 0.740.
**H1 holds in this regime.** A bug in my own runner (the saved summary's header replaced the table) was found by reading the
output and fixed; summaries were rebuilt from the saved episode data. 99 tests.

### 20. Merges and a conflict
Owner: "merge". #2, #3, #4 merged in order (admin bypass because the owner cannot approve his own PRs). #3 conflicted with #2 in
`.gitignore` (both added entries); both were kept.

### 21. B6 shows where B4's lead came from (#5)
B6 = grid search that also tries five altitudes. On `hard`: **B6 0.741 vs B4 0.740, a tie**; B6 beats B3 by 0.066. B4's lead
over B3 was **altitude choice, not smarter placement**. The bar for RL on `hard` is 0.74 (D-16).

### 22. RL libraries approved and installed
stable-baselines3 2.9.0, PyTorch 2.14.1 (CPU), TensorBoard 2.21.0, with Gymnasium 1.4.0 and Python 3.14 (D-17).

### 23. RL pipeline (#6)
A `static` crowd model and the `rl_static` profile (as hard as `hard` but the crowd stands still), training only on seeds 0-99
via a scenario pool (D-18), a control wrapper for the curriculum, `rl_train.py` (config-driven PPO, reward parts logged
separately), `rl_eval.py` (paired comparison on a split). Reference on val20: Random 0.413, B0 0.441, B1 0.600, B2 0.610,
B3 = B5 0.659.

### 24. First PPO run: below random
300k steps, velocity controls: **val20 0.394, below random (0.413).** Diagnosis: training coverage rose slowly (0.40 to 0.49);
the action noise was still 0.93; the deterministic policy drifted to the map edge (x = 1990); train and validation scores were
alike, so not over-fitting. The value function fitted well (explained variance 0.99).

### 25. Two retries and a slow laptop
Variant A (reward normalisation, starting noise 0.37) and variant B (reward normalisation only) at 1M steps in parallel ran at
only 172 steps/s each. Stopping B did not help. **Cause: the laptop was on battery** (Intel Core 3 100U throttles). Plugged in:
1,074 steps/s. A session restart killed A at about 487k steps; it was re-run (`A_full`) and **reproduced the same first scores**
(0.431, 0.468), which confirms training is deterministic by seed. `A_full` val8 over 1M steps: 0.431, 0.468, 0.414, 0.474,
0.481, 0.420, 0.426, 0.453, 0.427, 0.408: **a plateau.**

### 26. Viewer for any scenario, any pilot (#6) and the comparison picture (#7)
`view_run.py` now plays any seed, profile or custom scenario (`--users 600 --clusters 4 --mobility surge --obstacles 6`) with
B0-B5, random or a trained model. `compare_run.py` puts several pilots on one scenario in one picture. Gallery:

| Figure | Scenario | Result |
|---|---|---|
| [1_hard_moving_crowds.png](figures/1_hard_moving_crowds.png) | hard, seed 5, 600 users, 5 crowds, group drift | B0 0.49, B2 0.51, B3 0.55, B4 0.71, B6 0.71 |
| [2_still_crowd_AI_vs_pilots.png](figures/2_still_crowd_AI_vs_pilots.png) | rl_static, seed 105 | random 0.51, B0 0.53, B2 0.68, B3 0.78, PPO 0.40 |
| [3_surge_custom.png](figures/3_surge_custom.png) | custom: 800 users, 5 crowds, surge, 5 obstacles | B0 0.590, B1 0.600, B3 0.635, B4 0.605 (all die near 200 s) |

**Picture 2 explained the failure:** the PPO drone flew to the crowd (0.8 coverage at 30 s, like B3) and then **kept flying**,
off the map edge, down to 0.2. It learned to find the crowd, not to stop.

### 27. Real scenarios parked
The owner asked about dynamic scenarios and real places (a Nepal flood as an example). Explained what public data can provide
(buildings, shelters, population density, flood extents, terrain, tower locations) and what it cannot (survivor positions).
Owner: finish the plan first; the ideas were written into `CLAUDE.md` (D-25).

### 28. "Fly to this spot" controls and a 10-second rhythm (#8)
- Waypoint controls (`goto`): the action is where to fly; the drone stays when it arrives (D-19). `goto_v1` (decides every
  second, 500k steps): val8 0.447, 0.454, 0.444, 0.472, 0.465. Picture [4_goto_checkpoint.png](figures/4_goto_checkpoint.png):
  no more drifting off, but the drone circled around the crowd (seed 105: 0.638).
- Decide once every 10 s (`HoldWrapper`, D-20): `goto_hold10` (60k decisions): val8 0.477, 0.486, 0.481. **val20 0.525:
  paired +0.095 against random (significant), -0.085 against B2 (significant), -0.134 against B3.** Picture
  [5_goto_hold10.png](figures/5_goto_hold10.png): the drone holds still but settles at a worse spot after passing a good one.
  Gate G4 half met.

### 29. The owner's rule and the stopping rule
The owner rejected the idea of letting the AI pick from 100 map cells: the AI must learn by itself (D-24). A plan was approved
with five experiments, a stopping rule and fallbacks (D-26).

### 30. Experiment 1: why does it not stay at the best spot?
Probe of the `goto_hold10` model on seed 105: it chooses about the same target from the very first decision ((1261, 1934)) and
never changes it; it only passes through the good area on the way. Changing one input group moves its chosen target by:
own velocity 103 m, previous coverage/throughput/fairness 89 m, battery and time 5 m, altitude 6 m, own x,y 8 m, the all-users
map 266 m, the rescue map 445 m. Distance from its target to the best spot: seed 105 546 m (coverage 0.48 vs best 0.83),
seed 100 348 m (0.48 vs 0.51), seed 110 109 m (0.51 vs 0.53). **It reads the map but aims imprecisely.**

### 31. Experiments 2 and 3: leaner observation and a CNN
`obs_groups` (the observation can drop groups; default unchanged), `rl_net.py` (a CNN that reads the two maps as a picture with
coordinate channels), settings saved next to each model (D-22, D-23). 154 tests. Results:

| Run | Network | Observation | val8 at 20k / 40k / 60k | val20 | Paired vs B2 |
|---|---|---|---|---|---|
| E2 `e2_mlp_lean` | MLP | position + maps | 0.481 / 0.466 / 0.492 | 0.543 | -0.067 (sig.) |
| E3 `e3_cnn_full` | CNN | all | 0.496 / 0.502 / 0.516 | **0.549** | -0.061 (sig.) |
| E3b `e3b_cnn_lean` | CNN | position + maps | 0.467 / 0.477 / 0.464 | 0.528 | -0.082 (sig.) |

E3 against random: +0.119 (significant); against B3: -0.110. Architecture and observation barely moved the score.

### 32. The ceiling of the still-crowd test
Best single spot on a 41 x 41 grid at 150 m, full power, reached instantly: mean 0.686 over the 20 validation scenarios; map
centre 0.441. B3 (0.659) is already close to the ceiling: the still-crowd test is the "hello world" step of the curriculum.

### 33. Experiments 4 and 5
- E4 `e4_cnn_grid20` (20 x 20 map, profile `rl_static_g20`): val8 0.487, 0.520, 0.509 (1,080 s). A finer map did not help.
- E5a `e5a_cnn_150k` (CNN, 150k decisions): val8 0.496, 0.502, 0.516, 0.512, 0.532, 0.514, 0.516 (1,670 s; exploration noise
  0.25 at the end). Slow creep, peak 0.532.

### 34. Diagnosis: the exploration noise
In every run the exploration noise ended near 0.32-0.34 (start 0.37): about +-330 m of random wobble on each chosen waypoint
during training, wider than a crowd. The learning signal is dominated by that wobble, which explains why all variants plateau at
0.52-0.55. Fix approved by the owner (D-27): shrink the noise linearly from 0.37 to 0.05 over training.

### 35. Discussions with the owner
"Isn't this basic?" (yes, the still-crowd test is curriculum step 1); where NOMA sits (in `noma_rates`, behind every coverage
number; nobody decides it yet); what the finished project contains; novelty (two literature searches: the broad idea is
published, our contribution would be the benchmark, the fair evaluation and the findings; Chapter 11); the real-world gap
(sim-to-real); why research is not deployed (AT&T's tethered "Flying COW" drone exists; NOMA was standardised in LTE as MUST
according to one survey); the hardware path; a business track. The owner asked for the no-hardware 3D flying simulation as the
last stage of the project (D-28) and for this book (D-29).

### 36. Merges
#7 and #8 merged (owner's instruction). #8 was first updated with the latest `main` in a separate checkout and re-tested; CI
green on Python 3.11, 3.12 and the RL job.

### 37. Experiment 6: noise annealing
`StdAnnealCallback` in `rl_train.py` (`--std_end 0.05`), with a test. E6 (CNN) and E6b (MLP), 60k decisions each; the noise
fell as planned (0.27 at 20k, 0.16 at 40k, 0.06 at the end). val8: E6 0.488, 0.497, 0.475; E6b 0.476, 0.498, 0.490.
**Official val20: E6 0.509 (-0.102 vs B2), E6b 0.536 (-0.074).** The fix did not help: the noise was not the main
bottleneck, and my diagnosis in entry 34 was wrong.

### 38. Official scores of the remaining runs, and the stopping rule
val20 (paired vs B2): E4 finer map 0.545 (-0.065*), **E5a longer training 0.555 (-0.055*, best so far)**. Every variant lies
between 0.51 and 0.56. The five planned experiments and the extra one are done; the best AI is still significantly below B2.
**The agreed stopping rule (D-26) has been reached.** The owner decides whether to relax G4 and move to moving crowds.

### 39. The project book
The owner asked for everything to be documented in detail, "like a book", and kept up to date after every step (D-29). This
book was written: twelve chapters plus a NOMA chapter, figures and GIFs, rebuilt from the session history, the commits and the
saved results.

### 40. NOMA in the game: the OMA switch and hypothesis H3
The owner asked for NOMA to be front and centre ("my sir goes berserk without it"). Built (D-32):
- `UAVEnv(access="noma" | "oma")` (config `env.access`): the same game with NOMA or with OMA (FDMA, same total bandwidth and
  power). Both schemes are always reported in `info`; the search pilots evaluate candidate spots with the scheme being tested.
- `noma_vs_oma.py`: every pilot plays the same scenarios under both schemes; paired NOMA minus OMA per scenario.
- `noma_picture.py`: a picture of the NOMA pairs on the map and every user's speed under NOMA and OMA.
- 8 tests (`test_noma_access.py`).

Results (100 scenarios each, 16 Wh so every pilot survives; Chapter 13 has the tables):
- **30 dBm (default):** NOMA gives +46 to +66 Mbps more total speed (about +20-25%, significant for every pilot). Coverage is
  mixed: B0 +0.012 for NOMA, but B1, B2, B3 0.017-0.020 lower with NOMA. Fairness is about 0.19-0.20 lower with NOMA.
- **20 dBm (`lowpower`):** NOMA wins coverage for every pilot, +0.052 to +0.066 (5-7 more people served per 100), and total speed
  +30 to +47 Mbps. Fairness 0.10-0.13 lower.
- **Hard scenarios (`hard`, 20 dBm, 2 x 2 km):** NOMA covers 6-7 more people per 100 for the moving pilots (B2 +0.065, B3 +0.059,
  significant), total speed up to +48% (B3 155.8 vs 104.9 Mbps), rescue outage lower for B3 (-0.031); B0's coverage gain
  (+0.008) is not significant.
- **Why NOMA loses coverage at 30 dBm:** with the fixed 80/20 split, the weak user of each pair always hears the strong user's
  signal as interference, so its SINR can never exceed 0.8 / 0.2 = 4 and its speed is capped at 100 kHz x log2(5) = **232 kbps**,
  whatever the power (checked: still 232 kbps at 60 dBm, while OMA gives the same users 507 kbps at 30 dBm). Video users
  (500 kbps) in the weak half of a pair can never be served with NOMA. This is the classic limitation of fixed NOMA power
  allocation; the fix (choosing the split per pair) is roadmap stage B.
- Pictures: `noma_picture.py` on scenario 7 at 20 dBm (1,000 users): NOMA coverage 0.81 vs OMA 0.76, total speed 337 vs 263 Mbps,
  58 users served only thanks to NOMA, none only by OMA ([7_noma_pairs_lowpower.png](figures/7_noma_pairs_lowpower.png)).

### 41. GIFs saved into the book
`figures/gifs/`: the first viewer run, a custom 600-user surge flown by B2, the first PPO model, the best AI (E5a) on scenario 105
(coverage 0.609), B3 on the same scenario (0.781), and B4 on the hard scenario 5 (0.709).

### 42. A long pause
The NOMA vs OMA batch, started on 10-19 at 18:17, seemed hung on 10-21: no output for about 42 hours. Its workers had used only
about 140 s of CPU each: the laptop had been asleep, pausing the run. It resumed when the laptop woke and finished normally (all three H3 runs complete on 10-21).

## 2026-10-21

### 43. The book as a PDF
`docs/book/build_pdf.py` turns the Markdown chapters into `docs/book/UAV-NOMA-Project-Book.pdf` (ReportLab, with the DejaVu fonts
that come with matplotlib): a title page, contents with page numbers, every table, list and code block, every figure once, GIFs as
their last frame, and an appendix gallery for figures the text does not link. A bug in my converter (a line starting with "#2,"
was neither a heading nor a paragraph, so the parser never moved on) made the first attempt run for 8 minutes; fixed. New rule:
rebuild the PDF after every change to the book.

### 44. A senior-level plan, reviewed by a second agent (Chapter 14)
The owner asked me to approach the problem as a senior communications and AI engineer would, and to have the solution reviewed by
another agent. My draft: split the problem by time scale (compute the NOMA allocation and the placement, learn only the mission
strategy), fix NOMA with adaptive power allocation, and measure the headroom for RL with an oracle before training more.
The reviewer confirmed the maths and found real gaps: an unfair OMA comparison, a guarantee that is true by construction, a
ceiling that ignores flight time, and above all that **the AI never sees obstacles or demand while the search pilots do**. It also
proposed better steps. I checked its claims in the code, accepted most of them, and declined one (a spatial action head that looks
like the rejected 100-cell menu) until the owner decides. The agreed 7-step plan and four owner decisions are in Chapter 14.

### 45. Step 1 of the plan: why the AI stalls (two agents in parallel)
The owner merged PR #9 and asked for step 1 with several agents working in parallel. Agent 1 built an "information ladder":
three copies of B3's search that know less (only the AI's capped maps; uncapped maps; plus buildings), with 19 tests. Agent 2
checked the AI on its own training scenarios and measured what the capped map hides. Results (Chapter 8.7): the search that
sees only what the AI sees scores 0.605 (level with B2), the AI 0.555; so half the gap to B3 is information and half is
learning. The AI is behind even on scenarios it trained on (underfitting). The map cap hides the size of 59% of the crowd,
but a 20 x 20 map did not help, and B3's real trick is parking *between* crowds, which the AI never learned. I checked the
code, reproduced the main number and showed it does not depend on the assumed crowd size (0.588-0.606).

### 46. Owner's decisions, a second review, and two tracks in parallel
The owner merged PR #10, answered the four questions of Chapter 14.7 (D-38) and asked me to discuss the next designs with
another agent before building, in case it had a better idea. It did. I gave a reviewer my designs for adaptive NOMA and for a
better learner; it ran the real code and found three flaws in the NOMA design (D-39) and one in the learner design (a privileged
critic helps in SAC, hardly in PPO; D-40). I questioned it on speed and training cost; it measured both and we agreed the specs.
Two agents now build the tracks in parallel, each in its own copy of the repository: Track 1 adaptive NOMA vs equally optimised
OMA; Track 2 the better learner. The physics default stays as it is while G4 is open (D-41).
The owner also asked how far the project is from completion: about 55-60% of the core; 5-7 weeks of focused work for the
research question (tracks 1 and 2, G5 on moving crowds, final evaluation), 10-12 weeks with the extras and the flying sim.

### 47. Track 1 done: adaptive NOMA beats equally optimised OMA
The Track 1 agent built two new access schemes (`oma_opt`, `noma_opt`) exactly as agreed in D-39, with 45 tests, and ran them
in the game on 100 scenarios per profile while the AI trained alongside (about 1.5 hours in total on the shared laptop). Result
(Chapter 13.9): with both schemes optimised the same way, NOMA serves 3-5 more people per 100 for every pilot, with more total
speed, better fairness and fewer unserved rescue users; B3 on lowpower reaches 98.3% coverage. Imperfect SIC (eps 0.05) halves
the gain but does not remove it. The catch, for both optimised schemes: much less total speed than the old fixed schemes. I
checked the work: the old schemes are byte-identical and reproduce the Chapter 13 numbers, 227 tests pass, and I re-derived
the power formula independently (exact to 1e-15 on 2,000 random pairs).


### 48. The GIFs were never on GitHub (found and fixed)
Building the PDF from a clean copy of the repository showed 22 pictures instead of 26: the 6 GIFs of the book had never been
committed, because `.gitignore` ignores every `*.gif` (a rule from the start, meant for viewer output). They existed only on the
owner's laptop. Fixed with an exception for `docs/book/figures/gifs/`; the 6 GIFs (4.7 MB) are now in the repository.
