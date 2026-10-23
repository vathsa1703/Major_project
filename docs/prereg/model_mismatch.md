# Pre-registration: can an AI beat model-based pilots when the true channel differs from the textbook model?

Status: **FINAL, committed 2026-10-23 before any AI training** (lead's GO of 2026-10-23, with conditions). Reviewer
amendments of 2026-10-23 are included. Any later change is recorded as a dated amendment at the end, never by editing
the text above it.

> **READ FIRST: the pre-registered 9-cell mismatch grid was NULL.** No cell of the pre-registered room-test grid
> (shadowing sigma {4, 8} x correlation {25, 50, 150} m, building loss 25 dB, hidden buildings {2, 4}) reached the room
> criterion (largest +0.017). `mm_h8` and `mm_combo` are **EXPLORATORY cells added AFTER seeing that null**; their room
> was confirmed on fresh seeds 1000-1019 before any training. **Any verdict on them is EXPLORATORY, not a
> pre-registered pass.** Expected outcome, written down before training: the AI most likely FAILS (room 0.026-0.036 is
> smaller than the known learning gap of about 0.08, section 8).

## 1. Question and hypothesis

The search pilots (B3, B6) choose where to fly by scoring candidate spots with the SAME radio model the game uses. In
this experiment the game's TRUE world (env.step: who is really served) differs from the planners' NOMINAL textbook model
(Al-Hourani mean path loss + 15 dB on the known buildings). An AI trained in the true world learns from MEASURED coverage
and might beat model-based pilots. Hypothesis H-MM: in at least one mismatch cell with measurable room, a trained agent's
3-seed mean coverage beats the level-1 bar (below), paired over the validation scenarios, Holm-corrected over cells.

## 2. Scenarios and cells

- Base: profile family `mm_*` = `rl_static` (2 km map, 20 dBm, 3-8 known buildings, still crowds, 16 Wh) with the
  owner's G5 settings (noma_opt, sic_eps 0.05, rescue_first, a_max 4 m/s^2). `hard` (moving crowds) only as a
  robustness check of the passing cells, never for the pass mark.
- Perturbations (config `mismatch:`, each with its own rng stream (seed, stream, draw); all ENGINEERING ASSUMPTIONS, no
  primary source verified; to read: 3GPP TR 36.777 Annex B, TR 38.901 shadow fading, Al-Hourani et al. Globecom 2014):
  user-side correlated shadowing (sigma {4, 8} dB at grazing, std falling linearly to 0 overhead; correlation length
  {25, 50, 150} m), true building loss 25 dB (planner 15), hidden buildings {2, 4} (absent from the planner's map).
- Room test result (`uav_dataset/results/mismatch/room.md`, val 100-119): **no cell of the pre-registered grid passes**
  (largest: 4 hidden buildings +0.017 [+0.009, +0.026]; shadowing 8 dB / 150 m +0.016 [+0.010, +0.023]). After that
  null, two LARGER-DOSE cells were added (exploratory, labelled so everywhere): `mm_h8` (8 hidden buildings) and
  `mm_combo` (shadowing 8 dB / 150 m + true building loss 25 dB + 4 hidden buildings). Both pass on val (+0.036, +0.035)
  and again on FRESH seeds 1000-1019 (mm_h8 +0.026 [+0.012, +0.041]; mm_combo +0.033 [+0.020, +0.046]).
- **Training cells: `mm_combo` and `mm_h8` (EXPLORATORY), plus the negative control `mm_none`** (no mismatch).
  These cells were chosen after the pre-registered grid gave a null; their room was confirmed on fresh seeds before any
  training. The rules below are fixed now, but a "pass" in these cells is an exploratory finding that needs a new
  pre-registered confirmation before it can be called a result.

## 3. Room criterion (already measured, before training)

Room = B6true - per-scenario best of (B6, B6meas), paired over val seeds 100-119. A cell has room if the mean is
>= 0.02 AND the 95% CI lower bound is > 0. Cells without room are not trained (a null is reported as a null).

## 4. Pilots (frozen before training)

- B6 (nominal grid x altitude search every 10 s), B3 (nominal grid, fixed 150 m), B6r (B6 + off-grid pattern search
  100 -> 50 -> 25 m; resolution control), B6true (B6r on the TRUE channel; upper bound, not a competitor).
- B6meas (level-1 information parity with the AI: nominal model + the aggregate coverage it measures each second where it
  flies; same flight cost): nominal top-k spots >= 300 m apart, visited in the shortest tour with a dwell, commit to the
  best measured, then a measured pattern search (compass probes, optional altitude probes; keep only improving moves),
  re-check every 30 s. k / dwell / probe steps / altitude probes tuned on design seeds 10000-10009 only and frozen in
  config `b6meas:` (tuning table in room.md).
- B6cal (per-user gain reports) is NOT built: the AI gets no per-user reports, so it is not the AI's information level.

## 5. Agent

- E0's design: PPO, Dict observation `pos, vel, battery, time, prev, crowd_n, history, heat_all_u, heat_rescue_u`
  (raw measurements only, D-24: maps of where people are, crowd size, own position/velocity/battery, the measured
  coverage last second and in the own history; NO shadowing map, no true building loss, no hidden buildings), CNN
  extractor, decisions held 10 s, gamma 0.95, reward v1 (coverage), 150,000 decisions (the E0 budget), fresh training
  scenarios 10000-19999 (never val or test seeds; the shadowing map, hidden buildings are re-drawn per scenario seed).
- Steering: **`gotoz`** (where + altitude), accepted by the lead before training (section 9, question 1). E0 used
  `goto`.
- 3 training seeds (0, 1, 2) per cell. Kaggle, one notebook per cell (3 notebooks: mm_combo, mm_h8, mm_none), 3 seeds in
  parallel; kernels `srivathsajr/uav-mismatch-mm-<cell>`; code = commit 4075bcd of `origin/final/integrate` + the
  changed files embedded in run.py (sha256 checked on Kaggle and recorded in run_info.json).

## 6. Bar and pass mark

- Level-1 bar = per scenario, the best of B6, B6meas and B3 (all at most level-1 information).
- **AI pass (per cell; EXPLORATORY in these cells):** the agent's 3-seed mean (averaged per scenario) beats the bar on val 100-119: paired mean
  difference > 0 with the two-sided paired p-value (normal approximation, `evalstats.paired_p`) Holm-corrected over the
  training cells (`mm_combo`, `mm_h8`; the negative control is not in the family) below 0.05, in at least one cell.
- **Negative control:** on `mm_none` the AI must NOT beat B6; if it does, look for a bug before reading any other cell.
- Also reported (no pass/fail): share of room captured = (AI - bar) / (B6true - bar); per-seed results; the
  **re-drawn perturbation check** (val 100-119 with `mismatch.draw = 1`: same crowds and known buildings, new shadowing
  map / hidden buildings; a memorising agent would drop); **NOMA vs OMA** for the agent (same agent with `oma_opt`,
  identical perturbation draw); `hard` robustness for passing cells.
- The test scenarios (120-139) are read ONCE, after everything above is fixed.

## 7. Analysis code (frozen)

`uav_dataset/mismatch_eval.py run` (per cell, draw 0 and draw 1; at most 2 local processes) and `combine` (Holm over
cells, summary table). Statistics: `evalstats.paired_diff` (normal 95% CI), `paired_p`, `holm`.

## 8. Expectations written down first (so a null is read as a null)

- User-side shadowing is expected to give ~0 room: it averages over many users per spot.
- (Measured, not expected: user-side shadowing gave a small but nonzero room, +0.008 to +0.016, all below the 0.02 mark.)
- Even where room exists, the AI starts from a known gap: on `rl_static`, E0 reached 0.576 vs B3 0.659 (book 8.8), a
  learning gap of about 0.08 with the model known. The room in the training cells is 0.026-0.036, smaller than that gap,
  so the expected outcome is that the AI does NOT pass; the informative numbers are the share of room captured and
  whether the AI's deficit to the bar is smaller in `mm_combo` / `mm_h8` than in `mm_none`.

## 9. Questions settled before the GO

1. Steering: E0 used `goto` (fixed 150 m altitude). In `mm_*` B6 picks the 300 m ceiling in 20/20 val scenarios (both
   `mm_none` and `mm_combo`; B6true in 15/20 on `mm_combo`), and a fixed 150 m pilot (B3) is 0.06 below B6, so `goto`
   would cap the agent below the bar by construction. Proposal: `gotoz` (where + altitude), same budget (150,000
   decisions; the laptop smoke run trained at 23 decisions/s, about 1.8 h per run). **Decided: `gotoz` (lead,
   2026-10-23, before training).**
2. Optional hybrid (D-56 style): B6meas decides, the AI learns only a correction; disclosed as a hybrid. Not part of
   this pre-registration.

## Amendments

(none yet)
