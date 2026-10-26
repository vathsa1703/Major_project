# Pre-registration: how much user-location information does a placement planner need?

Contribution 2 of the project. Written and committed on 2026-10-23 BEFORE any main run. Before this commit only these
were run: two full-information timing episodes per planner and profile (B6 and B3 on seeds 100 and 101, both profiles,
no report-based pilot) and two smoke episodes of the runner (full-information B6, hard, seeds 100-101). No report-based
configuration has been run on any scenario of this study. Code: `uav_dataset/baselines.py` (`ReportsView`, `B6rep`,
`B3rep`), `uav_dataset/voi_exp.py` (runner + analysis), `uav_dataset/test_voi.py`, config section `voi:`.

## 1. Question in plain words

Ground towers are down; the drone is the network. A phone that attaches to the drone can send its GPS position
(emergency-location reporting), but in practice only some phones do, GPS has an error, and reports arrive every so
often. Our best simple planner (B6: try 196 spots x 5 altitudes = 980 candidates plus "stay" every 10 s with the full
radio physics, fly to the best) normally uses the TRUE position of every user. **What share f of phones must report,
with what GPS error sigma and what report interval (age), for the planner to keep at least 98% of the coverage it gets
with full information?**

## 2. Information model (`baselines.ReportsView`; all pure NumPy, seeded)

- **Who reports.** Phone u reports iff U_u < f, with U_u ~ U[0, 1) drawn once per episode from rng
  (scenario seed, 7100, rep, 0). Fixed for the whole episode. Nested: the reporters at f = 0.1 are a subset of those at
  f = 0.2 (common random numbers, so the f-curve is paired within a scenario). rep = 0 for every run.
- **GPS error.** Every report carries its own error: reported position = true position at the report time +
  sigma x Z[t, u], Z standard 2-D normal (std sigma PER AXIS) from rng (scenario, 7100, rep, 2); clipped to the map.
  The same Z is used for every sigma.
- **Report interval (age).** Phone u reports at the times phase_u + k x age (phase_u uniform in {0, ..., age - 1} from
  rng (scenario, 7100, rep, 1): phones are not synchronised) and once on attach (its first active second; t = 0 for
  everyone outside competing sites). The planner uses each phone's LAST report: information age uniform in [0, age).
  age = 0: every phone reports every second.
- **Visibility.** The planner sees a reporting phone if it was attached (active) at its last report time. Unreported
  users are invisible. A phone that has left since (competing sites: movers deactivate at A) stays visible at its stale
  position until its next scheduled report. In competing sites the env models a mover and its arrival at B as two user
  entries; each has its own report draw (a re-attach is treated as a new phone; the expected reporter share stays f).
- **Crowd size.** f is assumed known. k visible reporters stand for n_hat = round(k / f) users, rounded up to even
  (NOMA pairs). The n_hat - k extra pseudo-users are placed at the reporters' reported positions (copies split evenly,
  largest remainder, deterministic).
- **Classes.** Reporters' classes and min rates are known (they are in the report). The extra pseudo-users get classes
  from the configured class mix (rescue 10%, video 20%, voice 30%, iot 20%, normal 20%), counts by largest remainder,
  interleaved along the list (`explicit_classes`).
- **Empty belief.** With fewer than 2 users in the belief the planner scores every candidate 0 and therefore stays
  where it is (B6's tie rule: the candidate closest to the drone).
- **Radio layer unchanged.** The planner scores candidates with the env's own physics (`UAVEnv.evaluate_users`: same
  channel, obstacles, access scheme, power, the scenario's fixed total bandwidth) on its belief. The drone then serves
  the TRUE users with the scenario's access scheme (`env.step` is untouched). The obstacles are known to the planner
  (as for B6; only the user information is degraded).
- **Full information.** f = 1, sigma = 0, age = 0 gives exactly the true users (test: B6rep == B6 and B3rep == B3 action
  for action, both profiles).

## 3. Planners

- **Primary: B6rep** = B6's search on the belief. **Secondary: B3rep** = B3's search (14 x 14 grid at 150 m + stay) on
  the belief. Each is compared with ITSELF on full information (B6, B3), scenario by scenario.
- B6fc on announced cells: NOT run (optional in the brief; left out to stay inside the compute budget).

## 4. Design

- **Profiles:** `hard` (2 x 2 km, 20 dBm, 3-8 obstacles, moving crowds of 4 dynamic mobility models, fixed NOMA) and
  `sites_d20_t60_ann` (the owner's G5 settings: competing sites 2 km apart, 60 s ramp, announced; noma_opt, SIC residual
  0.05, rescue first, a_max 4 m/s^2).
- **Scenarios:** 30 per configuration, the same 30 for every configuration: seeds 100-119 (the validation split) and
  1000-1009 (fresh; outside train 0-99, val, test 120-139 and the RL training range 10000-19999). The test split is not
  touched. No model is selected on these seeds (the planners have no trained parts), so using val is not a leak.
- **Configurations** (f, sigma m, age s):
  - B6: f in {0.05, 0.1, 0.2, 0.5, 1.0} at sigma 10, age 0; f in {0.05, 0.1, 0.2, 0.5, 1.0} at sigma 50, age 0 (added
    to the brief's grid so that "sigma <= 50 m" in the pass rule can be tested); sigma 0 at f 0.2; age 30 and 60 at
    f 0.2, sigma 10. 13 configurations + full information.
  - B3: f in {0.05, 0.1, 0.2, 0.5, 1.0} at sigma 10, age 0; sigma 0 and 50 at f 0.2; age 30 and 60 at f 0.2, sigma 10.
    9 configurations + full information.
  - Total: 2 profiles x (14 + 10) x 30 = 1,440 episodes. Estimated ~5.5 CPU hours (B6 ~9 s per episode on `hard`,
    ~35 s on the sites cell).
- **Metric:** `coverage_full` of each episode (mean coverage over the 300 s, dead drone = 0; run_baselines.run_episode).

## 5. Analysis (fixed now; `voi_exp.py analyse`)

- **Coverage ratio** R = mean over scenarios of coverage(config) / mean over scenarios of coverage(full information),
  same planner, same scenarios. 95% CI: paired bootstrap over scenarios, 10,000 resamples, numpy rng seed 0, percentile
  interval. Also reported: paired difference coverage(config) - coverage(full info), mean +/- 95% CI (normal
  approximation, `evalstats.paired_diff`).
- **f\*** (per profile, planner, sigma in {10, 50}, age 0) = the smallest grid f whose R AND the R of every larger grid
  f are >= 0.98 (point estimates); "not reached" if R(f = 1) < 0.98. **95% interval of f\***: recompute f\* in every
  bootstrap resample (the same resamples for all f of that curve) and take the 2.5% and 97.5% quantiles (inverted CDF;
  "not reached" counts as larger than 1). **Conservative f\***: the same rule applied to the lower CI bounds of R.
- **Pass criterion (primary, B6 only):** PASS if, on BOTH profiles and for BOTH sigma = 10 m and sigma = 50 m, f\* is
  identifiable and below 1, meaning the upper end of its 95% interval is a grid value below 1 (i.e. <= 0.5).
  Otherwise FAIL, and we report which profile / sigma fails and why (for example "98% is not reached even with every
  phone reporting at 50 m error" or "f\* = 1").
- **Secondary (descriptive, no pass/fail):** B3's f\* at sigma 10; the sigma effect (0 / 10 / 50 m) and the age effect
  (0 / 30 / 60 s) at f = 0.2 as R with CIs and paired differences.
- **Exploratory (labelled as such):** R by crowd size (100 / 300 / 600 / 1000 users) at each f, B6, sigma 10, age 0,
  and the mean number of reporting phones f x n; a possible design rule in absolute reporter counts.
- **Plots:** R vs f (log axis, B6 sigma 10 and 50, B3 sigma 10, both profiles) and the sigma / age sensitivity at
  f = 0.2. Files `uav_dataset/results/voi/voi_ratio_vs_f.png`, `voi_sigma_age.png`, copied to `docs/prereg/`.

## 6. Engineering assumptions (named, not verified)

- GPS error 10 m (open sky consumer GPS ~5 m; urban/rubble worse) and 50 m (degraded / network-assisted fallback):
  scale only, no source checked. Errors independent per report (real GPS errors are correlated in time; that would
  make errors at age 0 behave more like a bias).
- Reporting independent of position and class (real non-reporting is not random: older phones, dead batteries,
  people trapped indoors).
- f known to the planner (in practice it would be estimated, e.g. from the number of attached phones vs reports).
- The drone knows nothing about non-reporting phones (in reality an attached phone also reveals its signal strength;
  using it would only help, so this is a lower bound on what the planner can know).

## 7. Compute plan

`hard` locally (2 processes). `sites_d20_t60_ann` on Kaggle (kernels `srivathsajr/uav-voi-sites-p0` and `-p1`, each half
of the tasks with 4 workers; code from origin/final/integrate with the changed files written from base64 strings whose
SHA-256 hashes are printed in the kernel log and recorded in the report).
