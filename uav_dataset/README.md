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
    python view_run.py --seed 5 --profile hard --policy B3     # watch any scenario with any pilot (data/run.gif)
    python view_run.py --seed 9 --users 600 --clusters 4 --mobility surge --obstacles 6 --policy B2   # your own
    python run_baselines.py --profile hard                    # compare all baselines (Gate G3)
    pip install -r ../requirements-rl.txt && python rl_train.py   # train PPO (config: rl:), then rl_eval.py
    pip install -r ../requirements-dashboard.txt                # showcase + planning dashboard, then FROM THE REPO ROOT:
    streamlit run uav_dataset/dashboard.py                    # opens http://localhost:8501 (AI models: UAV_MODELS_DIR)
    # Online: Streamlit Community Cloud, repo vathsa1703/Major_project, branch main, file uav_dataset/dashboard.py,
    # Python 3.12; it installs uav_dataset/requirements.txt and flies the committed showcase AI in uav_dataset/models/.

All settings are in `config.yaml`. Change values there, never in the code. One config per dataset version.
`data/` is not in git: regenerate it. Splits are by seed and must never mix: train 0-99, val 100-119, test 120-139.

## Files
| File | What it does |
|---|---|
| `make_dataset.py` | All the physics: scenarios, users, mobility, obstacles, channel (Al-Hourani + fading), NOMA/OMA, energy model, sweep |
| `uav_env.py` | Gymnasium env (`reset`, `step`) built on `make_dataset.py`, so env and dataset cannot disagree |
| `view_run.py` | Top-down viewer / GIF of one episode (demo policies only, not baselines) |
| `dashboard.py` / `dashboard_core.py` | Streamlit dashboard (Showcase, Fly, Compare, Plan, About); all its logic is in `dashboard_core.py` (no streamlit import, tested) |
| `export_excel.py` | Combines the split CSVs into one workbook with a `split` column |
| `test_*.py` | Tests for NOMA, mobility, obstacles/fading/energy and the env |

## Tables (also the Excel sheets)
- `scenarios`: seed, n_users, n_clusters, cluster_radius_m, scatter_fraction, area_m, bandwidth_hz, pairing, mobility, n_obstacles
- `users` (t=0): seed, user_id, x, y, cluster_id (-1 = scattered), class, min_rate_bps
- `trajectory`: seed, t, user_id, x, y, vx, vy, cluster_id, class (snapshot every 30 s for 300 s)
- `obstacles`: seed, obstacle_id, x_min, y_min, x_max, y_max
- `sweep`: seed, x, y, h, p_dbm, pairing, coverage, sum_rate_mbps, spectral_eff, fairness, outage_rescue, coverage_oma, sum_rate_oma_mbps, energy_j_per_step

## Not verified yet (do not present as validated)
1. Zeng energy formulas are checked against the paper, but our drone (W = 20 N) is our own choice and d0 = 0.6 is unverified.
   Al-Hourani (a, b, eta) is NOT checked against the original paper. See `../docs/assumptions.md` for every parameter.
2. No MATLAB parity test yet (Gate G1).
3. Engineering assumptions with no source: per-class min rates, walking/surge speeds, 15 dB obstacle loss,
   5 W circuit power, 40% PA efficiency, 10 Wh battery, reward energy weight. Each needs a sensitivity range.

## Model notes
- Mean path loss = FSPL + P_LoS*eta_LoS + (1-P_LoS)*eta_NLoS (the architecture doc's formula omits the NLoS term).
- NOMA: strongest user paired with weakest (or random), fixed 0.8/0.2 split, SIC feasibility checked.
  OMA = FDMA with the same total bandwidth and power. Bandwidth = n_users x 50 kHz.
- Blocked links (2D segment crosses a rectangle) get extra loss; fading is off in the dataset, optional in the env.
