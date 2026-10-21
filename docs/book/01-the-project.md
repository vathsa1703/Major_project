# Chapter 1. The project

## 1.1 The problem
**In plain words.** When an earthquake or flood hits, the mobile phone towers in the area often stop working: no power, broken
cables, collapsed buildings. Survivors cannot call for help and rescue teams cannot coordinate. A drone carrying a small mobile
base station can fly over the area and act as a temporary tower. But a drone has a small battery, the signal is blocked by
buildings, people move around, and one drone has to serve many people at once. Where should it fly, how high, and how strongly
should it transmit?

**Technically.** A UAV-mounted aerial base station (UAV-BS) restores downlink coverage in a disaster area. Users are spatially
clustered and mobile, the air-to-ground channel has a line-of-sight probability that depends on the elevation angle, the UAV is
energy-constrained (rotary-wing propulsion dominates consumption), and the downlink uses non-orthogonal multiple access (NOMA)
so that pairs of users share one frequency resource. The control problem is the joint choice of 3D position and transmit power
over time.

## 1.2 Where the idea came from
- **The guide's idea:** a moving base station using NOMA.
- **The team's extension** (Srivathsa's pitch): add moving survivor crowds, collapsed buildings, a battery limit, and a
  reinforcement-learning (RL) controller, then compare it fairly with strong simple strategies. The full plan is in
  `ARCHITECTURE.md` and `PROJECT_PLAN.md` (shared as PDFs at the start, summarised in `CLAUDE.md`).
- **Positioning.** A *simulation-based planning tool*: rescue planners can test drone strategies in software before flying real
  hardware, saving battery, hardware and flight time. It may only be called a "digital twin" (and only "digital-twin-style") if it
  is fed real or replayed state data (plan section 11). Until then the wording is "simulation-based planning tool".

## 1.3 The research question and the hypotheses
**Research question:** can a crowd-aware RL controller adapt the drone's position, altitude and transmit power to shifting
survivor demand better than static and heuristic strategies, under a battery limit?

Every experiment must serve one of these hypotheses:

| ID | Hypothesis | In plain words |
|---|---|---|
| H1 | Adaptive UAV control beats a fixed UAV once crowds move | A drone that follows people does better than one parked in the middle |
| H2 | RL beats strong heuristics (k-means B2, grid search B3, PSO B4) only when dynamics and battery limits make heuristics short-sighted; report where it wins and where it doesn't | The AI should only win in hard, changing situations, and we must say where it loses |
| H3 | NOMA pairing improves throughput and fairness over OMA at equal bandwidth and power | Sharing a frequency between two people (NOMA) beats giving everyone a separate slice (OMA) |
| H4 (stretch) | Coordinated multi-UAV control beats independent or centroid placement | Several drones working together beat drones acting alone |

## 1.4 The gates
The plan forbids starting a layer before the previous one passes its gate:

| Gate | Criterion | Status (2026-10-19) |
|---|---|---|
| G1 Simulator core | Python matches MATLAB reference vectors; unit tests green; one scenario renders | Tests green and scenarios render; **MATLAB parity not done** (needs the MATLAB reference numbers) |
| G2 Physics | Altitude optimum reproduced; energy model sanity tests; NOMA feasibility logic tested | **Met** (Chapter 4, 10) |
| G3 Baselines | All baselines run on 100+ seeded scenarios; reproducible comparison table | **Met** (Chapter 7) |
| G4 Single-agent RL | PPO learns beyond random on the static scenario and matches or beats B2 there | **Half met**: beats random, not B2 (Chapter 8) |
| G5 Dynamic RL | Evidence on at least one dynamic scenario, positive or negative, with 5 seeds | Not started |
| G6 Multi-UAV | G5 stable; 2-UAV environment passes tests | Not started |
| G7 Freeze | Feature freeze at month 10 | Not reached |

## 1.5 The team (from the task documents)
| Person | Role | Owns | Backup |
|---|---|---|---|
| Srivathsa | Wireless physics, project owner, repo owner and reviewer | physics, energy, MATLAB parity, assumptions, API | Sagar |
| Sagar | Simulation | world, environment, scenarios, obstacles, mobility | Srivathsa |
| Arani | Baselines and experiments | baselines, experiment runner, statistics, plots, CI | Harshita |
| Harshita | RL and the real-data link | RL training, trace replay, state sync | Arani |

Rules from the plan: every module has a primary and a backup who can explain it; nobody merges code they cannot explain; the
viva rule is "no 'that is Sagar's part'". Much of the simulator, baselines and RL pipeline described in this book was built in
an AI-assisted session with the owner before the team started; the team's tasks are being re-scoped to *own, review and
extend* this code (see the decision log, D-31).

## 1.6 What "finished" means
The plan's deliverables: literature matrix (verified citations), assumptions table with sources, validated simulator with test
suite and MATLAB parity report, baseline suite, Gymnasium environments (single and multi-UAV), trained models with logs,
experiment scripts reproducing every figure, dashboard and API, report or paper draft, demo video, viva slides and a 30-second
pitch. The roadmap from today to there is in Chapter 11 and `docs/roadmap.md`.

## 1.7 The rule about the AI
Decided by the owner on 2026-10-19 (decision D-24): **the AI learns by itself.** It receives only raw measurements that a real
drone could have and the coverage score. No hints, no menu of candidate spots, no imitation of the baselines, no privileged
information. Allowed: the network design, training length, hyperparameters, seeds and the curriculum order.
