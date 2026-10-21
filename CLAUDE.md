# CLAUDE.md — UAV-NOMA Disaster Network Planning Simulator

Read at the start of every session. Update "Current state" when a phase or gate moves.
(The Maieutic LMS CLAUDE.md that may be loaded from Downloads is a different project. Ignore it here.)

## What we're building
A **simulation-based planning tool** for UAV base stations in disaster areas (ground towers down, survivors in moving clusters, battery-limited UAV, NOMA downlink). Never say "digital twin" without the qualifier ("digital-twin-style" only with state sync / trace replay).
Research question: can a crowd-aware RL controller adapt UAV position, altitude and power to shifting demand better than static and heuristic strategies under a battery limit?
Origin: the guide asked for a moving base station using NOMA; the team extended it with crowds, obstacles, energy and RL. NOMA must stay visible in every result.

## Hypotheses (every experiment serves one)
- H1: adaptive control beats a fixed UAV once crowds move.
- H2: RL beats strong heuristics (k-means B2, grid search B3, PSO B4) only under dynamics + battery limits. Report the regime boundary, including losses. Never compare RL against B0 alone.
- H3: NOMA beats OMA at equal bandwidth and power.
- H4: coordinated multi-UAV control beats independent/centroid placement (stretch).

## Build order and gates (do not start the next layer until the gate passes)
Simulator -> baselines -> RL -> multi-UAV. G1 simulator core (MATLAB parity, tests green) · G2 physics (altitude optimum, energy and NOMA-feasibility tests) · G3 baselines on 100+ seeds · G4 PPO beats random and matches B2 on static · G5 dynamic RL, 5 seeds · G6 multi-UAV · G7 feature freeze at M10.
Tiers: MVP (1 UAV, 3 moving clusters, LoS/NLoS, NOMA pairs, battery, baselines, plots) must ship; Target adds obstacles, evacuation, PPO/SAC, API, dashboard; Stretch is multi-UAV/MAPPO etc.

## Current state
Phases (our own breakdown, mapped to PROJECT_PLAN months): 1 validate the slice · 2 configurable scenarios · 3 time + mobility · 4 obstacles + fading · 5 energy + battery + Gymnasium env: all built · 6 baselines B0-B5 built and run on 100 scenarios (Gate G3, results in `docs/g3_baselines.md`). 7 RL pipeline built, Gate G4 HALF met: best PPO (E5a) 0.555 vs B2 0.610 on val20; the agreed STOPPING RULE IS REACHED (owner to decide: relax G4 and go to moving crowds, or try SAC/memory). 8 NOMA/OMA switch in the game + H3 run (Chapter 13 of the book). Full record: `docs/book/`. Still open from G1/G2: MATLAB parity and finishing the Al-Hourani check.
Only `uav_dataset/` exists: a single-UAV dataset generator + Gymnasium env (`uav_env.py`) + baselines (`baselines.py`) + RL training/eval (`rl_train.py`, `rl_eval.py`) + viewer (`view_run.py`). The first dataset version is kept in `uav_dataset/data_v1/`.
- RL (G4 attempt, branch rl/ppo-static; `pip install -r requirements-rl.txt`; PPO from Stable-Baselines3, MLP 64x64, CPU): `python rl_train.py` (config `rl:`, profile `rl_static` = `hard` with a still crowd, 16 Wh, controls `xy` = move only), `python rl_eval.py --model <zip> --split val`. Training uses only seeds 0-99 (`scenario_seeds` pool), val 100-119 for model choice, test 120-139 untouched. Reference on val (20 scenarios): Random 0.413, B0 0.441, B1 0.600, B2 0.610, B3 = B5 0.659. First PPO run (300k steps) 0.394 = BELOW random (undertrained: action noise still 0.93, deterministic policy drifted to the map edge; train and val scores matched, so not overfitting). Retry with reward normalisation + log_std_init -1: val 0.431/0.468/0.414/0.474 at 100k/200k/300k/400k steps, still far below B2. Training runs ~1,000 steps/s plugged in but ~160 on battery (laptop throttles). The 1M-step run (`A_full`) PLATEAUED: val 0.431/0.468/0.414/0.474/0.481/0.420/0.426/0.453/0.427/0.408 every 100k steps, never near B2, so more steps alone will not fix it. `compare_run.py` on seed 105 shows WHY: the PPO drone flies to the crowd and reaches ~0.8 coverage at t~30 s (same as B3) but then KEEPS FLYING, leaves the map and falls to 0.2: it learned to find the crowd, not to stop. Velocity actions + a reward that only counts coverage give no incentive to output zero velocity near the optimum. FIXES TRIED (full log in `docs/rl_g4.md`): waypoint ('goto') controls stopped the drift but the drone circled (deciding every second); holding each decision for 10 s (`hold_steps`, same rhythm as the baselines) removed the circling and learned 3x faster. BEST RUN `goto_hold10`: val (20 scenarios) PPO 0.525 vs Random 0.430 (paired +0.095*, significant) vs B2 0.610 (paired -0.085*) vs B3 0.659: G4 is HALF MET (beats random, does not match B2). It still leaves the best spot after reaching it. Next idea: discrete grid-cell actions (choose one of 100 cells, a classification problem) or a CNN. Compare pilots on one scenario in one picture: `python compare_run.py --seed 5 --profile hard --policies B0,B2,B3,B4`. Play any scenario: `python view_run.py --seed 5 --profile hard --policy B3` (or `--policy ppo --model ...`, or your own with `--users 600 --clusters 4 --mobility surge --obstacles 6`).
- G3 baselines (`baselines.py`, `run_baselines.py`, `evalstats.py`, 89 tests): at 16 Wh (all survive) B4 PSO 0.914, B3 0.909, B5 0.908, B2 0.887, B1 0.884, B0 fixed 0.882 coverage; B1/B2 do not significantly beat B0. At the configured 10 Wh NO policy survives 300 s (hover needs 14.7 Wh) so the ranking mostly measures survival time. In the Zeng model flying at ~10 m/s costs less than hovering (134 vs 176 J/s), so B5's premise (hover to save energy) fails. HEADROOM IS SMALL: a fixed drone already covers 88%, so RL can gain only a few points. Open decision: battery size / harder scenarios before training RL.
- Harder scenarios (`profiles:` in config.yaml, `UAV_PROFILE` / `--profile`, 98 tests): in profile `hard` (2x2 km, 20 dBm, 3-8 obstacles, dynamic mobility only, 16 Wh) all policies survive and a fixed drone B0 falls to 0.428 while B4 PSO reaches 0.740 (31-point gap vs 3 in the default scenarios): H1 holds there. Ranking: B4 0.740 > B3 = B5 0.675 > B2 0.633 = B1 0.627 >> B0. B6 (grid search + altitude, added to test whether B4's lead was altitude) scores 0.741, a TIE with B4 0.740: B4's lead over B3 was altitude choice, not placement. B4/B6 are one-step greedy, so anticipation is the only thing RL can add. RL bar on `hard` = 0.74. Details in `docs/g3_baselines.md`.
- Phase 4+5 (built, 52 tests pass: `test_noma.py`, `test_mobility.py`, `test_phase45.py`, `test_env.py`): collapsed-building rectangles (0-5 per scenario, 15 dB excess loss on a crossed link = engineering assumption; 2D only, users inside a rectangle count as blocked); optional Rician/Rayleigh fading (off in the dataset, per-env toggle); Zeng-Xu-Zhang propulsion + climb + comm (P_tx/0.4) + 5 W circuit; 10 Wh battery (~3.5 min hover, so it binds in a 300 s episode); UAV limits 15 m/s, 50-300 m; two harder mobility models (`hotspot_jump`, `surge`, 3 m/s). `UAVEnv`: obs 211 floats (11 scalars + two 10x10 heatmaps, all users and rescue users), action [vx,vy,vz,power] in [-1,1], reward v1 coverage / v2 minus lambda_E x energy, battery-empty terminates with penalty. Env and dataset share one physics code path (`make_dataset.py`).
- H1 re-check at 10 dBm with obstacles and harder crowds (`python mobility_check.py 30 10`, 30 scenarios, only 3-9 per mobility model so noisy): oracle-best minus fixed centre drone = surge 0.23, attraction 0.14, random_waypoint 0.06, group_drift 0.06, hotspot_jump 0.04 coverage (max gap at one snapshot: surge 0.75). Dynamics now matter, mostly for sudden events. The oracle is an upper bound, not a controller.
- Phase 2 (dataset v2): each seed draws its own n_users (100/300/600/1000), clusters (2-5), radius (50-200 m), scatter share; 5 classes (rescue/video/voice/iot/normal, spec's mix); bandwidth = n_users x 50 kHz; pairing `extreme` or `random`; `sic_feasible` is its own function. Outputs: `scenarios_*`, `users_*`, `sweep_*` CSVs (sweep 813,120 rows, altitudes 50-1000 m) and `uav_noma_dataset.xlsx` (sheets scenarios/users/sweep, `split` column).
- Checked: altitude optimum exists per class (`altitude_by_class.py`): iot ~500 m, voice 200-600 m, normal 100-400 m, rescue 50-200 m, video 50 m (higher rate target -> lower best altitude; altitudes above 500 m are diagnostic only, plan h_max is 300-500 m). NOMA/OMA sum-rate ratio ~0.80 / 1.01 / 1.14 / 1.17 at 0/10/20/30 dBm (OMA wins at 0 dBm, plausible low-SNR physics, not proven). 9 pytest tests pass.
- Phase 3 (done): `simulate()` moves users 300 s (1 s steps, snapshot every 30 s) with a per-scenario model: random_waypoint, group_drift or attraction (speeds 0.5-1.5 m/s, engineering assumptions). New `trajectory_*.csv` (823,900 rows) and Excel sheet `trajectory`; the xlsx is ~147 MB. 20 tests pass (`test_noma.py`, `test_mobility.py`). Not done: evacuation model, `demand` field, time in the sweep (sweep is t=0 positions only).
- H1 check (`mobility_check.py`, 15 scenarios, fixed drone at centre, 200 m, 20 dBm): a fixed drone already covers 79-89% and the oracle-best position adds only 1-6 points, so crowd movement barely matters in this setup. Dynamics are too weak/benign for H1/H2; Phase 4-5 scenarios must be harder (lower power, bigger area, surges, hotspot jumps, battery) before RL is worth testing.
- Per-class min rates are ENGINEERING ASSUMPTIONS and not signed off by the team. At 0 dBm video (500 kbps) coverage is ~0. Decide before any result goes in a report.
- Open decisions: battery size/episode length and UAV limits were chosen by the user (10 Wh, 300 s, 15 m/s, 50-300 m) but are still assumptions; evacuation (social-force) model and `demand` field not built; Excel export fails with PermissionError if the xlsx is open in Excel (close it first).
- Parameter check (2026-10-16, full table in `docs/assumptions.md`, 7 tests in `test_parameters.py`): Zeng energy formulas, delta, k, rho, s VERIFIED in arXiv:1804.02238. Our P0/Pi/Utip/v0 are DERIVED from those formulas for a small 20 N UAV (R 0.4 m, Omega 300): they match within 0.1%, but the paper's own drone is W = 100 N (hover ~1.37 kW), and d0 = 0.6 is UNVERIFIED (paper uses 0.3). Al-Hourani: formulas CONSISTENT in two secondary papers; (9.61, 0.16, 1, 20) appears in their simulation tables but the 'urban' label is NOT confirmed, and the original IEEE WCL paper (DOI 10.1109/LWC.2014.2342736) was NOT read. Still to do: read that paper and confirm the table.
- NOT done: MATLAB parity (G1); k-means / QoS-aware pairing, optimized power split, imperfect SIC (a real SIC failure only appears there, since roles are set by gain), BER.
- Known gaps: `energy_j_per_step` is constant hover power (168.5 J); `sweep_one` loops in Python over drone positions; no `demand` field per user yet.

## Roadmap (full version in `docs/roadmap.md`, agreed with the owner on 2026-10-19)
A close G4 (stop rule) -> B NOMA becomes a decision (OMA switch, power split, pairing) -> C dynamic scenarios and events (moving crowds, rising flood, evacuation, aftershock, drone failure) -> D realism upgrades (agent does not know where people are, a real place such as a Nepal flood, wind/GPS/delay noise, backhaul, safety layer, a real measurement) -> E evaluation and write-up -> F LAST: a simulated quadcopter with a real autopilot model flying under our controller, no hardware. Business track in parallel.

## Ideas backlog (parked by the owner on 2026-10-19: finish the planned gates first)
- **Dynamic events** (no new libraries): rising flood that pushes people to higher ground, shelter evacuation, aftershock that adds
  collapsed buildings mid-scenario, survivors appearing or disappearing, drone failure. These are where adaptive control should beat a
  parked drone. (Plan items: evacuation model, UAV failure, stress tests E9.)
- **Real-place scenarios**, e.g. a Nepal flood: OpenStreetMap buildings/shelters (obstacles, evacuation targets), WorldPop-style population
  density (crowd placement), satellite flood extents (Copernicus / Sentinel-1) for which areas are underwater, SRTM elevation for terrain,
  OpenCelliD for which towers might be down. Needs new map libraries and internet downloads (ask first); OSM needs a credit line.
  Survivor positions and movement are NOT published anywhere, so the crowd would be RECONSTRUCTED from density + flood extent and must be
  labelled "a scenario based on ...", never "real data" (plan: simulation-based planning tool; twin-style only with real traces, E14).

## Dataset generator (`uav_dataset/`)
    python make_dataset.py users|sweep|all|quick   # all takes ~1 min
    python export_excel.py                         # CSVs -> one Excel file
    python altitude_by_class.py [n]                # Gate G2 diagnostic
    python -m pytest test_noma.py
Change settings only in `config.yaml` (one config per dataset version). Splits by seed, never mixed: train 0-99, val 100-119, test 120-139.
- scenarios table: seed, n_users, n_clusters, cluster_radius_m, scatter_fraction, area_m, bandwidth_hz, pairing.
- users table (t=0 snapshot): seed, user_id, x, y, cluster_id (-1 scattered), class, min_rate_bps.
- sweep table: seed, x, y, h, p_dbm, pairing, coverage, sum_rate_mbps, spectral_eff, fairness, outage_rescue, coverage_oma, sum_rate_oma_mbps, energy_j_per_step.
- Model: mean path loss = FSPL + P_LoS*eta_LoS + (1-P_LoS)*eta_NLoS; NOMA pairs strongest with weakest (or random), fixed 0.8/0.2 split, SIC feasibility checked; OMA = FDMA with the same total bandwidth and power; total power and bandwidth shared by all users; no fading/obstacles.
- Excel sheets hold at most ~1,048,575 rows; `export_excel.py` fails loudly above that.

## Conventions (non-negotiable)
- Vectorized NumPy, no Python loops over users in the hot path, seeded RNG only, config-driven (no magic numbers in code).
- Everything below the Gymnasium env is pure Python/NumPy with no UI or RL dependency. Baselines, RL and the API all call the same `env.step()`.
- Every physical parameter needs value, unit, source (paper) or "engineering assumption", and a sensitivity range. Take Al-Hourani and Zeng-Xu-Zhang values from the papers and cite them. Do not invent.
- Results only from committed configs + seeds. RL: at least 5 seeds, mean +/- 95% CI, paired comparisons, report negative results.
- Tests required for physics changes. Parity tests must stay green once they exist.
- **The AI learns by itself** (owner's rule, 2026-10-19): it gets raw measurements and the coverage reward only. No hints, no menu of candidate spots, no imitation of the baselines, no privileged information. Allowed: network design, training length, hyperparameters, seeds, curriculum order. Stopping rule for G4 tuning: `docs/rl_g4.md` / the approved plan.

## Working agreements
- **Keep the project book current (owner's rule, 2026-10-19).** `docs/book/` records everything in detail. After every step,
  in the same pull request: a dated journal entry (02), a numbered decision for any decision (03), results with exact numbers
  in the right chapter (07, 08, 13), figures/GIFs into `docs/book/figures/`, then rebuild the PDF (`python docs/book/build_pdf.py`,
  needs `requirements-docs.txt`). Never rewrite old entries to look better; record corrections as new entries.
- **Review major plans with an independent agent** (owner's rule, 2026-10-21) acting as a senior communications/AI engineer;
  verify its claims in the code before accepting them; record draft, review and agreed plan in the book.
  Current agreed plan: book chapter 14.6; 4 owner decisions open in 14.7. STEP 1 DONE (10-21, book 8.7): B3obs (search with
  only the AI's maps) 0.605 vs AI 0.555 vs B3 0.659 on val20 -> half information, half learning; AI underfits; B3 parks
  between crowds. OWNER DECISIONS (D-38): asymmetric critic yes (raw true state only, never a baseline's coverage map),
  cell action head NO, hierarchical later, go to moving crowds (G5) after tracks 1+2. IN PROGRESS (10-21): Track 1 adaptive
  NOMA (`oma_opt`/`noma_opt`, admit-then-pair, imperfect SIC; D-39) and Track 2 better learner (uncapped map, crowd size,
  history, fresh seeds, SAC + privileged critic; D-40). Keep `access: noma` default while G4 is open (D-41).
- Go phase by phase. Propose schema changes or new dependencies before making them, then wait for confirmation.
- After each step, summarize in plain words: what was built, what was tested, what is left. Say clearly what was not verified.
- Flag blockers instead of working around them. The rest of the team, not only the author, must be able to explain any code. The user is new to RL/NOMA terms, so explain simply first, then in scientific terms.
- Dashboard/API is a parallel track and never blocks the research.

## Environment
Windows 11, PowerShell/Git Bash, Python with numpy, pandas, matplotlib, pyyaml, pytest, xlsxwriter. Not a git repo.
