# Gate G4 attempts: PPO on a still crowd

**Task.** Profile `rl_static`: 2 x 2 km, 20 dBm, 3-8 obstacles, the crowd stands still, 16 Wh battery. The agent only controls
position (altitude fixed at 150 m, full power). It trains on seeds 0-99, is checked on 8 validation scenarios during training
(seeds 100-107) and scored on all 20 validation scenarios (seeds 100-119) at the end. Test seeds (120-139) are untouched.
**G4 = beat random AND match or beat B2.**

## What was tried

| Run | Controls | Decides every | Steps | Validation score during training (8 scenarios) | Verdict |
|---|---|---|---|---|---|
| `static_xy_v1_s0` | velocity (`xy`) | 1 s | 300k | final 20-scenario score 0.394 | below random (0.413) |
| `A_full` (reward scaling, noise 0.37) | velocity | 1 s | 1M | 0.43, 0.47, 0.41, 0.47, 0.48, 0.42, 0.43, 0.45, 0.43, 0.41 | plateau, no better than parking |
| `goto_v1` | waypoint (`goto`) | 1 s | 500k | 0.447, 0.454, 0.444, 0.472, 0.465 | plateau at 0.46 |
| `goto_hold10` | waypoint | **10 s** | 60k decisions | 0.477, 0.486, 0.481 | **0.525 on 20 scenarios** |

Findings, in the order they were learned:
1. **Velocity controls fail by drifting.** The drone found the crowd (0.8 coverage at 30 s, like B3) and then kept flying off the map.
   Hovering needs the agent to output exactly zero velocity, and nothing rewards that.
2. **Waypoint controls ("fly to this spot") stop the drift** but the drone circled the crowd, deciding anew every second.
3. **Holding each decision for 10 s** (the rhythm the baselines use) removed the circling, and learned in about a third of the
   time. A game is now 30 decisions instead of 300.
4. **Result of the best run (`goto_hold10`, 20 validation scenarios):** PPO 0.525 vs Random 0.430 (paired +0.095, significant)
   vs B2 0.610 (paired -0.085, significant) vs B3 0.659 (paired -0.134, significant).
   **G4 is half met: it beats random, it does not match B2.**
5. **What is still wrong:** on scenario 105 the drone reaches the best spot at about 30 s (0.80, same as B3), then leaves it
   and settles at a worse one (0.5). It knows roughly where the crowd is but does not stay at the best point.

## Ideas not tried yet
- **Discrete grid actions:** pick one of the 100 map cells as the waypoint. Choosing the densest cell becomes a classification
  problem, which a small network learns much better than outputting coordinates. This is also how B3 works.
- A convolutional network or an explicit "offset to the densest cell" feature in the observation.
- More steps and several training seeds (the plan wants at least 5 seeds per configuration for the final numbers).

## Full validation table of the best run

Split: val (20 scenarios, seeds 100-119). Profile: rl_static. Controls: goto. Area 2000 m, 20 dBm, battery 16 Wh.

Scenarios per policy: 20. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B0 | 0.441 +/- 0.101 | 0.441 +/- 0.101 | 100% | 2717.5 +/- 881.6 | 0.865 +/- 0.071 | 0.489 +/- 0.100 |
| B1 | 0.600 +/- 0.076 | 0.600 +/- 0.076 | 100% | 4190.8 +/- 1121.8 | 0.584 +/- 0.093 | 0.494 +/- 0.058 |
| B2 | 0.610 +/- 0.068 | 0.610 +/- 0.068 | 100% | 4484.4 +/- 1128.2 | 0.526 +/- 0.086 | 0.529 +/- 0.043 |
| B3 | 0.659 +/- 0.069 | 0.659 +/- 0.069 | 100% | 4576.6 +/- 1156.6 | 0.542 +/- 0.102 | 0.557 +/- 0.043 |
| B5 | 0.659 +/- 0.069 | 0.659 +/- 0.069 | 100% | 4576.6 +/- 1156.6 | 0.542 +/- 0.102 | 0.557 +/- 0.043 |
| PPO | 0.525 +/- 0.084 | 0.525 +/- 0.084 | 100% | 3972.2 +/- 1099.8 | 0.701 +/- 0.112 | 0.512 +/- 0.076 |
| Random | 0.430 +/- 0.093 | 0.430 +/- 0.093 | 100% | 3241.9 +/- 978.9 | 0.872 +/- 0.060 | 0.477 +/- 0.099 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B0 | B1 | B2 | B3 | B5 | PPO | Random |
|---|---|---|---|---|---|---|---|
| B0 | - | -0.158* | -0.169* | -0.218* | -0.218* | -0.084* | +0.011 |
| B1 | +0.158* | - | -0.011 | -0.060* | -0.060* | +0.075* | +0.170* |
| B2 | +0.169* | +0.011 | - | -0.049* | -0.049* | +0.085* | +0.180* |
| B3 | +0.218* | +0.060* | +0.049* | - | +0.000 | +0.134* | +0.229* |
| B5 | +0.218* | +0.060* | +0.049* | +0.000 | - | +0.134* | +0.229* |
| PPO | +0.084* | -0.075* | -0.085* | -0.134* | -0.134* | - | +0.095* |
| Random | -0.011 | -0.170* | -0.180* | -0.229* | -0.229* | -0.095* | - |

Mean coverage_full by mobility model (scenario counts: static 20):

| mobility | B0 | B1 | B2 | B3 | B5 | PPO | Random |
|---|---|---|---|---|---|---|---|
| static | 0.441 | 0.600 | 0.610 | 0.659 | 0.659 | 0.525 | 0.430 |
