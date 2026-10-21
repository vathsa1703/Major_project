# Chapter 11. Outlook

## 11.1 Roadmap (agreed 2026-10-19, full version in [`docs/roadmap.md`](../roadmap.md))
| Stage | Content | Status |
|---|---|---|
| A | Close the still-crowd gate G4 (five experiments plus noise annealing), then stop tuning | experiments done; G4 half met |
| B | **NOMA becomes a decision**: an OMA switch for a clean H3 experiment in the game (built 10-19), then the AI chooses the power split and pairing; classical versions for the baselines; imperfect SIC and bit-error rate as ablations | in progress |
| C | Dynamic scenarios and events: moving crowds (curriculum steps 2-5), rising flood, evacuation, aftershock, survivors appearing, drone failure | planned |
| D | Realism: the AI does not know where people are; a real place (e.g. a Nepal flood) from public data; wind, GPS error, delays; backhaul; a safety layer; one real measurement | planned |
| E | Evaluation and write-up: E1-E14 with 5 seeds, generalisation, sensitivity, literature matrix, report, demo, viva | planned |
| F | **Last:** a simulated quadcopter with an autopilot model flying under our controller, no hardware | planned |

## 11.2 Is it novel? (first literature check, 2026-10-19)
Two web searches, not a full review. Every paper must be read and checked by a person before it is cited.
- **Already published:** deep RL for UAV base stations with NOMA, including mobile users, 3D trajectories, power control,
  battery limits and disaster areas. Examples found:
  - NOMA in UAV-aided cellular offloading (Zhong et al., arXiv:2011.14776): k-means plus a deep Q-network for 3D trajectory
    and power, with roaming users;
  - AdaptSky (arXiv:2107.01004): joint NOMA power allocation and 3D placement;
  - a NOMA-DQN battery-aware path-planning paper (HAL hal-04762084);
  - a disaster-area UAV base-station study with NOMA pairing and power splitting;
  - multi-agent RL with action masking for UAV mobile communications (arXiv:2303.16737).
- **So the method is not new.** We cannot claim "first to apply RL to UAV-NOMA".
- **Possible contributions** (to be checked properly):
  1. an open, tested, reproducible simulator and benchmark (none found in the searches);
  2. a fair evaluation against strong non-learning pilots across regimes, with paired statistics (the papers seen compare
     against OMA, random or circular paths, according to the search snippets);
  3. specific findings: most of a pilot's lead can come from choosing the altitude; forward flight costs less energy than
     hovering; lessons on RL controls, decision rhythm and exploration noise;
  4. NOMA measured inside the game for every pilot, with confidence intervals (Chapter 13).
- **Defensible claim:** "an open, tested simulator and evaluation protocol for UAV-NOMA planning in disaster scenarios, a
  comparison against strong baselines across regimes, and an analysis of when RL helps". This matches the plan's own
  contribution statement.
- **How to strengthen it:** make NOMA a joint decision (stage B), test where RL should win (stage C), add a real place
  (stage D), and build the literature matrix.

## 11.3 The real-world gap
A real drone running this software would not perform as it does in the simulation. This is called the sim-to-real gap.

| In the simulator | In reality |
|---|---|
| Pilots know where everyone is (the AI sees a density map) | Nobody knows where survivors are; it must be estimated from phone signals |
| The signal follows a statistical formula | Real buildings, terrain, trees, weather and interference |
| NOMA works perfectly | NOMA needs special base-station hardware and receivers; ordinary phones are believed not to support it (to be checked) |
| The drone moves exactly as told | Wind, GPS error, control delays, real battery behaviour |
| No rules | Aviation permission, a radio licence, a safety pilot |
| No backhaul | The drone needs its own link to the network (tether, microwave, satellite) |

What carries over: the qualitative lessons and the method (compare strategies fairly before flying). What does not: the absolute
numbers. The report must say so.

**What already exists in practice** (news sources from 2017-2018, may be out of date): AT&T's tethered "Flying COW" drone carried
LTE radios to restore service in Puerto Rico after Hurricane Maria, and reportedly after Hurricane Ida in Louisiana. People place
it; it uses no AI and no NOMA. NOMA was standardised for LTE downlink as "MUST" in Release 14, according to one survey;
whether it is used in commercial networks was not found.

**Why research often stays research:** simple solutions already work; the sim-to-real gap; hardware is needed on both ends;
regulation and safety; trust and liability; a small, slow market; and survivors' positions are unknown. These are also where
the opportunity and the risk lie.

## 11.4 Hardware path (outside this project, in stages)
Our software is the "brain" that decides where the drone goes; a ready-made autopilot (ArduPilot or PX4) keeps it in the air.
Our "fly to this spot" actions map directly onto autopilot waypoint commands (MAVLink).

| Stage | What is done | Needs a drone |
|---|---|---|
| 0 | Software in the loop: our controller flies a simulated autopilot (roadmap stage F) | no |
| 1 | NOMA on the bench: two software-defined radio receivers and one transmitter; check pairing and SIC, measure bit errors | no |
| 2 | Measure the signal against height from a mast or building | no |
| 3 | Hover tests with a small drone carrying the radio | yes |
| 4 | Closed loop with a safety pilot or tether | yes |
| 5 | A pilot with a partner (an emergency team or telecom company) | yes |

Needs: a mentor with radio or drone experience; India's DGCA drone rules; a radio licence or licence-free bands; and money
(roughly a few hundred to a couple of thousand dollars per software-defined radio, from about a thousand for a capable drone;
unchecked figures).

## 11.5 Business track
Novelty is not the test for a business; a paying customer with a painful problem is. For a student team the most realistic
product is software only: a planning and rehearsal tool for emergency teams or telecom operators ("where to station drones, how
many, how high, before flying"). It avoids hardware, flying and regulation, but whether anyone would pay is unknown, and drone
cell sites already exist (above).

Next step, costing nothing: talk to 5-10 people who do this work (disaster agencies, telecom emergency teams, drone service
companies) and ask what they do today, what goes wrong, and what it costs them. Then decide.

## 11.6 Open decisions for the owner
1. The minimum data rate for each user class (needed before any number goes into the report).
2. The battery size for the final experiments (10 Wh makes everyone die; 16 Wh makes everyone survive; a sweep is experiment E7).
3. Whether to relax Gate G4 and move to moving crowds (the agreed stopping rule has been reached; Chapter 8).
4. Sending Sagar's revised task and inviting Sagar and Harshita to the repository.
5. Getting the Al-Hourani paper and the MATLAB reference numbers.
