# Chapter 10. What is verified and what is not

**Plain words.** A simulator is only believable if its numbers come from somewhere. Every parameter is either checked against a
published paper, derived from checked formulas, or openly labelled as our own assumption with a range to test. The full table
is in [`docs/assumptions.md`](../assumptions.md); this chapter summarises it and lists the other checks.

## 10.1 Status labels
- **VERIFIED**: read in the cited paper.
- **DERIVED**: follows from verified formulas for a drone we chose (the choice itself is an assumption).
- **CONSISTENT**: appears in secondary papers that cite the original; the original was not read.
- **STANDARD**: a physical constant or textbook convention.
- **ASSUMPTION**: our engineering choice, with a sensitivity range to test (experiment E13).

## 10.2 Summary
| Area | Status | Notes |
|---|---|---|
| Energy formula (Zeng, Xu, Zhang, arXiv:1804.02238) | **VERIFIED** | propulsion power (Eq. 6), hover powers (Eq. 61), delta, k, rho, s |
| Our drone's P0, Pi, Utip, v0, A | **DERIVED** | a 20 N drone, R = 0.4 m, Omega = 300 rad/s; within 0.1% of the formulas. The paper's own drone is 100 N and hovers at about 1.37 kW |
| d0 = 0.6 | unverified | the paper uses 0.3 for its own drone |
| Channel formulas (Al-Hourani et al., IEEE WCL 2014) | **CONSISTENT** | same form in arXiv:1802.01117 and arXiv:1705.03304; the original was not read |
| a = 9.61, b = 0.16, eta_LoS = 1 dB, eta_NLoS = 20 dB | **CONSISTENT** | appear together in two papers' tables at 2 GHz, without an environment label; "urban" not confirmed |
| Free-space path loss, thermal noise | **STANDARD** | FSPL at 1 km and 2 GHz = 98.46 dB (tested) |
| User-class minimum rates | **ASSUMPTION, not signed off** | video and rescue are often unreachable at low power |
| Obstacle loss 15 dB, fading K = 10 dB, PA efficiency 0.4, circuit power 5 W, battery 10/16 Wh, walking and surge speeds, reward energy weight 0.05 | **ASSUMPTION** | ranges listed in `docs/assumptions.md` |
| NOMA power split 0.8 / 0.2, pairing strongest with weakest | **ASSUMPTION** (fixed design choice) | to become decisions in roadmap stage B |

## 10.3 Other checks done
- **Altitude optimum (Gate G2):** reproduced on dataset v1 (peak at 0 dBm near 250 m) and per user class on v2 (Chapter 2,
  entry 7). The optimum moves lower as the rate target rises.
- **NOMA logic:** the power split sums to 1; more power to the weak user lowers the strong user's rate; a deliberately bad pair
  is flagged by the SIC check; rates rise with power; NOMA gives more total speed than OMA at full power (tests).
- **NOMA vs OMA in the game:** the same move gives the same NOMA and OMA numbers whichever scheme scores; the search pilots
  evaluate candidate spots with the scheme being tested (tests in `test_noma_access.py`).
- **Energy model:** hover = P0 + Pi; the power curve dips below hover at moderate speed; climbing costs extra; descending gives
  nothing back (our assumption); radio power is under 5% of flight power.
- **Game:** passes Gymnasium's checker; deterministic by seed; the drone never leaves its limits; the battery never goes negative.
- **Statistics:** paired comparisons on identical scenarios, 95% confidence intervals, fixed seed lists.
- **Training is reproducible:** a training run killed by a session restart was re-run with the same seed and printed the same
  validation scores.

## 10.4 Not done yet
1. **Read the Al-Hourani paper** (DOI 10.1109/LWC.2014.2342736) and confirm the table and which environment each row is. The
   owner is trying to get it (college library, IEEE Xplore, Google Scholar, or by asking the author). Save it as
   `docs/papers/Al-Hourani_2014_LAP_altitude.pdf` (git-ignored).
2. **MATLAB parity (Gate G1):** compare our gain, SINR and rate with reference numbers from the team's MATLAB code.
3. **Sign off the minimum rates** and the other assumptions, then run their sensitivity ranges (experiment E13).
4. **One real measurement:** a radio or phone on a mast or a cheap drone at several heights, compared with our altitude curve.
5. **A literature matrix** of 15-25 papers, every citation checked by a person (the plan's month-1 task).

## 10.5 What the results may and may not claim
**May claim:** comparisons between strategies inside this model, with the stated assumptions; qualitative lessons (an optimal
altitude exists and depends on the rate target; forward flight can cost less than hovering; most of a pilot's advantage can come
from choosing the altitude; NOMA's gain over OMA in total speed and coverage under stated conditions).

**May not claim:** absolute coverage numbers for a real disaster, real-world performance of the AI, or "digital twin". The data
is synthetic and conclusions are conditional on the model (plan section 9).
