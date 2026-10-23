# Viva deck outline (14 slides, about 15 minutes)

Each slide: the title, what goes on it, the figure to show (paths from `docs/book/figures/` unless stated) and speaker notes in
plain English. Numbers are the same as in `report.md` (the source sections are given there). Items marked [PENDING] depend on
experiments that are not finished. Wording rule: "simulation-based planning tool", never "digital twin".

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
- 399 automated tests, CI on every change, seeded scenarios.
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
- G5 round 1 on the 2 km sites: all 8 agents below the bar (best 0.680 vs 0.756 / 0.753); NOMA still +8 to +13 people per 100
  over OMA for the same agent. Round 2 of the full AI dropped (D-56).
- In progress (expected 24-25 Oct 2026, not results): anticipation rule, hybrid timing AI.
- **Figure:** `docs/report/figures/room_fresh_seeds.png` (report Figure 5.13); Tables 5.7-5.10 as backup.
- **Speaker notes:** "Before spending two weeks training, we asked: if a pilot knew the future perfectly, how much better could
  it do? For walking crowds the answer was almost nothing, because the drone is ten times faster than people. So we built
  scenarios where looking ahead matters, and measured the room there first. Our first learning agents still lost to a simple
  forecasting pilot; we report that too."

## 11. 3D demo: does a real-looking drone change anything?
- The same pilots flown by a simulated quadcopter with an autopilot, motor lag, tilt limit and wind.
- Coverage gap -0.003 to -0.012; wind changes it by at most 0.002 (5 scenarios per cell: a short check). Its battery numbers are
  not trustworthy yet.
- **Figure / live demo:** `docs/report/figures/fig_3d_flight.png` (report Figure 5.14), or live: the dashboard's "3D flight" page
  (`streamlit run uav_dataset/dashboard.py`).
- **Speaker notes:** "Our game moves the drone like a chess piece. Here a full flight model with an autopilot flies the same
  plan. The answer barely changes, so our conclusions are not an artefact of the simple flight model. This is still a simulation,
  not a real flight."

## 12. Contributions
- An open, tested, reproducible simulation-based planning tool for UAV-NOMA in disasters (seeds, configs, 399 tests, CI).
- A fair evaluation protocol: strong simple pilots, paired confidence intervals, pre-registered pass marks.
- NOMA measured inside the mission for every pilot, including against an equally optimised OMA.
- Findings: altitude choice explains most of a search pilot's lead; circling saves a quarter of the battery; the clairvoyant
  headroom test tells you whether learning can help before you train.
- **Figure:** none.
- **Speaker notes:** "We do not claim to be the first to use RL for UAV-NOMA; others have. Our contribution is the tool, the fair
  comparison, and the honest map of where learning helps and where a simple rule is enough."

## 13. Limitations
- Synthetic data; 2D buildings with a fixed loss; no backhaul, no interference, no bit errors.
- Simple pilots know true positions; real survivors' positions are unknown.
- Al-Hourani original paper not yet read; minimum rates not signed off; MATLAB parity not done.
- Our altitudes (50-300 m) exceed the usual 120 m legal limit [VERIFY: Drone Rules 2021].
- **Figure:** none.
- **Speaker notes:** "Absolute numbers do not transfer to a real disaster. The comparisons and the lessons do. Here is exactly
  what we have not verified yet."

## 14. Future work and thank you
- In progress (expected 24-25 Oct 2026): anticipation rule, hybrid timing AI, value of location information.
- Locate survivors from their connected phones; a real place from OpenStreetMap (demo); tethered drones; the 120 m limit.
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
- Competing-sites room tables (report Tables 5.8, 5.9) and G5 round 1 (Table 5.10).
- Sim-to-sim table (report Table 5.11).
