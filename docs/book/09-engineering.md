# Chapter 9. Engineering

## 9.1 Repository
GitHub: `vathsa1703/Major_project` (public). Default branch `main`, protected. Collaborators: `vathsa1703` (owner);
`Arani-Acharjee` invited with write access (pending acceptance on 2026-10-19). Sagar and Harshita not yet invited.

```
CLAUDE.md                project rules and current state (read at the start of every session)
CONTRIBUTING.md          how to work: branch, test, pull request, review
requirements.txt         simulator, baselines, tests (numpy pandas matplotlib pyyaml gymnasium pytest xlsxwriter openpyxl)
requirements-rl.txt      + stable-baselines3, torch, tensorboard (only for training and evaluating the AI)
requirements-docs.txt    + reportlab (only for rebuilding the book PDF with docs/book/build_pdf.py)
pyproject.toml           ruff (lint), pytest and coverage settings
.github/                 CI workflow, CODEOWNERS, pull-request template
docs/                    assumptions.md, g3_baselines.md, rl_g4.md, roadmap.md, book/ (this book), summary/ (plain-English
                         summary PDF), prereg/ (pre-registrations and results of the final studies), case_nepal/ (Kathmandu)
uav_dataset/
  config.yaml            every setting and profile (change values here, never in the code)
  make_dataset.py        physics, scenarios, movement, obstacles, channel (incl. the model-mismatch true world), NOMA, energy
  export_excel.py        CSVs -> one Excel workbook
  uav_env.py             the Gymnasium game (nominal vs true channel: env.gains / evaluate(model=...))
  baselines.py           pilots B0-B8, B6fc, B6dep, B6r / B6true / B6meas, B3obs*, report-fed B6rep / B3rep
  run_baselines.py       runs pilots on many scenarios, writes the comparison table
  evalstats.py           mean +/- 95% CI, paired differences
  rl_utils.py            control modes, decision hold, AI and random adapters, model settings
  rl_net.py              CNN map reader (needs PyTorch)
  rl_train.py            PPO training
  rl_eval.py             AI vs random vs baselines on a split
  view_run.py            play one scenario with one pilot, save a GIF
  compare_run.py         several pilots on one scenario in one picture
  noma_vs_oma.py         H3: every pilot under NOMA and under OMA, paired comparison
  noma_picture.py        the NOMA pairs on the map and every user's speed under NOMA vs OMA
  access_benchmark.py    the four access schemes at each scheme's best spot (one snapshot)
  altitude_by_class.py   Gate G2 diagnostic (best altitude per user class)
  mobility_check.py      H1 check (fixed drone vs best position over time)
  accel_loiter_exp.py    step 5: acceleration limit and the circling pilot B7 (7.10)
  oracle.py              the clairvoyant pilot (7.11); sites_exp.py competing-sites room tests (7.12-7.13)
  g5_eval.py             G5 round-1 evaluation (8.9)
  voi_exp.py             value of location information: runner + analysis (7.14)
  anticip_exp.py         anticipation rule: footprint, old/new cells, fit, evaluation; anticip_report.py tables (7.15)
  hybrid.py              hybrid timing AI environment; hybrid_tables.py, hybrid_train.py, hybrid_eval.py (8.10)
  mismatch_exp.py        wrong-physics room test, B6meas tuning, confirmation; mismatch_eval.py AI evaluation (8.11)
  osm_place.py           OpenStreetMap download/processing; place.py height grid, 3-D ray test, place crowd (7.16)
  nepal_case.py          Kathmandu case study runner, report, figures (7.16); places/ holds the processed map
  quadsim.py             simulated quadcopter with autopilot and wind (4.9); sim2sim_exp.py point mass vs quadcopter
  dashboard.py           Streamlit dashboard; dashboard_core.py its logic (no Streamlit import)
  test_*.py              505 tests
```
Not committed: `uav_dataset/data/`, `data_v1/`, `results/`, logs, Excel files, `docs/papers/` (local copies of papers).

## 9.2 How work flows (D-12)
1. Branch from `main`: `git checkout -b name/what-it-does`.
2. Before pushing: `python -m ruff check .` and `python -m pytest -q --cov`.
3. Open a pull request into `main` and fill in the template (what changed, which hypothesis or gate, checklist, how tested).
4. CI must be green; the code owner (`vathsa1703`) reviews; stale approvals are dismissed on new pushes; review conversations must
   be resolved. Merges so far were done by the owner's instruction with the admin bypass (the owner cannot approve his own PRs).

**Branch protection on `main`:** pull request required; 1 approving review from a code owner; dismiss stale reviews; status checks
`test (3.11)` and `test (3.12)` required and the branch must be up to date; conversation resolution required; no force pushes, no
deletion; admin enforcement off.

## 9.3 Continuous integration (`.github/workflows/ci.yml`)
| Job | What it runs |
|---|---|
| `test (3.11)`, `test (3.12)` | install `requirements.txt`, `ruff check .`, `pytest -q --cov` (fails below 80% coverage on `make_dataset.py`, `uav_env.py`, `baselines.py`, `evalstats.py`), smoke run `make_dataset.py quick` |
| `rl smoke test (3.12)` | install `requirements-rl.txt` (CPU PyTorch), run `test_rl.py` and `test_rl_net.py` including a short PPO training |

Lint rules: ruff E, F, W, I, B with line length 120; E741, E702 and E731 ignored (single-letter names, `a; b` and short lambdas
are normal in the math code).

## 9.4 Tests (505 on 2026-10-26)
Counted with `python -m pytest --collect-only -q` on the integration branch `final/integrate-2` (all 505 pass; the full
suite takes about 10 minutes on the laptop with `OMP_NUM_THREADS=2`). The earlier count was 399 on 2026-10-23.

| File | Tests | Covers |
|---|---|---|
| `test_noma.py` | 9 | gain vs distance, rate vs power, power split, SIC check (forced failure), pairing, scenario variety, class mix |
| `test_mobility.py` | 19 | bounds, snapshot count, reproducibility, speed limits, sudden events, attraction, group shape |
| `test_phase45.py` | 13 | obstacle geometry, blocked-link loss, fading on/off and mean power, energy model, battery |
| `test_env.py` | 11 | Gymnasium checker, determinism, limits, speed cap, battery end and penalty, truncation, reward versions, fading |
| `test_pipeline.py` | 9 | splits never overlap, config consistency, user ranges, sweep shape and values, NOMA vs OMA at high power, Jain index |
| `test_parameters.py` | 7 | values derived from Zeng's formulas, propulsion equation, FSPL reference, LoS probability, assumptions document coverage |
| `test_profiles.py` | 9 | profiles change only what they name, never leak, environment runs under each |
| `test_baselines.py` | 76 | statistics, helpers, every pilot (now including B6dep, B6r, B6true, B6meas) valid and deterministic, B0-B6 behaviours, information-ladder pilots ignore what their rung may not see, runner accounting, report |
| `test_compare_run.py` | 3 | same scenario for every pilot, dead drone counts zero, determinism |
| `test_rl.py` | 54 | control modes (incl. `moveby`), waypoint flight, decision hold, scenario pool, static crowd, reward parts, observation groups (incl. the announcement), model settings, viewer pilots, PPO smoke, Dict observation, uncapped maps, crowd size, history, fresh seed pool, privileged state only when asked, the AI never asks for it when flying |
| `test_rl_net.py` | 11 | CNN output size, reproducibility, position sensitivity, PPO with CNN, noise annealing, Dict extractor, the actor's output unchanged when only privileged data changes (before and after training), SAC save/load |
| `test_accel_loiter.py` | 24 | acceleration limit off = old results bit-exact, limit bound, shaking exploit closed, energy formula, braking without overshoot, B7 circle radius and speed, run-to-empty prediction |
| `test_sites.py` | 26 | competing sites: old results bit-exact with an all-active mask (all four radio schemes, a whole B6 mission), coverage only over active users, the switch schedule, site distance and map bounds, walking speed caps, the countdown off by default, B8 behaviour, the oracle on sites profiles |
| `test_oracle.py` | 22 | coverage table equals the game's evaluation, evaluate(t) leaves the game untouched, the planner's first move equals B6's, every planned move is flyable, planner equals brute force on a small grid, bound never below the planner, replay deterministic, never imported by the AI code |
| `test_dashboard_core.py` | 18 | dashboard logic without streamlit: same settings give the same disaster, trace equals the experiment code, maps render, comparisons, plan and battery advice |
| `test_access.py` | 45 | adaptive NOMA and optimised OMA: closed form, imperfect SIC, brute force on small crowds, power budget, monotone in power, odd crowds, rescue first, old schemes unchanged |
| `test_noma_access.py` | 8 | NOMA default, both schemes reported, OMA scoring, evaluate uses the tested scheme, NOMA total speed, H3 table and runner, NOMA picture |
| `test_b6fc.py` | 17 | forecasting pilot: flight prediction equals a real flight, B6 when nothing moves or nothing is announced, never reads the future, announcement used only when announced, memo and screening, confirmation runner, shards and merge |
| `test_quadsim.py` | 26 | simulated quadcopter: hover, kicks, steps, limits, geofence, wind and gusts, integration step, energy vs Zeng, dynamics off = bit-exact (stored fingerprint to 1e-12 relative), every pilot flies the quad, 3D viewer payload, no UI/RL imports |
| `test_place.py` | 16 | real place: local metres, OSM processing and height rules, committed map reproducible, ray test vs brute force, geometric LoS, link cache, crowd assumptions, every pilot runs, no overrides, 3D payload, synthetic scenarios unchanged |
| `test_voi.py` | 20 | phone reports: full information = B6 / B3 exactly, seeded and nested reporters, invisible non-reporters, count scaling, GPS error per report, report age, stale movers on sites, radio layer serves the true users, B6 fingerprint and the default pilot list unchanged |
| `test_anticip.py` | 8 | anticipation rule: new cells change one thing each, memo-backed evaluation, footprint radius, cell parameters and model, shards, runners, fit and evaluation end to end |
| `test_b6dep.py` | 9 | departure-time pilot: two-leg flight equals a real flight, B6 without / unannounced / after the event, never reads the future, extrapolation cap, determinism, beats B6fc where B6fc leaves too early |
| `test_hybrid.py` | 16 | hybrid timing AI: tables equal the oracle tensor, table-driven B6 flies exactly like live B6, follow/leave mapping, reward, episode length, B-target from the announcement only, ignores the future, raw observation groups, training pool disjoint, PPO smoke |
| `test_mismatch.py` | 29 | wrong physics: off by default and bit-exact in every old profile, true vs nominal channel, shadowing field, hidden buildings, separate rng streams and draws, B6r / B6true / B6meas behaviour and information parity, profiles change only `mismatch`, refused on a real place, cache keys |

Bugs caught by tests or CI so far: the fading flag not reaching the channel (test), a missing `tabulate` dependency (CI), a
policy adapter used before `reset()` (test).

## 9.5 Pull requests
| PR | Merged | Title |
|---|---|---|
| #1 | 10-15 | Add CI, lint config, code owners, PR template and pipeline tests |
| #2 | 10-19 | Verify parameters against the papers; assumptions table and tests |
| #3 | 10-19 | Baselines B0-B5, runner, stats and the Gate G3 comparison |
| #4 | 10-19 | Config profiles (lowpower, bigarea, hard) and baselines on harder scenarios |
| #5 | 10-19 | Add B6 (grid search + altitude): B4's lead was altitude choice |
| #6 | 10-19 | RL pipeline (PPO), play-your-own-scenario viewer, RL CI job |
| #7 | 10-19 | compare_run.py: compare several pilots on one scenario in one picture |
| #8 | 10-19 | RL: waypoint controls + 10-second hold (PPO now beats random, not yet B2) |
| #9 | 10-21 | NOMA vs OMA in the game (H3), G4 experiments 2-6, roadmap, and the project book |
| #10 | 10-21 | Plan step 1: information-ladder pilots and why the AI stalls |
| #11 | 10-21 | Book: owner's decisions and reviewed designs for tracks 1 and 2 |
| #12 | 10-21 | Track 1: adaptive NOMA vs equally optimised OMA (H3) |
| #13 | 10-21 | Track 2: better learner (PPO/SAC, privileged critic) and the G4 verdict |
| #14 | 10-21 | Step 5: acceleration limit, turning energy, circling pilot B7; new roadmap |
| #15 | 10-21 | Dashboard: Streamlit showcase and planning tool |
| #16 | 10-21 | Step 3: clairvoyant pilot - no room for anticipation in today's scenarios |
| #17 | 10-22 | Scenario redesign (D-52): competing sites, B8, room test - 7 of 9 designs pass |
| #18 | 10-22 | Prepare the dashboard for online sharing (Streamlit Community Cloud) |
| #19 | open | Record the live dashboard link |
| #20 | 10-23 | Integrate: confirmation, G5 round 1, move-by steering, announcement inputs, simulated quadcopter + 3D |
| #21 | open (draft) | Draft final report (report, literature matrix, viva slide outline, PDF) |
| #22 | 10-26 | Real-place case study: Kathmandu floods (scenario based on OSM), dashboard + 3D |
| next | open | Integrate the four final studies (value of location information, anticipation rule, hybrid timing AI, model mismatch) and this book update (branch `final/integrate-2`) |

The four study branches (`contrib/value-of-info`, `contrib/anticipation`, `rl/hybrid-timing`, `exp/model-mismatch`) had no
pull requests of their own; they are merged one by one (`--no-ff`) in `final/integrate-2`. Conflicts and how they were
resolved: `oracle._cache_key` (both B6dep's and the hybrid's new sections excluded); `baselines.py` (B6dep and the mismatch
pilots both kept, one pilot list); `make_dataset.channel_gain` and `uav_env` (the real-place links of #22 and the mismatch's
true world both kept; mismatch + real place raises `NotImplementedError`, the combination was never built). Integration
fixes in the same branch: three over-long lines (ruff), the oracle / hybrid cache keys ignore the new pilot-only sections
and an inactive mismatch (old caches stay valid), `run_baselines.default_policies()` keeps the default run list unchanged,
and `test_voi`'s pinned pilot list now includes the merged pilots.

The first commit (`4cd4cc4`, 2026-10-15) imported the generator, environment and 52 tests directly to `main` (the repository was
empty); everything after went through pull requests.

## 9.6 Software versions (owner's laptop)
Windows 11, Python 3.14.7, numpy 2.5.3, pandas 3.0.6, matplotlib 3.11.2, pyyaml 6.0.3, gymnasium 1.4.0, pytest, xlsxwriter,
openpyxl, stable-baselines3 2.9.0, torch 2.14.1 (CPU), tensorboard 2.21.0. CI uses Python 3.11 and 3.12 with the newest packages
(dependencies are not pinned; a new release can break a build).

## 9.7 Commands
```
pip install -r requirements.txt                 # simulator, baselines, tests
pip install -r requirements-rl.txt              # + the AI
cd uav_dataset
python make_dataset.py all && python export_excel.py
python -m pytest -q --cov                        # from the repository root
python run_baselines.py --profile hard
python rl_train.py --policy cnn --std_end 0.05 --name my_run
python rl_eval.py --model results/rl/my_run/model.zip --split val
python view_run.py --seed 5 --profile hard --policy B3
python compare_run.py --seed 105 --profile rl_static --policies random,B2,B3,ppo --model results/rl/my_run/model.zip
cd ..
pip install -r requirements-docs.txt && python docs/book/build_pdf.py   # rebuild the book PDF (about 1 minute)
```

## 9.8 Troubleshooting (things that actually happened)
| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: matplotlib` | packages not installed | `pip install -r requirements.txt` |
| `PermissionError` writing the Excel file | the file is open in Excel | close it, run `export_excel.py` again |
| CI fails with `Import tabulate failed` | a library installed locally but not listed | never rely on unlisted packages; fixed by a hand-written table |
| Training 6x slower than usual (about 160 steps/s) | laptop on battery, CPU throttled | plug in the charger (about 1,000 steps/s) |
| A training run disappeared | the session restarted and killed background jobs | re-run; training is deterministic by seed; checkpoints every 10k decisions |
| Two training runs side by side are slow | they share the CPU | set `OMP_NUM_THREADS=2`, or run one at a time |
| A run seems hung for hours, workers use almost no CPU | the laptop slept | keep it awake and plugged in; it resumes on wake |
| Commits show the wrong author | the machine's global git identity is another project's | `git config user.name/user.email` set inside this repository only |
| A model plays badly in the viewer | wrong controls or decision hold | models now carry their settings in `config.json` and the tools read them |
| CI: `test_profiles.py` fails after `test_place.py` has run (PR #22) | `apply_profile` resets the config from the base but never deletes keys, so a key a test added to the profiles table leaked into later tests | `test_place.py` restores `md.CFG["profiles"]` on teardown; tests change only keys the base config already has |
| CI: a bit-exact fingerprint test (`test_quadsim.py`) fails on GitHub but passes on the laptop (PR #22) | numpy's exp/log kernels differ by CPU type in the last bits; CI runners vary | compare stored fingerprints to 1e-12 relative (`pytest.approx`), far below any real change; the rounded SHA-1 in `test_voi.py` was checked: its closest value is 4.7e-14 from a rounding boundary, about 400 times the last-bit noise |
