# Roadmap: from today to the finished project

Agreed with the owner on 2026-10-21 (D-50). It replaces the order agreed on 2026-10-19 (stages A-F, kept in the book,
Chapter 11 and journal). Each stage is short and gated, with its pass mark fixed before results are seen (as D-43), so the
project does not get stuck again. Items marked (approval) need the owner's OK.

Rules that hold for every stage:
- **The AI learns by itself** (D-24): raw measurements and the coverage score only; a privileged critic during training only
  (D-38). No hints, no menu of candidate spots, no imitation of the baselines.
- Same scenarios for every method, paired statistics with 95% CIs, at least 5 training seeds for final numbers, test seeds
  (120-139) read once, at the end. Negative results are reported.
- Major plans are reviewed by an independent agent first (D-36); the book and its PDF are updated in every pull request.
- "Simulation-based planning tool", never "digital twin".

## Where we are (2026-10-21)
- **Proven:**
  - H1: an adaptive drone beats a parked one (hard 0.741 vs 0.428).
  - H3: adaptive NOMA beats equally optimised OMA by +0.03 to +0.05 coverage for every pilot.
  - Circling (B7) serves 26% more people per battery.
- **G4 (still crowd): closed as not met.** The best AI scored 0.576 against a pass mark of 0.580. The cause is known: it flies past the best spot. The fixes are in the backlog or inside G5 (D-49).
- **Built:** the simulator, dataset, game, pilots B0-B7, the AI pipeline (PPO/SAC, privileged critic), the acceleration limit, a 14-chapter book with PDF, and 277 tests with CI.

## Stage 0: housekeeping and new defaults (about 1 day)
- Merge the open PRs.
- Step 3's oracle headroom result goes into the book.
- Switch the defaults to the owner's G5 settings (D-48): `noma_opt`, sic_eps 0.05, rescue first, acceleration limit 4 m/s^2.
- Re-run the baseline tables once under them.

## Stage 1: G5, the AI on moving crowds (H2), core, about 2 weeks
- **Where:** only the crowd types where the clairvoyant pilot (step 3) beats B6 by at least 0.02. If there are none, make the scenarios harder first.
- **Agent:**
  - start from E0;
  - add the previous-frame map (motion information, a raw measurement);
  - add "move by" steering and longer training (the fix for flying past the best spot).
- **Curriculum:** moving crowds, then altitude, then power, then a battery-aware reward.
- **Compare against:** B2, B3, B6, B7, the clairvoyant ceiling and the fraction of the oracle's lead closed.
- **Pass mark:** fixed in the G5 plan before training. Run 3 seeds to choose, 5 seeds for the final configuration. Cloud compute if the laptop is too slow (approval).

## Stage 2: disaster events (about 1 week)
- Rising flood, shelter evacuation (simple social force), aftershock adding buildings, survivors appearing or disappearing, drone failure.
- Re-run the pilots and the best agent on them.

## Stage 3: realism and safety (about 1-1.5 weeks)
- The drone does not know exactly where people are (noisy, partial maps).
- Wind, GPS error and command delay.
- **Safety layer:** geofence, battery reserve and return-home, and a fallback to B6 when the AI's choice looks worse.
- **Optional:** a real place, e.g. a Nepal flood (OpenStreetMap, WorldPop; approval for the new libraries and downloads), labelled "a scenario based on ...".
- **Needs the team:** MATLAB parity, the Al-Hourani paper, sign-off of the minimum rates.

## Stage 4: final evaluation and write-up, core (about 1.5-2 weeks)
- Regime grid (battery x mobility x power) with 5 seeds and Holm correction; the test set read once; sensitivity to the assumptions.
- **Report goals:**
  1. NOMA vs OMA.
  2. Adaptive vs fixed.
  3. Learned vs search on moving crowds, with wins and losses.
  4. The share of the best possible coverage; safety rules never broken.
- **Deliverables:** literature matrix, report (the book as its base), viva slides, demo video, a 1-2 page summary for the guide.

## Stage 5, last: a simulated drone that really flies, no hardware (about 1.5-3 weeks)
- Our pilot (unchanged) sends "go to (x, y, height)" every 10 s to a realistic simulated quadcopter (physics, autopilot, wind).
- Coverage is computed from the drone's actual simulated position. The gap to our game is measured (the "sim-to-real" gap).
- **Light option first:** a Python quadcopter simulator such as gym-pybullet-drones (approval; it may need Python 3.12).
- **Heavy option:** ArduPilot SITL over MAVLink with Mission Planner.

## Parallel tracks
- **Dashboard** (approved, being built): a Streamlit web page on the same engine with five pages: showcase, fly a disaster, compare, plan, about. Its numbers equal the experiments'.
- **Business interviews:** cost nothing.
- **Backlog:**
  - G4b still-crowd fixes;
  - measurement-based fine-tuning (fix C, the owner's call under D-24);
  - multi-UAV (stretch);
  - the spatial action head (rejected under D-24).

If the deadline is close, cut in this order: Stage 5, the real place, Stage 2. Stages 1 and 4 are the project.
