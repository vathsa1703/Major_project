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
| D-35 | 10-21 | The book is also published as a PDF, rebuilt after every change | Owner |
| D-36 | 10-21 | Major plans are reviewed by an independent agent before work starts; the agreed plan is Chapter 14.6 | Owner |
| D-37 | 10-21 | Information-ladder pilots B3obs/B3obsU/B3obsUO as diagnostics; assumed crowd 500; not in default runs | Claude (plan step 1) |
| D-38 | 10-21 | Owner's answers to 14.7: asymmetric critic yes; cell action head no; hierarchical design later; move to moving crowds after tracks 1 and 2 | Owner |
| D-39 | 10-21 | Adaptive NOMA design after a second review: admit-then-pair, minimum-power closed form, imperfect SIC from the start, same slot rule for both schemes | Claude + reviewer |
| D-40 | 10-21 | Better-learner design after a second review: uncapped map, crowd size, own measurement history, fresh seeds, SAC with a training-only privileged critic | Claude + reviewer |
| D-41 | 10-21 | The physics default stays `access: noma` until G4 is closed, so the bars the AI is judged against do not move | Claude + reviewer |
| D-42 | 10-21 | Adaptive NOMA added as `noma_opt` (with `oma_opt` as its fair reference); default unchanged; G5 default is the owner's call | Claude |
| D-43 | 10-21 | G4 pass mark: 3-run average on val20 >= B2 - 0.03 (0.580) and clearly above random; extra runs only from 0.570 | Owner (set before the result) |
| D-44 | 10-21 | Acceleration limit 4 m/s^2 (sensitivity 2-8), off until G4 closes; closes the battery-saving 'shaking' exploit | Owner |
| D-45 | 10-21 | Circling pilot B7 is judged by total service until the battery is empty | Owner |
| D-46 | 10-21 | Turning/acceleration energy term added, labelled as our extension of the Zeng model | Owner |
| D-47 | 10-21 | G4 closed as NOT met (best 0.576 < 0.580); stop still-crowd tuning; E0 is the starting agent for G5 | Rule D-43 + D-26 |
| D-48 | 10-21 | Settings for G5 onwards: access `noma_opt`, sic_eps 0.05, rescue_first on, acceleration limit 4 m/s^2 on | Owner |
| D-49 | 10-21 | Still-crowd fixes (G4b: move-by steering, longer training, bigger net; fix C) go to the backlog; the move-by fix is tested inside G5 | Owner |
| D-50 | 10-21 | New roadmap (stages 0-5) replaces the 10-19 order; dashboard built now as a parallel showcase track (Streamlit approved) | Owner |
| D-51 | 10-21 | Clairvoyant test: no room for anticipation in today's moving-crowd scenarios (+0.002 < 0.02); redesign scenarios before G5 | Pre-registered rule |
| D-52 | 10-22 | Scenario redesign 'competing sites', PRE-REGISTERED before any run: design grid, baselines, pass mark, fresh-seed confirmation, negative control | Owner + reviewer |
| D-53 | 10-22 | Phases 1-2 of D-52: battery alone gives no room (B8 = B7); 7 of 9 competing-sites designs pass the 0.02 room test; go on to B6-forecast and fresh-seed confirmation | Pre-registered rule |
| D-54 | 10-23 | The AI may use the announced schedule; it gets the same announcement contents as the forecasting pilot B6fc | Owner |
| D-55 | 10-23 | G5 rules pre-registered before any training: cells, controls, budget, bar, pass mark, NOMA vs OMA report | Owner + Claude |

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

### D-35 The book as a PDF
`python docs/book/build_pdf.py` rebuilds `docs/book/UAV-NOMA-Project-Book.pdf` from the chapters. It needs `reportlab`
(`requirements-docs.txt`); Pillow comes with matplotlib. The Markdown stays the source of truth; the PDF is rebuilt in every pull
request that changes the book.

### D-36 Independent review of plans
The owner asked that major plans be reviewed by a second agent acting as a senior engineer, and that both look for a better
solution together. Claims from the review are checked in the code before being accepted. First use: Chapter 14 (draft, review,
agreed plan, decisions for the owner).

### D-37 The information-ladder pilots
To find out whether the AI is limited by what it sees, three diagnostic pilots run B3's exact search with less information
(Chapter 8.7). They rebuild a stand-in crowd from the maps, so they need an assumed crowd size: **500 people (engineering
assumption, the mean of the crowd sizes drawn by the generator; `baselines.obs_pseudo_users`)**; checked at 200 and 1,000
(validation 0.588 / 0.605 / 0.606). Non-rescue people are given the population's class mix, since their needs are not on the
maps. The pilots are not part of the standard baseline runs (`run_baselines.py` runs B0-B6 unless they are named), so the
G3 tables are unchanged.

### D-38 The owner's four decisions (Chapter 14.7)
1. **Asymmetric critic: yes.** During training only, the critic (the part that judges, thrown away afterwards) may see the
   true raw state: true crowd density, buildings, rescue users, needs, crowd size. The flying policy never sees it. Not
   allowed even for the critic: anything computed by a baseline's scorer (for example a map of coverage at every spot), which
   would amount to copying the baseline. Disclosed in every result that uses it.
2. **Cell action head: no.** It resembles the rejected 100-cell menu (D-24).
3. **Hierarchical design (Option A): later**, after the moving-crowd results.
4. **Move on to moving crowds (G5)** after tracks 1 and 2, whatever the still-crowd score.

### D-39 Adaptive NOMA: the reviewed design (Track 1)
My first design (Chapter 14.3, P1) had four flaws the second review found and I verified:
- With perfect SIC, NOMA never needs more power than OMA for a pair, so a per-pair "NOMA or OMA" choice is decided before any
  experiment. The choice only matters with **imperfect SIC** (a residual epsilon of the removed signal), which is therefore part
  of the design from the start (epsilon = 0 and 0.05, engineering assumption).
- Deciding per pair after extreme pairing ties every cheap user to an expensive partner; the reviewer measured that this is
  even worse than optimised OMA. Instead: **admit users cheapest-first, then pair the admitted users** (strongest with weakest).
  The largest number of users that fits the power budget is found by binary search (measured: same result as an exhaustive scan
  on 4 of 5 scenarios, 40-100 ms per evaluation of 196 spots).
- The split alpha* assumed equal power per pair. Instead each pair gets its **minimum power**, in closed form:
  p_s = gamma_s N (eps gamma_w / g_w + 1 / g_s) / (1 - eps gamma_s gamma_w), p_w = gamma_w (p_s + N / g_w).
- Bandwidth accounting decides the result, so one rule for both schemes: the slot of a user who is not served is wasted.
Both schemes are optimised the same way (`oma_opt`, `noma_opt`); leftover power is scaled up by one common factor. Optional
"rescue users first" admission. The old schemes stay byte-identical.

### D-40 A better learner: the reviewed design (Track 2)
- Inputs (all raw measurements): an **uncapped** crowd map (no saturation), the **number of connected users**, and the drone's
  own last 4 positions and measured coverages. Fresh procedural training scenarios (10,000+ seeds, never val/test). Planning
  horizon gamma 0.95 to match 30 decisions per game.
- **SAC with a privileged critic.** In PPO a privileged critic only estimates how good a situation is (it reduces noise but
  cannot show where to go). In SAC the critic scores *actions*, so a critic that knows the true state can learn where the good
  spots are and steer the policy towards them, while the policy itself still sees only raw measurements. A test checks that
  changing the privileged inputs leaves the policy's output unchanged.
- Budget: SAC is about 5-20 decisions per second on this laptop (PPO about 60), so one seed per variant first, more seeds only
  for a variant that beats B3obs (0.605). Stopping rule: if none does, close G4 as a negative result and go to moving crowds.

### D-41 Keep `access: noma` while G4 is open
Adaptive NOMA changes coverage by 10-25 points and moves the best spots, so it would change B2, B3 and B3obs, the bars the AI is
judged against. Track 2 trains and evaluates with today's NOMA; the project default for G5 is decided after Track 1's results.

### D-42 Adaptive NOMA is an option, not yet the default
`noma_opt` and `oma_opt` are new values of `env.access`; `sic_eps: 0.0` and `rescue_first: false` are new settings under
`access:` (engineering assumptions). The default stays `noma` (D-41), so every earlier number is unchanged and reproducible.
Before G5 the owner chooses the project default once. My recommendation: `noma_opt` with `sic_eps: 0.05` (realistic, still
beats optimised OMA) and `rescue_first: true` (fits a disaster mission), reported next to `oma_opt` so H3 stays a fair test.

### D-43 The G4 pass mark
The old test ("not significantly worse than B2") flipped on luck: two runs with the same 0.573 got opposite verdicts, because
20 scenarios give wide error bars. The owner chose, before E3's result was known: **G4 passes if the average over 3 training
runs on the 20 validation scenarios is at least B2 - 0.03 = 0.580 and the AI is clearly better than random.** Only a version
whose first run reaches 0.570 gets the 2 extra runs.

### D-44 to D-46 Physics fixes approved before the circling experiment
A reviewer found, and I reproduced, that the drone can change velocity instantly, so alternating +10 and -10 m/s every second
keeps it in place at the cheaper forward-flight power (131 J/s instead of 174 J/s hover). No earlier result used this (no pilot
shakes, the AI's reward ignores energy), but any energy result or energy reward could be gamed. The owner approved: an
acceleration limit (4 m/s^2, engineering assumption, sensitivity 2/4/8, **off by default until G4 closes** so earlier results
stay bit-exact); total service until the battery is empty as the circling pilot's main measure; and a load-factor energy term
for turning and braking, labelled as our extension of Zeng-Xu-Zhang (whose rotary-wing model covers steady straight flight).

### D-47 G4 closed as not met
Best 3-run average 0.576 (E0) < 0.580; E3 0.565; E2 below the extra-run threshold. On a second unseen set the AI is clearly
behind B2 (-0.050). By D-43 and the stopping rule (D-26) the still-crowd tuning stops; this is reported as a negative result
with its causes (Chapter 8.7-8.8). Per the owner's decision 4 (D-38) the project moves to moving crowds (G5) with E0 as the
starting agent.

### D-48 Settings from G5 on
The owner chose, for every experiment from G5 on: adaptive NOMA (`env.access: noma_opt`) with imperfect SIC `sic_eps: 0.05`
and rescue users admitted first, plus the acceleration limit (`uav.a_max_mps2: 4`) with the turning-energy term. Optimised OMA
(`oma_opt`) is always reported next to it so H3 stays a fair test. The old settings stay selectable, so every earlier number
remains reproducible. Before any G5 result, the baseline tables are re-run once under these settings.

### D-49 Still-crowd fixes deferred
"We have been stuck here for a long time" (owner): the still-crowd fixes go to the backlog. The fault they target (the AI flies
past the best spot) would also hurt on moving crowds, so the "move by" steering and longer training are built into the G5 plan
instead of a separate round.

### D-50 Roadmap and dashboard
The roadmap of 10-19 is replaced by stages 0-5 (`docs/roadmap.md`): 0 housekeeping and new defaults; 1 G5 (core); 2 disaster
events; 3 realism and safety layer; 4 final evaluation and write-up (core); 5 a simulated drone that really flies (last).
The owner asked for a dashboard now, to show the work visually; it is a parallel track (Streamlit, approved) built on the same
engine, so its numbers equal the experiments'.

### D-51 No room for anticipation in today's scenarios
Pre-registered rule (step 3 plan): if a pilot that knows the crowd's whole future beats B6 by less than 0.02 coverage for every
crowd type, the moving-crowd scenarios leave no room for an anticipating AI, and they are redesigned before G5. Result: +0.001 to
+0.003 for every type (Chapter 7.11). The rule fired. G5 does not start on today's scenarios; the redesign direction is the
owner's choice (options in Chapter 14.8 progress note).

### D-52 Scenario redesign: competing sites (pre-registered on 2026-10-22, before any result)
Why: step 3 (D-51) showed that a pilot knowing the future gains only +0.002 over B6, because the drone (15 m/s, re-planning
every 10 s) is much faster than walking crowds. A fourth review round (reviewer's 1-D toy model) showed where room appears:
when **demand switches between sites far apart faster than the drone can fly across** (two sites 1.5 km apart, abrupt switch:
+0.077; 0.8 km: +0.031). A tight battery alone is expected to fail (one simple rule, B8, captures the hover/circle choice),
and walking crowds that drift apart are followed by a greedy pilot.

**Design (fixed now):**
- New profiles only (`sites_*`); existing profiles and global defaults unchanged; every new feature off by default, with
  old results bit-exact (tests). The owner's G5 settings (D-48) live inside the new profiles.
- Map 2 x 2 km, 20 dBm; 2-3 sites; crowds still or drifting <= 1 m/s (bursts <= 3 m/s).
- Event: at t0 in [60, 150] s a share of 50-70% of the active demand moves from site A to site B within tau seconds,
  through an `active[t, user]` mask (inactive users leave the coverage denominator and get no resources; total bandwidth fixed).
  Event types and their disaster justification: a ground tower restored at a known time (users at A leave the drone), a rescue
  operation or shelter opening at B (users arrive), survivors appearing after an aftershock or flood front.
- **Design grid:** site distance D in {1.0, 1.5, 2.0 km} x tau in {0, 60, 180 s} x {announced (countdown), unannounced},
  battery 16 Wh; the passing cells are then repeated at 12-13 Wh.
- **Baselines (the bar):** the best per cell of B6, B7, B8 (B6 targets; circle when the battery would not last) and B6fc
  (forecasting greedy using only what the agent can observe: the announced schedule, crowd velocities from the last frame).
- **Headroom test:** clairvoyant DP (energy-free first; energy-aware DP only on passing cells) minus the best baseline,
  **pass mark >= 0.02 coverage**; measured on design seeds 0-99, then **re-measured on fresh seeds** before it counts.
- **Report every cell** (a regime map by transit time / demand time scale), including cells with no room.
- **Negative control:** today's `hard` (headroom 0.002): a later AI must not beat B6 there; if it does, look for a bug.
- **Never change these scenarios after seeing AI results.** RL trains on seeds 10,000+, is chosen on val, test read once.
- Owner's questions on the announced schedule (is it a raw measurement under D-24?), "AI ties the forecaster" as an H2
  outcome, and longer recharge missions (later) stay open; the announced cells are built and measured, but the AI uses them
  only if the owner confirms.

### D-53 Outcome of D-52 phases 1-2
Phase 1: the simple battery rule B8 equals or beats circling at 12 and 13 Wh, so a battery-only redesign leaves no room for an
AI (as predicted). Phase 2: a pilot that knows the future beats the best simple pilot by +0.025 to +0.108 in 7 of 9 designs
(Chapter 7.12); the two 1.0 km designs with a gradual switch fail; 1.5 km with a 3-minute switch passes only just (+0.0201),
reported as borderline. As pre-registered, nothing counts yet: B6-forecast is added and the passing designs are re-measured on
fresh scenarios before any AI is trained on them.

### D-54 The AI may use the announced schedule
In the competing-sites scenarios an operator message can announce the event ("from t0, about m people will be taken from A
to the shelter at B over tau"). The owner decided the AI may use it: it is a message a real base station would receive, so
it is a raw measurement under D-24. For a fair contest the AI gets **the same contents** the forecasting pilot B6fc uses:
the countdown to the event (`event_countdown`) and the rest of the message (`event_announce`: where from, where to, the share
that moves and the switch duration). Training cells: `sites_d20_t0_ann`, `sites_d20_t60_ann`. Both groups are opt-in, so old
models and results are unchanged.

### D-55 G5 rules, pre-registered on 2026-10-23 before any training
- **Cells:** the two primary cells confirmed on fresh seeds (D-52 phases 3-4): sites 2.0 km apart, switch sudden (`t0`) or
  over 60 s (`t60`), announced. Owner's G5 settings (adaptive NOMA, SIC 0.05, rescue first, acceleration limit 4 m/s^2).
- **Agent:** E0's design (PPO, Dict observation with uncapped maps, crowd size, own history, CNN; fresh training scenarios
  10,000-19,999; gamma 0.95; decisions held 10 s) plus the announcement groups (D-54).
- **Round 1 (choose the steering):** per cell, `goto` vs the new `moveby` ("move this far"; 0 = stay), 2 training seeds each =
  8 runs of 150,000 decisions (the E0 budget; the sites scenarios train at about 10 decisions/s on the laptop, so 300,000 would
  not fit a Kaggle session). The better steering per cell is chosen on the 20 validation scenarios (100-119).
- **Round 2 (final):** the chosen version, 5 training seeds per cell.
- **Bar:** per scenario, the best of B6, B7, B8, B6fc (announced). If the departure-time pilot B6dep is built and tested before
  round 2 is evaluated, it joins the bar (a stronger bar can only make passing harder).
- **Pass mark (G5):** the AI's 5-seed mean beats the bar on the validation scenarios, paired, Holm-corrected over the two cells,
  in at least one cell. Also reported: the share of the clairvoyant pilot's room the AI captures, and NOMA vs OMA for the AI
  (same AI, `oma_opt`). Negative control: on a no-room cell (`sites_d10_t0`, and `hard`) the AI must not beat the bar; if it
  does, look for a bug. The test scenarios (120-139) are read once, at the end.
- **Compute:** Kaggle (owner's account, via the Kaggle command-line tool), two notebooks in parallel, one per cell.

