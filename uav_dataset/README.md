# UAV-NOMA dataset generator + Gymnasium env

Simulation-based planning tool for UAV base stations in disaster areas (moving crowds, collapsed buildings,
battery-limited drone, NOMA downlink). **Synthetic data**: results are conditional on the model.
Read `../CLAUDE.md` first for the project rules, hypotheses (H1-H4) and gates.

## Setup
    pip install -r ../requirements.txt

## Run (from this folder)
    python make_dataset.py all        # scenarios, users, trajectory, obstacles, sweep CSVs into data/ (~1 min)
    python export_excel.py            # CSVs -> one Excel file (close it in Excel first, or the write fails)
    python -m pytest                  # 52 tests
    python altitude_by_class.py 20    # Gate G2 diagnostic: best altitude per user class
    python mobility_check.py 30 10    # H1 check: fixed drone vs oracle-best position (30 scenarios, 10 dBm)
    python view_run.py --seed 3 --policy follow   # watch one episode (saves data/run.gif)

All settings are in `config.yaml`. Change values there, never in the code. One config per dataset version.
`data/` is not in git: regenerate it. Splits are by seed and must never mix: train 0-99, val 100-119, test 120-139.

## Files
| File | What it does |
|---|---|
| `make_dataset.py` | All the physics: scenarios, users, mobility, obstacles, channel (Al-Hourani + fading), NOMA/OMA, energy model, sweep |
| `uav_env.py` | Gymnasium env (`reset`, `step`) built on `make_dataset.py`, so env and dataset cannot disagree |
| `view_run.py` | Top-down viewer / GIF of one episode (demo policies only, not baselines) |
| `export_excel.py` | Combines the split CSVs into one workbook with a `split` column |
| `test_*.py` | Tests for NOMA, mobility, obstacles/fading/energy and the env |

## Tables (also the Excel sheets)
- `scenarios`: seed, n_users, n_clusters, cluster_radius_m, scatter_fraction, area_m, bandwidth_hz, pairing, mobility, n_obstacles
- `users` (t=0): seed, user_id, x, y, cluster_id (-1 = scattered), class, min_rate_bps
- `trajectory`: seed, t, user_id, x, y, vx, vy, cluster_id, class (snapshot every 30 s for 300 s)
- `obstacles`: seed, obstacle_id, x_min, y_min, x_max, y_max
- `sweep`: seed, x, y, h, p_dbm, pairing, coverage, sum_rate_mbps, spectral_eff, fairness, outage_rescue, coverage_oma, sum_rate_oma_mbps, energy_j_per_step

## Not verified yet (do not present as validated)
1. Al-Hourani (a, b, eta) and Zeng-Xu-Zhang energy parameters are from memory: check against the papers.
2. No MATLAB parity test yet (Gate G1).
3. Engineering assumptions with no source: per-class min rates, walking/surge speeds, 15 dB obstacle loss,
   5 W circuit power, 40% PA efficiency, 10 Wh battery, reward energy weight. Each needs a sensitivity range.

## Model notes
- Mean path loss = FSPL + P_LoS*eta_LoS + (1-P_LoS)*eta_NLoS (the architecture doc's formula omits the NLoS term).
- NOMA: strongest user paired with weakest (or random), fixed 0.8/0.2 split, SIC feasibility checked.
  OMA = FDMA with the same total bandwidth and power. Bandwidth = n_users x 50 kHz.
- Blocked links (2D segment crosses a rectangle) get extra loss; fading is off in the dataset, optional in the env.
