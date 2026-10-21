# Chapter 7. Baselines and their results

## 7.1 The simple pilots
**Plain words.** Before trusting an AI pilot we need strong rivals that do not learn: if the AI only beats "a drone that does
nothing", it proves nothing. Each rival plays exactly the same game (`env.step()`), on exactly the same scenarios.

| ID | Name | What it does | Settings |
|---|---|---|---|
| B0 | Fixed | sits at the map centre at 150 m and full power, forever | |
| B1 | Follow the crowd | every second, flies toward the centre of the biggest true cluster | uses true cluster ids |
| B2 | Weighted k-means | every 10 s, clusters the users (k = 3, rescue users count 3x) and flies to the heaviest cluster centre | uses true positions |
| B3 | Grid search | every 10 s, scores a grid of candidate spots (10 x 10, or 14 x 14 on 2 km maps) plus the current spot at 150 m and flies to the best | uses `env.evaluate` |
| B4 | Particle swarm (PSO) | every 10 s, searches position, altitude and power with 12 particles x 10 iterations; objective = the v2 reward | |
| B5 | Energy-aware | like B3, but moves only if the coverage gain x 10 s exceeds the extra energy cost of moving; that cost is clamped at 0 because forward flight is cheaper than hovering, so B5 behaves like B3 (D-14) | |
| B6 | Grid search + altitude | like B3, but tries 5 altitudes (50, 100, 150, 200, 300 m) at every grid spot | added 10-19 (D-16) |
| B7 | Circling pilot | chooses spots like B6, but circles them (radius 50 m) at the speed that uses the least power (9.8 m/s) instead of hovering | added 10-21 (D-45, 7.10) |
| B3obs, B3obsU, B3obsUO | Information ladder | B3's search with only the AI's capped maps / uncapped maps / plus buildings; diagnostic only, not in the default runs | added 10-21 (D-37, Chapter 8.7) |

The baselines see the true user positions (privileged information); the AI only sees maps. That makes them a strong test.
Code: `uav_dataset/baselines.py`; settings in `config.yaml` (`baselines:`).

## 7.2 How results are measured
- **coverage_full**: the share of users served, averaged over the whole 300 s, counting 0 after the battery dies (the main metric).
- **coverage_alive**: the same, only over the seconds the drone was flying.
- **survived the horizon**: share of scenarios where the battery lasted 300 s.
- **served-user-seconds per Wh**, **rescue outage** (share of rescue users not served), **fairness** (Jain's index).
- Every value is **mean +/- 95% confidence interval** over scenarios (`evalstats.mean_ci`, 1.96 standard errors).
- **Paired differences** (`evalstats.paired_diff`): for every scenario, pilot A's score minus pilot B's; then mean and CI of those
  differences. Fairer than comparing two averages because it cancels "that scenario was easy for everyone". A `*` means the CI
  excludes 0, so the difference is not luck (a tiny `+0.000*` is not a real gap).

Reproduce: `cd uav_dataset && python run_baselines.py [--profile <name>] [--battery_wh <Wh>] [--seeds N]` (results go to
`uav_dataset/results/`, not committed; the tables below are copies).

## 7.3 What the results say (summary)
1. **Default scenarios, 10 Wh:** no pilot survives 300 s (hovering needs 14.7 Wh), so the ranking mostly measures survival time.
   B4 has the best coverage while alive (0.913) but ties B0 overall because it dies first.
2. **Moving costs less than hovering** in this energy model (134 vs 176 J/s), so pilots that move last longer.
3. **Default scenarios, 16 Wh (everyone survives):** B4 0.914, B3 0.909, B5 0.908, B2 0.887, B1 0.884, B0 0.882. A parked drone
   already covers 88%: very little headroom. B1 and B2 do not significantly beat B0.
4. **`hard` profile:** the parked drone falls to 0.428 and the best pilots reach 0.740: a 31-point gap. **H1 holds here.**
   Neither low power alone nor a big map alone produces it; the combination does.
5. **B6 ties B4** (0.741 vs 0.740): B4's lead over B3 was choosing a better altitude, not better placement. The bar for the AI on
   `hard` is about 0.74.
6. **On the still-crowd test used for RL (`rl_static`, validation seeds):** Random 0.413, B0 0.441, B1 0.600, B2 0.610,
   B3 = B5 0.659; the best single spot reached instantly would give 0.686.
7. Caveats: baseline settings are untuned engineering choices; minimum rates are unsigned assumptions; one-step-greedy searches
   (B3, B4, B6) cannot anticipate where a crowd is going.

Bar charts: [default 10 Wh](figures/baselines_default_10wh.png), [default 16 Wh](figures/baselines_default_16wh.png),
[hard, 7 pilots](figures/baselines_hard_7policies.png). Example flights: [hard scenario 5](figures/1_hard_moving_crowds.png),
[surge custom scenario](figures/3_surge_custom.png).

## 7.4 Default scenarios, 10 Wh (100 scenarios, seeds 0-99)

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


## 7.5 Default scenarios, 16 Wh (100 scenarios)

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


## 7.6 Profile `lowpower` (50 scenarios, 10 Wh)

Profile: lowpower. Area 1000 m, max power 20 dBm, battery 10 Wh, horizon 300 s.

Scenarios per policy: 50. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B0 | 0.552 +/- 0.023 | 0.796 +/- 0.032 | 0% | 8699.8 +/- 1464.1 | 0.354 +/- 0.079 | 0.746 +/- 0.017 |
| B1 | 0.581 +/- 0.017 | 0.817 +/- 0.023 | 0% | 9403.9 +/- 1612.2 | 0.313 +/- 0.049 | 0.690 +/- 0.018 |
| B2 | 0.617 +/- 0.018 | 0.826 +/- 0.022 | 0% | 9948.8 +/- 1701.0 | 0.298 +/- 0.048 | 0.704 +/- 0.014 |
| B3 | 0.616 +/- 0.014 | 0.859 +/- 0.019 | 0% | 9986.7 +/- 1694.2 | 0.221 +/- 0.048 | 0.742 +/- 0.012 |
| B4 | 0.582 +/- 0.010 | 0.880 +/- 0.015 | 0% | 9548.8 +/- 1633.6 | 0.125 +/- 0.038 | 0.818 +/- 0.011 |
| B5 | 0.617 +/- 0.014 | 0.859 +/- 0.019 | 0% | 9990.6 +/- 1694.4 | 0.221 +/- 0.048 | 0.742 +/- 0.012 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B0 | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| B0 | - | -0.030* | -0.065* | -0.065* | -0.031* | -0.065* |
| B1 | +0.030* | - | -0.036* | -0.035* | -0.001 | -0.035* |
| B2 | +0.065* | +0.036* | - | +0.000 | +0.035* | +0.000 |
| B3 | +0.065* | +0.035* | -0.000 | - | +0.034* | -0.000 |
| B4 | +0.031* | +0.001 | -0.035* | -0.034* | - | -0.034* |
| B5 | +0.065* | +0.035* | -0.000 | +0.000 | +0.034* | - |

Mean coverage_full by mobility model (scenario counts: group_drift 14, hotspot_jump 11, random_waypoint 10, surge 8, attraction 7):

| mobility | B0 | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| attraction | 0.556 | 0.597 | 0.639 | 0.634 | 0.590 | 0.636 |
| group_drift | 0.531 | 0.532 | 0.582 | 0.585 | 0.563 | 0.585 |
| hotspot_jump | 0.571 | 0.607 | 0.626 | 0.629 | 0.592 | 0.629 |
| random_waypoint | 0.578 | 0.590 | 0.623 | 0.626 | 0.587 | 0.625 |
| surge | 0.525 | 0.607 | 0.638 | 0.626 | 0.589 | 0.626 |


## 7.7 Profile `bigarea` (50 scenarios, 10 Wh)

Profile: bigarea. Area 2000 m, max power 30 dBm, battery 10 Wh, horizon 300 s.

Scenarios per policy: 50. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B0 | 0.522 +/- 0.018 | 0.765 +/- 0.027 | 0% | 8298.9 +/- 1384.0 | 0.497 +/- 0.099 | 0.730 +/- 0.031 |
| B1 | 0.582 +/- 0.016 | 0.812 +/- 0.022 | 0% | 9420.7 +/- 1610.3 | 0.375 +/- 0.057 | 0.622 +/- 0.017 |
| B2 | 0.627 +/- 0.017 | 0.821 +/- 0.021 | 0% | 10135.2 +/- 1732.4 | 0.357 +/- 0.055 | 0.649 +/- 0.014 |
| B3 | 0.603 +/- 0.014 | 0.845 +/- 0.019 | 0% | 9786.4 +/- 1665.5 | 0.306 +/- 0.060 | 0.675 +/- 0.017 |
| B4 | 0.589 +/- 0.010 | 0.876 +/- 0.013 | 0% | 9639.5 +/- 1647.1 | 0.209 +/- 0.046 | 0.746 +/- 0.013 |
| B5 | 0.604 +/- 0.014 | 0.844 +/- 0.019 | 0% | 9788.0 +/- 1665.7 | 0.307 +/- 0.060 | 0.675 +/- 0.017 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B0 | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| B0 | - | -0.060* | -0.104* | -0.081* | -0.066* | -0.081* |
| B1 | +0.060* | - | -0.044* | -0.021* | -0.006 | -0.021* |
| B2 | +0.104* | +0.044* | - | +0.023* | +0.038* | +0.023* |
| B3 | +0.081* | +0.021* | -0.023* | - | +0.015* | -0.000 |
| B4 | +0.066* | +0.006 | -0.038* | -0.015* | - | -0.015* |
| B5 | +0.081* | +0.021* | -0.023* | +0.000 | +0.015* | - |

Mean coverage_full by mobility model (scenario counts: group_drift 14, hotspot_jump 11, random_waypoint 10, surge 8, attraction 7):

| mobility | B0 | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| attraction | 0.527 | 0.599 | 0.645 | 0.615 | 0.600 | 0.613 |
| group_drift | 0.493 | 0.541 | 0.598 | 0.567 | 0.568 | 0.567 |
| hotspot_jump | 0.529 | 0.610 | 0.641 | 0.625 | 0.598 | 0.625 |
| random_waypoint | 0.532 | 0.582 | 0.613 | 0.616 | 0.599 | 0.616 |
| surge | 0.549 | 0.602 | 0.658 | 0.612 | 0.589 | 0.615 |


## 7.8 Profile `hard`, all 7 pilots (100 scenarios, 16 Wh)

Profile: hard. Area 2000 m, max power 20 dBm, battery 16 Wh, horizon 300 s.

Scenarios per policy: 100. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B0 | 0.428 +/- 0.042 | 0.428 +/- 0.042 | 100% | 4207.4 +/- 664.6 | 0.846 +/- 0.034 | 0.504 +/- 0.041 |
| B1 | 0.627 +/- 0.027 | 0.627 +/- 0.027 | 100% | 7157.9 +/- 870.4 | 0.535 +/- 0.031 | 0.538 +/- 0.021 |
| B2 | 0.633 +/- 0.027 | 0.633 +/- 0.027 | 100% | 7575.5 +/- 901.2 | 0.524 +/- 0.031 | 0.562 +/- 0.019 |
| B3 | 0.675 +/- 0.025 | 0.675 +/- 0.025 | 100% | 7680.0 +/- 901.9 | 0.506 +/- 0.029 | 0.592 +/- 0.018 |
| B4 | 0.740 +/- 0.023 | 0.740 +/- 0.023 | 100% | 8079.1 +/- 936.5 | 0.417 +/- 0.036 | 0.709 +/- 0.017 |
| B5 | 0.675 +/- 0.025 | 0.675 +/- 0.025 | 100% | 7680.6 +/- 903.0 | 0.505 +/- 0.029 | 0.593 +/- 0.018 |
| B6 | 0.741 +/- 0.023 | 0.741 +/- 0.023 | 100% | 8004.4 +/- 926.0 | 0.419 +/- 0.038 | 0.715 +/- 0.017 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B0 | B1 | B2 | B3 | B4 | B5 | B6 |
|---|---|---|---|---|---|---|---|
| B0 | - | -0.199* | -0.205* | -0.247* | -0.312* | -0.247* | -0.313* |
| B1 | +0.199* | - | -0.006 | -0.048* | -0.114* | -0.048* | -0.114* |
| B2 | +0.205* | +0.006 | - | -0.042* | -0.108* | -0.042* | -0.108* |
| B3 | +0.247* | +0.048* | +0.042* | - | -0.065* | +0.000 | -0.066* |
| B4 | +0.312* | +0.114* | +0.108* | +0.065* | - | +0.066* | -0.000 |
| B5 | +0.247* | +0.048* | +0.042* | -0.000 | -0.066* | - | -0.066* |
| B6 | +0.313* | +0.114* | +0.108* | +0.066* | +0.000 | +0.066* | - |

Mean coverage_full by mobility model (scenario counts: attraction 27, surge 25, group_drift 25, hotspot_jump 23):

| mobility | B0 | B1 | B2 | B3 | B4 | B5 | B6 |
|---|---|---|---|---|---|---|---|
| attraction | 0.482 | 0.665 | 0.664 | 0.700 | 0.770 | 0.700 | 0.769 |
| group_drift | 0.419 | 0.646 | 0.652 | 0.701 | 0.760 | 0.701 | 0.757 |
| hotspot_jump | 0.376 | 0.575 | 0.577 | 0.625 | 0.699 | 0.624 | 0.700 |
| surge | 0.427 | 0.615 | 0.630 | 0.667 | 0.727 | 0.667 | 0.730 |


## 7.9 Still crowd `rl_static`, validation seeds 100-119 (reference for the AI)

Split: val (20 scenarios, seeds 100-119). Profile: rl_static. Controls: xy. Area 2000 m, 20 dBm, battery 16 Wh.

Scenarios per policy: 20. Values are mean +/- 95% CI over scenarios.

| Policy | coverage_full | coverage_alive | survived the horizon | served-user-s per Wh | rescue outage | fairness |
|---|---|---|---|---|---|---|
| B0 | 0.441 +/- 0.101 | 0.441 +/- 0.101 | 100% | 2717.5 +/- 881.6 | 0.865 +/- 0.071 | 0.489 +/- 0.100 |
| B1 | 0.600 +/- 0.076 | 0.600 +/- 0.076 | 100% | 4190.8 +/- 1121.8 | 0.584 +/- 0.093 | 0.494 +/- 0.058 |
| B2 | 0.610 +/- 0.068 | 0.610 +/- 0.068 | 100% | 4484.4 +/- 1128.2 | 0.526 +/- 0.086 | 0.529 +/- 0.043 |
| B3 | 0.659 +/- 0.069 | 0.659 +/- 0.069 | 100% | 4576.6 +/- 1156.6 | 0.542 +/- 0.102 | 0.557 +/- 0.043 |
| B5 | 0.659 +/- 0.069 | 0.659 +/- 0.069 | 100% | 4576.6 +/- 1156.6 | 0.542 +/- 0.102 | 0.557 +/- 0.043 |
| Random | 0.413 +/- 0.091 | 0.413 +/- 0.091 | 100% | 3193.6 +/- 932.4 | 0.870 +/- 0.056 | 0.459 +/- 0.095 |

Paired difference in coverage_full (row minus column; positive = row is better; * = the 95% CI excludes 0):

| | B0 | B1 | B2 | B3 | B5 | Random |
|---|---|---|---|---|---|---|
| B0 | - | -0.158* | -0.169* | -0.218* | -0.218* | +0.028 |
| B1 | +0.158* | - | -0.011 | -0.060* | -0.060* | +0.186* |
| B2 | +0.169* | +0.011 | - | -0.049* | -0.049* | +0.197* |
| B3 | +0.218* | +0.060* | +0.049* | - | +0.000 | +0.246* |
| B5 | +0.218* | +0.060* | +0.049* | +0.000 | - | +0.246* |
| Random | -0.028 | -0.186* | -0.197* | -0.246* | -0.246* | - |

Mean coverage_full by mobility model (scenario counts: static 20):

| mobility | B0 | B1 | B2 | B3 | B5 | Random |
|---|---|---|---|---|---|---|
| static | 0.441 | 0.600 | 0.610 | 0.659 | 0.659 | 0.413 |

## 7.10 The circling pilot B7: does circling save battery? (plan step 5, 2026-10-21)
**Plain words.** In the energy model of Zeng, Xu and Zhang, a drone flying at about 10 m/s uses less power than one hovering
(126 W against 168 W), as with helicopters, which get extra lift from forward flight. So instead of parking over the best spot,
B7 flies a 50 m circle around it. It chooses its spots exactly like B6. All runs with the acceleration limit and the turning
cost switched on, so the comparison cannot be won by the shaking trick.

**Main test (D-45): fly until the battery is empty.** Still crowds (`rl_static`), 10 Wh, up to 600 s, 50 scenarios:

| Pilot | People-seconds served | Flight time | Coverage while flying | Mean power |
|---|---|---|---|---|
| B6 (hovers) | 67,682 | 198 s | 0.697 | 182.5 W |
| **B7, circle 50 m** | **85,033 (+25.6%*)** | **249 s** | 0.696 (same) | 144.9 W |
| B7, circle 100 m | 83,725 (+23.7%*) | 251 s | 0.680 | 143.7 W |

Circling serves **about 26% more people per battery** with the same coverage while flying. Simple arithmetic predicts +31%
(power ratio 173.7 / 132.7 W); the measured gain is a little lower because both pilots pay the same fixed cost of flying to
their spot. A 50 m circle beats a 100 m circle (the wider circle strays further from the best spot).

**In the normal 5-minute mission** (`hard`, moving crowds, 100 scenarios):

| Battery | B6 (hovers) | B7 (circles) | Difference |
|---|---|---|---|
| 12 Wh | 0.596 (never survives) | **0.716** | +0.120* |
| 13 Wh | 0.652 (never survives) | **0.730** (survives 98%) | +0.079* |
| 14 Wh | 0.707 (survives 3%) | **0.731** | +0.024* |
| 16 Wh | **0.739** | 0.731 | -0.009* |

When the battery cannot cover hovering for the whole mission, circling wins clearly; when there is plenty of battery,
hovering is slightly better (circling keeps the drone up to 50 m from the best spot).

**Robustness (30 scenarios, one parameter changed at a time):** the gain stays between +21% and +31%: drag d0 0.3 (the paper's
value) +30.7%, induced power Pi +-20% +30.4% / +20.8%, acceleration limit 2 or 8 m/s^2 +24.9% / +26.2%, radius 100 m +24.4%.
So the conclusion does not depend on the unverified d0 = 0.6.

**Not verified.** The turning-energy term is our own quasi-steady extension; whether Zeng's forward-flight formula holds in
tight, slow circles is not verified (in this model even a 10 m circle is cheaper than hovering). Vertical acceleration is not
charged. Runs used today's NOMA, no fading, full power.

**Reproduce:** `python accel_loiter_exp.py run b` (also `a`, `c`, `d`), then `python accel_loiter_exp.py report`.

