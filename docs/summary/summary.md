# What we have built so far, in plain words

*UAV-NOMA Disaster Network Planning Simulator. Status on 22 October 2026. Full details: the project book (docs/book).*

## The idea in one paragraph
After a disaster, phone towers are often down. A drone can carry a small "flying phone tower" and give survivors a signal.
Our project is a **computer simulation** of that situation. It answers: *where should the drone fly, at what height, and how
should it share its signal, so that as many survivors as possible stay connected before its battery runs out?* The drone
shares its signal using **NOMA**, a newer technique that lets two people use the same slice of radio at the same time. We
compare simple, hand-written ways of flying the drone with an **AI that learns to fly by itself**.

## What is built
| Part | What it is |
|---|---|
| **Disaster simulator** | A virtual disaster area: up to 1,500 survivors in groups, collapsed buildings that block signals, people who walk or suddenly move, a drone with a realistic battery |
| **Radio model** | How strong the signal is at each person (from a published model), and how many people get a good enough connection with NOMA or with the older technique (OMA) |
| **Dataset** | Over 800,000 rows of results, also as an Excel file |
| **8 programmed pilots (B0-B7)** | Simple rules for flying the drone, from "stay parked in the middle" to "search every spot" and "circle to save battery" |
| **The AI pilot** | A program that learns to fly by trial and error, seeing only what a real drone could measure |
| **Dashboard** | A web page to set up a disaster, fly any pilot, compare them and get a recommended plan |
| **Project book** | 14 chapters, a PDF, charts and animations; every decision recorded |
| **Quality checks** | 315 automatic tests, run on every change on GitHub |

## What we have proven
**1. A drone that moves beats a parked drone (hypothesis H1).** When crowds move, a drone that follows them serves
**74 of every 100 people**; a drone parked in the middle serves **43**.

**2. NOMA beats the older technique (hypothesis H3).** We gave both techniques the same smart tuning, to be fair.
NOMA still serves **3 to 5 more people out of every 100**, in every situation we tried, and gives more total speed. In the
easier scenarios it serves **98 of every 100 people**, and almost no rescue workers are left without signal (0.4%). It
still wins when the phone cannot remove the other person's signal perfectly.

Chart: [NOMA vs OMA, same tuning for both](../book/figures/8_access_schemes_hard.png)

**3. Circling saves battery.** In our energy model a drone flying slow circles uses less power than one hovering in place.
Circling serves **26% more people per battery charge**, and with a small battery it finishes the mission while a hovering
drone runs out. This holds even when we change the uncertain energy numbers.

**4. The AI learns by itself.** Seeing only rough crowd maps (no exact positions), it went from worse than random to
**0.576**, close to a hand-written pilot that knows more (0.610). It finds the best spot within 30 seconds.

## What did not work, and what we learned
- **The AI does not stay at the best spot.** It finds the best spot and then flies past it. On standing crowds it ended
  about 0.03 below the hand-written pilot, so the first AI checkpoint (gate G4) was not passed. The fix ("move by" steering
  and longer training) is planned for the next stage.

Picture: [the AI (green line) flies past the best spot; the programmed pilots stay](../book/figures/10_e0_vs_b3_seed105.png)

- **On walking crowds no AI can win.** We built a "fortune-teller" drone that knows where everyone will walk. Even it gains
  only 0.2% over a simple pilot, because the drone (15 m/s) is much faster than people walking (1-3 m/s). This saved us
  two weeks of useless training, and it is a finding in itself: for slow situations, a simple program is enough.
- **We found and closed a hidden flaw** in the simulator: the drone could "shake" on the spot to fake a battery saving.
  It is now fixed, and no earlier result had used it.

## Where we are now: finding where an AI can win
We redesigned the scenarios so that **the need for help suddenly jumps between places far apart**: for example a phone
tower is repaired at one site and a shelter opens at another, 1-2 km away. Results (12 scenarios per design, still to be
confirmed on fresh scenarios): a drone that thinks ahead could serve **up to 11 more people out of every 100**, compared with 0.2 for
walking crowds. The rule we wrote down beforehand (at least 2 more) is met in 7 of the 9 designs, most clearly when the
sites are 2 km apart.

| Distance between sites | Sudden switch | Switch over 1 minute | Switch over 3 minutes |
|---|---|---|---|
| 1.0 km | **+2.5** | +0.9 | +0.5 |
| 1.5 km | **+7.2** | **+3.9** | +2.0 (just) |
| 2.0 km | **+10.8** | **+9.8** | **+5.6** |

*(More people served out of every 100 by a drone that knows what is coming, compared with the best simple pilot.)*

## What comes next
1. Finish this check, repeat it on fresh scenarios, and add the strongest simple pilot (one that also uses announced
   schedules).
2. **Train the AI on these new scenarios** (the main experiment, about two weeks).
3. Disaster events (rising flood, aftershock), then realism (wind, GPS errors), then the final evaluation and report.
4. Last: a realistic 3D simulated drone flying with our controller.

## How we work
Every important plan is checked by an independent reviewer first. The rules for every experiment are written down
**before** it runs, so the goalposts never move. Every result is reported, including the ones where the AI loses, and
nothing is called "proven" unless the numbers clearly show it.
