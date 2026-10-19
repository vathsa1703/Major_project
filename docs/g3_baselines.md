# Gate G3: baseline comparison

Six baselines run through the same `UAVEnv.step()` on the same 100 seeded scenarios (seeds 0-99), 300 s horizon.
Reproduce: `cd uav_dataset && python run_baselines.py` and `python run_baselines.py --battery_wh 16 --tag _16wh`
(about 4 minutes each; every episode is deterministic and tested). Outputs go to `uav_dataset/results/` (not committed).

| ID | Strategy |
|---|---|
| B0 | Fixed at the map centre, 150 m, full power |
| B1 | Fly toward the centre of the biggest true cluster, every step |
| B2 | Weighted k-means (k = 3, rescue users x3), go to the heaviest cluster centre, every 10 steps |
| B3 | Grid search over 10 x 10 positions (plus the current one), every 10 steps |
| B4 | Particle swarm over x, y, altitude and power, every 10 steps (12 particles, 10 iterations) |
| B5 | Like B3, but stays put unless the coverage gain pays for the extra energy |

**Metric.** `coverage_full` = mean coverage over the full 300 s horizon, counting a dead drone as 0 coverage.
`coverage_alive` = mean coverage over the steps the drone was flying. Values are mean +/- 95% CI over 100 scenarios.
In the paired table, `*` means the CI of the per-scenario difference excludes 0 (it can be tiny: +0.000* is not a real gap).

## What the numbers say (read with the caveats below)
1. **The battery decides the 10 Wh ranking.** Hovering needs 14.7 Wh for 300 s, and even the cheapest cruise (about 10 m/s)
   needs about 11 Wh, so with 10 Wh **no policy survives the horizon** (0% in every row). Ranking by `coverage_full` then mostly
   measures how long each policy stays alive: B4 has the best `coverage_alive` (0.913) but ties B0 on `coverage_full`
   (0.601 vs 0.602) because it dies first.
2. **Moving is cheaper than hovering in this energy model.** At 10 m/s the drone uses about 134 J/s against 176 J/s hovering
   (Zeng's power curve, see `docs/assumptions.md`). So policies that move last longer, and the premise of B5
   ("hover unless the gain pays for the move") does not hold here: its extra cost is clamped at 0, so B5 behaves like B3.
3. **With a battery that lasts (16 Wh, everyone survives):** B4 0.914, B3 0.909, B5 0.908, B2 0.887, B1 0.884, B0 0.882.
   The search baselines (B3, B4, B5) beat the fixed drone by about 3 points. B1 and B2 do **not** beat B0 significantly.
4. **There is little headroom.** A fixed drone already covers 88% of users, and the best baseline reaches 91%. Any RL agent
   can gain at most a few points over the strong baselines in these scenarios. That is the main risk for H2.

## Caveats
- B1 uses the true cluster ids and B2-B5 use the true user positions (privileged information). RL will only see heatmaps.
- B3, B4, B5 evaluate candidates with the average channel (no fading) for the current user positions.
- B4's objective is the one-step reward, so it can choose a short life (high power) over a long one.
- Settings (K = 10, grid, swarm size, margin, rescue weight, 150 m altitude) are engineering choices in `config.yaml`
  and were not tuned. Different choices may change the ranking of B1 and B2.
- The 16 Wh run is a sensitivity check. The battery size in `config.yaml` is still 10 Wh.
- Per-class minimum rates are unsigned assumptions, so absolute coverage numbers carry that uncertainty.

## Results: battery 10 Wh (config default)

Battery: 10 Wh, horizon 300 s.

Scenarios per policy: 100. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B0 | 0.602 +/- 0.006 | 0.880 +/- 0.009 | 0% | 10052.6 +/- 1208.2 | 0.073 +/- 0.024 | 0.729 +/- 0.008 |
| B1 | 0.619 +/- 0.005 | 0.882 +/- 0.007 | 0% | 10362.0 +/- 1249.4 | 0.101 +/- 0.025 | 0.689 +/- 0.006 |
| B2 | 0.650 +/- 0.006 | 0.886 +/- 0.006 | 0% | 10860.6 +/- 1310.1 | 0.089 +/- 0.021 | 0.694 +/- 0.005 |
| B3 | 0.651 +/- 0.004 | 0.908 +/- 0.005 | 0% | 10880.0 +/- 1302.9 | 0.040 +/- 0.013 | 0.726 +/- 0.005 |
| B4 | 0.601 +/- 0.004 | 0.913 +/- 0.004 | 0% | 10092.4 +/- 1213.9 | 0.021 +/- 0.005 | 0.778 +/- 0.005 |
| B5 | 0.653 +/- 0.005 | 0.907 +/- 0.005 | 0% | 10901.3 +/- 1302.3 | 0.039 +/- 0.013 | 0.727 +/- 0.005 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B0 | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| B0 | - | -0.017* | -0.048* | -0.049* | +0.000 | -0.052* |
| B1 | +0.017* | - | -0.031* | -0.032* | +0.017* | -0.035* |
| B2 | +0.048* | +0.031* | - | -0.001 | +0.049* | -0.003 |
| B3 | +0.049* | +0.032* | +0.001 | - | +0.050* | -0.002* |
| B4 | -0.000 | -0.017* | -0.049* | -0.050* | - | -0.052* |
| B5 | +0.052* | +0.035* | +0.003 | +0.002* | +0.052* | - |

Mean coverage_full by mobility model (scenario counts: group_drift 23, surge 22, hotspot_jump 21, random_waypoint 17, attraction 17):

| mobility        |    B0 |    B1 |    B2 |    B3 |    B4 |    B5 |
|:----------------|------:|------:|------:|------:|------:|------:|
| attraction      | 0.605 | 0.623 | 0.656 | 0.656 | 0.609 | 0.664 |
| group_drift     | 0.589 | 0.604 | 0.639 | 0.647 | 0.601 | 0.647 |
| hotspot_jump    | 0.608 | 0.62  | 0.645 | 0.648 | 0.597 | 0.649 |
| random_waypoint | 0.606 | 0.616 | 0.657 | 0.657 | 0.598 | 0.658 |
| surge           | 0.603 | 0.63  | 0.656 | 0.65  | 0.603 | 0.652 |

## Results: battery 16 Wh

Battery: 16 Wh, horizon 300 s.

Scenarios per policy: 100. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B0 | 0.882 +/- 0.008 | 0.882 +/- 0.008 | 100% | 10068.6 +/- 1209.4 | 0.069 +/- 0.023 | 0.731 +/- 0.008 |
| B1 | 0.884 +/- 0.007 | 0.884 +/- 0.007 | 100% | 10343.3 +/- 1248.1 | 0.098 +/- 0.025 | 0.689 +/- 0.006 |
| B2 | 0.887 +/- 0.006 | 0.887 +/- 0.006 | 100% | 10850.0 +/- 1306.9 | 0.088 +/- 0.021 | 0.694 +/- 0.004 |
| B3 | 0.909 +/- 0.005 | 0.909 +/- 0.005 | 100% | 10907.3 +/- 1308.6 | 0.037 +/- 0.011 | 0.726 +/- 0.004 |
| B4 | 0.914 +/- 0.004 | 0.914 +/- 0.004 | 100% | 10308.0 +/- 1241.1 | 0.018 +/- 0.004 | 0.783 +/- 0.005 |
| B5 | 0.908 +/- 0.005 | 0.908 +/- 0.005 | 100% | 10924.7 +/- 1308.0 | 0.037 +/- 0.011 | 0.727 +/- 0.004 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B0 | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| B0 | - | -0.002 | -0.005 | -0.027* | -0.033* | -0.027* |
| B1 | +0.002 | - | -0.003* | -0.025* | -0.031* | -0.025* |
| B2 | +0.005 | +0.003* | - | -0.022* | -0.028* | -0.022* |
| B3 | +0.027* | +0.025* | +0.022* | - | -0.006* | +0.000* |
| B4 | +0.033* | +0.031* | +0.028* | +0.006* | - | +0.006* |
| B5 | +0.027* | +0.025* | +0.022* | -0.000* | -0.006* | - |

Mean coverage_full by mobility model (scenario counts: group_drift 23, surge 22, hotspot_jump 21, random_waypoint 17, attraction 17):

| mobility        |    B0 |    B1 |    B2 |    B3 |    B4 |    B5 |
|:----------------|------:|------:|------:|------:|------:|------:|
| attraction      | 0.885 | 0.892 | 0.893 | 0.917 | 0.919 | 0.917 |
| group_drift     | 0.866 | 0.866 | 0.874 | 0.9   | 0.911 | 0.9   |
| hotspot_jump    | 0.889 | 0.88  | 0.884 | 0.905 | 0.911 | 0.905 |
| random_waypoint | 0.89  | 0.888 | 0.887 | 0.909 | 0.915 | 0.909 |
| surge           | 0.882 | 0.895 | 0.897 | 0.914 | 0.918 | 0.914 |
