## Hybrid timing AI: G5 evaluation (pre-registered, docs/prereg/hybrid_timing.md)

HYBRID: B6 chooses WHERE, the PPO timing policy chooses only WHEN to leave for the announced destination.
All numbers: mean coverage over 300 s, replayed through env.step. Paired differences with 95% CI (* = CI excludes 0).

### sites_d20_t0_ann (val, 20 scenarios)

Bar = per-scenario best of B6, B7, B8, B6fc: mean 0.756 (B6 0.711, B7 0.705, B8 0.711, B6fc 0.748).
Clairvoyant dp (replayed): 0.805; room over the bar +0.048 +/- 0.010*.
Check: hybrid pilot that never leaves == B6 on every scenario: True.
Diagnostic (hindsight, not flyable): best fixed departure per scenario 0.769; vs bar +0.013 +/- 0.010*; vs B6 +0.058 +/- 0.017*.

| agent | coverage (NOMA) | agent - bar (95% CI) | agent - B6 | leave share | first leave (decision) | coverage with OMA | NOMA - OMA |
|---|---|---|---|---|---|---|---|
| hyb_t0_s0 | 0.753 | -0.004 +/- 0.018 | +0.041 +/- 0.014* | 0.71 | 6.7 (never on 0) | 0.615 | +0.137 +/- 0.037* |
| hyb_t0_s1 | 0.753 | -0.003 +/- 0.013 | +0.042 +/- 0.012* | 0.77 | 6.5 (never on 0) | 0.614 | +0.139 +/- 0.038* |
| hyb_t0_s2 | 0.752 | -0.005 +/- 0.012 | +0.041 +/- 0.015* | 0.73 | 7.7 (never on 0) | 0.631 | +0.121 +/- 0.032* |

**3-seed mean** (per scenario, mean over the agents): 0.752; vs bar -0.004 +/- 0.013 (p = 0.573); vs B6 +0.041 +/- 0.013*.
Share of the clairvoyant room captured: (agent - bar) / (dp - bar) = -0.004 / +0.048 = -8%.
NOMA vs OMA (same agents, access oma_opt): 0.752 vs 0.620, NOMA - OMA +0.132 +/- 0.034*.

Per training seed (NOMA): hyb_t0_s0 0.753, hyb_t0_s1 0.753, hyb_t0_s2 0.752; over training seeds 0.752 +/- 0.001 (mean +/- 95% CI).

### sites_d20_t60_ann (val, 20 scenarios)

Bar = per-scenario best of B6, B7, B8, B6fc: mean 0.753 (B6 0.721, B7 0.717, B8 0.721, B6fc 0.748).
Clairvoyant dp (replayed): 0.798; room over the bar +0.044 +/- 0.009*.
Check: hybrid pilot that never leaves == B6 on every scenario: True.
Diagnostic (hindsight, not flyable): best fixed departure per scenario 0.761; vs bar +0.008 +/- 0.007*; vs B6 +0.041 +/- 0.013*.

| agent | coverage (NOMA) | agent - bar (95% CI) | agent - B6 | leave share | first leave (decision) | coverage with OMA | NOMA - OMA |
|---|---|---|---|---|---|---|---|
| hyb_t60_s0 | 0.738 | -0.016 +/- 0.015* | +0.017 +/- 0.012* | 0.56 | 10.8 (never on 0) | 0.608 | +0.130 +/- 0.037* |
| hyb_t60_s1 | 0.726 | -0.028 +/- 0.016* | +0.005 +/- 0.009 | 0.20 | 15.5 (never on 4) | 0.595 | +0.130 +/- 0.033* |
| hyb_t60_s2 | 0.739 | -0.015 +/- 0.008* | +0.018 +/- 0.011* | 0.14 | 10.5 (never on 8) | 0.616 | +0.123 +/- 0.029* |

**3-seed mean** (per scenario, mean over the agents): 0.734; vs bar -0.019 +/- 0.011 (p = 0.000694); vs B6 +0.014 +/- 0.007*.
Share of the clairvoyant room captured: (agent - bar) / (dp - bar) = -0.019 / +0.044 = -44%.
NOMA vs OMA (same agents, access oma_opt): 0.734 vs 0.606, NOMA - OMA +0.128 +/- 0.031*.

Per training seed (NOMA): hyb_t60_s0 0.738, hyb_t60_s1 0.726, hyb_t60_s2 0.739; over training seeds 0.734 +/- 0.008 (mean +/- 95% CI).

### Pre-registered pass mark

Pass = in at least one cell the seed mean (Round A: 3 seeds) beats the bar: mean paired difference > 0 and Holm-adjusted p < 0.05 over the 2 cells.

| cell | agent - bar | p | Holm p | passes |
|---|---|---|---|---|
| sites_d20_t0_ann | -0.004 +/- 0.013 | 0.573 | 0.573 | False |
| sites_d20_t60_ann | -0.019 +/- 0.011 | 0.000694 | 0.00139 | False |

**Verdict: NOT MET** (0 of 2 cells pass; 2 cells evaluated).
