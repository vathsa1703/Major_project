# Chapter 3. Decision log

Every significant decision, with the question, the options considered, what was chosen, who decided, and the consequences.
New decisions are appended with the next number. A decision is never deleted; if it is reversed, a later decision says so.
"Owner" means Srivathsa (repository owner and reviewer). "Proposed" means suggested by the assistant and accepted by the owner.

| # | Date | Decision | Who |
|---|---|---|---|
| D-01 | 10-14 | Work phase by phase, each with a check | Owner |
| D-02 | 10-14 | One Excel workbook with a `split` column, CSVs kept | Owner (proposed) |
| D-03 | 10-14 | Bandwidth scales with the number of users | Owner |
| D-04 | 10-14 | Five user classes with the spec's mix; minimum rates as assumptions | Owner |
| D-05 | 10-14 | Extend altitudes to 1,000 m (diagnostic) and check the optimum per class | Owner |
| D-06 | 10-14 | Three walking mobility models, 300 s, snapshots every 30 s | Proposed |
| D-07 | 10-15 | Battery 10 Wh with 300 s episodes | Owner |
| D-08 | 10-15 | UAV limits 15 m/s, 50-300 m | Owner |
| D-09 | 10-15 | Add sudden crowd events (surge, hotspot jump) | Owner |
| D-10 | 10-15 | Gymnasium environment plus a simple viewer | Owner |
| D-11 | 10-15 | Generated data is not committed; it is regenerated from config and seeds | Proposed |
| D-12 | 10-15 | Branches, pull requests, owner review, CI, protected `main` | Owner |
| D-13 | 10-16 | Our drone is a small 20 N UAV derived from Zeng's formulas | Proposed |
| D-14 | 10-19 | Main metric `coverage_full` (a dead drone counts zero); B5's energy cost clamped at 0 | Proposed |
| D-15 | 10-19 | Harder scenarios as config profiles; `hard` uses 16 Wh | Owner (both options) |
| D-16 | 10-19 | Add B6 (grid search plus altitude) before judging RL | Proposed |
| D-17 | 10-19 | Install stable-baselines3 and PyTorch; keep them in `requirements-rl.txt` | Owner |
| D-18 | 10-19 | Train on seeds 0-99, choose on 100-119, test 120-139 once | Proposed (plan) |
| D-19 | 10-19 | Waypoint ("fly to this spot") controls | Proposed |
| D-20 | 10-19 | The agent decides once every 10 s | Proposed |
| D-21 | 10-19 | Merge PRs with the owner's admin bypass after CI is green | Owner |
| D-22 | 10-19 | Observation groups and a CNN in a separate module | Proposed |
| D-23 | 10-19 | Save each model's settings next to it | Proposed |
| D-24 | 10-19 | The AI learns by itself: no hints, no menu, no privileged information | Owner |
| D-25 | 10-19 | Park dynamic events and real-place scenarios until the gates are done | Owner |
| D-26 | 10-19 | G4 tuning: five experiments, a stopping rule, agreed fallbacks | Owner (plan approved) |
| D-27 | 10-19 | Anneal the exploration noise (outside the five experiments) | Owner |
| D-28 | 10-19 | The no-hardware 3D flying simulation is the last stage | Owner |
| D-29 | 10-19 | Keep a detailed project book, updated after every step | Owner |
| D-30 | 10-14 | Never call it a digital twin; it is a simulation-based planning tool | Plan |
| D-31 | 10-15 | Sagar's task becomes own, review and extend (draft, not yet sent) | Proposed |
| D-32 | 10-21 | NOMA/OMA switch in the game; H3 measured for every pilot | Owner ("add NOMA") |
| D-33 | 10-21 | G4 tuning stops: the stopping rule is reached at 0.555 vs B2 0.610 | Rule D-26 (owner to decide next) |
| D-34 | 10-21 | Keep figures and GIFs in the book; the book is updated in every pull request | Owner |

---

### D-01 Work phase by phase
**Question.** The owner's parameter spec described the finished simulator; build it all at once?
**Decision.** No: phases 1-5, each with a check (validate the slice, configurable scenarios, time and mobility, obstacles and
fading, energy and the environment).
**Why.** Several spec values conflicted (battery never runs out, rates collapse at 1,000 users, sweep too large). Building in
layers lets each layer be tested before the next depends on it.

### D-02 One Excel workbook
**Question.** The owner expected one dataset file; the generator produced six CSVs (two tables x three splits).
**Options.** One workbook with sheets; two CSVs with a `split` column; keep six CSVs.
**Decision.** One workbook (`export_excel.py`) with one sheet per table and a `split` column; the CSVs stay as the source.
**Consequence.** Excel's limit is about 1,048,575 rows per sheet; the exporter fails loudly above it. The workbook later grew to
145 MB, slow to open; a small preview workbook was offered for the guide.

### D-03 Bandwidth scales with users
**Question.** With 1,000 users on 10 MHz each user gets about 10 kHz and nobody reaches a minimum rate.
**Options.** Scale bandwidth with users (50 kHz each); scale minimum rates down; keep both fixed.
**Decision.** Bandwidth = users x 50 kHz (200 users = 10 MHz).
**Consequence.** Per-user rates stay comparable across scenario sizes; unrealistic beyond about 100 MHz. Listed as an
engineering assumption.

### D-04 Five user classes
**Decision.** rescue 10%, video 20%, voice 30%, iot 20%, normal 20% (the spec's example). Minimum rates rescue 200 kbps,
video 500 kbps, voice 50 kbps, iot 10 kbps, normal 100 kbps.
**Status.** The minimum rates are **engineering assumptions, not signed off.** Video is almost never covered at low power.
They must be decided before any number goes into the report.

### D-05 Altitudes to 1,000 m and a per-class check
**Why.** After D-04 the mixed altitude curve lost its peak. Extending the sweep and checking per class showed the optimum exists
for every class and moves lower as the rate target rises. Altitudes above 500 m are diagnostic only (the plan's maximum is
300-500 m).

### D-06 Walking mobility
Random waypoint, group drift and attraction to shelters; speeds 0.5-1.5 m/s; 300 s at 1 s steps; snapshots every 30 s so the
trajectory table fits in Excel. The sweep still uses the t = 0 positions.

### D-07 Battery 10 Wh, 300 s
**Options.** Small battery (10 Wh, about 3.5 minutes of hover) with 300 s; a realistic 50 Wh battery with 1,800 s episodes; the
spec's 50-100 Wh with short episodes (never runs out).
**Decision.** 10 Wh, 300 s.
**Consequence found later (D-14).** Hover needs 14.7 Wh for 300 s and the cheapest cruise about 11 Wh, so no policy survives;
rankings then mostly measure survival time. The `hard` profile uses 16 Wh. The battery size remains an open decision for the
final experiments (a battery sweep is experiment E7).

### D-08 UAV limits
Maximum horizontal speed 15 m/s, vertical 5 m/s, altitude 50-300 m, start at 150 m, maximum power 30 dBm.

### D-09 Sudden crowd events
`surge` (everyone suddenly runs to one point) and `hotspot_jump` (one crowd relocates), 3 m/s, starting between 60 and 180 s.
**Why.** The first H1 check showed gentle movement barely hurts a parked drone.

### D-10 Gymnasium and a viewer
New dependency approved by the owner. The environment is the "game" all pilots and the AI play through the same `env.step()`.

### D-11 Data is not committed
About 430 MB of generated data is regenerated in about a minute from `config.yaml` and the fixed seeds, so it stays out of git.

### D-12 Strict review workflow
Everyone works on `name/what-it-does` branches; pull requests need green CI (lint, tests on Python 3.11 and 3.12, coverage gate,
smoke run) and the code owner's approval; stale approvals are dismissed; `main` cannot be force-pushed or deleted. The owner's
admin bypass stays on because GitHub does not let an author approve their own PR (D-21).

### D-13 Our drone
Zeng's paper's own simulated drone weighs 100 N and hovers at about 1.37 kW. Our parameters correspond to a small 20 N drone
(R = 0.4 m, Omega = 300 rad/s), hovering at 168.49 W. This is our choice, stated in `docs/assumptions.md`; d0 = 0.6 is unverified.

### D-14 The main metric and B5
`coverage_full` = coverage averaged over the whole 300 s, counting 0 after the battery dies. It rewards staying alive. Because
forward flight at about 10 m/s costs less than hovering in Zeng's model, B5's "extra energy for moving" became negative and was
clamped at 0; B5 then behaves like B3.

### D-15 Harder scenarios as profiles
Profiles (`lowpower`, `bigarea`, `hard`, later `rl_static`, `rl_static_g20`) override config values without changing the default
dataset. `hard`: 2 x 2 km, 20 dBm, 3-8 obstacles of 60-200 m, only sudden or drifting crowds, 16 Wh, 14 x 14 search grid.

### D-16 B6
B4's lead could have been altitude choice. B6 (grid search plus five altitudes) tied B4, which settled the question and set the
RL bar on `hard` at 0.74.

### D-17 RL libraries
stable-baselines3 and PyTorch (CPU) approved by the owner. They live in `requirements-rl.txt` so the simulator, baselines and most
tests do not need them; a separate CI job runs the RL tests.

### D-18 Data splits for RL
Training scenarios come only from seeds 0-99 (a scenario pool in the environment); validation seeds 100-119 are used to compare
and choose models; test seeds 120-139 are read once at the end.

### D-19 Waypoint controls
**Problem.** With velocity controls the trained drone found the crowd and then drifted away: hovering requires exactly zero
velocity and nothing rewarded it.
**Decision.** The action is a spot on the map (and later an altitude and a power); the drone flies there and stays. Velocity
controls remain available (`xy`, `xyz`, `xyzp`).

### D-20 Decide every 10 seconds
**Problem.** Deciding every second, the drone circled around the crowd.
**Decision.** The choice is held for 10 s, the rhythm the baselines re-plan at; a game becomes 30 decisions instead of 300.

### D-21 Merging
The owner instructs merges; they are done with the admin bypass after CI is green, never before.

### D-22 Observation groups and the CNN
The observation is built from named groups (position, velocity, battery, time, previous scores, the two maps), so runs can drop
groups. The CNN lives in `rl_net.py` so importing the rest never needs PyTorch.

### D-23 Settings next to each model
`config.json` is saved next to every model, and the viewers and evaluator read controls, decision hold and observation groups
from it. This prevents playing an old model with the wrong settings.

### D-24 The AI learns by itself
**Question.** Should the AI choose from 100 map cells to make learning easier?
**Owner's decision.** No. The AI gets raw measurements and the coverage score and must learn by itself. Not allowed: hints, a
menu of candidate spots, imitating the baselines, privileged information. Allowed: network design, training length,
hyperparameters, seeds, curriculum order. Recorded in `CLAUDE.md`.

### D-25 Parked ideas
Dynamic events (rising flood, evacuation, aftershock, survivors appearing, drone failure) and real-place scenarios (for example a
Nepal flood from public map data) wait until the planned gates are done. They are now stages C and D of the roadmap.

### D-26 Stopping rule for G4
Five experiments (diagnose, leaner observation, CNN, finer map, more training and seeds), then stop. If PPO is still significantly
below B2: report it, consider moving to moving crowds (the owner may relax G4), try SAC or a memory network, and only with the
owner's approval a hybrid design reported separately.

### D-27 Noise annealing
Diagnosis showed the exploration noise stays near 0.33 (about +-330 m), wider than a crowd. The owner approved one extra
experiment outside the five: shrink the noise linearly from 0.37 to 0.05 over training. It gives the AI no information about the
task.

### D-28 The flying simulation comes last
A simulated quadcopter with an autopilot model, driven by our controller through "fly to this spot" commands, is the final stage
(stage F of the roadmap). Real hardware is outside this project.

### D-29 This book
Everything is documented in `docs/book/` and updated after every step (journal entry, decision, results).

### D-30 Wording
From the plan: "simulation-based planning tool"; "digital-twin-style" only with real state data or trace replay.

### D-31 Sagar's task
Most of Sagar's first three weeks of tasks (crowd generator, movement, environment) already existed. A message was drafted: own,
review and extend the world code, write the explanation document, build the evacuation model, then scenario presets. Not yet sent
by the owner.

### D-32 NOMA measured inside the game
**Question.** NOMA was only visible inside the physics; the guide needs to see it working.
**Decision.** `UAVEnv(access="noma"|"oma")` and `noma_vs_oma.py`: every pilot plays the same scenarios under NOMA and under OMA
with the same total bandwidth and power, compared scenario by scenario; `noma_picture.py` shows the pairs. This is hypothesis H3
(experiment E3) done properly.
**Consequence.** NOMA wins total speed everywhere and coverage when power is scarce; with the fixed 80/20 split OMA is slightly
better on coverage at full power because the weak user is capped at 232 kbps. This motivates stage B: choosing the power split.

### D-33 The G4 stopping rule is reached
Five experiments and the extra noise experiment are done; the best AI (E5a, 0.555) is still significantly below B2 (0.610).
Per D-26, tuning stops and the result is reported. The next step is the owner's decision: relax G4 and move to moving crowds,
or try other learners (SAC, memory) that give no hints.

### D-34 Figures and GIFs in the book
Pictures and animations that support a result are copied into `docs/book/figures/` (and `figures/gifs/`) with captions saying
which run produced them. Every pull request that changes results updates the book.
