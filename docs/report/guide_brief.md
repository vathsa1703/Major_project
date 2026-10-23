# UAV-NOMA Disaster Network Planning Simulator: brief for the guide

*23 October 2026. Draft for feedback. Every number comes from the project book (`docs/book/`); the full report draft is
`docs/report/report.md` / `UAV-NOMA-Report.pdf`.*

## What the project is
After a disaster the phone towers are down; a drone carrying a small base station can act as a temporary tower. We built a
**simulation-based planning tool** that tests, in software, where such a drone should fly, how high, and how it should share its
radio with **NOMA** (two people on one frequency slice), so that as many survivors as possible stay connected before the battery
runs out. We compare simple programmed pilots with an AI pilot that learns by itself, fairly and on the same scenarios.

## What is done and what it shows
All comparisons use the same seeded scenarios for every pilot, with paired 95% confidence intervals; pass marks were written
down before results were seen.

| Question | Result | Verdict |
|---|---|---|
| **H1** Does a moving drone beat a parked one? | Hard scenarios (2 x 2 km, low power, buildings, moving crowds): best pilot 0.741 of people served vs 0.428 parked. In small, easy maps the gap is tiny (0.914 vs 0.882). | Supported where the area is large and power scarce |
| **H3** Does NOMA beat OMA? | With both schemes optimised the same way, adaptive NOMA serves **3-5 more people per 100** for every pilot (low power, grid-search pilot: 0.983 vs 0.945; unserved rescue users 0.4% vs 3.0%). It still wins with imperfect interference cancellation. Price: serving the most people lowers total data speed for both schemes. | Supported |
| **Energy** Hover or circle? | Circling the best spot at about 10 m/s serves **25.6% more people-seconds per battery** than hovering; with a 12-13 Wh battery the circling drone finishes the 5-minute mission and the hovering one does not. | Robust to the uncertain energy parameters (+21% to +31%) |
| **Where can an AI win at all?** | A pilot that knows the future gains only +0.002 on walking crowds: no room. When demand jumps between sites far apart, room exists; on 20 fresh scenarios per design it is **confirmed in 5 of 9 designs**, clearly only at 2 km (+0.04 to +0.09). | A method to measure the prize before training |
| **H2** AI on still crowds (Gate G4) | Best AI 0.576 against a pre-set pass mark of 0.580 (simple k-means pilot 0.610). | **Not met** |
| **H2** AI on 2 km competing sites (G5, round 1) | All 8 trained agents below the bar: best **0.680 vs 0.756 / 0.753**, and below plain grid search too. For the same agents, NOMA beats OMA by 0.08-0.13. | **Not met** |
| **Realistic drone** | A simulated quadcopter with autopilot, motor lag, tilt limit and wind flies the same plans: coverage changes by only **-0.003 to -0.012**; wind by at most 0.002. Its battery numbers are not trustworthy yet. | Coverage conclusions carry over |

Figure 1: [NOMA vs OMA when both are optimised the same way (hard scenarios)](../book/figures/8_access_schemes_hard.png)

Figure 2: [Circling vs hovering](figures/circling_vs_hovering.png)

Figure 3: [Where a pilot that thinks ahead could win, on fresh scenarios (pass mark 0.02)](figures/room_fresh_seeds.png)

**Honest summary.** The physics-based search pilots are the main controller in our results. The learning AI has not beaten them
anywhere yet. We measured *why*: on walking crowds there is nothing to win; on still crowds half the gap is information the AI
does not have and half is learning; on competing sites the room is about one decision, *when to leave*, which the full AI did
not learn with our training budget.

## In progress (expected 24-25 October 2026)
These are not results yet. Each has its judging rule written down before it runs.
1. **Anticipation rule.** One number from site distance, drone speed, switch time and mission length that predicts whether
   anticipation (and so any AI) can beat greedy re-planning. Fitted on the 9 designs, then tested on 8 new designs with the
   predictions written down first.
2. **Hybrid timing AI.** The search pilot chooses *where*; the AI learns only *when* to leave for the other site. Judged
   against the same bar (best of four simple pilots per scenario) on the 2 km designs, with a no-room control.
3. **Value of location information.** Phones that attach to the drone can report their position. How many reports, how
   accurate and how fresh must they be for the planner to reach 98% of full-information coverage?

After these: the final evaluation (the untouched test scenarios are read once), the report and the viva material.
[Dates for the final evaluation and the report to be fixed with you.]

## Questions for you
1. **Minimum data rates per user class** (rescue 200 kbps, video 500 kbps, voice 50 kbps, IoT 10 kbps, normal 100 kbps): may we
   keep them as stated engineering assumptions, or should we use specific values or a source?
2. **Framing:** is it acceptable to present the result as "physics-based search is the main controller; AI helps only in
   specific regimes, and we measured where", including the negative AI results?
3. **Which contribution should the report emphasise:** the anticipation rule (when can any AI help?) or the value of location
   information (how much phone position data a planner needs)?
4. **Report format:** does the department have a template (chapter order, citation style, page limits, plagiarism check)?
5. **Real place:** do you expect a scenario based on a real area (OpenStreetMap buildings), or is it fine as a short demo?
6. **Altitude limit:** should we enforce the usual 120 m legal limit for drones (our drone currently flies 50-300 m) and
   re-run the main results?
7. **Timeline:** what are the submission dates for the report, the demo and the viva?
