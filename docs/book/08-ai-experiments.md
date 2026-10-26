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

**Update 2026-10-21:** step 1 of the agreed plan (Chapter 14.6) asked *why* the AI stalls. Answer in 8.7: about half of its gap
to B3 is information it does not have, the other half is the AI not using what it does have.

## 8.7 Why the AI stalls: the information ladder and the train/validation check (plan step 1)
**The question.** The search pilots score spots with the true positions of every person, the buildings and each person's
needs. The AI sees only two coarse 10 x 10 maps (everyone, rescue users), and those maps are **capped**: a cell holding more
than 10% of the crowd simply reads "full". Is the AI stuck because it lacks information, or because it learns badly?

**The method: an information ladder.** Three new pilots run *exactly* B3's search (same candidate spots, altitude, power,
rhythm, tie-break) but score the spots with less information. Each rung adds one piece:

| Pilot | What it knows |
|---|---|
| `B3obs` | only the AI's own two capped maps; it rebuilds a stand-in crowd of 500 people at the cell centres (crowd size = engineering assumption, D-37), no buildings, needs from the population mix |
| `B3obsU` | the same maps **without the cap** (true share of people per cell) |
| `B3obsUO` | plus the true **buildings** |
| `B3` | plus exact positions inside each 200 m cell, the true crowd size and every person's needs |

**Results, validation (20 scenarios, seeds 100-119, profile `rl_static`), paired with the AI E5a:**

| Pilot | Coverage | vs the AI (paired) |
|---|---|---|
| B3 (everything) | 0.659 | +0.104* |
| B3obsUO (maps uncapped + buildings) | 0.629 | +0.074* |
| B3obsU (maps uncapped) | 0.613 | +0.059* |
| **B3obs (exactly what the AI sees)** | **0.605** | **+0.050*** |
| B2 (k-means, true positions) | 0.610 | +0.055* |
| AI E5a | 0.555 | |
| Random | 0.430 | -0.125* |

On 20 *training* scenarios (seeds 0-19, which are harder for every pilot): B3 0.603, B3obsU 0.586, B3obsUO 0.581, B3obs 0.561,
B2 0.568, AI 0.538 (AI vs B3obs -0.023*). Steps along the ladder that are significant: cap removal +0.025* (train only), last
rung (exact positions, crowd size, needs) +0.030* val and +0.022* train; the buildings step is not significant on either split.

| Gap AI to B3 | caused by missing information (B3obs to B3) | caused by the AI not using what it sees (AI to B3obs) |
|---|---|---|
| validation 0.104 | 0.054 | 0.050 |
| training 0.065 | 0.042 | 0.023 |

**Train vs validation (is it memorising?).** The same models on 20 training scenarios and the 20 validation scenarios, as
a share of B3's score: goto_hold10 0.78 / 0.80, e3 CNN 0.88 / 0.83, e5a CNN 0.89 / 0.84, e4 CNN 20 x 20 0.89 / 0.83. The AI is
clearly behind B3 **even on scenarios it trained on** (e5a -0.065*), so the main problem is **underfitting** (it has not
learned the task well), not memorising. The CNNs lose a little more on new scenarios (about 0.04 in the gap to B3); whether
that difference is significant was not tested.

**What the capped map hides.** On the 10 x 10 map, 3.4 cells per scenario read "full" on average and they hold 59% of all
people; the densest cell holds 25% on average (up to 54%). Parking over the best "full" cell gives 0.616 coverage, over the
worst 0.435, and the AI cannot tell them apart. But the 20 x 20 map mostly removes the saturation (22% of people in full
cells) and the AI scored the same (0.545), so the cap is not the main limit.

**The key insight.** B3 often parks **between** crowds, sometimes over an almost empty cell (its own cell is "full" in only
17 of 40 scenarios, but a neighbouring cell is in 35 of 40), so one footprint reaches several crowds. Flying to the truly
densest cell gives only 0.565, which is where every AI version stalls (0.53-0.56). **The AI has learned "go to the crowd",
not "find the spot that reaches several crowds".**

**What it means.**
1. The plateau is **half information, half learning.** A one-step search with only the AI's maps reaches 0.605, level with B2.
   So better learning with the *current* inputs could plausibly reach about 0.60, i.e. match B2 and pass G4; matching B3 needs
   more information (finer positions and the crowd size matter most; buildings least).
2. G4 as defined (match B2) is therefore **not impossible by design**: an information-matched search already matches B2.
3. For step 4 of the plan: an uncapped map is cheap and correct to add; an obstacle map is the least promising extra input; a
   finer map or a count of people (which a base station knows from connected users) are more promising.

**Sensitivity check (mine, after the agents' runs):** B3obs with an assumed crowd of 200 / 500 / 1,000 people scores
0.588 / 0.605 / 0.606 on validation, always above the AI's 0.555, so the conclusion does not depend on that assumption.

**Who did what.** Two agents worked in parallel (owner's request): one built the three pilots, their tests and the ladder
runs; the other ran the train/validation check and measured the map cap. I reviewed the code (the pilots read only what
their rung allows), re-ran the 500-person result (identical), ran the sensitivity check and wrote this section.

Reproduce: `python rl_eval.py --policies Random,B0,B2,B3,B3obs,B3obsU,B3obsUO --split val --model results/rl/e5a_cnn_150k/model.zip`
(and `--split train --seeds 20`). Tests: 19 new in `test_baselines.py` (the pilots ignore everything outside their rung).

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

## 8.8 Track 2: a better learner, and the G4 verdict (2026-10-21)
**What changed for the AI (D-40), all raw measurements a real drone has:**
- an **uncapped** crowd map (square root of the share of people per cell, so no cell ever reads "full"), and the same for the
  rescue map;
- the **number of connected users** (log scale);
- its **own history**: where it was at its last 4 decisions and how many people it served there;
- **fresh training scenarios** (seeds 10,000-19,999, never validation or test) instead of the same 100 maps;
- a planning horizon (gamma) of 0.95, matched to 30 decisions per game.
Three learners: **E0** PPO with these inputs; **E2** SAC (a learner that scores actions directly); **E3** SAC with a
**training-only privileged critic** (owner's decision D-38): during training, the part that judges moves saw the true 20 x 20
crowd density, rescue users, buildings, people's needs and crowd size; the flying part never did. Three tests guard this: the
actor's network has no input for that data, its output is bit-identical when only the privileged data changes (before and after
training), and when flying the AI never asks the game for it.

**The pass mark (D-43, set by the owner before E3's result): G4 passes if the 3-run average on the 20 validation scenarios is
at least B2 - 0.03 = 0.580, and the AI clearly beats random.** A version earns 2 extra runs only if its first run reaches 0.570.

**Results on the 20 validation scenarios** (bars: B2 0.610, B3obs 0.605, B3 0.659, Random 0.430):

| Version | Run 1 | Run 2 | Run 3 | **3-run average** | vs pass mark 0.580 |
|---|---|---|---|---|---|
| E0 PPO, new inputs | 0.573 | 0.574 | 0.581 | **0.576 +/- 0.011** | short by 0.004 |
| E2 SAC | 0.567 | (no extra runs: below 0.570) | | | |
| E3 SAC, privileged critic | 0.571 | 0.572 | 0.551 | **0.565 +/- 0.029** | short by 0.015 |
| old best E5a (8.3) | 0.555 | | | | |

E0 (all 3 runs averaged per scenario) vs B2 -0.034 +/- 0.038, vs B3obs -0.029*, vs B3 -0.083*, vs Random +0.146*.

**A second set of scenarios the AI never saw** (seeds 0-19; bars: B2 0.568, B3obs 0.561, B3 0.603, Random 0.320): E0 0.524 /
0.515 / 0.517 (average 0.519, vs B2 -0.050*), E2 0.534 (vs B2 -0.034, not significant), E3 0.502 / 0.521 / 0.478 (average
0.501, vs B2 -0.068*). Here the AI is clearly behind B2, so the gap is real and not an artefact of the 20 validation scenarios.

**Verdict: Gate G4 is NOT met** under the owner's rule. The best version (E0) is 0.004 short on validation and about 0.05 behind
B2 on the second set. By the pre-agreed stopping rule we stop tuning for the still crowd.

**What we learned.**
1. **Better inputs and fresh scenarios helped, steadily:** 0.555 to 0.576, with very little spread between runs (0.573-0.581).
2. **The privileged critic did not help** (E3 0.565, more spread, worst on the second set), although in theory it is the
   version where a privileged critic should matter most. SAC was not better than PPO and costs 3-4 times more computer time.
3. **The AI still does not stay at the best spot.** On seed 105 it reaches B3's spot at about 30 s (0.80 coverage), then flies
   on to the upper crowd behind a building and settles at 0.66, while B3 and B3obs stay and score 0.78
   ([10_e0_vs_b3_seed105.png](figures/10_e0_vs_b3_seed105.png)). Over the 20 validation scenarios its final position is 264-291 m
   from B3's. It no longer simply heads for the densest cell (it ends there in 0-10% of games, B3 in 30%), but it does not find
   the spot between crowds either.
4. **The gap is learning, not information:** a plain search with exactly the same inputs (B3obsUN, uncapped maps plus the true
   crowd size) scores 0.606; with or without the crowd size or the cap, the search barely changes (0.605-0.613). The AI has the
   information; it does not turn it into the best position.

**What comes next (owner's decision 4, D-38):** move to moving crowds (G5), where a pilot that only reacts to the present is
always a step late. Step 3's clairvoyant pilot measures first how much there is to win there. E0 is the starting agent.

**Technical notes.** PPO: 150k decisions per run, 41-79 min. SAC: 100k decisions, 80-111 min, replay buffer 50k (RAM
limited), one gradient step per 4 decisions. CIs over scenarios use z = 1.96 (a t value would widen them by about 7%; no
verdict changes). Reproduce: `python rl_train.py --algo PPO --obs_mode dict --gamma 0.95 --train_seeds 10000-19999 ...` (the
exact settings are saved in each model's `config.json`); `python rl_eval.py --model <zip> --policies Random,B2,B3,B3obs,B3obsUN
--split val`.

## 8.9 G5 round 1: the AI on competing sites (2026-10-23)
**Setup, fixed beforehand (D-55).** The two 2 km designs (sudden switch; over 1 minute), announced; the owner's G5 settings.
The AI is E0's design plus the announcement as inputs (D-54: when, from where, to where, how many). Two steering versions:
`goto` ("fly to this spot") and the new **`moveby`** ("move this far"; 0 = stay; the target is fixed at the decision, built to
stop the "flies past the spot" fault). 2 training seeds each, 150,000 decisions per run (about 3.5 h), trained on **Kaggle**
(two notebooks in parallel, the owner's account, the key file placed by the owner). Bar: per scenario the best of B6, B7, B8
and the forecasting pilot.

**Results (20 validation scenarios):**

| Design | Bar (B6 / forecaster) | goto s0 | goto s1 | moveby s0 | moveby s1 | best AI vs bar |
|---|---|---|---|---|---|---|
| 2 km, sudden | 0.756 (0.711 / 0.748) | 0.673 | 0.680 | 0.671 | 0.669 | **-0.076 ± 0.015*** |
| 2 km, over 1 min | 0.753 (0.721 / 0.748) | 0.673 | 0.680 | 0.616 | 0.629 | **-0.073 ± 0.012*** |

**Every AI is clearly below the bar and also below plain B6** (by 0.03 to 0.10). The `moveby` steering did not help here
(equal on the sudden design, worse on the 1-minute design). **NOMA vs OMA for the AI:** the same agents serve 0.08 to 0.13
more people with adaptive NOMA than with tuned OMA (all significant; the agents were trained with NOMA, so their OMA runs are
outside what they learned).

**What it means.** The room exists (the future-knowing pilot gains up to +0.09 there), but an AI that has to learn *everything*
(where to fly as well as when) from rough maps does not reach it with this budget: it does not even react as well as the
search pilot. The room is mostly about **one decision: when to leave for the other site** (7.13). Round 2 of the full AI (5
more seeds) was dropped as uninformative; the owner approved a **hybrid timing AI** instead (D-56: the search pilot chooses
where; the AI chooses only when to leave), plus the "anticipation rule" and "value of location information" studies.
Reproduce: Kaggle kernels `uav-g5-round1-t0/t60`, then `python g5_eval.py --profile sites_d20_t0_ann --models <folder> --out <dir>`.

## 8.10 The hybrid timing AI: the search pilot chooses where, the AI only when to leave (2026-10-24)
**Plain words.** 8.9 showed the full AI cannot learn *everything* at once, and 7.13 showed the room is mostly in one decision:
**when to leave site A for site B**. So we gave the AI only that decision. It is like a co-driver who never touches the
wheel and only says "leave now" or "not yet"; the search pilot B6 does all the steering (where, at what height). **It is a
hybrid, and every report must say so.**

**Scientific statement.** Every 10 s (B6's own rhythm, 30 decisions per episode) a PPO policy picks Discrete(2): FOLLOW (fly
to B6's choice now) or LEAVE (fly to the B-target, the lattice node with the best forecast coverage for the announced
post-event demand, fixed at t = 0 from the announcement). Observation = the raw G5 inputs (maps, crowd size, own state,
history, the announcement); it never sees B6's choice or the B-target. Reward = coverage. An agent that always follows flies
exactly B6 (tested). Training: fixed pool of 200 fresh scenarios (10000-10199), 100,000 decisions per run, 3 training seeds per
cell, Kaggle; the FINAL model is evaluated (no model selection). 2 cells: `sites_d20_t0_ann`, `sites_d20_t60_ann`.

**Pre-registered rule** (`docs/prereg/hybrid_timing.md`, before any training): in at least one cell the 3-seed mean beats the
bar (per scenario the best of B6, B7, B8, B6fc) on val 100-119: mean paired difference > 0 AND Holm-adjusted p < 0.05 over the
2 cells. Seeds 3 and 4 only if Round A passes.

**Result: NOT MET** (`uav_dataset/results/hybrid/summary.md`):

| Cell | Bar | Hybrid (3-seed mean) | Hybrid - bar | p (Holm) | Hybrid - B6 | Clairvoyant room over the bar | Hindsight best single departure - bar |
|---|---|---|---|---|---|---|---|
| 2 km, sudden (`t0`) | 0.756 | **0.752** | -0.004 ± 0.013 (a tie) | 0.573 (0.573) | **+0.041 ± 0.013*** | +0.048 ± 0.010* | +0.013 ± 0.010* |
| 2 km, over 1 min (`t60`) | 0.753 | **0.734** | -0.019 ± 0.011* (a loss) | 0.0007 (0.0014) | **+0.014 ± 0.007*** | +0.044 ± 0.009* | +0.008 ± 0.007* |

Per training seed: t0 0.753 / 0.753 / 0.752; t60 0.738 / 0.726 / 0.739 (every seed below the bar in t60). The AI learned to
leave (leave share 0.71-0.77 in t0; first leave around decision 7) and clearly beats plain B6 in both cells, but it captures
none of the room over the bar (share captured -8% in t0, -44% in t60). Round B (2 more seeds) was not run, as pre-registered.

**Why so little can be won here.** The hindsight diagnostic (the best fixed departure per scenario, chosen with the
outcome; not flyable) is only +0.013 / +0.008 above the bar: with these two actions, even *perfect* timing barely beats the
forecasting pilot. The rest of the clairvoyant room (+0.048 / +0.044) needs more than a leave-time choice. Note also that the
bar here did not include B6dep (it was not yet in the pilot list at evaluation time, as the pre-registration allowed); on the
same 20 val scenarios B6dep scores 0.780 / 0.774 (7.15), so against today's best simple pilot the hybrid is further behind
(difference of means, not a paired test).

**NOMA vs OMA (same agents, `oma_opt`):** t0 0.752 vs 0.620, **NOMA - OMA +0.132 ± 0.034***; t60 0.734 vs 0.606,
**+0.128 ± 0.031***.

**Not verified.** 3 training seeds only (Round B not triggered); one training budget; the B-target is one fixed spot per
episode; the hindsight ceiling is a diagnostic, not a pilot. The agents were trained with NOMA, so their OMA runs are outside
what they learned.

**Reproduce:** `python hybrid_tables.py build` / `bundle` (B6 tables of the training pool), `python hybrid_train.py --profile
<cell> --bundle <file>` (Kaggle, one kernel per cell), `python hybrid_eval.py --profile <cell> --models <folder> --out
<dir> [--bar_from <G5 round-1 episodes.csv>]`, then `--report` (OMA tables are built per scenario and cached; per-episode
rows in `uav_dataset/results/hybrid/t0|t60/episodes.csv`).

## 8.11 The AI under "wrong physics" (model mismatch, 2026-10-24)
**Plain words.** The search pilots plan with the textbook radio model. If the real radio differs (hidden collapsed buildings,
signal shadowing, thicker walls), they plan with a wrong map, like a taxi driver using last year's street map. An AI that
learns only from what it measures might not be fooled. We asked: when the textbook is wrong, can the AI beat the pilots that
trust it?

**Scientific statement.** A new `mismatch:` config section makes the TRUE world (what `env.step` serves) differ from the
NOMINAL model the pilots plan with: (a) user-side correlated log-normal shadowing (sigma 4 or 8 dB at grazing angles,
correlation 25 / 50 / 150 m), (b) a true building loss of 25 dB (planner 15 dB), (d) hidden buildings that are not on the
planner's map. All off by default (old results bit-exact; tests). New pilots: **B6r** (B6 + off-grid pattern search, to
separate "finer placement" from "knowing the channel"), **B6true** (B6r on the TRUE channel: an upper bound, not a
competitor), **B6meas** (learning-free, the AI's information level: the nominal model plus the coverage it *measures* each
second where it flies; surveys the top 3 nominal spots, then a measured pattern search; tuned on design seeds 10000-10009
only). Room = B6true minus the best of B6 and B6meas; a cell has room if >= 0.02 with the CI above 0. Scenarios: still crowds
on a 2 km map with the G5 settings (`mm_*` profiles). AI: E0's design with `gotoz` steering (where + altitude), 150,000
decisions, 3 training seeds per cell, Kaggle.

**Pre-registered rule** (`docs/prereg/model_mismatch.md`, final 2026-10-23 before any training): the AI's 3-seed mean beats
the level-1 bar (per scenario the best of B6, B6meas, B3) on val 100-119, paired, Holm over the training cells, in at least
one cell. Negative control `mm_none` (textbook right): the AI must NOT beat B6.

**Room test (no AI), the pre-registered grid: NULL** (`uav_dataset/results/mismatch/room.md`). None of the 9 pre-registered
cells reached 0.02: largest 4 hidden buildings +0.017 [+0.009, +0.026] and shadowing 8 dB / 150 m +0.016 [+0.010, +0.023].
Two **larger-dose cells were added afterwards and are EXPLORATORY**: `mm_h8` (8 hidden buildings) +0.036 [+0.023, +0.050]
and `mm_combo` (shadowing 8 dB / 150 m + loss 25 dB + 4 hidden) +0.035 [+0.020, +0.050] on val, confirmed on fresh seeds
1000-1019 (+0.026 [+0.012, +0.041]; +0.033 [+0.020, +0.046]) before any training.

**AI result: NOT MET in any cell** (`docs/prereg/model_mismatch_results.md`; draw 0, val 100-119, 20 scenarios):

| Cell | Bar (best of B6, B6meas, B3) | AI (3-seed mean) | AI - bar [95% CI] | Holm p | AI - B6 | B6true (upper bound) | NOMA - OMA (AI) |
|---|---|---|---|---|---|---|---|
| `mm_h8` (exploratory) | 0.795 | 0.756 | **-0.039** [-0.061, -0.016] | 0.0008 | **+0.004** [-0.036, +0.043] | 0.829 | +0.111 [+0.078, +0.143] |
| `mm_combo` (exploratory) | 0.801 | 0.700 | **-0.101** [-0.138, -0.064] | <0.0001 | -0.066 [-0.101, -0.030] | 0.832 | +0.078 [+0.053, +0.103] |
| `mm_none` (negative control) | 0.865 | 0.817 | -0.048 [-0.066, -0.031] | <0.0001 | -0.048 [-0.066, -0.030] | 0.869 | +0.076 [+0.051, +0.100] |

Pilots on draw 0: `mm_h8` B3 0.672, B6 0.752, B6meas 0.786, B6true 0.829; `mm_none` B3 0.800, B6 0.865, B6meas 0.857,
B6true 0.869. Every training seed loses to the bar (`mm_h8` -0.051 / -0.035 / -0.029; `mm_combo` -0.102 / -0.083 / -0.118).

**Checks.** The negative control behaves as required (the AI does not beat B6 when the textbook is right: -0.048). The
memorisation check (draw 1: a fresh draw of the hidden errors on the same scenarios) gives the same picture (`mm_h8` -0.046
[-0.063, -0.028]; `mm_combo` -0.090 [-0.128, -0.051]).

**What it means.** The AI is not fooled by the wrong textbook (with 8 hidden buildings plain B6 drops from 0.865 to 0.752,
and the AI ties it, +0.004), but it is still beaten by a pilot that **measures and searches**. The useful finding is a model-based fix,
not an AI result: measuring a few spots and then searching recovers most of the loss (`mm_h8`: B6 0.752 -> B6meas 0.786,
ceiling 0.829). It matches the expectation written down before training (the room, 0.026-0.036, is smaller than the known
learning gap of about 0.08).

**Not verified.** Every mismatch parameter is an engineering assumption (no primary source read; 3GPP TR 36.777 Annex B,
TR 38.901 and Al-Hourani Globecom 2014 are listed to read); the elevation-dependent shadowing std is a linear assumption;
"another environment class of Al-Hourani" was not built because no second parameter row is verified; `hard` robustness was
not run (no cell passed); the mismatch is not defined for real-place scenarios (the code refuses the combination).

**Reproduce:** `python mismatch_exp.py room`, `tune`, `confirm`, `report` (room test, B6meas tuning, fresh-seed
confirmation); Kaggle kernels
`uav-mismatch-mm-{none,h8,combo}`; `python mismatch_eval.py run --cell <cell> --models <folder> --out results/mismatch/ai
[--draw 1]`, then `python mismatch_eval.py combine mm_h8 mm_combo mm_none --out results/mismatch/ai`.
