# Viva deck outline (18 slides, about 18 minutes)

Each slide: the title, what goes on it, the figure to show (paths from `docs/book/figures/` unless stated) and speaker notes in
plain English. Numbers are the same as in `report.md` (the source sections are given there). Items marked [PENDING] depend on
experiments that are not finished. Wording rule: "simulation-based planning tool", never "digital twin"; the Kathmandu case is
"a scenario based on" the 2024 floods, never "real data", and every map carries "(c) OpenStreetMap contributors".
Updated 2026-10-26 with the finished studies (value of information, anticipation rule, hybrid timing, model mismatch,
Kathmandu case).

---

## 1. Title
- UAV-NOMA Disaster Network Planning Simulator: a simulation-based planning tool for drone base stations using NOMA.
- Team names, guide, department, date [PENDING: names].
- **Figure:** `users_preview_v3.png` as a background strip (four disaster scenarios).
- **Speaker notes:** "Our project asks a practical question: after a disaster, where should a drone carrying a phone tower fly,
  and how should it share its signal, so that as many survivors as possible stay connected before the battery runs out?"

## 2. The problem
- Towers fail after floods and earthquakes; survivors cannot call for help.
- A drone base station helps, but: small battery, signal blocked by buildings, people move, hundreds of users share one radio.
- **Figure:** `viewer_first_run.png` (a drone over a crowd, served and unserved people).
- **Speaker notes:** "Three things make this hard. The battery lasts minutes. Buildings block the signal. And people move,
  sometimes suddenly. So the drone has to decide where to be, how high, and how to share its power, all the time."

## 3. The idea
- Guide's idea: a moving base station using NOMA. Our extension: moving crowds, collapsed buildings, a battery, and a learning
  pilot, compared fairly with strong simple pilots.
- Four hypotheses: H1 moving beats parked; H2 learning beats simple pilots only where things change; H3 NOMA beats OMA;
  H4 several drones (stretch).
- **Figure:** none (a 4-row hypothesis table).
- **Speaker notes:** "Every experiment we ran answers one of these four questions. We wrote the pass marks down before seeing
  the results, so we could not move the goalposts."

## 4. The system
- One physics engine: crowds, movement, buildings, the Al-Hourani channel, NOMA and OMA, the Zeng-Xu-Zhang energy model.
- One "game" (Gymnasium environment) that every pilot plays: simple pilots, the AI, a clairvoyant planner, a dashboard, a 3D
  quadcopter.
- 399 automated tests (on 23 Oct; more since), CI on every change, seeded scenarios.
- **Figure:** the architecture diagram (report Figure 3.1; rendered PNG is produced in `docs/report/build/diagram_1.png` by
  `build_report.py`).
- **Speaker notes:** "Everything calls the same code, so the dashboard, the experiments and the AI can never disagree. Every
  scenario has a seed number: the same seed always gives the same disaster, so anyone can repeat our results."

## 5. NOMA in one picture, and the first result
- NOMA: two people share one frequency slice; the far person gets more power; the near person removes the far person's signal
  first (SIC).
- Fixed 80/20 NOMA: always more total speed (+20-27%), more people served when power is scarce (+5-7 per 100), but at full power
  a hard ceiling of 232 kbps for the weak user.
- **Figure:** `7_noma_pairs_lowpower.png` (pairs on the map; the weak users sit on the 232 kbps line).
- **Speaker notes:** "With a fixed split, the weak user always hears the strong user as noise, so its speed can never pass 232
  kilobits per second, however much power we add. A video user needs 500. That is why we built an adaptive version."

## 6. NOMA result: a fair fight
- Both schemes optimised the same way (minimum power per user, cheapest first).
- Adaptive NOMA serves 3-5 more people per 100 than equally optimised OMA, for every pilot; still wins with imperfect SIC;
  rescue users almost all served (lowpower B3: 0.4% unserved).
- Honest trade-off: serving the most people costs total speed (55-65% less than the fixed schemes).
- **Figure:** `8_access_schemes_hard.png` (and `9_access_schemes_lowpower.png` as backup).
- **Speaker notes:** "Comparing tuned NOMA against untuned OMA would be cheating, so we tuned both. NOMA still wins, by 3 to 5
  people in every 100. We also say what it costs: when the goal is to connect as many people as possible, total speed drops."

## 7. Moving vs parked (H1)
- Hard scenarios (2 x 2 km, low power, buildings, moving crowds): parked drone 0.428, best pilots 0.740-0.741.
- Most of the best pilot's lead was choosing the altitude (B6 = B4).
- **Figure:** `baselines_hard_7policies.png`; optional `1_hard_moving_crowds.png` (flight paths on scenario 5).
- **Speaker notes:** "A drone that moves serves 74 people in 100; a parked one serves 43. In small, easy maps the difference is
  tiny, so we say exactly where H1 holds: big area, low power."

## 8. Circling saves battery
- In the rotary-wing energy model, flying at about 10 m/s costs less than hovering (126 W vs 168 W).
- Circling the best spot (B7) serves 25.6% more people per battery; with 12-13 Wh it finishes the mission while a hovering drone
  dies (+0.08 to +0.12 coverage). Robust to the uncertain energy numbers (+21% to +31%).
- **Figure:** `docs/report/figures/circling_vs_hovering.png` (report Figure 5.12).
- **Speaker notes:** "Like a helicopter, a drone gets free lift from moving forward. So instead of hovering, our pilot flies
  small circles. Same coverage while flying, but a quarter more service per battery charge."

## 9. The AI story, part 1: still crowds (G4, negative result)
- The AI sees only what a real drone could measure (coarse crowd maps); simple pilots see everyone's true position.
- From below random (0.394) to 0.576; pass mark 0.580: **not met**.
- Information ladder: half the gap is missing information, half is learning. The AI goes to the crowd; the best pilot parks
  between crowds.
- **Figure:** `10_e0_vs_b3_seed105.png` (the AI flies past the best spot).
- **Speaker notes:** "We report this honestly: our AI did not pass its first gate. But we found out why. Half of the gap is
  information it does not have, and half is that it learned 'go to the crowd' instead of 'find the spot that reaches several
  crowds'."

## 10. The AI story, part 2: measure the prize before training (headroom method)
- A clairvoyant pilot that knows the future: on walking crowds it beats the simple pilot by only +0.002. No AI can win there.
- Redesigned scenarios (demand jumps between sites 1-2 km apart): room up to +0.108; room appears when the flight across takes
  as long as the switch.
- Confirmed on 20 fresh scenarios per design: room in 5 of 9 designs, clearly only at 2 km (+0.04 to +0.09).
- Can a formula predict the room from distance, speed, switch time and mission length? Pre-registered on 8 new designs:
  R^2 0.58 (pass 0.7), 5 of 8 calls right (pass 7): **not confirmed**. The clairvoyant test has to be run per design.
- **Figure:** `docs/report/figures/room_fresh_seeds.png` (report Figure 5.13); backup `docs/report/figures/anticipation_rule.png`
  (Figure 5.14) and Tables 5.7-5.10.
- **Speaker notes:** "Before spending two weeks training, we asked: if a pilot knew the future perfectly, how much better could
  it do? For walking crowds the answer was almost nothing, because the drone is ten times faster than people. So we built
  scenarios where looking ahead matters, and measured the room there first. We also tried to replace that test by a simple
  formula; it got only 5 of 8 new designs right, so we say it was not confirmed."

## 11. The AI story, part 3: three more chances, three more losses
- G5 round 1, full AI on the 2 km sites: all 8 agents below the bar (best 0.680 vs 0.756 / 0.753).
- Hybrid: grid search decides where, the AI only *when* to leave: -0.004 (n.s.) and -0.019* vs the bar; it beats plain grid
  search (+0.041*), but a hand-written departure rule scores higher (0.780 / 0.774).
- Wrong textbook channel (hidden buildings, shadowing): AI -0.039* / -0.101* vs the bar; a pilot that measures a few spots and
  then searches recovers most of the loss.
- Why: the shortfall splits into foresight 0.02, not using the announcement 0.05-0.07, no altitude choice 0.02, rough maps
  0.03, learning about 0.
- NOMA still +8 to +14 people per 100 over tuned OMA for every agent.
- **Figure:** report Tables 5.12, 5.13 and 5.15 (one simple bar chart can be drawn from them).
- **Speaker notes:** "We gave the AI three more chances, each with the pass mark written first. It never beat the best simple
  pilot. Interestingly, it is not a bad learner: it matches a search that sees what it sees. It loses on what it is given."

## 12. How much location data does a planner need? (pre-registered, passed)
- After a disaster the drone is the network; phones can send their GPS position. How many, how accurate, how fresh?
- Result: 98% of full-information coverage with reports from half of the phones on moving crowds (one in twenty on competing
  sites); 50 m GPS error costs nothing measurable; reports at most 30 s old.
- **Figure:** `docs/report/figures/voi_ratio_vs_f.png` (report Figure 5.16).
- **Speaker notes:** "The planner needs to know roughly where the crowds are and how big they are, not where each person stands.
  That gives a rescue team a simple rule: half the phones, every 30 seconds, ordinary GPS is enough."

## 13. A scenario based on the September 2024 Kathmandu floods
- 2 x 2 km of Kathmandu along the Bagmati: 12,061 real building footprints from OpenStreetMap, a 3D line-of-sight test;
  people reconstructed (roofs in a flood band, shelters, dry ground): **not real data**.
- Pilots rank exactly as on the synthetic map. NOMA's gain for the best pilot doubles: +0.127 (0.781 vs 0.654) vs +0.064.
- Honest flag: the best pilot flies at about 290 m, above the usual 120 m legal limit.
- **Figure:** `docs/case_nepal/figures/nepal_map.png`, then `docs/case_nepal/figures/nepal_bars.png` (report Figures 5.17, 5.18);
  credit line "(c) OpenStreetMap contributors" visible.
- **Speaker notes:** "The buildings are real, the people are not: we placed them with stated assumptions. On real geometry our
  conclusions hold, and NOMA helps even more, because people on roofs and people in narrow lanes have very different signals."

## 14. 3D demo: does a real-looking drone change anything?
- The same pilots flown by a simulated quadcopter with an autopilot, motor lag, tilt limit and wind.
- Coverage gap -0.003 to -0.012; wind changes it by at most 0.002 (5 scenarios per cell: a short check). Its battery numbers are
  not trustworthy yet.
- **Figure / live demo:** `docs/report/figures/fig_3d_flight.png` (report Figure 5.15), or live: the dashboard's "3D flight" page
  (`streamlit run uav_dataset/dashboard.py`).
- **Speaker notes:** "Our game moves the drone like a chess piece. Here a full flight model with an autopilot flies the same
  plan. The answer barely changes, so our conclusions are not an artefact of the simple flight model. This is still a simulation,
  not a real flight."

## 15. Contributions
- An open, tested, reproducible simulation-based planning tool for UAV-NOMA in disasters (seeds, configs, 399+ tests, CI).
- A fair evaluation protocol: strong simple pilots, paired confidence intervals, pre-registered pass marks.
- NOMA measured inside the mission for every pilot, including against an equally optimised OMA.
- Findings: H1 (moving beats parked where the area is large and power scarce); H3 (NOMA +3-5 per 100 over tuned OMA, about
  13 for the best pilot on the Kathmandu map); circling saves a quarter of the battery; the clairvoyant headroom test tells you
  whether learning can help before you train; a design rule for phone location data; the quadcopter sim-to-sim check; an
  honest map of where AI does and does not help (four negative AI results, one rule not confirmed).
- **Figure:** none.
- **Speaker notes:** "We do not claim to be the first to use RL for UAV-NOMA; others have. Our contribution is the tool, the fair
  comparison, and the honest map of where learning helps and where a simple rule is enough."

## 16. Limitations
- Synthetic data; 2D buildings with a fixed loss; no backhaul, no interference, no bit errors.
- Simple pilots know true positions; real survivors' positions are unknown.
- Al-Hourani original paper not yet read; minimum rates not signed off; MATLAB parity not done.
- Our altitudes (50-300 m) exceed the usual 120 m legal limit [VERIFY: Drone Rules 2021]; in Kathmandu B6 flies at ~290 m.
- Kathmandu: real buildings but reconstructed people; 94% of building heights drawn; no flood map.
- **Figure:** none.
- **Speaker notes:** "Absolute numbers do not transfer to a real disaster. The comparisons and the lessons do. Here is exactly
  what we have not verified yet."

## 17. Next study: finding survivors from their phones (find-and-serve)
- Status: study in progress; no results yet.
- The drone is the only tower, so phones attach and transmit; uplink strength gives a noisy distance ring; rings from several
  spots intersect, like GPS in reverse; shadowing, rubble and fading widen them; the drone trades search against serving.
- Path: simulation -> lab (software-defined radio + open-source LTE stack) -> field trial with an operator or rescue agency
  (WPC test licence, DGCA permission: to be checked) -> adoption (operators, regulators, NDRF).
- Barriers: technically an IMSI-catcher; SIM authentication needs the operator's core network; phone batteries; rubble;
  drone endurance and airspace; proven tools (thermal cameras, dogs, acoustic devices); cost.
- **Figure:** the path table (report Table 7.2).
- **Speaker notes:** "This is where the project goes next. Related systems exist (SARDO, LifeSeeker; still to be verified); our
  angle is to find people and serve them with NOMA in the same flight."

## 18. Future work and thank you
- Final evaluation on the untouched test seeds; merge the study branches.
- Find-and-serve; real places with flood maps and population density; tethered drones; the 120 m limit.
- Disaster events (flood, aftershock), wind and GPS errors, a safety layer; ArduPilot SITL; several drones.
- Business track: a planning and rehearsal tool for emergency teams; talk to 5-10 practitioners first.
- **Figure:** `gifs/best_ai_e5a_seed105.gif` or a dashboard screenshot.
- **Speaker notes:** "Thank you. We are happy to show any scenario live in the dashboard."

---

## Backup slides (if asked)
- Energy formula and our 20 N drone (report Section 3.5).
- Adaptive NOMA closed form (report Section 3.4).
- Information ladder table (report Table 5.5).
- All G4 runs (report Table 5.6).
- Competing-sites room tables (report Tables 5.8, 5.9), anticipation rule (Table 5.10) and G5 round 1 (Table 5.11).
- Hybrid timing AI (Table 5.12), shortfall decomposition (Table 5.13), model mismatch (Tables 5.14, 5.15).
- Sim-to-sim table (report Table 5.16); value of information (Table 5.17); Kathmandu case (Table 5.18).
