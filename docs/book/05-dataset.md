# Chapter 5. The dataset

**Plain words.** The dataset is a set of tables describing 140 invented disaster scenarios: who is where, how they move, where
the collapsed buildings are, and how good the signal would be for every drone position, height and power. It is *synthetic*:
generated from `config.yaml` and the seeds, so anyone can regenerate exactly the same data. The AI does not learn from these
tables (it learns by playing the game in Chapter 6); the tables are for checking the physics, drawing charts and comparing
NOMA with OMA.

## 5.1 How to regenerate it
```
cd uav_dataset
python make_dataset.py all       # about 1 minute; writes data/*.csv and two pictures
python export_excel.py           # one Excel workbook (close it in Excel first, or the write fails)
```
The data folder is not in git (D-11). `make_dataset.py quick` writes a small 3-scenario sweep for smoke tests.

## 5.2 Versions
| Version | Date | What changed | Where it is |
|---|---|---|---|
| v1 | 10-14 | 200 users, 3 clusters (100 m), 10% scattered, 2 classes (rescue 0.2 Mbps, normal 0.1 Mbps), 10 MHz, 8 altitudes | kept in `data_v1/` |
| v2 | 10-14 | varied scenarios (100-1,000 users, 2-5 clusters), 5 classes, bandwidth per user, pairing option, 12 altitudes up to 1,000 m, then moving crowds and the trajectory table | overwritten by v3 |
| v3 (current) | 10-15 | collapsed buildings, energy from the propulsion model, 5 mobility models (incl. surge and hotspot jump), obstacles table | `data/` |

## 5.3 Files and splits
Every table exists per split (`*_train.csv`, `*_val.csv`, `*_test.csv`): train = seeds 0-99, val = 100-119, test = 120-139.
The Excel workbook `data/uav_noma_dataset.xlsx` (145 MB) holds all five tables as sheets with an extra `split` column.

| Table / sheet | Rows (v3) | One row is |
|---|---|---|
| `scenarios` | 140 | one scenario |
| `obstacles` | 341 | one collapsed building |
| `users` | 74,900 | one person at t = 0 |
| `trajectory` | 823,900 | one person at one snapshot (every 30 s for 300 s) |
| `sweep` | 813,120 | one drone position, altitude and power in one scenario (140 x 121 positions x 12 altitudes x 4 powers) |

## 5.4 Columns
**scenarios:** `seed`, `n_users`, `n_clusters`, `cluster_radius_m`, `scatter_fraction`, `area_m`, `bandwidth_hz`, `pairing`,
`mobility`, `n_obstacles`.

**obstacles:** `seed`, `obstacle_id`, `x_min`, `y_min`, `x_max`, `y_max` (metres).

**users:** `seed`, `user_id`, `x`, `y` (metres), `cluster_id` (-1 = scattered), `class`, `min_rate_bps`.

**trajectory:** `seed`, `t` (s), `user_id`, `x`, `y`, `vx`, `vy` (m/s, the velocity of the step starting at t), `cluster_id`, `class`.

**sweep:** `seed`, `x`, `y`, `h` (drone position and altitude), `p_dbm` (total transmit power), `pairing`, `coverage` (share of
users served with NOMA), `sum_rate_mbps`, `spectral_eff` (sum rate / bandwidth), `fairness` (Jain), `outage_rescue` (share of
rescue users not served), `coverage_oma`, `sum_rate_oma_mbps`, `energy_j_per_step` (hovering energy at that power).

## 5.5 What the workbook contains (read back on 2026-10-15)
The v3 workbook was read cell by cell with openpyxl. No empty cells in any sheet.
- **scenarios:** users per scenario 100-1,000 (mean 535); clusters 2-5 (mean 3.72); radius 50.0-198.8 m (mean 127.2); scatter
  5.1-9.9%; area 1,000 m in all; bandwidth 5-50 MHz; obstacles 0-5 (mean 2.4); pairing `extreme` in all 140; mobility: group
  drift 33, surge 31, hotspot jump 28, random waypoint 24, attraction 24.
- **users:** voice 22,639, normal 15,023, iot 14,950, video 14,899, rescue 7,389; minimum rate 10-500 kbps (mean about 156 kbps).
- **trajectory:** t from 0 to 300 s; velocity components from -3.9 to +4.1 m/s.
- **sweep:** altitude 50-1,000 m; power 0-30 dBm; coverage NOMA mean 0.507 (maximum 0.990), OMA mean 0.500 (maximum 1.000);
  sum rate NOMA mean 83.3 Mbps, OMA mean 75.2 Mbps; fairness mean 0.674; rescue outage mean 0.650; energy per step 173.49-175.99 J.

Points to know: only `extreme` pairing appears; the sweep uses the t = 0 positions only; NOMA coverage never reaches 1.0 while
OMA does (not investigated); the high rescue outage comes from the assumed 200 kbps rescue minimum rate.

## 5.6 Key charts
- [users_preview_v3.png](figures/users_preview_v3.png): four training scenarios, crowds and scattered users, rescue users circled.
- [altitude_check_v3.png](figures/altitude_check_v3.png): mean coverage against altitude, NOMA and OMA, per power level (all classes mixed).
- [altitude_by_class_v2.png](figures/altitude_by_class_v2.png): the same per user class; every class has a best altitude.
- [noma_vs_oma_v1.png](figures/noma_vs_oma_v1.png): NOMA vs OMA sum rate and coverage per power level (dataset v1).

## 5.7 Is it enough data?
Count scenarios, not rows: 140. Enough for the physics checks, the NOMA-vs-OMA comparison and the baseline gate (100+ seeded
scenarios). It is not training data for the AI. A "preview" workbook with a few scenarios was offered for the guide, because the
full workbook is slow to open.
