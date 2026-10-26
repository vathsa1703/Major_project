# Results: the AI under "wrong physics" (model mismatch), 2026-10-24

Pre-registration: `model_mismatch.md` (GO 2026-10-23). Nothing in it was changed after the results were seen.
Cells `mm_h8` and `mm_combo` are **exploratory** (the pre-registered grid had no room, section 2), so a pass would have needed
a new confirmation; there was none to confirm.

**Plain words.** The simple pilots plan with the textbook radio model. In these tests the real radio differs from the textbook:
signal shadowing, hidden buildings, stronger building loss. We asked whether an AI that learns from measured results alone
can beat pilots that trust the textbook. **It cannot.** In every test the AI is clearly below the best simple pilot. The one
good sign: where the textbook is wrong (`mm_h8`), plain B6 loses about 0.11, and the AI ties it (+0.004). So the AI is not
fooled by the wrong textbook, but it is still beaten by the pilot that measures (B6meas).

## Pre-registered evaluation (draw 0, val 100-119, 20 scenarios, 3 training seeds, 150,000 decisions each, Kaggle)

| Test | Bar (best of B6, B6meas, B3) | AI (3-seed mean) | AI - bar [95% CI] | Holm p | Pass | B6true (upper) | AI - B6 | NOMA - OMA (AI) |
|---|---|---|---|---|---|---|---|---|
| mm_h8 (8 hidden buildings) | 0.795 | 0.756 | -0.039 [-0.061, -0.016] | 0.0008 | no | 0.829 | +0.004 [-0.036, +0.043] | +0.111 [+0.078, +0.143] |
| mm_combo (all errors together) | 0.801 | 0.700 | -0.101 [-0.138, -0.064] | <0.0001 | no | 0.832 | -0.066 [-0.101, -0.030] | +0.078 [+0.053, +0.103] |
| mm_none (negative control: textbook is right) | 0.865 | 0.817 | -0.048 [-0.066, -0.031] | <0.0001 | no (by design) | 0.869 | -0.048 [-0.066, -0.030] | +0.076 [+0.051, +0.100] |

Pilots on draw 0 (coverage): mm_h8 B3 0.672, B6 0.752, B6meas 0.786, B6true 0.829; mm_none B3 0.800, B6 0.865,
B6meas 0.857, B6true 0.869.

Per training seed (AI - bar): mm_h8 -0.051, -0.035, -0.029; mm_combo -0.102, -0.083, -0.118; mm_none -0.038, -0.048, -0.059.
Every seed loses, so the result does not hinge on one bad run.

## Checks
- **Negative control passes as required:** with the textbook right (`mm_none`) the AI does not beat B6 (-0.048).
- **Memorisation check (draw 1, a fresh random draw of the hidden errors on the same scenarios):** mm_h8 -0.046
  [-0.063, -0.028], mm_combo -0.090 [-0.128, -0.051]. Same picture.
- **NOMA stays visible:** the same agents serve 0.08 to 0.11 more people with adaptive NOMA than with tuned OMA (all
  significant; the agents were trained with NOMA).

## Against the expectations written down first (prereg section 8)
- Expected: the AI does NOT pass. **Confirmed.**
- Expected to be informative: is the deficit smaller where the textbook is wrong? **Partly.** Relative to the bar, mm_h8
  (-0.039) is a little better than the control (-0.048), but mm_combo (-0.101) is much worse. Relative to plain B6 the AI
  goes from -0.048 (control) to +0.004 (mm_h8): the AI's relative position improves by about 0.05 when the textbook is wrong.
- Share of room captured is negative in every cell (the AI is below the bar, so it captures none of the room).

## What it means for the project
Learning from measurements is not enough to beat a pilot that **measures and searches** (B6meas) with this training budget.
The useful finding for the report: when the radio model is wrong, a cheap fix (measure a few spots, then search) recovers
most of the loss (mm_h8: B6 0.752 -> B6meas 0.786, ceiling 0.829). This is a model-based fix, not an AI result.

Reproduce: Kaggle kernels `uav-mismatch-mm-{none,h8,combo}`, then
`python mismatch_eval.py run --cell <cell> --models <folder> --out results/mismatch/ai [--draw 1]` and
`python mismatch_eval.py combine mm_h8 mm_combo mm_none --out results/mismatch/ai`.
