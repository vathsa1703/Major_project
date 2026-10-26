# UAV-NOMA Disaster Network Planning Simulator: brief for the guide

*26 October 2026. Draft for feedback. Numbers come from the project book (`docs/book/`) and from the result files of the
studies finished on 23-24 October; the full report draft is `docs/report/report.md` / `UAV-NOMA-Report.pdf`.*

## What the project is
After a disaster the phone towers are down; a drone carrying a small base station can act as a temporary tower. We built a
**simulation-based planning tool** that tests, in software, where such a drone should fly, how high, and how it should share its
radio with **NOMA** (two people on one frequency slice), so that as many survivors as possible stay connected before the battery
runs out. We compare simple programmed pilots with an AI pilot that learns by itself, fairly and on the same scenarios.

## Results
All comparisons use the same seeded scenarios for every pilot, with paired 95% confidence intervals; pass marks were written
down before results were seen. Coverage = share of people served.

| Question | Result | Verdict |
|---|---|---|
| **H1** Does a moving drone beat a parked one? | Hard scenarios (2 x 2 km, low power, buildings, moving crowds): best pilot 0.741 vs 0.428 parked. Small, easy maps: 0.914 vs 0.882. | Supported where the area is large and power scarce |
| **H3** Does NOMA beat OMA? | Both optimised the same way: adaptive NOMA serves **3-5 more people per 100** for every pilot; still wins with imperfect interference cancellation. Price: less total data speed for both optimised schemes. | Supported |
| **Real map** (a scenario based on the Sept 2024 Kathmandu floods; 12,061 OpenStreetMap buildings, people reconstructed, not real data) | Pilots rank exactly as on the synthetic map. NOMA's gain for the best pilot **doubles**: +0.127 (0.781 vs 0.654) vs +0.064 on the synthetic map. The best pilot flies at about 290 m, above the usual 120 m legal limit. | Conclusions survive real geometry |
| **Energy** Hover or circle? | Circling the best spot at about 10 m/s serves **25.6% more people-seconds per battery** than hovering (robust: +21% to +31%). | Supported |
| **How much location data does a planner need?** (pre-registered) | Keeps 98% of full-information coverage with GPS reports from **half of the phones** on moving crowds (one in twenty on competing sites); 50 m GPS error costs nothing measurable; reports should be at most 30 s old. | **Passed** |
| **Is there room for an AI at all?** (clairvoyant test) | A pilot that knows the future gains only +0.002 on walking crowds. Room exists only where demand jumps between sites about 2 km apart. | A method to measure the prize before training |
| **Can a formula predict that room?** (pre-registered) | Fitted on 9 designs, tested on 8 new ones: R^2 0.58 (pass 0.7), 5 of 8 calls right (pass 7). | **Not confirmed** |
| **H2** AI on still crowds (G4) | Best AI 0.576 vs pass mark 0.580. | Not met |
| **H2** AI on 2 km competing sites (G5 round 1) | Best of 8 agents 0.680 vs bar 0.756 / 0.753. | Not met |
| **H2** Hybrid: search decides where, AI only *when* to leave | -0.004 (n.s.) and -0.019* vs the bar; beats plain grid search by +0.041* / +0.014*. A hand-written departure rule scores higher (0.780 / 0.774). | Not met |
| **H2** AI when the real radio differs from the textbook | -0.039* and -0.101* vs the bar. A pilot that measures a few spots and then searches recovers most of the loss. | Not met |
| **Realistic drone** | A simulated quadcopter with autopilot and wind flies the same plans within 0.012 coverage. | Coverage conclusions carry over |

**NOMA stays visible:** every AI agent above also serves 0.08-0.14 more people with adaptive NOMA than with tuned OMA.

Figure 1: [NOMA vs OMA at equal bandwidth and power: Kathmandu case and synthetic hard map (map data (c) OpenStreetMap contributors)](../case_nepal/figures/nepal_bars.png)

Figure 2: [How many phones must report their GPS position (98% line)](figures/voi_ratio_vs_f.png)

**Honest summary.** The physics-based search pilots are the main controller. The learning AI did not beat them in any of four
pre-registered tests. We can say why: on walking crowds there is nothing to win; where there is room, the AI's shortfall comes
from its inputs (no altitude choice, rough maps) and from not using the operator's announcement, not from poor learning.

## Next study (in progress; no results yet): find-and-serve
After a disaster the drone is the only tower, so phones attach to it and transmit. Their uplink signal strength gives a noisy
distance ring; rings measured from several spots intersect (like GPS in reverse) and locate the phone. The drone must trade
searching against serving, with NOMA. Path to real use: simulation -> lab test with a software-defined radio and an open-source
LTE stack -> field trial with an operator or rescue agency (in India likely a WPC test licence and DGCA permission, to be
checked) -> adoption. Barriers: technically an IMSI-catcher (licensed spectrum, operator cooperation), SIM authentication needs
the operator's core network, phone batteries, rubble, drone endurance, and proven tools (thermal cameras, dogs).

## Questions for you
1. **Minimum data rates** (rescue 200, video 500, voice 50, IoT 10, normal 100 kbps): keep as stated engineering assumptions?
2. **Framing:** is "search is the main controller; learning did not help where we tested, and we measured where it could"
   acceptable, with all negative AI results in the report?
3. **Altitude limit:** should we re-run the main results and the Kathmandu case with a 120 m ceiling?
4. **Find-and-serve:** include it in this report as future work only, or wait for its first results?
5. **Report format:** department template, citation style, page limit, plagiarism check?
6. **Timeline:** submission dates for the report, the demo and the viva? [Dates to be fixed with you.]
