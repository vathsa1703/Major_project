# Chapter 14. How a senior communications and AI engineer would solve this

Status: **draft proposal (14.1-14.4), independently reviewed (14.5), agreed plan (14.6)**, written 2026-10-21. Nothing in this
chapter has been built yet. The owner's decisions in 14.7 are pending.

How to read it: 14.1-14.4 are my first draft, kept as written so the review makes sense. Where the review corrected the draft,
the correction is in 14.5 and the plan to follow is 14.6.

## 14.1 Reading the evidence first
1. **The still-crowd task is close to solved by search.** The best single spot reached instantly gives 0.686; grid search (B3)
   already gets 0.659. The maximum any controller can add over B3 is about 0.03 (less in practice: see the review, 14.5). Gate G4 tests *learnability*, not a chance to win.
2. **The AI plateaus at 0.51-0.56 whatever we change** (network, inputs, map resolution, training length, exploration schedule).
   The probe showed why: it maps the heatmap to a target point imprecisely (100-550 m off) and commits to it. We are asking a
   policy-gradient method to learn an *argmax over a 2D coverage field* from a coarse 10 x 10 density picture. That is an
   optimisation problem dressed up as a sequential decision problem; RL is the wrong tool for that layer.
3. **NOMA, as configured, has a hard ceiling.** With a fixed 80/20 split the weak user's SINR is capped at 4, so its rate is
   capped at 232 kbps whatever the power. That is why OMA covers slightly more users at 30 dBm.
4. **Where RL could genuinely win is untested and unmeasured.** H2 says RL should win only under dynamics and battery limits. We
   have never measured how much a perfect *anticipating* controller could gain over the best myopic one (B6) in moving scenarios.
   If that headroom is small, no RL can win there either.

## 14.2 The principle: separate the problem by time scale
A wireless-systems engineer splits the control problem by how fast each decision must change and how much is known:

| Layer | Time scale | Decision | Right tool |
|---|---|---|---|
| Radio resource allocation | every slot (1 s) | NOMA pairing, power split, NOMA or OMA per pair | closed-form / optimisation (known channels) |
| Placement | every 10 s | the best 3D spot for the users as they are now | search / optimisation (B3, B6, PSO) |
| Mission strategy | tens of seconds to minutes | where the crowd will be, when to move, how to spend the battery, which group to prioritise | **learning (RL)**, because it needs anticipation and long-term trade-offs |

"Do not learn what you can compute." Learning is spent where computation cannot reach: the future and the long-term budget.

## 14.3 The plan, in priority order
### P1. Fix the NOMA layer with adaptive hybrid NOMA/OMA (days, no learning)
For each pair (strong user s, weak user w) with the pair's resources b = 2B/N and p = 2P/N:
- **QoS-aware power split:** give the weak user just enough power to reach its minimum rate R_w:
  gamma_w = 2^(R_w / b) - 1, alpha* = gamma_w (p g_w + N0) / ((1 + gamma_w) p g_w), valid if alpha* < 1
  (N0 here is the noise *power* over the pair's bandwidth b, not the density; corrected in 14.5).
  The strong user gets the rest: rate b log2(1 + (1 - alpha*) p g_s / N0). SIC stays feasible because g_s >= g_w.
  This is the "cognitive-radio-inspired" power allocation discussed in the NOMA literature (to verify the citation).
- **Per-pair mode choice:** compute the users served (then the total rate) with NOMA at alpha* and with OMA (each user b/2, p/2,
  exactly our current OMA), and use the better one. Because OMA is one of the options for every pair, **coverage can never be
  worse than OMA**, and NOMA is used wherever it helps.
- **Need-aware pairing:** sort by gain, but avoid pairing two high-rate users; compare extreme pairing with need-aware pairing.
- Then re-run H3 with three schemes: OMA, NOMA fixed 80/20, hybrid adaptive NOMA. Expected: the 232 kbps ceiling disappears and
  NOMA's coverage gain at 30 dBm turns positive. This strengthens the NOMA story the guide cares about, without any AI.

### P2. Measure the headroom for RL before training more (days)
Build an **anticipating oracle**: it knows the crowd's future positions (we simulate them) and plans the drone's waypoints with
model-predictive control or dynamic programming over a 30-60 s horizon, with the drone's speed limit and battery. Compare
oracle vs B6 (best myopic) on the dynamic profiles (surge, hotspot jump, attraction) and with binding batteries.
- If oracle - B6 is large (say over 0.05), there is a real prize for an AI that learns to anticipate: H2 is worth testing.
- If it is small, H2 should be reported as "no room for RL in these regimes", or the scenarios redesigned (e.g. sudden events,
  multiple crowds competing for one drone, tight batteries) until there is headroom. This is what a senior would do before
  spending weeks on training.

### P3. Re-architect the AI (owner's decision on the rule D-24)
- **Option A, hierarchical (recommended for performance):** the AI decides the *mission-level* choices every 30 s (which area
  or crowd to serve next, altitude band, how much battery to spend now), and the computed layers (P1 radio allocation, a local
  placement search) execute them. The AI still learns by itself; it is never told the answer to its own decision. But it relies
  on computed sub-layers, which is a different reading of "the AI learns by itself" and must be the owner's call.
- **Option B, end-to-end (respecting the rule literally):** keep the AI flying directly, but give it realistic measurements a
  base station really has (per-user signal-quality reports, CQI) and train with an **asymmetric critic** (the critic sees true
  positions during training only; the flying policy never does), SAC or a recurrent network, and many more samples. Accept that
  it may stay below the search pilots on still crowds.

### P4. Exploit the energy physics (days)
Forward flight at about 10 m/s costs less than hovering. Add **B7, a loitering pilot** that circles the best spot at the
minimum-power speed. In battery-limited scenarios this may serve more user-seconds per Wh than hovering pilots. It is a good
baseline and a good question for RL: can it discover loitering by itself?

### P5. Realism of the radio layer (later)
Time-domain scheduling (serve users over time with proportional-fair scheduling instead of all users every second), an antenna
pattern, imperfect SIC, and the "drone does not know where people are" observation. These matter for credibility and for the
real-world gap (Chapter 11).

### P6. Then dynamic RL (Gate G5) with 5 seeds, on the regimes P2 found to have headroom.

## 14.4 What this changes in the project story
"NOMA with adaptive power allocation never does worse than OMA and does better where it matters; search solves placement; the
AI's job is anticipation and battery strategy, and we measured how much room that job has before training it." That is a
defensible, senior-level contribution, honest about where learning helps.

## 14.5 The independent review
A second agent, briefed as a senior wireless and RL engineer, read the code, the results and this draft. It was asked to find
errors and better ideas, not to agree. I checked each of its claims against the code before accepting it.

**Confirmed as correct.**
- The QoS-aware split alpha* is right, **with N0 meaning the noise power over the pair's bandwidth** (the code computes noise as
  density x bandwidth). The case alpha* >= 1 (the weak user needs all the power, the strong user gets nothing) must be handled
  explicitly: then the pair falls back to OMA or the weak user is not served.
- A split with alpha < 0.5 is valid in theory (the decoding order comes from the channel gains, not from the power), but practical
  receivers usually assume alpha >= 0.5. Report how often alpha* < 0.5 happens and test a clamp as a sensitivity check.
- SIC is always feasible when roles follow gain, so **`sic_feasible` can never fail in the current code**. A real failure needs
  imperfect SIC or errors in the gain estimates. Already noted in Chapter 4; now listed as a known limitation.

**Errors and gaps the review found in the draft.**
1. **"Hybrid NOMA never does worse than OMA" is a tautology**, and the comparison is unfair if OMA stays unoptimised. A fair H3
   optimises OMA as well (a QoS-aware bandwidth and power split inside each pair, and a "serve only the strong user" option). The
   finding to report is the *size* of the gap between optimised NOMA and optimised OMA. Also: the per-pair choice must check the
   strong user's own minimum rate, and the number of users must be even (an unpaired user gets nothing under NOMA).
2. **The 0.686 ceiling ignores flight time.** It assumes the drone is instantly at the best spot, but flying there from the centre
   takes up to about 94 s at 15 m/s. The real headroom over B3 on still crowds is below 0.03.
3. **The AI's information was never checked.** Verified in the code: the observation (`OBS_GROUPS` in `uav_env.py`) has **no
   obstacle map, no demand information** (only the rescue map) and no motion information (one heatmap per frame). The search
   pilots B3-B6 evaluate spots with the true positions *and* the obstacles. So the plateau may be an **information ceiling**, not
   an RL failure. This is the most important point of the review.
4. **A bigger NOMA lever than the split:** every pair gets the same power p = 2P/N. Greedy admission (give each pair the minimum
   power it needs, admit the cheapest pairs first until the power runs out) serves more users, for NOMA and OMA alike.
5. `gamma: 0.995` in `config.yaml` is commented "300 steps", but a game is now 30 decisions (verified). The still-crowd task is
   close to a one-shot choice.
6. Training uses only 100 maps. Draw training scenarios from fresh seeds (1,000+), kept disjoint from validation and test.
7. Credibility: a regime grid (battery x mobility x power) with paired CIs, a correction for many comparisons (Holm), the test set
   read once, and H3 with four schemes (OMA equal split, OMA optimised, NOMA fixed, NOMA hybrid).
8. P5 (time scheduling, antenna patterns) should mostly be cut: it changes the definition of coverage and would invalidate every
   earlier result. Only imperfect SIC is worth its half day.

**Where I disagree with the reviewer.**
- It recommends a **spatial action head** (the network outputs a probability over map cells plus an offset inside the cell). That
  is technically sound and common, but in effect it is the **"choose one of 100 cells" design the owner rejected** (D-24). It is not
  adopted without the owner's explicit approval.
- It says that with D-24 as written G4 "cannot be won by design", because the baselines use privileged information. Plausible, but
  not shown yet. The information-matched baseline (step 1 below) will tell.

## 14.6 The agreed plan (draft and review combined), in order
| # | Step | Why | Effort |
|---|---|---|---|
| 1 | **Information-matched baseline "B3-obs"**: grid search that uses only what the AI sees (density map cells, no obstacles, no classes); also compare the AI's training and validation scores | decides whether the plateau comes from missing information or from RL itself | 1 day. **Done 10-21** (Chapter 8.7): half information, half learning |
| 2 | **Hybrid adaptive NOMA**: QoS-aware split, per-pair NOMA/OMA choice checking both users' minimum rates, an *equally optimised* OMA, greedy power admission across pairs; added as new `access` options so old results stay reproducible; tests; re-run H3 with four schemes and the baseline tables | removes the 232 kbps ceiling and makes H3 fair and strong | 3-4 days |
| 3 | **Clairvoyant oracle on moving crowds** at a battery that binds: a receding-horizon B6 that knows the next 30-60 s of positions; later report how much of the oracle's lead over B6 the AI closes | measures whether H2 has anything to win before more training | 2-3 days |
| 4 | **Give the AI the raw measurements it lacks (within D-24):** an obstacle map, a demand map, the previous frame; fresh training seeds; fix gamma | the cheapest fixes that stay inside the owner's rule | 3-4 days |
| 5 | **B7 loitering pilot** (circles at the cheapest speed) with an energy-parameter sensitivity sweep; metric: served user-seconds at a binding battery | tests a real physics insight; cheap | 1-2 days |
| 6 | Owner's decisions (14.7), then **dynamic RL (Gate G5)** on the regimes with headroom, 5 seeds, regime grid | the actual research question | 1.5-2 weeks |
| 7 | Imperfect SIC as an ablation | makes the SIC check meaningful | 0.5 day |

About 4-5 weeks in total, realistic for a final-year project if time scheduling, antenna patterns and multi-UAV stay out.
Steps 1 and 2 need no decision from the owner beyond approving the plan; step 4's new observations are raw measurements and fit
D-24; steps 3 and 5 add pilots, not hints.

## 14.7 Decisions needed from the owner
1. **Asymmetric critic:** may the critic (the part of PPO that only judges during training and is thrown away afterwards) see true
   user positions during training? The flying policy never would. Both reviewers think this keeps the spirit of D-24 if disclosed.
2. **Spatial action head:** allowed or not (it resembles the rejected 100-cell menu)?
3. **Hierarchical design (Option A)** for the dynamic stage, where the AI chooses mission-level goals and computed layers carry
   them out: allowed or not?
4. **Relax G4** and move on to moving crowds after steps 1 and 4, whatever the still-crowd score?

## 14.8 Progress
- **Step 1 done (2026-10-21), Chapter 8.7.** About half of the AI's gap to B3 is missing information and half is the AI not
  using what it sees (it underfits even on its training scenarios). A search with only the AI's maps reaches 0.605, level
  with B2, so G4 is reachable in principle. Consequences for step 4: remove the map cap and give the AI a finer map or a
  count of people; an obstacle map is the least promising input. The learning half points at the action design (the AI aims
  at the densest cell instead of a spot between crowds), which is exactly where owner decisions 1 and 2 in 14.7 matter.
- **Owner's decisions (2026-10-21), D-38:** asymmetric critic yes; cell action head no; hierarchical later; move to moving
  crowds after tracks 1 and 2.
- **Second review before tracks 1 and 2 (2026-10-21).** Before writing code I sent the concrete designs for adaptive NOMA (step 2)
  and the better learner (step 4) to a new reviewer agent, then questioned its answers. It ran the real code on 5 scenarios and
  found that my NOMA design was flawed (per-pair choice decided in advance, wrong admission order, a split formula that assumed
  equal power per pair) and that a privileged critic does little in PPO but a lot in SAC. One snapshot of its measurements
  (best spot per scheme, 5 validation scenarios, 20 dBm): today's NOMA 0.56-0.80, today's OMA 0.46-0.74, optimised OMA
  0.68-0.91, adaptive NOMA 0.75-0.96 (0.71-0.90 with imperfect SIC). These are a reviewer's quick check, not results; the real
  runs are in Track 1. The agreed designs are D-39, D-40 and D-41; both tracks now run in parallel.

