# Roadmap: from today to the finished project

Agreed with the owner on 2026-10-19. The order is chosen so that each stage builds on the one before and the riskiest unknowns
are tested first. The **no-hardware flying simulation is the last stage** by the owner's decision. Items marked (approval) need
the owner's OK before a new library or a change of rules.

Rules that hold for every stage:
- **The AI learns by itself.** It gets raw measurements (what a drone could measure) and the coverage score. No hints, no menu of
  candidate spots, no imitation of the baselines, no privileged information (true positions, cluster ids).
  Allowed: network design, training length, hyperparameters, seeds, the curriculum order.
- Same scenarios for every method, paired statistics, at least 5 training seeds for final numbers, test seeds (120-139) read once.
- Failures are reported (plan risk register). Never claim "digital twin"; the tool is a "simulation-based planning tool".
- Every parameter has a value, unit, source or "engineering assumption" and a sensitivity range (`docs/assumptions.md`).

## Where we are
Simulator, 154 tests, CI, six baselines plus B6, harder scenario profiles, an RL pipeline (PPO), comparison pictures and a
play-any-scenario viewer are built. Gate G4 (still crowd) is half met: PPO beats random (0.549 vs 0.430) but not B2 (0.610).
Last two runs (finer map, longer training) were still training when this was written. Open: exploration-noise fix (approval),
Al-Hourani paper, MATLAB parity, per-class minimum-rate sign-off, battery size decision.

## Stage A: close the still-crowd gate (G4), then stop
- Finish experiments 4 and 5 (`docs/rl_g4.md`), decide on the exploration-noise annealing run (approval).
- If PPO is still below B2, stop tuning, write it up, and the owner decides whether to relax G4 and move on.

## Stage B: NOMA becomes a decision (H3)
- A switch in the game to run the same scenario with OMA instead of NOMA (clean H3 experiment with confidence intervals).
- The agent also chooses the NOMA power split and the pairing method (the plan's curriculum step 6). Baselines get a classical
  version (optimised power split per pair; k-means and need-based pairing). Imperfect SIC and bit-error rate as ablations.
- Result: "joint placement, height, power and NOMA sharing", the most relevant research problem in this project.

## Stage C: dynamic scenarios and events (G5, hypothesis H2, experiment E9)
- Curriculum steps 2 to 5: moving crowds, then altitude, then power, then a battery-aware reward.
- New events: rising flood that pushes people to higher ground, shelter evacuation (social-force-lite), aftershock that adds
  collapsed buildings mid-scenario, survivors appearing or disappearing, drone failure.
- This is where a pilot that only looks at the present is always one step late, so an AI that anticipates has a chance to win.

## Stage D: realism upgrades (what the simulator does not yet model)
| Upgrade | What changes | Needs |
|---|---|---|
| **The drone does not know where people are** | The agent sees only what a network can measure (signal reports from some phones, a few known positions), not exact crowd maps | code only |
| **A real place** (for example a Nepal flood) | Real buildings and shelters (OpenStreetMap), population density (WorldPop-style), flood extent from satellite maps, elevation, which towers are down. Crowd is RECONSTRUCTED and labelled "a scenario based on ..." | new map libraries, downloads (approval) |
| **Wind, GPS error, delays, real battery behaviour** | Noise and delays, then retrain and test under them | code only |
| **The drone's own link to the network (backhaul)** | A simple model of the tether or radio link | code only |
| **Safety layer** | Geofence and an override that can take control from the AI | code only |
| **Check against reality** | One real measurement (cheap drone or mast and a phone or radio at several heights) compared with our altitude curve; MATLAB parity; read the Al-Hourani paper | the owner's help |

## Stage E: evaluation and write-up
- Experiments E1 to E14 with 5 seeds each, generalisation to unseen scenarios, sensitivity to the assumptions (ranges in `docs/assumptions.md`).
- Literature matrix (15 to 25 papers, every citation checked by a person), report, demo, viva slides, 30-second pitch.
- Possible extras if time allows: several drones, a dashboard and API ("planning tool").

## Stage F (last): a simulated drone that actually flies, no hardware
- Connect the trained controller to a simulated quadcopter with a real autopilot model, using the same "fly to this spot"
  commands a real autopilot takes (MAVLink). The simulator shows it flying in 3D with wind and stabilisation. Lightweight option
  first: a Python physics simulator that installs with pip and runs on Windows (approval for the new library); heavier option:
  ArduPilot or PX4 software-in-the-loop with Gazebo.
- Demo for the guide: the controller flying the simulated drone over a scenario, with coverage shown live.
- The step after that is real hardware, outside this project: NOMA on the bench with software-defined radios, signal measurements
  on a mast, hover tests, closed loop with a safety pilot, then a pilot with a partner. Needs a mentor, aviation and radio permission.

## Business track (in parallel, costs nothing)
Talk to 5 to 10 people who do this work (emergency teams, telecom emergency groups, drone service companies) and ask what they do
today and what it costs. Novelty is not the test for a business; a paying customer with a painful problem is. A software-only
planning and rehearsal tool avoids the hardware, flying and regulation problems, but whether anyone would pay for it is unknown.
