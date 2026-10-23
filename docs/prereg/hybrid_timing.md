# Pre-registration: the hybrid timing AI (owner decision D-56, item 3)

Written and committed BEFORE any training run. Nothing below may change after training starts; any deviation is
recorded as a dated note at the end of this file (never by editing the text above it).

## 1. What is tested, in plain words

G5 round 1 (book 8.9) showed that a full AI that chooses x and y itself loses to the best simple pilot on the
announced competing-sites cells (best 0.680 vs bar 0.756 / 0.753). The clairvoyant pilot shows that the room over the
bar is in **timing**: leaving site A for site B at the right moment before the announced move (+0.046 / +0.047 on fresh
seeds). The hybrid gives the AI only that decision.

**It is a hybrid, and every report must say so.** A search pilot (B6) decides WHERE the drone goes (x, y, altitude).
A small PPO policy decides only WHEN to leave for the announced destination.

## 2. Design (code: `uav_dataset/hybrid.py`, `hybrid_tables.py`, `hybrid_train.py`, `hybrid_eval.py`)

- **Cells:** `sites_d20_t0_ann` and `sites_d20_t60_ann` (D = 2 km, switch over tau = 0 / 60 s, announced).
- **Action** (every 10 s = B6's own decision rhythm, so 30 decisions per episode): `Discrete(2)`.
  - 0 FOLLOW: fly to B6's choice now (B6's exact rule; an agent that always follows flies exactly B6: tested).
  - 1 LEAVE: fly to the B-target.
  Both are allowed at every decision (it may return to following B6). Flight: `go_to` at B6's power (full).
  Why discrete and not a continuous "leave probability": the decision is binary; PPO's categorical head already
  explores with a probability, a continuous output would add a second, arbitrary threshold.
- **B-target:** the lattice node (B6's 14 x 14 x 5 candidates) with the best coverage for the announced post-event
  demand, built ONCE at t = 0 from the announcement and the users active at t = 0 with B6fc's own forecast
  (`B6Forecast.forecast` at t0 + tau, when every announced mover has switched). Ties: closest to site A's centre (the
  shortest flight), then B6's order. Never built from the true movers, their true positions or any future state.
- **Observation (the AI):** the G5 observation, raw only: `pos, vel, battery, time, prev, crowd_n, history,
  event_countdown, event_announce, heat_all_u, heat_rescue_u` (Dict, D-24, D-54). It never sees B6's choice, the
  B-target or any table.
- **Reward:** v1 coverage, summed over the 10 held seconds.
- **Speed (precomputed B6):** for every scenario of the training pool, B6's coverage of every lattice node at every
  decision time is computed once (`hybrid_tables.py`; equal to oracle.py's tensor rows at t = 10 k: tested). At decision
  k the pilot reads only row k (now) plus a live evaluation of the 'stay' spot, so it is exactly live B6 (tested on
  fixed seeds, every metric bit-exact). Tests also show the observation and the B-target are unchanged when every future
  position and activity flag is scrambled, and that garbage in the table's future rows does not change B6's choice.

## 3. Training (on Kaggle, CPU)

- **Pool:** FIXED scenarios 10000-10199 (200, fresh procedural seeds, disjoint from val 100-119 and test 120-139), the
  same seeds in both cells. Each episode draws a pool scenario at random.
- **Budget:** 100,000 decisions per run (= 3,333 episodes, about 17 visits per pool scenario).
- **Seeds, in two rounds:** Round A = 3 PPO training seeds (0, 1, 2) per cell, 6 runs. Round B adds seeds 3 and 4
  (same pool, same budget) ONLY IF Round A's 3-seed mean beats the bar under the pass mark of section 4 in at least one
  cell; the 5-seed result is then the one reported. If Round A does not pass, the 3-seed result is the final one.
- **PPO (SB3):** Dict CNN extractor of G5 (`rl_net.DictMapExtractor`, no privileged input), net_arch [64, 64], gamma
  0.95, ent_coef 0.01, lr 3e-4, n_envs 4, n_steps 256, batch 256, 10 epochs, GAE 0.95, clip 0.2, reward
  normalisation (VecNormalize, rewards only). All in config.yaml `hybrid:`.
- **No model selection:** the FINAL model of every run is evaluated. No validation scenario is played during training.
  Checkpoints exist only for crash recovery.

## 4. Evaluation (locally, `hybrid_eval.py`)

- **Scenarios:** val 100-119 (20 per cell). Test 120-139 is not touched.
- **Bar (D-55):** per scenario the best of B6, B7, B8, B6fc, **plus B6dep if `baselines.POLICIES` contains it when the
  evaluation runs** (decided now). Bar rows may be copied from the G5 round-1 run on the same profile and code; the
  report checks that the hybrid pilot that never leaves reproduces B6 exactly on all 20 scenarios.
- **Agent score per scenario:** the mean of the training seeds' coverage on that scenario (3-seed mean in Round A,
  5-seed mean if Round B runs).
- **Pass mark:** in at least one cell, the seed mean beats the bar: mean paired difference (agent - bar over the 20
  scenarios) > 0 AND Holm-adjusted p < 0.05 over the 2 cells (`evalstats.paired_p`, two-sided normal approximation;
  `evalstats.holm`).
- **Also reported (not part of the pass mark):** each seed's mean; agent - bar and agent - B6 with 95% CI; the share of
  the clairvoyant room captured = (agent - bar) / (dp - bar) with the clairvoyant dp replayed on the same 20 val
  scenarios; NOMA vs OMA (the same agents with access `oma_opt`, B6 tables computed under `oma_opt`); when the agent
  leaves (first LEAVE decision, share of LEAVE); a hindsight diagnostic = the best fixed departure per scenario
  (follow B6 until d, then leave; not flyable, it uses the outcome).
- Whatever the outcome, it is reported, including a loss.

## 5. Pilot used to fix the settings (training-pool seeds only)

Departure sweep on pool seeds 10000-10016 (17 scenarios per cell, both cells; no val or test scenario was played):
the hybrid pilot follows B6 until decision d and then leaves, for every d = 0..29 and 'never' (= B6), replayed
through env.step. Per scenario: B6, the best d with hindsight (ceiling of the two actions with one departure), and
the departure that a discounted agent would pick (first decision where leaving now beats every later departure, with
discount gamma).

| cell | B6 | best d (hindsight) | gamma 0.95 | gamma 0.99 | gamma 1 | best single d for all |
|---|---|---|---|---|---|---|
| sites_d20_t0_ann | 0.702 | 0.772 | 0.771 | 0.772 | 0.772 | 0.758 (d = 4) |
| sites_d20_t60_ann | 0.715 | 0.760 | 0.757 | 0.760 | 0.760 | 0.750 (d = 6) |

Reading: (1) there is room for the timing decision: perfect timing adds +0.070 / +0.045 over B6 on these pool scenarios
(on val the bar is B6 + 0.045 / + 0.032, G5 round 1), so the t60 cell is tight; (2) the discount 0.95 asked for in the
design costs only 0.001 / 0.003 against undiscounted timing, so gamma stays 0.95; (3) the best departure moves with
t0 (decision 0-7 for t0 = 60-136 s), so a single fixed time loses 0.014 / 0.010 to per-scenario timing: the agent must
read the countdown.

## 6. Dated notes

- 2026-10-23 (before any training run): the owner asked for results sooner. The plan above was set accordingly before
  this file was first committed: Round A = 3 seeds per cell at 100k decisions (instead of 5 seeds at 150k), a pool of
  200 instead of 300 scenarios, verdict on the 3-seed mean with the same pass mark, 2 more seeds only if Round A beats
  the bar (then the 5-seed result is reported). Training runs on Kaggle, one kernel per cell (tables of the pool built
  in 4 processes, then 3 runs in parallel).
- 2026-10-24 (after Round A): Round A did not meet the pass mark in either cell (results:
  `uav_dataset/results/hybrid/summary.md`), so by section 3 Round B (seeds 3, 4) is not run and the 3-seed result is
  final. Deviations from the text above: none. B6dep was not in `baselines.POLICIES` at evaluation time, so the bar is
  B6, B7, B8, B6fc; their val rows were copied from G5 round 1 (`results/g5/r1_*/episodes.csv`), and the hybrid pilot
  that never leaves reproduced the copied B6 rows exactly on all 40 scenarios.
