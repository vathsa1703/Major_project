# Kathmandu (Bagmati) case study: results

A scenario based on the September 2024 Kathmandu (Bagmati river) floods. The crowd is RECONSTRUCTED from the map with engineering assumptions (not real data). Map data © OpenStreetMap contributors (ODbL).

Seeds 0-19 (crowd draws); episodes per (profile, access, pilot): 20-20. Values: mean +/- 95% CI over scenarios; paired differences per scenario; * = the CI excludes 0. Coverage = mean share of the active users served over the 300 s horizon (dead drone = 0). Rescue served = the same for the rescue class. Total speed = mean sum rate. G5 settings in both profiles (noma_opt vs oma_opt, SIC residual 0.05, rescue first, a_max 4 m/s^2, 20 dBm, 16 Wh).

## Kathmandu place profile (place_kathmandu_bagmati)

| pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | rescue served NOMA | rescue served OMA | total speed NOMA (Mbit/s) | total speed OMA | battery left NOMA (Wh) | flown NOMA (m) |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 0.674 +/- 0.032 | 0.479 +/- 0.033 | +0.195 +/- 0.012* | 0.761 +/- 0.040 | 0.761 +/- 0.040 | 33.0 | 25.0 | 1.52 | 0 |
| B2 | 0.713 +/- 0.033 | 0.521 +/- 0.035 | +0.191 +/- 0.009* | 0.801 +/- 0.030 | 0.801 +/- 0.030 | 38.3 | 27.2 | 3.12 | 2596 |
| B3 | 0.741 +/- 0.032 | 0.577 +/- 0.035 | +0.164 +/- 0.010* | 0.823 +/- 0.029 | 0.816 +/- 0.030 | 39.4 | 29.7 | 2.21 | 1097 |
| B6 | 0.781 +/- 0.025 | 0.654 +/- 0.030 | +0.127 +/- 0.008* | 0.892 +/- 0.024 | 0.888 +/- 0.026 | 41.1 | 32.6 | 1.41 | 1294 |
| B7 | 0.774 +/- 0.025 | 0.626 +/- 0.029 | +0.148 +/- 0.007* | 0.890 +/- 0.024 | 0.889 +/- 0.026 | 40.3 | 31.7 | 3.64 | 3176 |
| B8 | 0.781 +/- 0.025 | 0.654 +/- 0.030 | +0.127 +/- 0.008* | 0.892 +/- 0.024 | 0.888 +/- 0.026 | 41.1 | 32.6 | 1.41 | 1294 |
| B6fc | 0.781 +/- 0.025 | 0.654 +/- 0.030 | +0.127 +/- 0.008* | 0.892 +/- 0.024 | 0.888 +/- 0.026 | 41.1 | 32.6 | 1.41 | 1294 |

Paired difference to B6:

| pilot | access | minus B6 (paired, 95% CI) |
|---|---|---|
| B0 | noma_opt | -0.107 +/- 0.025* |
| B2 | noma_opt | -0.069 +/- 0.012* |
| B3 | noma_opt | -0.041 +/- 0.008* |
| B7 | noma_opt | -0.008 +/- 0.002* |
| B8 | noma_opt | +0.000 +/- 0.000 |
| B6fc | noma_opt | +0.000 +/- 0.000 |
| B0 | oma_opt | -0.175 +/- 0.027* |
| B2 | oma_opt | -0.133 +/- 0.014* |
| B3 | oma_opt | -0.077 +/- 0.010* |
| B7 | oma_opt | -0.028 +/- 0.004* |
| B8 | oma_opt | +0.000 +/- 0.000 |
| B6fc | oma_opt | +0.000 +/- 0.000 |

Ranking (noma_opt): B8 0.781 > B6fc 0.781 > B6 0.781 > B7 0.774 > B3 0.741 > B2 0.713 > B0 0.674

Ranking (oma_opt): B8 0.654 > B6fc 0.654 > B6 0.654 > B7 0.626 > B3 0.577 > B2 0.521 > B0 0.479

## Synthetic `hard` with the same G5 settings

| pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | rescue served NOMA | rescue served OMA | total speed NOMA (Mbit/s) | total speed OMA | battery left NOMA (Wh) | flown NOMA (m) |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 0.560 +/- 0.093 | 0.369 +/- 0.117 | +0.191 +/- 0.057* | 0.595 +/- 0.130 | 0.595 +/- 0.130 | 23.9 | 14.7 | 1.52 | 0 |
| B2 | 0.726 +/- 0.054 | 0.568 +/- 0.079 | +0.159 +/- 0.037* | 0.781 +/- 0.061 | 0.781 +/- 0.061 | 49.7 | 30.1 | 2.95 | 2259 |
| B3 | 0.769 +/- 0.054 | 0.633 +/- 0.081 | +0.135 +/- 0.038* | 0.852 +/- 0.060 | 0.817 +/- 0.062 | 48.4 | 34.8 | 2.49 | 1548 |
| B6 | 0.837 +/- 0.044 | 0.773 +/- 0.063 | +0.064 +/- 0.021* | 0.938 +/- 0.037 | 0.923 +/- 0.053 | 53.4 | 44.6 | 1.52 | 1333 |
| B7 | 0.833 +/- 0.045 | 0.761 +/- 0.064 | +0.072 +/- 0.021* | 0.936 +/- 0.038 | 0.921 +/- 0.053 | 52.4 | 43.1 | 3.73 | 3162 |
| B8 | 0.837 +/- 0.044 | 0.773 +/- 0.063 | +0.064 +/- 0.021* | 0.938 +/- 0.037 | 0.923 +/- 0.053 | 53.4 | 44.6 | 1.52 | 1333 |
| B6fc | 0.836 +/- 0.047 | 0.777 +/- 0.063 | +0.059 +/- 0.018* | 0.935 +/- 0.042 | 0.925 +/- 0.052 | 53.4 | 44.8 | 1.32 | 1089 |

Paired difference to B6:

| pilot | access | minus B6 (paired, 95% CI) |
|---|---|---|
| B0 | noma_opt | -0.278 +/- 0.067* |
| B2 | noma_opt | -0.111 +/- 0.023* |
| B3 | noma_opt | -0.069 +/- 0.014* |
| B7 | noma_opt | -0.005 +/- 0.002* |
| B8 | noma_opt | +0.000 +/- 0.000 |
| B6fc | noma_opt | -0.001 +/- 0.005 |
| B0 | oma_opt | -0.404 +/- 0.078* |
| B2 | oma_opt | -0.206 +/- 0.051* |
| B3 | oma_opt | -0.140 +/- 0.047* |
| B7 | oma_opt | -0.012 +/- 0.007* |
| B8 | oma_opt | +0.000 +/- 0.000 |
| B6fc | oma_opt | +0.004 +/- 0.004* |

Ranking (noma_opt): B6 0.837 > B8 0.837 > B6fc 0.836 > B7 0.833 > B3 0.769 > B2 0.726 > B0 0.560

Ranking (oma_opt): B6fc 0.777 > B6 0.773 > B8 0.773 > B7 0.761 > B3 0.633 > B2 0.568 > B0 0.369

## NOMA gain: real geometry vs synthetic

| pilot | NOMA - OMA, place | NOMA - OMA, hard_g5 | difference of the gains (Welch-style CI) |
|---|---|---|---|
| B0 | +0.195 +/- 0.012* | +0.191 +/- 0.057* | +0.003 +/- 0.058 |
| B2 | +0.191 +/- 0.009* | +0.159 +/- 0.037* | +0.032 +/- 0.038 |
| B3 | +0.164 +/- 0.010* | +0.135 +/- 0.038* | +0.029 +/- 0.039 |
| B6 | +0.127 +/- 0.008* | +0.064 +/- 0.021* | +0.063 +/- 0.022* |
| B7 | +0.148 +/- 0.007* | +0.072 +/- 0.021* | +0.076 +/- 0.022* |
| B8 | +0.127 +/- 0.008* | +0.064 +/- 0.021* | +0.063 +/- 0.022* |
| B6fc | +0.127 +/- 0.008* | +0.059 +/- 0.018* | +0.068 +/- 0.019* |

## Who is served (place profile, mean share of each group's active users served)

| pilot | access | stranded (roofs, flood band) | at shelters | dry ground | scattered | evacuees (at shelters after rescue) |
|---|---|---|---|---|---|---|
| B0 | noma_opt | 0.806 | 0.593 | 0.634 | 0.603 | 0.645 |
| B2 | noma_opt | 0.781 | 0.718 | 0.599 | 0.594 | 0.820 |
| B3 | noma_opt | 0.802 | 0.736 | 0.657 | 0.635 | 0.836 |
| B6 | noma_opt | 0.834 | 0.771 | 0.720 | 0.683 | 0.856 |
| B7 | noma_opt | 0.829 | 0.765 | 0.708 | 0.672 | 0.851 |
| B8 | noma_opt | 0.834 | 0.771 | 0.720 | 0.683 | 0.856 |
| B6fc | noma_opt | 0.834 | 0.771 | 0.720 | 0.683 | 0.856 |
| B0 | oma_opt | 0.738 | 0.311 | 0.375 | 0.359 | 0.438 |
| B2 | oma_opt | 0.685 | 0.463 | 0.354 | 0.333 | 0.669 |
| B3 | oma_opt | 0.714 | 0.539 | 0.425 | 0.396 | 0.729 |
| B6 | oma_opt | 0.777 | 0.601 | 0.545 | 0.517 | 0.762 |
| B7 | oma_opt | 0.764 | 0.565 | 0.506 | 0.479 | 0.742 |
| B8 | oma_opt | 0.777 | 0.601 | 0.545 | 0.517 | 0.762 |
| B6fc | oma_opt | 0.777 | 0.601 | 0.545 | 0.517 | 0.762 |

Run time per episode (s, mean): place B6 20, place B6fc 64, hard_g5 B6 31, hard_g5 B6fc 144

place: B6fc equals B6 (to 1e-12) in 40 of 40 episodes (the evacuation is unannounced and people stand still, so B6fc's forecast is the present).

hard_g5: B6fc equals B6 (to 1e-12) in 0 of 40 episodes.

## Sensitivity (place profile)

| variant | pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | base coverage NOMA |
|---|---|---|---|---|---|
| los_statistical | B0 | 0.375 +/- 0.036 | 0.246 +/- 0.032 | +0.129 +/- 0.012* | 0.674 +/- 0.032 |
| los_statistical | B2 | 0.459 +/- 0.039 | 0.330 +/- 0.043 | +0.129 +/- 0.012* | 0.713 +/- 0.033 |
| los_statistical | B6 | 0.636 +/- 0.030 | 0.495 +/- 0.040 | +0.141 +/- 0.017* | 0.781 +/- 0.025 |
| band150 | B0 | 0.668 +/- 0.035 | 0.469 +/- 0.036 | +0.199 +/- 0.014* | 0.674 +/- 0.032 |
| band150 | B6 | 0.779 +/- 0.031 | 0.641 +/- 0.037 | +0.138 +/- 0.011* | 0.781 +/- 0.025 |
| band300 | B0 | 0.645 +/- 0.039 | 0.444 +/- 0.030 | +0.201 +/- 0.017* | 0.674 +/- 0.032 |
| band300 | B6 | 0.763 +/- 0.034 | 0.636 +/- 0.037 | +0.127 +/- 0.006* | 0.781 +/- 0.025 |
