# Pre-registration: the anticipation rule (2026-10-23)

Committed BEFORE any run of the 8 new cells below. The commit time of this file is the proof. Nothing in sections 1-6
may change after that commit; any later deviation is reported as a deviation, next to the result.

## 1. Question in plain words

When can a drone that *thinks ahead* beat a drone that simply re-plans greedily every 10 s? Our guess: only when the
drone must spend real time *between* the two places where people need it (no coverage from either), and only when
that dead time is a noticeable share of the mission. We turn that into two numbers per scenario family and predict
the room for anticipation from them, then test the prediction on 8 families nobody has run.

## 2. Definitions (fixed)

- **Cell** = a scenario family: competing sites (D-52), A-B distance D, demand ramp tau, drone top speed v_max,
  episode length T; everything else as `sites_base` (2 km map, 20 dBm, noma_opt, sic_eps 0.05, rescue first,
  a_max 4 m/s^2, obstacles, 14 x 14 x 5 B6 grid).
- **Footprint radius rho** (per cell): `anticip_exp.footprint_one` on design seeds 0-19 at t = 0: drone over site A's
  centre at the B6 altitude level that serves most of A's users; coverage of A's active users (all active users
  present, the cell's physics) as the drone moves r away (10 m steps, mean over 8 directions); rho = smallest r where
  it halves (linear interpolation). Cell value = median over the 20 seeds. Values (`anticipation/footprint.csv`):
  646-703 m (d10 670, d125 646, d15 690, d175 703, d20 688). rho does not depend on tau, v_max or T.
- **Transit time** T_tr = max(0, D - 2 rho) / v_max (time between the two footprints).
- **A** = (T_tr + 10 s) / (tau + 10 s) (transit vs ramp, 10 s = decision period); **M** = T_tr / T.
- **Headroom h** (per cell) = mean over the cell's scenarios of (dp - bar pilot), paired; dp = the clairvoyant
  energy-free plan (oracle.py) replayed through env.step; bar pilot = the best simple pilot by cell mean.
  Announced bar (the modelled h): fit cells best of {B6, B7, B8, B6fc_u, B6fc_a, B6dep}; new cells best of
  {B6, B6fc_u, B6fc_a, B6dep}. (B7 and B8 are not run in the new cells: at batteries where nobody runs out, B8 is
  exactly B6 and B7 was below B6 in all 9 fit cells, by 0.002-0.008.) The unannounced h (bar without B6fc_a, B6dep)
  is reported too but not modelled.
- **B6dep** (new pilot, baselines.B6Depart, commit 17c010a): B6 plus WHEN to leave for the announced destination:
  every 10 s, while the announced move is not over, it scores "stay at B6's choice until departure d, then fly to one
  of the 3 best spots for the end of the move" for d = now, now + 10 s, ... up to t0 + tau, plus "never leave", on
  one common horizon (now .. episode end, every 5 s, transit and braking from the env's own kinematics) with B6fc's
  forecast (announced schedule; velocity extrapolation capped at 60 s); flies the best plan's first leg. Same
  information as B6fc. Tests: test_b6dep.py (9).

## 3. Fit data (9 D-52 cells, fresh seeds 1000-1019, 20 each)

B6dep was run on Kaggle (kernels srivathsajr/uav-anticip-old-d10/-d15/-d20, repo commit 4075bcd + the embedded
files of 17c010a, sha256 in their run_info.json); B6 re-run there equals the phase-4 file exactly (max |diff| 0.0 on
180 rows). Other pilots and dp from the merged D-52 phase-4 file (sha256 9395b372...aa28a). Rows:
`anticipation/oldcells_episodes.csv`. B6dep is the bar pilot in all 9 cells.

| cell | D m | tau s | T_tr s | A | M | h announced (95% CI) | h unannounced |
|---|---|---|---|---|---|---|---|
| sites_d10_t0 | 1000 | 0 | 0.0 | 1.000 | 0.0000 | +0.0013 +/- 0.0018 | +0.0155 |
| sites_d10_t60 | 1000 | 60 | 0.0 | 0.143 | 0.0000 | +0.0019 +/- 0.0013 | +0.0048 |
| sites_d10_t180 | 1000 | 180 | 0.0 | 0.053 | 0.0000 | +0.0020 +/- 0.0013 | +0.0035 |
| sites_d15_t0 | 1500 | 0 | 7.9 | 1.794 | 0.0265 | +0.0138 +/- 0.0077 | +0.0555 |
| sites_d15_t60 | 1500 | 60 | 7.9 | 0.256 | 0.0265 | +0.0145 +/- 0.0073 | +0.0286 |
| sites_d15_t180 | 1500 | 180 | 7.9 | 0.094 | 0.0265 | +0.0096 +/- 0.0050 | +0.0116 |
| sites_d20_t0 | 2000 | 0 | 41.6 | 5.161 | 0.1387 | +0.0359 +/- 0.0123 | +0.0915 |
| sites_d20_t60 | 2000 | 60 | 41.6 | 0.737 | 0.1387 | +0.0318 +/- 0.0089 | +0.0710 |
| sites_d20_t180 | 2000 | 180 | 41.6 | 0.272 | 0.1387 | +0.0261 +/- 0.0081 | +0.0291 |

With B6dep in the bar, the announced room no longer passes 0.02 at 1.5 km (it did with B6fc_a as the best
announced pilot: 0.038 / 0.029 / 0.012); only the 2 km cells keep room (0.026-0.036).

## 4. Model (fixed) and how it was chosen

Candidates, all monotone (non-decreasing) in A and M, fitted on the 9 cells (`anticip_exp.fit`):
- `ratio`: h = k M A / (1 + A) (1 parameter; LOO RMSE 0.0153, fit R^2 0.522);
- `power`: h = a M^p (A / (1 + A))^q, p in [0.05, 2], q in [0, 2] on a 0.01 grid, a by least squares
  (3 parameters; LOO RMSE 0.0023, fit R^2 0.986);
- `loglin`: log h = a + b log A + c M (OLS on log max(h, 0.001)) (LOO RMSE 0.0084, fit R^2 0.812).
Selection rule: the lowest leave-one-out RMSE on the 9 fit cells. **Disclosure:** my first candidate set was
{ratio, loglin}; loglin won it, but its exp(16.4 M) term predicted h = 0.31 for `sites_v8_d20_t0`, whose M (0.26)
is about twice the fit range (<= 0.139). Seeing that (on fit data and the new cells' A, M only, no new-cell run), I
added `power` and made loglin non-selectable. The selectable set is therefore {ratio, power}; the rule picks
**power: h = 0.09542 x M^0.48 x (A / (1 + A))^0.20**. The other candidates' predictions are listed for information.

Reading: the room grows roughly with the square root of the dead-transit share M; the ramp (through A) matters
only weakly once B6dep (which already times its departure) is in the bar; no transit gap (M = 0) means no room.

## 5. Predictions for the 8 new cells (frozen)

Seeds 2000-2011 (12 per cell; disjoint from design 0-19, val 100-119, test 120-139, phase 4 1000-1019, RL 10000+).
The owner reduced 20 -> 12 seeds per cell on 2026-10-23 for speed, before any new-cell run. Pilots: dp, B6, B6fc_u,
B6fc_a (both screen_top 100, as in phase 4), B6dep (announced); all announced pilots see the same announcement.
Battery (engineering choice so that every pilot lasts; h is energy-free by design): 16 Wh, 24 Wh at 25 m/s, 40 Wh
for 600 s. 600 s cells: event start t0 uniform in [120, 300] s (D-52's [60, 150] x 2).

| new cell | changed vs sites_base | rho m | T_tr s | A | M | PREDICTED h | call |
|---|---|---|---|---|---|---|---|
| sites_v8_d15_t60 | v_max 8 m/s; D 1.5 km, tau 60 | 690 | 14.9 | 0.356 | 0.0496 | 0.0173 | no room |
| sites_v25_d15_t60 | v_max 25 m/s; D 1.5 km, tau 60 | 690 | 4.8 | 0.211 | 0.0159 | 0.0092 | no room |
| sites_v8_d20_t0 | v_max 8 m/s; D 2 km, tau 0 | 688 | 78.0 | 8.802 | 0.2601 | 0.0489 | room |
| sites_v25_d20_t0 | v_max 25 m/s; D 2 km, tau 0 | 688 | 25.0 | 3.497 | 0.0832 | 0.0275 | room |
| sites_T600_d20_t0 | T 600 s; D 2 km, tau 0 | 688 | 41.6 | 5.161 | 0.0694 | 0.0256 | room |
| sites_T600_d15_t60 | T 600 s; D 1.5 km, tau 60 | 690 | 7.9 | 0.256 | 0.0132 | 0.0087 | no room |
| sites_d175_t30 | D 1.75 km, tau 30 s | 703 | 22.9 | 0.822 | 0.0763 | 0.0237 | room |
| sites_d125_t120 | D 1.25 km, tau 120 s | 646 | 0.0 | 0.077 | 0.0000 | 0.0000 | no room |

(Machine-readable: `anticipation/fit.json`, `anticipation/fit.md`.)

## 6. Pass criteria (fixed)

1. R^2 = 1 - sum (h_meas - h_pred)^2 / sum (h_meas - mean h_meas)^2 over the 8 new cells >= 0.7.
2. Correct room / no-room call (h >= 0.02 vs < 0.02, predicted vs measured, cell means) in >= 80% of the 8 cells,
   i.e. at least 7 of 8.
The rule is CONFIRMED only if both hold. If it fails, the report says which variable the residuals point to (v_max
cells, 600 s cells or off-grid D/tau), as a result in itself. Measured h is reported with its 95% CI; a correct call
on a cell whose CI includes 0.02 is still counted as given (no re-scoring).

## 7. Not part of the test (reported alongside)

Unannounced h; survival; per-pilot means; the gap decomposition on the G5 cells (val seeds 100-119):
dp -> best simple pilot -> B3 (full information, the goto agent's control set) -> B3obsUN (same search, the agent's
information) -> best G5 round-1 agent.

Reproduce: `python anticip_exp.py footprint`, `oldcells --cells ... --shard k/4`, `merge old`,
`fit --confirm <phase-4 file>`, `newcells --cells ... --shard k/4`, `merge new`, `evaluate`.
