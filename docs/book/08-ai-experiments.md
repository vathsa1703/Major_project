# Chapter 8. AI experiments

This chapter records every training run, what it showed and why. It supersedes the earlier summary in `docs/rl_g4.md`.

## 8.1 The task and the bar (Gate G4)
**Task.** Profile `rl_static`: a 2 x 2 km map, 20 dBm, 3-8 collapsed buildings, a crowd that stands still, 16 Wh. The AI only
controls the drone's position (altitude 150 m, full power): curriculum step 1, the "hello world" of the project.
**Gate G4:** the AI must beat random **and** match or beat B2 (not significantly worse in the paired comparison).

| Level (validation seeds 100-119) | coverage_full |
|---|---|
| Random | 0.413-0.430 (depends on the random controls used) |
| B0, parked in the middle | 0.441 |
| **B2, k-means (the gate)** | **0.610** |
| B3, grid search | 0.659 |
| Ceiling: best single spot, reached instantly | 0.686 |

**Rules** (D-24, D-26): the AI gets raw measurements and the coverage score only; training on seeds 0-99; models compared on
validation seeds 100-119; test seeds 120-139 untouched. Five planned experiments, then stop; one extra approved (D-27).

## 8.2 All runs

| Run | Controls | Decides every | Network | Observation | Noise | Training | val8 during training | val20 | vs B2 (paired) |
|---|---|---|---|---|---|---|---|---|---|
| `static_xy_v1_s0` | velocity | 1 s | MLP | all | 1.0 -> 0.93 | 300k steps | (training coverage 0.40 -> 0.49) | 0.394 | below random |
| `A_full` | velocity | 1 s | MLP | all | 0.37 | 1M steps | 0.431 0.468 0.414 0.474 0.481 0.420 0.426 0.453 0.427 0.408 | - | - |
| `goto_v1` | waypoint | 1 s | MLP | all | 0.37 | 500k steps | 0.447 0.454 0.444 0.472 0.465 | - | - |
| `goto_hold10` | waypoint | 10 s | MLP | all | 0.37 -> 0.32 | 60k decisions | 0.477 0.486 0.481 | 0.525 | -0.085 * |
| E2 `e2_mlp_lean` | waypoint | 10 s | MLP | position + maps | 0.37 -> 0.33 | 60k | 0.481 0.466 0.492 | 0.543 | -0.067 * |
| **E3 `e3_cnn_full`** | waypoint | 10 s | **CNN** | all | 0.37 -> 0.32 | 60k | 0.496 0.502 0.516 | **0.549** | -0.061 * |
| E3b `e3b_cnn_lean` | waypoint | 10 s | CNN | position + maps | 0.37 -> 0.34 | 60k | 0.467 0.477 0.464 | 0.528 | -0.082 * |
| E4 `e4_cnn_grid20` | waypoint | 10 s | CNN | all, 20 x 20 maps | 0.37 -> ~0.32 | 60k | 0.487 0.520 0.509 | 0.545 | -0.065 * |
| **E5a `e5a_cnn_150k`** | waypoint | 10 s | CNN | all | 0.37 -> 0.25 | 150k | 0.496 0.502 0.516 0.512 0.532 0.514 0.516 | **0.555** | **-0.055 *** |
| E6 `e6_cnn_anneal` | waypoint | 10 s | CNN | all | **0.37 -> 0.05 (annealed)** | 60k | 0.488 0.497 0.475 | 0.509 | -0.102 * |
| E6b `e6b_mlp_anneal` | waypoint | 10 s | MLP | all | **0.37 -> 0.05 (annealed)** | 60k | 0.476 0.498 0.490 | 0.536 | -0.074 * |

`*` = significant (the 95% CI of the paired difference excludes 0). Every run is one training seed; differences of about 0.02
between runs are within noise. `A_full` was a rerun after a session restart killed the first attempt at about 487k steps; it
reproduced the first scores exactly (0.431, 0.468), which confirms that training is deterministic by seed.

## 8.3 What each step taught us
1. **Velocity controls: the drone finds the crowd and drifts away.** The first run scored below random. The picture
   [2_still_crowd_AI_vs_pilots.png](figures/2_still_crowd_AI_vs_pilots.png) (seed 105) shows the PPO drone reaching 0.8 coverage at
   about 30 s, like B3, then flying on and off the map edge (0.2). Hovering needs exactly zero velocity, and nothing rewards it.
   Training for 1M steps did not help (plateau 0.41-0.48).
2. **Waypoint controls stop the drift, but deciding every second makes it circle**
   ([4_goto_checkpoint.png](figures/4_goto_checkpoint.png)): coverage swings between 0.5 and 0.75.
3. **Deciding every 10 s stops the circling and learns about three times faster** ([5_goto_hold10.png](figures/5_goto_hold10.png)).
   First run that clearly beats random (+0.095, significant). Still below B2 (-0.085, significant).
4. **Experiment 1 (diagnosis):** the trained AI picks almost the same target from its very first decision and never changes it;
   it only passes through the good area on the way. Its target is 109 m, 348 m and 546 m from the best spot on seeds 110, 100 and
   105. Changing only its own velocity input moves the target 103 m; previous scores 89 m; the maps 266-445 m. It reads the maps
   but aims imprecisely, and is somewhat sensitive to inputs that should not matter for a still crowd.
5. **Experiments 2-4:** dropping inputs, a CNN, and a finer map all land within 0.03 of each other (0.528-0.549 on val20).
   **The brain and the inputs are not the bottleneck.**
6. **Experiment 5a:** 2.5 times more training creeps up slowly (peak 0.532 on val8).
7. **The exploration noise is the likely bottleneck.** In every run the noise ended at 0.32-0.34 (about +-330 m on a 2 km map),
   wider than a crowd (50-200 m). The score of each tried spot is dominated by that random wobble, so the AI cannot refine its aim.
   Experiment 6 shrank the noise from 0.37 to 0.05 over training (D-27). **It did not help** (val20 0.509 with the CNN, 0.536
   with the MLP), so the noise was not the main bottleneck either. My diagnosis was wrong, and this is recorded as such.
8. **Best result: E5a, the CNN trained longest: 0.555 on val20, still significantly below B2 (-0.055).** Every variant lands
   between 0.51 and 0.56: network, inputs, map resolution, training length and exploration schedule each change the score by
   at most a few hundredths. The AI learns to head roughly for the crowd but does not aim precisely enough to match a pilot that
   evaluates candidate spots directly.

## 8.4 Status and what happens next
Gate G4 is **half met** (beats random, not B2). **The agreed stopping rule has been reached** (D-26): all five experiments
and the extra noise experiment are done, and the best AI (0.555) is still significantly below B2 (0.610). Per the rule we stop
tuning and report this result. The owner decides whether to relax G4 and move on to moving crowds, where one-step search
pilots are always a step late and an AI that anticipates has a real chance. Other learners (SAC, a network with memory) remain
options that give no hints.

## 8.5 Validation table: `goto_hold10`

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

## 8.6 Validation table: E3 `e3_cnn_full` (best so far)

Split: val (20 scenarios, seeds 100-119). Profile: rl_static. Controls: None. Area 2000 m, 20 dBm, battery 16 Wh.

Scenarios per policy: 20. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B2 | 0.610 +/- 0.068 | 0.610 +/- 0.068 | 100% | 4484.4 +/- 1128.2 | 0.526 +/- 0.086 | 0.529 +/- 0.043 |
| B3 | 0.659 +/- 0.069 | 0.659 +/- 0.069 | 100% | 4576.6 +/- 1156.6 | 0.542 +/- 0.102 | 0.557 +/- 0.043 |
| PPO | 0.549 +/- 0.094 | 0.549 +/- 0.094 | 100% | 3991.7 +/- 1220.6 | 0.658 +/- 0.111 | 0.507 +/- 0.079 |
| Random | 0.430 +/- 0.093 | 0.430 +/- 0.093 | 100% | 3241.9 +/- 978.9 | 0.872 +/- 0.060 | 0.477 +/- 0.099 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B2 | B3 | PPO | Random |
|---|---|---|---|---|
| B2 | - | -0.049* | +0.061* | +0.180* |
| B3 | +0.049* | - | +0.110* | +0.229* |
| PPO | -0.061* | -0.110* | - | +0.119* |
| Random | -0.180* | -0.229* | -0.119* | - |

Mean coverage_full by mobility model (scenario counts: static 20):

| mobility | B2 | B3 | PPO | Random |
|---|---|---|---|---|
| static | 0.610 | 0.659 | 0.549 | 0.430 |
