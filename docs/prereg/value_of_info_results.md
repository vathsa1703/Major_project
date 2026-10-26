# Value of information: results (pre-registered in `value_of_info.md`, commit 68fc052)

Run 2026-10-23. 1,440 episodes = 2 profiles x 24 pilots x 30 scenarios, all survived the 300 s. Made by
`python voi_exp.py analyse` (uav_dataset/results/voi/, not committed); the tables below are its `summary.md`, verbatim.

**Execution notes (no design change).** `sites_d20_t60_ann`: 2 Kaggle kernels (`srivathsajr/uav-voi-sites-p0`, `-p1`,
4 workers each, 0.55 h each). `hard`: started locally (2 workers); to finish sooner (the lead allowed up to 4 kernels) it
was split into thirds: part 0 locally, parts 1 and 2 on Kaggle (`uav-voi-hard-p1`, `-p2`, 0.08 h and 0.12 h). The
interrupted local run had already done 124 episodes of parts 1-2; Kaggle re-ran them and every one is BIT-IDENTICAL
(max |difference| in coverage 0.0), so local and Kaggle results are interchangeable. Kaggle code = origin/final/integrate
+ baselines.py, config.yaml, voi_exp.py of commit de1eb2e written from base64 (SHA-256 182780355db4..., 1133f1241a34...,
8292413fdcd9..., checked in the kernel logs). CPU time of the unique episodes: hard 1.84 h, sites 4.38 h (6.2 h).

**Primary result: PASS.** B6 keeps >= 98% of its full-information coverage with f* = 0.5 of phones reporting on `hard`
(95% interval [0.1, 0.5]) and f* = 0.05 on `sites_d20_t60_ann` (95% interval [0.05, 0.2]), at GPS error 10 m AND 50 m.

**Plain reading.** On a 2 km map with 20 dBm and a 14 x 14 search grid (154 m spacing), the planner needs to know
roughly WHERE the crowds are and how big they are, not where each person stands: 50 m GPS error costs nothing measurable
(B6, f 0.2: 0.978 at 10 m vs 0.979 at 50 m; f 1: 1.000 vs 0.994). The share of phones that report matters on moving
crowds (`hard`: 5% -> 95.7%, 20% -> 97.8%, 50% -> 99.0%), much less on the competing-sites cell, where every crowd is a
dense site and even 5% of phones (about 20 reports) find them (98.3%). Report age matters where people move AWAY in an
event: on the sites cell at 20% reporting, B6 drops from 100.4% (age 0) to 98.4% (30 s) and 97.8% (60 s), B3 from
98.7% to 96.3%; on `hard` the age effect is small (97.8% -> 97.5%).
Design rule for a rescue team (within this simulator): **get position reports from about half of the attached phones,
refreshed at least every 30 s; GPS quality down to ~50 m is good enough. With only ~1 phone in 5 reporting expect ~2%
less coverage on moving crowds, and with 1 in 20 about 4% less.**

Notes for reading the tables. (1) Ratios above 1 occur (sites, B6 f 1 sigma 10: 1.007 [1.002, 1.011]): B6 is a greedy
10 s planner, not an optimal one, so a perturbed picture of the crowd can by chance lead it to slightly better spots;
it is not "better information". (2) f* uses the pre-registered "this f and every larger f" rule; on `hard` B6 at f 0.2
is 0.978, just below 0.98, which is why f* is 0.5 and not 0.2. (3) Table 3 is exploratory (2-10 scenarios per row).

## Analysis output (voi_exp.py analyse)

Scenarios per configuration: 30 (seeds 100-119 and 1000-1009), paired with the same planner on the true users. Ratio = mean coverage / mean full-information coverage; 95% CI by paired bootstrap over scenarios (10000 resamples, seed 0). diff = coverage minus full information, mean +/- 95% CI (normal approximation). Target 98%.

## Table 1. Coverage ratio per configuration

| profile | planner | f | sigma (m) | age (s) | mean reporters | coverage | full info | ratio [95% CI] | diff | reaches 98% (point / CI low) |
|---|---|---|---|---|---|---|---|---|---|---|
| hard | B6 | 0.05 | 10 | 0 | 20 | 0.737 | 0.770 | 0.957 [0.938, 0.970] | -0.033 +/- 0.013 | no / no |
| hard | B6 | 0.1 | 10 | 0 | 39 | 0.749 | 0.770 | 0.973 [0.961, 0.982] | -0.021 +/- 0.008 | no / no |
| hard | B6 | 0.2 | 10 | 0 | 79 | 0.753 | 0.770 | 0.978 [0.968, 0.985] | -0.017 +/- 0.007 | no / no |
| hard | B6 | 0.5 | 10 | 0 | 197 | 0.763 | 0.770 | 0.990 [0.986, 0.994] | -0.008 +/- 0.003 | yes / yes |
| hard | B6 | 1 | 10 | 0 | 393 | 0.770 | 0.770 | 1.000 [0.999, 1.001] | -0.000 +/- 0.001 | yes / yes |
| hard | B6 | 0.05 | 50 | 0 | 20 | 0.738 | 0.770 | 0.958 [0.941, 0.972] | -0.032 +/- 0.012 | no / no |
| hard | B6 | 0.1 | 50 | 0 | 39 | 0.749 | 0.770 | 0.972 [0.961, 0.981] | -0.021 +/- 0.008 | no / no |
| hard | B6 | 0.2 | 50 | 0 | 79 | 0.754 | 0.770 | 0.979 [0.971, 0.986] | -0.016 +/- 0.006 | no / no |
| hard | B6 | 0.5 | 50 | 0 | 197 | 0.761 | 0.770 | 0.988 [0.984, 0.992] | -0.009 +/- 0.003 | yes / yes |
| hard | B6 | 1 | 50 | 0 | 393 | 0.766 | 0.770 | 0.994 [0.991, 0.997] | -0.004 +/- 0.002 | yes / yes |
| hard | B6 | 0.2 | 0 | 0 | 79 | 0.748 | 0.770 | 0.972 [0.960, 0.982] | -0.022 +/- 0.009 | no / no |
| hard | B6 | 0.2 | 10 | 30 | 79 | 0.752 | 0.770 | 0.976 [0.967, 0.983] | -0.019 +/- 0.006 | no / no |
| hard | B6 | 0.2 | 10 | 60 | 79 | 0.751 | 0.770 | 0.975 [0.967, 0.982] | -0.019 +/- 0.006 | no / no |
| hard | B3 | 0.05 | 10 | 0 | 20 | 0.677 | 0.705 | 0.960 [0.932, 0.980] | -0.028 +/- 0.019 | no / no |
| hard | B3 | 0.1 | 10 | 0 | 39 | 0.695 | 0.705 | 0.986 [0.979, 0.993] | -0.010 +/- 0.005 | yes / no |
| hard | B3 | 0.2 | 10 | 0 | 79 | 0.695 | 0.705 | 0.985 [0.976, 0.993] | -0.011 +/- 0.007 | yes / no |
| hard | B3 | 0.5 | 10 | 0 | 197 | 0.701 | 0.705 | 0.994 [0.991, 0.997] | -0.004 +/- 0.002 | yes / yes |
| hard | B3 | 1 | 10 | 0 | 393 | 0.705 | 0.705 | 0.999 [0.998, 1.000] | -0.001 +/- 0.001 | yes / yes |
| hard | B3 | 0.2 | 50 | 0 | 79 | 0.694 | 0.705 | 0.984 [0.973, 0.992] | -0.012 +/- 0.007 | yes / no |
| hard | B3 | 0.2 | 0 | 0 | 79 | 0.693 | 0.705 | 0.983 [0.974, 0.992] | -0.012 +/- 0.007 | yes / no |
| hard | B3 | 0.2 | 10 | 30 | 79 | 0.692 | 0.705 | 0.982 [0.972, 0.991] | -0.013 +/- 0.007 | yes / no |
| hard | B3 | 0.2 | 10 | 60 | 79 | 0.692 | 0.705 | 0.982 [0.975, 0.988] | -0.013 +/- 0.005 | yes / no |
| sites_d20_t60_ann | B6 | 0.05 | 10 | 0 | 20 | 0.705 | 0.717 | 0.983 [0.963, 1.004] | -0.012 +/- 0.015 | yes / no |
| sites_d20_t60_ann | B6 | 0.1 | 10 | 0 | 39 | 0.707 | 0.717 | 0.986 [0.965, 1.006] | -0.010 +/- 0.015 | yes / no |
| sites_d20_t60_ann | B6 | 0.2 | 10 | 0 | 79 | 0.720 | 0.717 | 1.004 [0.992, 1.018] | +0.003 +/- 0.010 | yes / yes |
| sites_d20_t60_ann | B6 | 0.5 | 10 | 0 | 197 | 0.716 | 0.717 | 0.998 [0.987, 1.009] | -0.002 +/- 0.008 | yes / yes |
| sites_d20_t60_ann | B6 | 1 | 10 | 0 | 393 | 0.722 | 0.717 | 1.007 [1.002, 1.011] | +0.005 +/- 0.003 | yes / yes |
| sites_d20_t60_ann | B6 | 0.05 | 50 | 0 | 20 | 0.708 | 0.717 | 0.987 [0.964, 1.008] | -0.009 +/- 0.016 | yes / no |
| sites_d20_t60_ann | B6 | 0.1 | 50 | 0 | 39 | 0.710 | 0.717 | 0.990 [0.970, 1.008] | -0.007 +/- 0.014 | yes / no |
| sites_d20_t60_ann | B6 | 0.2 | 50 | 0 | 79 | 0.719 | 0.717 | 1.003 [0.990, 1.017] | +0.002 +/- 0.010 | yes / yes |
| sites_d20_t60_ann | B6 | 0.5 | 50 | 0 | 197 | 0.718 | 0.717 | 1.001 [0.990, 1.012] | +0.000 +/- 0.008 | yes / yes |
| sites_d20_t60_ann | B6 | 1 | 50 | 0 | 393 | 0.723 | 0.717 | 1.007 [1.000, 1.015] | +0.005 +/- 0.005 | yes / yes |
| sites_d20_t60_ann | B6 | 0.2 | 0 | 0 | 79 | 0.713 | 0.717 | 0.994 [0.982, 1.007] | -0.004 +/- 0.009 | yes / yes |
| sites_d20_t60_ann | B6 | 0.2 | 10 | 30 | 79 | 0.706 | 0.717 | 0.984 [0.973, 0.995] | -0.012 +/- 0.008 | yes / no |
| sites_d20_t60_ann | B6 | 0.2 | 10 | 60 | 79 | 0.702 | 0.717 | 0.978 [0.967, 0.989] | -0.015 +/- 0.009 | no / no |
| sites_d20_t60_ann | B3 | 0.05 | 10 | 0 | 20 | 0.673 | 0.692 | 0.973 [0.951, 0.992] | -0.019 +/- 0.015 | no / no |
| sites_d20_t60_ann | B3 | 0.1 | 10 | 0 | 39 | 0.673 | 0.692 | 0.972 [0.954, 0.987] | -0.020 +/- 0.012 | no / no |
| sites_d20_t60_ann | B3 | 0.2 | 10 | 0 | 79 | 0.683 | 0.692 | 0.987 [0.972, 1.000] | -0.009 +/- 0.010 | yes / no |
| sites_d20_t60_ann | B3 | 0.5 | 10 | 0 | 197 | 0.685 | 0.692 | 0.989 [0.980, 0.998] | -0.007 +/- 0.006 | yes / yes |
| sites_d20_t60_ann | B3 | 1 | 10 | 0 | 393 | 0.688 | 0.692 | 0.994 [0.988, 0.999] | -0.004 +/- 0.004 | yes / yes |
| sites_d20_t60_ann | B3 | 0.2 | 50 | 0 | 79 | 0.683 | 0.692 | 0.987 [0.978, 0.996] | -0.009 +/- 0.006 | yes / no |
| sites_d20_t60_ann | B3 | 0.2 | 0 | 0 | 79 | 0.683 | 0.692 | 0.987 [0.974, 0.999] | -0.009 +/- 0.009 | yes / no |
| sites_d20_t60_ann | B3 | 0.2 | 10 | 30 | 79 | 0.674 | 0.692 | 0.973 [0.961, 0.985] | -0.018 +/- 0.009 | no / no |
| sites_d20_t60_ann | B3 | 0.2 | 10 | 60 | 79 | 0.666 | 0.692 | 0.963 [0.950, 0.975] | -0.026 +/- 0.009 | no / no |

## Table 2. f* = smallest report share reaching 98% (age 0)

f* = smallest grid f whose ratio and every larger f's ratio are >= 0.98 (point estimates). 95% interval = percentile interval of f* recomputed in every bootstrap resample. Conservative f* = the same rule on the lower CI bounds.

| profile | planner | sigma (m) | f* | 95% interval | share of resamples not reaching 98% | conservative f* | full-info coverage |
|---|---|---|---|---|---|---|---|
| hard | B6 | 10 | 0.5 | [0.1, 0.5] | 0.000 | 0.5 | 0.770 |
| hard | B6 | 50 | 0.5 | [0.1, 0.5] | 0.000 | 0.5 | 0.770 |
| hard | B3 | 10 | 0.1 | [0.05, 0.5] | 0.000 | 0.5 | 0.705 |
| sites_d20_t60_ann | B6 | 10 | 0.05 | [0.05, 0.2] | 0.000 | 0.2 | 0.717 |
| sites_d20_t60_ann | B6 | 50 | 0.05 | [0.05, 0.2] | 0.000 | 0.2 | 0.717 |
| sites_d20_t60_ann | B3 | 10 | 0.2 | [0.05, 0.5] | 0.000 | 0.5 | 0.692 |

- B6, hard, sigma 10 m: f* 0.5, 95% interval [0.1, 0.5] -> identifiable and < 1

- B6, hard, sigma 50 m: f* 0.5, 95% interval [0.1, 0.5] -> identifiable and < 1

- B6, sites_d20_t60_ann, sigma 10 m: f* 0.05, 95% interval [0.05, 0.2] -> identifiable and < 1

- B6, sites_d20_t60_ann, sigma 50 m: f* 0.05, 95% interval [0.05, 0.2] -> identifiable and < 1

**Pre-registered criterion** (B6, both profiles, sigma 10 and 50 m: f* identifiable and its 95% interval entirely below 1): PASS

## Table 3 (exploratory, not pre-registered). B6 ratio by crowd size (sigma 10 m, age 0)

Few scenarios per row: no CIs, read as a trend only. Reporters = f x crowd size.

| profile | users | scenarios | f=0.05 | f=0.1 | f=0.2 | f=0.5 | f=1 |
|---|---|---|---|---|---|---|---|
| hard | 100 | 8 | 0.938 | 0.973 | 0.972 | 0.990 | 1.000 |
| hard | 300 | 10 | 0.967 | 0.966 | 0.982 | 0.988 | 1.000 |
| hard | 600 | 10 | 0.961 | 0.979 | 0.978 | 0.991 | 1.000 |
| hard | 1000 | 2 | 0.970 | 0.975 | 0.980 | 0.997 | 0.999 |
| sites_d20_t60_ann | 100 | 8 | 0.939 | 0.928 | 0.982 | 0.984 | 1.001 |
| sites_d20_t60_ann | 300 | 10 | 0.985 | 1.009 | 1.002 | 1.006 | 1.018 |
| sites_d20_t60_ann | 600 | 10 | 1.024 | 1.024 | 1.034 | 1.004 | 1.003 |
| sites_d20_t60_ann | 1000 | 2 | 1.015 | 0.982 | 0.990 | 0.996 | 0.992 |
