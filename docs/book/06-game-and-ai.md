# Chapter 6. The game and the AI

## 6.1 The game (Gymnasium environment)
**Plain words.** The "game" is one scenario played second by second. Each second the pilot (a simple rule or the AI) says how
the drone should move and how strongly it should transmit; the people move; the game computes who is served and how much battery
was used, and gives a score. Every pilot plays the same game with the same scenarios, which is what makes the comparison fair.

**Technically.** `UAVEnv` in `uav_dataset/uav_env.py` is a standard Gymnasium environment (`reset(seed)`, `step(action)` returning
observation, reward, terminated, truncated, info). It passes Gymnasium's environment checker.

```python
env = UAVEnv()                       # options: reward, fading, battery_wh, scenario_seeds, scenario_overrides, obs_groups
obs, info = env.reset(seed=3)        # seed = scenario seed: same seed, same crowd, buildings and movement
obs, reward, terminated, truncated, info = env.step(action)
```

**State of the drone.** Starts at the map centre at 150 m with a full battery. Position stays inside the map and between 50 and
300 m; horizontal speed is capped at 15 m/s, vertical at 5 m/s.

**Action** (4 numbers in [-1, 1]): `[vx, vy, vz, power]`. vx and vy are scaled by 15 m/s (the speed vector is capped at 15 m/s),
vz by 5 m/s; power maps linearly to 0..P_max (never fully off, minimum 1 mW).

**Step.** Move the drone; advance the users one second along their scenario trajectory; compute the channel to every user
(Chapter 4) and the NOMA rates; coverage = share of users at or above their minimum rate; subtract the energy of the step from
the battery.

**Reward.** Each part is reported separately in `info` so reward hacking can be spotted:
- `reward_coverage` = coverage this second (version v1 uses only this);
- `reward_energy` = -0.05 x (energy this step / hovering energy) in version v2;
- `reward_terminal` = -1.0 x (share of users not covered) when the battery runs out.

**End of the episode.** `terminated` when the battery is empty; `truncated` after 300 s.

**Observation** (default 211 numbers, all scaled into [-1, 1]), built from named groups (D-22):

| Group | Numbers | Content |
|---|---|---|
| `pos` | 3 | x / map size, y / map size, altitude scaled between 50 and 300 m |
| `vel` | 3 | own velocity / maximum speed |
| `battery` | 1 | battery left as a fraction |
| `time` | 1 | time as a fraction of 300 s |
| `prev` | 3 | last coverage, last throughput (sum rate / twice the sum of minimum rates, capped at 1), last fairness |
| `heat_all` | 100 | a 10 x 10 map of where users are (share of users per cell x 10, capped at 1) |
| `heat_rescue` | 100 | the same for rescue users only |

`UAVEnv(obs_groups=...)` drops groups; `env.observation(groups)` lets a trained agent ask for the subset it was trained on.

**Other tools in the environment.**
- `evaluate(X, Y, H, power)`: coverage the drone *would* get at candidate spots, for the current users, without changing the game
  (used by the search baselines B3-B6).
- `scenario_seeds=[...]`: when training, `reset()` draws scenarios only from this pool (the training seeds).
- `scenario_overrides={...}`: replace scenario fields (users, clusters, mobility, obstacles, radius, scatter) to build your own.

## 6.2 How the AI controls the drone (wrappers)
`uav_dataset/rl_utils.py`.

**Control modes (`ControlWrapper`).**
| Mode | The AI outputs | Held fixed |
|---|---|---|
| `xy` / `xyz` / `xyzp` | velocity (horizontal / + vertical / + power) | altitude and/or full power |
| `goto` / `gotoz` / `gotozp` | a spot on the map (/ + a target altitude / + power) | altitude and/or full power |

Waypoint ("goto") controls were introduced because velocity-controlled agents drifted away from the crowd (D-19): with a spot as
the action, staying put just means repeating the same spot. The drone flies to the spot at full speed and stops there.

**Decision rhythm (`HoldWrapper`).** The AI decides once every `hold` seconds (default 10, D-20); its choice is re-applied each
second and the rewards of those seconds are added up. A game becomes 30 decisions instead of 300.

**Adapters** let the AI and random play through the same runner as the baselines: `RLPolicy(model, controls, hold, obs_groups)`
and `RandomPolicy(controls)`. `model_settings(path)` reads the settings saved next to a model (D-23); old models without a hold
setting default to deciding every second.

## 6.3 The AI's brain
**Plain words.** The AI is a small neural network. It looks at the observation and outputs an action. PPO (Proximal Policy
Optimization) is the method that adjusts the network after many games so that actions that led to more coverage become more
likely.

**Technically.** Stable-Baselines3 PPO with a Gaussian policy (actions are sampled around the network's output with a learned
"exploration noise" during training; the network's output itself is used at test time). Two network choices (`--policy`):
- `mlp`: two hidden layers of 64 units for the policy and the value function;
- `cnn` (`uav_dataset/rl_net.py`, `CnnMapExtractor`): the two maps are read as a 2-channel picture plus two coordinate channels
  (CoordConv) by two 3 x 3 convolution layers (16 and 32 filters) and a 128-unit layer; the scalar inputs go through a 32-unit
  layer; the two are joined, followed by the 64-64 heads. It adds no information, only a better way to read the maps.

## 6.4 Training (`rl_train.py`)
All settings come from `config.yaml` (`rl:`); flags override them:

| Setting | Value | Meaning |
|---|---|---|
| profile | `rl_static` | 2 x 2 km, 20 dBm, 3-8 obstacles, still crowd, 16 Wh |
| controls | `goto` | the AI chooses where to fly |
| hold_steps | 10 | it decides every 10 s |
| reward | v1 | coverage only (the energy cost is curriculum step 5) |
| total_timesteps | 100,000 decisions | each decision is 10 simulated seconds |
| n_envs | 4 | four scenarios played in parallel |
| n_steps / batch_size / n_epochs | 256 / 256 / 10 | PPO update sizes |
| learning_rate | 0.0003 | |
| gamma / gae_lambda / clip_range | 0.995 / 0.95 / 0.2 | |
| ent_coef | 0 | |
| log_std_init | -1 | starting exploration noise exp(-1) = 0.37 |
| std_end | null | if set (e.g. 0.05), the noise shrinks linearly to it (D-27) |
| norm_reward | true | rewards are rescaled (episode returns are about 150) |
| policy / obs_groups | mlp / all | |
| val_eval_every_steps / val_eval_scenarios | 20,000 / 8 | progress check on validation scenarios during training |
| checkpoint_every_steps | 10,000 | |

Training uses only training seeds 0-99 (D-18). During training it prints `VAL @ <steps>: coverage_full ...` on the first eight
validation scenarios, logs every reward part separately (TensorBoard tags `reward/coverage`, `reward/energy`, `reward/terminal`,
`val/coverage_full`), saves checkpoints and finally `results/rl/<name>/model.zip` with `config.json`.

```
pip install -r requirements-rl.txt
python rl_train.py --name my_run                              # defaults from config.yaml
python rl_train.py --policy cnn --std_end 0.05 --name e6      # flags override
```

Speed on the owner's laptop: about 1,000 simulated seconds per second plugged in, about 160 on battery; with the 10-second hold,
about 155 decisions per second for one run alone.

## 6.5 Evaluation and pictures
- `rl_eval.py --model <zip> --split val` plays the model, random and the chosen baselines on the same scenarios of a split and
  prints mean +/- 95% CI and paired differences (Chapter 7 explains the statistics). Test seeds are for the end only.
- `view_run.py` plays one scenario with one pilot and saves a GIF and the last frame; `compare_run.py` puts several pilots on one
  scenario in one picture (coverage over time plus each flight path).

```
python view_run.py --seed 9 --users 600 --clusters 4 --mobility surge --obstacles 6 --policy B2
python compare_run.py --seed 105 --profile rl_static --policies random,B2,B3,ppo --model results/rl/<name>/model.zip
```

## 6.6 Curriculum (from the plan)
1. Move only, still crowd (current, Gate G4).
2. Moving crowds.
3. Add altitude.
4. Add power.
5. Battery-aware reward (v2).
6. NOMA grouping and power split as decisions.
Each step must work before the next is switched on.
