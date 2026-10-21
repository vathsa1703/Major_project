# Chapter 12. Glossary

Plain-word meanings first; the technical term in brackets where it helps.

| Term | Meaning |
|---|---|
| **UAV** | Unmanned aerial vehicle: a drone. |
| **UAV-BS, aerial base station** | A drone carrying a mobile-network radio, acting as a temporary phone tower. |
| **Downlink** | Data going from the tower (the drone) to the phones. |
| **NOMA** | Non-orthogonal multiple access: two (or more) users share the same frequency slice at the same time; the transmitter mixes their signals with different power levels (superposition coding). |
| **OMA** | Orthogonal multiple access: every user gets a separate slice (here frequency slices, FDMA). The traditional way. |
| **FDMA** | Frequency-division multiple access: the bandwidth is cut into separate slices, one per user. |
| **SIC** | Successive interference cancellation: the strong user first decodes and removes the weak user's message, then decodes its own. |
| **SIC feasibility** | SIC only works if the strong user can decode the weak user's message at least as well as the weak user can. |
| **Pairing** | Choosing which two users share a slice in NOMA. Ours: strongest with weakest ("extreme") or random. |
| **Power split** | How the pair's power is divided: here 80% to the weak user, 20% to the strong user. |
| **SINR** | Signal-to-interference-plus-noise ratio: how strong the wanted signal is compared with everything else. Higher means faster data. |
| **Rate, data speed** | Bits per second a user gets: bandwidth x log2(1 + SINR) (Shannon). |
| **Minimum rate** | The speed a user needs to count as served; depends on their class (rescue, video, voice, iot, normal). |
| **Coverage** | The share of users who get at least their minimum rate. The main score in this project. |
| **coverage_full** | Coverage averaged over the whole 300 s, counting zero after the battery runs out. |
| **Sum rate, total speed** | All users' rates added together. |
| **Spectral efficiency** | Sum rate divided by bandwidth (bit/s per Hz). |
| **Fairness (Jain's index)** | 1 if everyone gets the same speed, lower if speeds are uneven. |
| **Outage** | A user not reaching their minimum rate. "Rescue outage" is the share of rescue users in outage. |
| **LoS / NLoS** | Line of sight (a clear straight path between drone and phone) / non-line of sight (blocked). |
| **Path loss** | How much the signal weakens on the way, in decibels. |
| **FSPL** | Free-space path loss: the weakening with distance alone. |
| **Air-to-ground channel (Al-Hourani model)** | A formula for the probability of LoS from the elevation angle, plus extra loss for LoS and NLoS links. It creates a best altitude. |
| **Elevation angle** | How high the drone appears above the horizon from the user's position. |
| **Fading (Rician / Rayleigh)** | Quick random ups and downs of the signal. Rician for LoS links, Rayleigh for NLoS. |
| **dBm, dB** | Logarithmic units: 30 dBm = 1 W, 20 dBm = 0.1 W; +3 dB is about double. |
| **Bandwidth** | The width of the frequency range used, in Hz. More bandwidth means more speed. |
| **Noise figure** | How much noise the receiver adds, in dB. |
| **Rotary-wing propulsion power (Zeng model)** | The formula for the power a multicopter needs at a given speed. Hovering is not the cheapest; moderate forward flight costs less. |
| **Hover** | Staying in one place in the air. |
| **Backhaul** | The drone's own link back to the main network. |
| **Scenario** | One invented disaster situation (crowd, buildings, movement), identified by its seed. |
| **Seed** | The number that makes the random generator produce the same scenario every time. |
| **Train / validation / test split** | Scenarios for learning (seeds 0-99), for choosing between models (100-119), and for the final honest score (120-139, used once). |
| **Profile** | A named set of setting changes (e.g. `hard`, `rl_static`) applied on top of `config.yaml`. |
| **Domain randomisation** | Drawing different scenario settings for every episode, so the AI cannot memorise one map. |
| **Synthetic data** | Data produced by our simulator, not measured in the real world. |
| **Gymnasium environment, the game** | The standard Python interface (`reset`, `step`) that every pilot plays through. |
| **Episode** | One full game of one scenario (300 s or until the battery is empty). |
| **Observation, state** | What the pilot sees each step (here 211 numbers: own position, battery, previous scores, two crowd maps). |
| **Action** | What the pilot decides each step (velocity or a target spot, altitude, power). |
| **Reward** | The score signal the AI learns from (here the coverage, optionally minus an energy cost). |
| **Policy** | The pilot's strategy: a rule or a neural network that turns observations into actions. |
| **Baseline** | A simple non-learning pilot used for comparison (B0-B6). |
| **Heuristic** | A simple rule of thumb, such as "fly to the biggest crowd". |
| **k-means** | A method that groups points into k clusters around centres (used by B2). |
| **Grid search** | Trying every spot on a grid and keeping the best (B3, B6). |
| **PSO** | Particle swarm optimisation: many candidate solutions move towards the best found so far (B4). |
| **Privileged information** | Facts the baselines may use but the AI may not, such as exact user positions. |
| **Reinforcement learning (RL)** | Learning by trial and error from a score, without being told the right answer. |
| **PPO** | Proximal Policy Optimization: the RL method used here (from Stable-Baselines3). |
| **SAC** | Soft Actor-Critic: another RL method, the plan's second choice. |
| **Neural network, MLP, CNN** | The AI's "brain". MLP: layers of numbers. CNN: reads a grid as a picture (convolutions). |
| **Exploration noise** | Random wobble added to the AI's actions during training so it tries new things. Too much hides the effect of its own choices. |
| **Annealing** | Shrinking something (here the exploration noise) step by step during training. |
| **Curriculum** | Training in stages from easy to hard (still crowd, moving crowd, altitude, power, battery, NOMA). |
| **Waypoint control** | The AI says "fly to this spot" instead of "fly this fast". |
| **Decision hold** | The AI decides once every 10 s and its choice is repeated in between. |
| **Checkpoint** | A saved copy of the AI during training. |
| **Gate (G1-G7)** | A check that must pass before the next layer of the project starts. |
| **Hypothesis (H1-H4)** | A claim the project tests. |
| **Confidence interval (95% CI)** | The range in which the true average very probably lies. |
| **Paired comparison** | Comparing two pilots scenario by scenario on the same scenarios, then averaging the differences. Fairer than comparing two averages. |
| **Significant (`*`)** | The confidence interval of the difference does not include zero, so the difference is not luck. |
| **Ablation** | Removing or changing one part to see how much it matters. |
| **Sensitivity analysis** | Varying an assumption over its range to see whether conclusions change. |
| **Parity test (MATLAB parity)** | Checking that our Python numbers match an independent MATLAB implementation. |
| **Sim-to-real gap** | The difference between how something performs in simulation and in reality. |
| **Digital twin** | A simulation kept in sync with a real system using live data. This project is not one; it is a simulation-based planning tool. |
| **Software in the loop (SITL)** | Running real control software against a simulated vehicle. |
| **MAVLink** | The standard message protocol for talking to drone autopilots. |
| **SDR** | Software-defined radio: a programmable radio board, used to build NOMA test setups. |
| **CI** | Continuous integration: GitHub automatically runs lint and tests on every change. |
| **Pull request (PR)** | A proposed change that is reviewed and tested before it joins `main`. |
| **Branch protection** | GitHub rules that stop unreviewed or untested code from reaching `main`. |
| **Lint (ruff)** | Automatic style and bug checks on the code. |
| **Coverage gate (test coverage)** | CI fails if the tests exercise less than 80% of the core code. (Not the same "coverage" as user coverage.) |
