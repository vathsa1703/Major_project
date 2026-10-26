# What we have built so far, in plain words

*UAV-NOMA Disaster Network Planning Simulator. Status on 26 October 2026. Full details: the project book (docs/book).*

## The idea in one paragraph
After a disaster, phone towers are often down. A drone can carry a small "flying phone tower" and give survivors a signal.
Our project is a **computer simulation** of that situation. It answers: *where should the drone fly, at what height, and how
should it share its signal, so that as many survivors as possible stay connected before its battery runs out?* The drone
shares its signal using **NOMA**, a newer technique that lets two people use the same slice of radio at the same time. We
compare simple, hand-written ways of flying the drone with an **AI that learns to fly by itself**.

## What is built
| Part | What it is |
|---|---|
| **Disaster simulator** | A virtual disaster area: up to 1,500 survivors in groups, collapsed buildings that block signals, people who walk, suddenly move or switch between distant sites, a drone with a realistic battery |
| **Radio model** | How strong the signal is at each person (from a published model), and how many people get a good enough connection with NOMA or with the older technique (OMA) |
| **A real place** | A 2 x 2 km piece of Kathmandu with its 12,061 real buildings (OpenStreetMap) and a 3-D line of sight from every phone to the drone |
| **Dataset** | Over 800,000 rows of results, also as an Excel file |
| **Programmed pilots** | Simple rules for flying the drone, from "stay parked in the middle" to "search every spot", "circle to save battery", "leave for the new site at the right moment" and "measure, then search" |
| **The AI pilot** | A program that learns to fly by trial and error, seeing only what a real drone could measure |
| **Simulated quadcopter** | A realistic drone model with an autopilot and wind, flying our plans, with a 3D view |
| **Dashboard** | A web page to set up a disaster, fly any pilot, compare them and get a recommended plan |
| **Project book** | 14 chapters, a PDF, charts and animations; every decision recorded |
| **Quality checks** | 505 automatic tests, run on every change on GitHub |

## What we have proven
**1. A drone that moves beats a parked drone (hypothesis H1).** When crowds move, a drone that follows them serves
**74 of every 100 people**; a drone parked in the middle serves **43**.

**2. NOMA beats the older technique (hypothesis H3).** We gave both techniques the same smart tuning, to be fair.
NOMA still serves **3 to 5 more people out of every 100** on the synthetic maps, in every situation we tried, and gives more
total speed. In the easier scenarios it serves **98 of every 100 people**, and almost no rescue workers are left without
signal (0.4%). It still wins when the phone cannot remove the other person's signal perfectly. In the final studies the gap
is **8 to 13 people per 100**, and on the real Kathmandu map it is about twice the synthetic gap for the best pilots.

Chart: [NOMA vs OMA, same tuning for both](../book/figures/8_access_schemes_hard.png)

**3. Circling saves battery.** In our energy model a drone flying slow circles uses less power than one hovering in place.
Circling serves **26% more people per battery charge**, and with a small battery it finishes the mission while a hovering
drone runs out. This holds even when we change the uncertain energy numbers.

**4. The AI learns by itself.** Seeing only rough crowd maps (no exact positions), it went from worse than random to
**0.576**, close to a hand-written pilot that knows more (0.610). It finds the best spot within 30 seconds.

**5. The drone does not need to know exactly where everyone is.** If about **half of the phones** send their GPS position,
refreshed at least every **30 seconds**, the best pilot keeps 98% of what it gets with perfect knowledge; a GPS error of 10 m
or 50 m makes no difference. When people stand in a few dense places, even 1 phone in 20 is enough.

Chart: [coverage vs share of phones reporting](../book/figures/voi_ratio_vs_f.png)

**6. The results hold on a real map.** On the Kathmandu flood scenario (a scenario *based on* the 2024 floods; the crowd is
reconstructed from the map, not real data) the pilots rank exactly as on our invented maps. The best one serves **78 of
every 100 people with NOMA vs 65 with OMA**, and 89 of every 100 people who need rescue are connected.

## What did not work, and what we learned
- **The AI does not beat the best simple pilot anywhere.** Where thinking ahead pays (people switch between sites 2 km
  apart) the full AI was 7-8 points below; an AI that only decides *when to leave* (a programmed pilot steers) tied the bar
  in one design and lost in the other; and when the radio "textbook" is wrong, the AI was not fooled, but a simple "measure,
  then search" pilot still did better. Our breakdown shows why: the AI does not fail at learning; it lacks information, and
  the simple pilots already use the announced schedule very well.
- **The AI does not stay at the best spot.** It finds the best spot and then flies past it. On standing crowds it ended
  about 0.03 below the hand-written pilot, so the first AI checkpoint (gate G4) was not passed. A "move by" steering built
  to fix this did not help on the competing sites.

Picture: [the AI (green line) flies past the best spot; the programmed pilots stay](../book/figures/10_e0_vs_b3_seed105.png)

- **On walking crowds no AI can win.** We built a "fortune-teller" drone that knows where everyone will walk. Even it gains
  only 0.2% over a simple pilot, because the drone (15 m/s) is much faster than people walking (1-3 m/s). This saved us
  two weeks of useless training, and it is a finding in itself: for slow situations, a simple program is enough.
- **We found and closed a hidden flaw** in the simulator: the drone could "shake" on the spot to fake a battery saving.
  It is now fixed, and no earlier result had used it.
- **Flag:** on the Kathmandu map the best pilot flies at about 290 m, far above the roughly 120 m that drone rules usually
  allow. A run capped at 120 m is still to do.

## Where an AI could win, and whether a rule predicts it
We redesigned the scenarios so that **the need for help suddenly jumps between places far apart**: for example a shelter
opens at one site 1-2 km from another. On fresh scenarios (20 per design, never used before), a drone that knows what is
coming serves up to **9 more people out of every 100** than the best simple pilot. The rule we wrote down beforehand (at
least 2 more) is met in **5 of the 9 designs** (7 of 9 had passed on the first, smaller set of scenarios, which is why fresh
scenarios were required), most clearly when the sites are 2 km apart.

| Distance between sites | Sudden switch | Switch over 1 minute | Switch over 3 minutes |
|---|---|---|---|
| 1.0 km | +1.6 | +0.5 | +0.4 |
| 1.5 km | **+5.6** | **+2.9** | +1.2 |
| 2.0 km | **+9.1** | **+7.1** | **+2.9** |

*(More people served out of every 100 by a drone that knows what is coming, compared with the best simple pilot that does
not use the announcement; fresh scenarios.)*

A rule of thumb that predicts this room from distance and timing was then **not confirmed** on 8 new designs (it called
5 of 8 right; it needed 7): drone speed and mission length matter in a way the rule does not capture. A new simple pilot
that picks the right moment to leave (B6dep) became the best simple pilot in all 17 designs.

## What comes next
1. A small new study (approved on 26 October): the drone first **finds** survivors' phones from their signal strength,
   then serves them with NOMA. Its rules are written down before any result.
2. The final evaluation on the untouched test scenarios, and the final report.

## How we work
Every important plan is checked by an independent reviewer first. The rules for every experiment are written down
**before** it runs, so the goalposts never move. Every result is reported, including the ones where the AI loses, and
nothing is called "proven" unless the numbers clearly show it.
