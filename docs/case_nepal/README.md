# Case study: a scenario based on the September 2024 Kathmandu (Bagmati river) floods

Draft for the project book (the lead moves it into `docs/book/`). Status: built and run on 20 crowd draws, no
training. Everything here is a **simulation-based planning** exercise: the buildings are real (OpenStreetMap), the
people are **reconstructed** from the map with engineering assumptions. It is *a scenario based on* the floods, not
real data, and not a digital twin (no state sync, no trace replay).

Map data (c) OpenStreetMap contributors, available under the Open Database Licence (ODbL 1.0,
openstreetmap.org/copyright). Every figure and the dashboard pages carry this credit.

## 1. In plain words

We took a real 2 x 2 km piece of Kathmandu along the Bagmati river (Teku and Kuleshwor, with Balkhu at the west edge
and Thapathali at the east edge), downloaded every building footprint from OpenStreetMap, gave each building a height,
and let the same drone pilots as in the synthetic scenarios serve a flood crowd there. The new physics piece is the
**line of sight**: instead of "a link that crosses a collapsed-building rectangle loses 15 dB", the simulator now draws
the straight line from each person's phone to the drone in 3-D and checks whether it passes **below a roof** anywhere.
A person on a roof sees the drone over the neighbours; a person in a narrow lane between four-storey houses usually
does not.

Headline (section 7): on the real map the pilots rank exactly as on the synthetic `hard` map (B6 0.781 > B7 0.774 > B3 0.741 > B2 0.713 > B0 0.674 with adaptive NOMA), and adaptive NOMA beats equally optimised OMA by +0.127 coverage for B6, about twice its gain on `hard` (+0.064).

## 2. The area

| item | value |
|---|---|
| centre | 27.6900 N, 85.3070 E |
| bounding box (S, W, N, E) | 27.681007, 85.296844, 27.698993, 85.317156 (2.000 x 2.000 km, built from the centre in the local-metre formulas below) |
| localities | Teku (Bagmati / Bishnumati confluence), Kuleshwor, Balkhu (west edge), Thapathali (east edge), Sanepa / Kupondole across the river |
| why here | riverside settlements reported flooded in late September 2024: Setopati, 27 Sep 2024: "Floodwaters have entered Balkhu and other settlements near the banks of Bagmati River" and "The vegetable and fruit market in Balkhu has also been inundated" (https://en.setopati.com/social/163750); Nepalnews: on 28 Sep 2024 "severe flooding destroyed UN Park" on the Thapathali bank (https://english.nepalnews.com/s/capital/one-shower-a-flooded-city-inside-kathmandus-inundation-crisis/). We did NOT verify Teku or Kuleshwor themselves as flooded in 2024 from a primary source (Kathmandu Post shows a waterlogged street in Kuleshwar on 27 Sep 2024, a photo caption only). |
| flood extent | NOT taken from a flood map. A band of fixed width around the river centreline (section 4) |
| download | one Overpass API request on 2026-10-23 (OSM base 2026-10-23T15:50Z), raw file `uav_dataset/data/osm/kathmandu_bagmati.json` (7.6 MB, not committed); processed file `uav_dataset/places/kathmandu_bagmati.json` (1.46 MB, committed; tests, CI and the dashboard need no internet) |

Local metres (`osm_place.py`): equirectangular around the box centre, `x = (lon - lon_c) cos(lat_c) pi/180 R + L/2`,
`y = (lat - lat_c) pi/180 R + L/2`, R = 6 371 008.8 m (mean Earth radius). Over 2 km the scale factor cos(lat) changes
by about 1e-4, so the error is far below a metre (below the 2 m height raster). The box is built from its centre with
the same formulas, so (0, 0)..(2000, 2000) is exactly the simulator's map.

Data counts (processed file): **12 061 building footprints**, of which **672 carry a height** (664 with
`building:levels`, 8 with `height`; 94% have no height tag); 8 waterway lines (Bagmati River, Bishnumati, Balkhu River,
Manamati, Tukucha Khola); **147 shelter candidates** (50 schools, 39 places of worship, 23 colleges, 17 hospitals, 15
clinics, 2 parks, 1 community centre; no `emergency=assembly_point` is mapped in the box). Tagged heights: median 9 m,
95th percentile 18 m, max 30 m after cleaning; one building tagged 25 storeys (75 m) on Bagmati Marg is treated as a
tagging error (rule below).

## 3. The radio model on a real city (height-aware line of sight)

**Height grid.** Footprints are rasterised to 2 m cells (1000 x 1000; a cell takes the height of the tallest footprint
that contains its centre; 28.8% of the cells are built). Heights: `height` tag, else `building:levels` x 3 m, else
drawn (seeded, once for the city) from the distribution of the tagged buildings of the same box. Tags above 45 m (15
storeys) are treated as tagging errors and redrawn.

**Ray test.** A phone at height z_u (1.5 m above the ground, or above the roof it stands on) sees the drone at
(X, Y, H) if no cell along the straight 3-D ray is taller than the ray at that point. The ray is sampled every 2 m
horizontally from the phone toward the drone, and only as far as it is still below the tallest roof of the map (30 m;
beyond that nothing can block it). Vectorised in blocks of 64 samples; blocked rays drop out early. A brute-force
reference test agrees exactly.

**Path loss (one consistent choice).** `los_model: geometric` (default): the ray test REPLACES Al-Hourani's
probabilistic P_LoS. Clear ray -> FSPL + eta_LoS (1 dB), blocked ray -> FSPL + eta_NLoS (20 dB), both from the same
Al-Hourani urban parameters the project already uses. Why replace instead of add: Al-Hourani's P_LoS(theta) is a
statistical stand-in for buildings whose positions are unknown (fitted to ITU-R statistical cities). Here the buildings
are known; keeping P_LoS AND adding a loss for the same buildings would count them twice. So "a blocked link gets
extra loss" stays, with the size of the extra loss (19 dB over a clear link) taken from the paper's NLoS term instead of
the 15 dB engineering assumption of the rectangles. The rectangle rule (Al-Hourani mean loss + 15 dB on a blocked ray)
is kept as the sensitivity variant `los_model: statistical`. The phone height also enters distance and elevation.

**Speed** (measured on this laptop while another simulation ran in parallel; `python nepal_case.py timing`): see
section 7. The cost is paid once per scenario: the ray test is cached per drone position over the scenario's whole user
pool (people never move in this scenario, they only switch from a roof to a shelter), so B6's 980 candidates every 10 s
are tested once, and all pilots and both access schemes of a scenario share the cache.

What it does NOT model: diffraction over roof edges (a ray is either clear or blocked), trees, terrain (the valley floor
is taken as flat; no elevation model was downloaded), indoor users (nobody is placed inside a building), the river
surface, reflections.

## 4. The flood and the people (all ENGINEERING ASSUMPTIONS)

| assumption | value | range / sensitivity | why |
|---|---|---|---|
| flooded area | within 200 m of the Bagmati centreline | 150-300 m (run: 150, 300) | no satellite flood map was used (UNOSAT published a preliminary one: about 8 km2 apparently flooded in a ~450 km2 analysed area, 30 Sep 2024, https://geo.btaa.org/catalog/f922be53-fdd6-483d-a4ee-a9612997d4f9; not downloaded, not validated in the field) |
| people per scenario | 300 / 600 / 1000 (drawn) | 300 / 600 / 1000 | |
| stranded on roofs | 30-50% of the people, on buildings inside the band (chosen by footprint area), at roof height + 1.5 m | | assumption: people inside the band have gone up to the roof (we did not find a source that counts this) |
| at shelters | 20-40%, on open ground within 60 m (Gaussian, std 30 m) of 1-4 shelter candidates outside the band but at most 600 m beyond its edge | | schools, temples, hospitals, colleges, parks |
| on dry ground | the rest minus scatter, in 2-4 gatherings (std 40-100 m) centred in the 300 m ring just outside the band, on open ground | | |
| scattered | 5-10%, open ground anywhere outside the band | | as the synthetic scenarios |
| rescue class share | 40% of the stranded, 10% (base mix) of everyone else | 20-60% | stranded people need rescue most |
| evacuation event | from t0 (60-150 s) a share (30-60%) of the stranded is taken to the nearest used shelter; mover k switches at t0 + 120 s x k / n_move (the boat trip itself is not simulated: the competing-sites mechanism of D-52) | event on/off | |
| user height | 1.5 m above ground or roof | | handset |
| missing building heights | from the tagged buildings of the box (seeded) | uniform 6-12 m if fewer than 100 tagged | 94% untagged |
| implausible tags | > 45 m treated as missing | | one 25-storey tag |
| storey height | 3 m | 2.8-3.5 m | |

Everyone stays where they are (people waiting for rescue), so the only crowd dynamics is the evacuation. Profile
`place_kathmandu_bagmati`: 2 x 2 km, 20 dBm, 16 Wh, B6 grid 14 x 14 x 5 altitudes, and the owner's G5 settings (D-48):
noma_opt, imperfect SIC 0.05, rescue first, a_max 4 m/s^2.

## 5. What was run

Pilots B0, B2, B3, B6, B7, B8, B6fc on seeds 0-19, each with noma_opt and oma_opt (equal bandwidth and power), on the
place profile and on the synthetic `hard` profile with the SAME G5 settings (`hard_g5`), so the comparison isolates the
geometry and the crowd. Sensitivity on the place profile: `los_model: statistical` (B0, B2, B6), flood band 150 m and
300 m (B0, B6). Commands: `python nepal_case.py run --shard 0/2` (+ `1/2`), `sens`, `report`, `figures`, `timing`.

## 6. Figures (in `docs/case_nepal/figures/`, copies in `uav_dataset/results/nepal/`)

- `nepal_map.png`: buildings shaded by height, the Bagmati, the assumed flood band, shelter candidates and the people
  of seed 0 by group.
- `nepal_paths.png`: flight paths and final spot of B0, B2, B3, B6, B7, B8 (noma_opt, seed 0).
- `nepal_coverage.png`: the share of people served for every drone position, at 100 m and at B6's altitude (300 m)
  before the evacuation, and at 300 m after it (seed 0).
- `nepal_bars.png`: NOMA vs OMA per pilot, place vs hard_g5.

## 7. Results

All tables verbatim in `results.md` (same folder; generated by `python nepal_case.py report`). Seeds 0-19 (crowd sizes
300 x 10, 600 x 5, 1000 x 5 on the place profile). Coverage = mean share of the people counted at each second who are
served, over 300 s (dead drone = 0). Mean +/- 95% CI over the 20 scenarios; paired differences; * = CI excludes 0.

### 7.1 Main table, Kathmandu place profile (G5 settings)

| pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | rescue served NOMA | rescue served OMA | total speed NOMA (Mbit/s) | total speed OMA | battery left NOMA (Wh) | flown NOMA (m) |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 0.674 +/- 0.032 | 0.479 +/- 0.033 | +0.195 +/- 0.012* | 0.761 +/- 0.040 | 0.761 +/- 0.040 | 33.0 | 25.0 | 1.52 | 0 |
| B2 | 0.713 +/- 0.033 | 0.521 +/- 0.035 | +0.191 +/- 0.009* | 0.801 +/- 0.030 | 0.801 +/- 0.030 | 38.3 | 27.2 | 3.12 | 2596 |
| B3 | 0.741 +/- 0.032 | 0.577 +/- 0.035 | +0.164 +/- 0.010* | 0.823 +/- 0.029 | 0.816 +/- 0.030 | 39.4 | 29.7 | 2.21 | 1097 |
| B6 | 0.781 +/- 0.025 | 0.654 +/- 0.030 | +0.127 +/- 0.008* | 0.892 +/- 0.024 | 0.888 +/- 0.026 | 41.1 | 32.6 | 1.41 | 1294 |
| B7 | 0.774 +/- 0.025 | 0.626 +/- 0.029 | +0.148 +/- 0.007* | 0.890 +/- 0.024 | 0.889 +/- 0.026 | 40.3 | 31.7 | 3.64 | 3176 |
| B8 | 0.781 +/- 0.025 | 0.654 +/- 0.030 | +0.127 +/- 0.008* | 0.892 +/- 0.024 | 0.888 +/- 0.026 | 41.1 | 32.6 | 1.41 | 1294 |
| B6fc | 0.781 +/- 0.025 | 0.654 +/- 0.030 | +0.127 +/- 0.008* | 0.892 +/- 0.024 | 0.888 +/- 0.026 | 41.1 | 32.6 | 1.41 | 1294 |

Paired difference to B6 (noma_opt / oma_opt): B0 -0.107* / -0.175*, B2 -0.069* / -0.133*, B3 -0.041* / -0.077*,
B7 -0.008* / -0.028*, B8 and B6fc +0.000 / +0.000 (identical episodes).

### 7.2 Synthetic `hard` with the same G5 settings (same seeds 0-19)

| pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | rescue served NOMA | rescue served OMA | total speed NOMA (Mbit/s) | total speed OMA | battery left NOMA (Wh) | flown NOMA (m) |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 0.560 +/- 0.093 | 0.369 +/- 0.117 | +0.191 +/- 0.057* | 0.595 +/- 0.130 | 0.595 +/- 0.130 | 23.9 | 14.7 | 1.52 | 0 |
| B2 | 0.726 +/- 0.054 | 0.568 +/- 0.079 | +0.159 +/- 0.037* | 0.781 +/- 0.061 | 0.781 +/- 0.061 | 49.7 | 30.1 | 2.95 | 2259 |
| B3 | 0.769 +/- 0.054 | 0.633 +/- 0.081 | +0.135 +/- 0.038* | 0.852 +/- 0.060 | 0.817 +/- 0.062 | 48.4 | 34.8 | 2.49 | 1548 |
| B6 | 0.837 +/- 0.044 | 0.773 +/- 0.063 | +0.064 +/- 0.021* | 0.938 +/- 0.037 | 0.923 +/- 0.053 | 53.4 | 44.6 | 1.52 | 1333 |
| B7 | 0.833 +/- 0.045 | 0.761 +/- 0.064 | +0.072 +/- 0.021* | 0.936 +/- 0.038 | 0.921 +/- 0.053 | 52.4 | 43.1 | 3.73 | 3162 |
| B8 | 0.837 +/- 0.044 | 0.773 +/- 0.063 | +0.064 +/- 0.021* | 0.938 +/- 0.037 | 0.923 +/- 0.053 | 53.4 | 44.6 | 1.52 | 1333 |
| B6fc | 0.836 +/- 0.047 | 0.777 +/- 0.063 | +0.059 +/- 0.018* | 0.935 +/- 0.042 | 0.925 +/- 0.052 | 53.4 | 44.8 | 1.32 | 1089 |

Paired difference to B6 (noma_opt / oma_opt): B0 -0.278* / -0.404*, B2 -0.111* / -0.206*, B3 -0.069* / -0.140*,
B7 -0.005* / -0.012*, B8 +0.000 / +0.000, B6fc -0.001 / +0.004*.

### 7.3 NOMA gain: real geometry vs synthetic

| pilot | NOMA - OMA, place | NOMA - OMA, hard_g5 | difference of the gains (Welch-style CI) |
|---|---|---|---|
| B0 | +0.195 +/- 0.012* | +0.191 +/- 0.057* | +0.003 +/- 0.058 |
| B2 | +0.191 +/- 0.009* | +0.159 +/- 0.037* | +0.032 +/- 0.038 |
| B3 | +0.164 +/- 0.010* | +0.135 +/- 0.038* | +0.029 +/- 0.039 |
| B6 | +0.127 +/- 0.008* | +0.064 +/- 0.021* | +0.063 +/- 0.022* |
| B7 | +0.148 +/- 0.007* | +0.072 +/- 0.021* | +0.076 +/- 0.022* |
| B8 | +0.127 +/- 0.008* | +0.064 +/- 0.021* | +0.063 +/- 0.022* |
| B6fc | +0.127 +/- 0.008* | +0.059 +/- 0.018* | +0.068 +/- 0.019* |

### 7.4 Who is served (place profile)

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

### 7.5 Sensitivity (place profile, 20 seeds each)

| variant | pilot | coverage NOMA | coverage OMA | NOMA - OMA (paired) | base coverage NOMA |
|---|---|---|---|---|---|
| los_statistical | B0 | 0.375 +/- 0.036 | 0.246 +/- 0.032 | +0.129 +/- 0.012* | 0.674 +/- 0.032 |
| los_statistical | B2 | 0.459 +/- 0.039 | 0.330 +/- 0.043 | +0.129 +/- 0.012* | 0.713 +/- 0.033 |
| los_statistical | B6 | 0.636 +/- 0.030 | 0.495 +/- 0.040 | +0.141 +/- 0.017* | 0.781 +/- 0.025 |
| band150 | B0 | 0.668 +/- 0.035 | 0.469 +/- 0.036 | +0.199 +/- 0.014* | 0.674 +/- 0.032 |
| band150 | B6 | 0.779 +/- 0.031 | 0.641 +/- 0.037 | +0.138 +/- 0.011* | 0.781 +/- 0.025 |
| band300 | B0 | 0.645 +/- 0.039 | 0.444 +/- 0.030 | +0.201 +/- 0.017* | 0.674 +/- 0.032 |
| band300 | B6 | 0.763 +/- 0.034 | 0.636 +/- 0.037 | +0.127 +/- 0.006* | 0.781 +/- 0.025 |

(The band variants change the crowd, so their numbers are not paired with the base run; the LoS variant keeps the
crowd and changes only the path-loss rule.)

### 7.6 Speed of the height-aware line of sight

Scene build (load the committed file, rasterise 12 061 footprints at 2 m, river-distance field): 1.6-2.8 s once per
process. Ray test of B6's whole candidate set (981 drone positions x the scenario's user pool, incl. the evacuees'
twins), measured with a second simulation running in parallel:

| seed | users in the pool | candidates | links | seconds | ms for one drone position (all users) |
|---|---|---|---|---|---|
| 0 | 350 | 981 | 343 350 | 1.69 | 1.15 |
| 1 | 384 | 981 | 376 704 | 2.06 | 1.11 |
| 2 | 677 | 981 | 664 137 | 3.60 | 2.48 |

About 5 microseconds per link, so a 1000-person scenario costs about 6-7 s once. Whole episodes (mean): B6 20 s
(place) vs 31 s (hard_g5), B6fc 64 s vs 144 s: the real city is not slower than the synthetic one, because the
cached ray test replaces the per-decision rectangle test and the place crowd does not move.

### 7.7 What the numbers say

In plain words:

- **The ranking of the pilots does not change** on the real map: B6 = B8 = B6fc > B7 > B3 > B2 > B0, with NOMA and with
  OMA, exactly as on the synthetic `hard` map. Every gap to B6 is significant except B8 / B6fc (identical here).
- **Moving the drone matters less here** (B6 - B0 = +0.107 vs +0.278 on `hard`): the flood crowd sits along a river
  that runs close to the map centre, and nobody walks away, so a parked drone at the centre already sees most people.
- **NOMA helps twice as much on the real city** for the searching pilots: B6 +0.127 vs +0.064 (difference +0.063,
  significant), B7 +0.148 vs +0.072. For the simple pilots (B0, B2, B3) the gains are similar (difference not
  significant). Our reading (a hypothesis, not tested separately): the height-aware LoS splits the users into two
  groups whose channels differ by about 19 dB (clear rays, e.g. people on roofs, vs rays blocked by the houses
  around a lane), and NOMA gains most when paired users have very different channels. On `hard` only the few users
  behind a collapsed-building rectangle are hurt.
- **Who is served:** with NOMA the stranded people on roofs are served best (0.83 with B6) and the people at shelters
  and on dry ground (lanes between buildings) less (0.68-0.77). With OMA the difference is much larger (shelters 0.60,
  dry ground 0.55, scattered 0.52 with B6) - the NOMA gain lands mostly on the ground-level people. Rescue users are
  served at 0.89 with both schemes (rescue-first admission).
- **Forecasting adds nothing here** (B6fc = B6 in 40 of 40 place episodes): the evacuation is not announced and people
  stand still, so B6fc's forecast equals the present. **Circling (B7)** costs 0.008 coverage and saves 2.2 Wh
  (3.64 vs 1.41 Wh left), i.e. +17.6% people-seconds per Wh (10 099 vs 8 590, noma_opt). B8 never circles (16 Wh is
  ample) and is B6.
- **The LoS model is the biggest assumption:** with Al-Hourani's statistical LoS kept and 15 dB added on blocked rays
  (the rectangle rule), coverage drops by 0.15-0.30 (B6 0.636 vs 0.781) - that variant counts the same buildings
  twice, which is why it is not the default. The NOMA gain stays (+0.13..+0.14). The flood-band width (150 / 300 m)
  moves B6 by less than 0.02.
- B6 flies at about 290 m (the top of the 50-300 m range) in both profiles: from high up the rays clear the roofs.

### 7.8 3D page

The dashboard's 3D flight page draws the place: all 12 061 OSM footprints extruded to the heights the radio model uses
(one merged mesh, light to dark by height; footprints simplified with a 1 m tolerance, whole metres; 514 KB of the
656 KB page data for seed 0, no cap needed), the Bagmati and the flood-band edge (dashed), people on roofs drawn at
roof height, and the credit line. The profile is selectable in the sidebar (people / crowds / buildings controls are
locked for a real place). Checked: the payload test, the JavaScript parses (`node --check`), the page is produced
(`results/nepal/flight3d_place_seed0_B6.html`, B6 flown by the simulated quadcopter: coverage 0.8145 vs 0.816 for the
point-mass game). NOT checked: the page was not opened in a browser in this run (no browser available to the agent).

## 8. Limitations (read before quoting a number)

- The crowd is invented from the map with the assumptions in section 4; survivor positions are not published. The
  flood band is a fixed-width strip, not the 2024 flood extent; the river is the OSM centreline (no bank polygons).
- 94% of the building heights are drawn from the 6% that are tagged; real heights could be systematically different.
- The ray test has no diffraction, trees, terrain or indoor users; the clear / blocked split is binary. The
  geometric LoS model replaces a statistical model fitted to whole cities; it has not been checked against a
  measurement in Kathmandu.
- Only 20 crowd draws; place and `hard_g5` use different scenarios, so the cross-profile comparison of NOMA gains is
  unpaired (Welch-style CI).
- People stand still apart from the evacuation, so this case says nothing about moving crowds (G5).
- The localities' flood status rests on news reports (Balkhu, UN Park / Thapathali); Teku and Kuleshwor were not
  verified as flooded in 2024 from a primary source.
