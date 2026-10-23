# Literature matrix (draft, every entry to be verified)

**Status rule.** Every entry carries **VERIFY** until a team member has opened the original (publisher page or PDF) and
checked the title, authors, venue, year, DOI and the one-line summary. "Checked online" below means only that the arXiv
abstract page or a repository record was found on 2026-10-23 with this title and these authors; it does **not** mean the paper
was read. Journal volume and page numbers marked "(recalled)" were not confirmed online. Nothing here was invented; where a
detail could not be found it says so.

Numbering matches the References of `report.md`.

## Main matrix (25 papers)

| # | Title | Authors | Venue, year | DOI / URL | Relevance (one line) | What we take or compare | Status |
|---|---|---|---|---|---|---|---|
| 1 | Optimal LAP altitude for maximum coverage | A. Al-Hourani, S. Kandeepan, S. Lardner | IEEE Wireless Commun. Lett., vol. 3, no. 6, pp. 569-572, 2014 | 10.1109/LWC.2014.2342736 | Closed-form LoS probability vs elevation angle; optimal platform altitude | Our channel model and its parameters (a = 9.61, b = 0.16, eta 1/20 dB); **original not read** (book 10.2): parameters taken from secondary sources [27], [28] | VERIFY (DOI found in a repository record; volume/pages from the book's assumptions table) |
| 2 | Energy minimization for wireless communication with rotary-wing UAV | Y. Zeng, J. Xu, R. Zhang | arXiv 2018; IEEE Trans. Wireless Commun., 2019 (vol. 18, no. 4, pp. 2329-2345 recalled) | arXiv:1804.02238 | Rotary-wing propulsion power model; forward flight cheaper than hover | Our energy model; formula and constants read and verified (book 10.2); our own 20 N drone derived from it | VERIFY (arXiv checked online; journal details recalled) |
| 3 | Energy-efficient UAV communication with trajectory optimization | Y. Zeng, R. Zhang | arXiv 2016; IEEE Trans. Wireless Commun., 2017 (vol. 16, no. 6, pp. 3747-3760 recalled) | arXiv:1608.01828 | Fixed-wing energy model; optimised circular trajectory | Motivation for the circling pilot B7 (note: fixed-wing, unlike our rotary-wing drone) | VERIFY (arXiv checked online; journal details recalled) |
| 4 | A tutorial on UAVs for wireless networks: applications, challenges, and open problems | M. Mozaffari, W. Saad, M. Bennis, Y.-H. Nam, M. Debbah | IEEE Commun. Surveys Tuts., 2019 (per arXiv comment) | arXiv:1803.00680 | Broad survey of UAV placement, trajectory, energy, channel | Problem framing in Chapters 1-2 | VERIFY (arXiv checked online) |
| 5 | Efficient 3-D placement of an aerial base station in next generation cellular networks | R. I. Bor-Yaliniz, A. El-Keyi, H. Yanikomeroglu | IEEE ICC 2016 (venue not confirmed online) | arXiv:1603.00300 | 3D placement of one aerial base station as an optimisation problem | Our search pilots (B3, B4, B6) belong to this family; used as baselines | VERIFY |
| 6 | 3D placement of an unmanned aerial vehicle base station (UAV-BS) for energy-efficient maximal coverage | M. Alzenad, A. El-Keyi, F. Lagum, H. Yanikomeroglu | arXiv 2017; journal version not confirmed (IEEE WCL recalled) | arXiv:1705.03415 | Place a UAV-BS to cover most users with least power | Coverage as the objective; placement baselines | VERIFY |
| 7 | Placement optimization of UAV-mounted mobile base stations | J. Lyu, Y. Zeng, R. Zhang, T. J. Lim | IEEE Commun. Lett., vol. 21, no. 3, pp. 604-607, 2017 (from a citing paper) | arXiv:1612.01047 | Spiral placement of several UAV base stations to cover all users | Multi-UAV future work (H4) | VERIFY (DOI not found) |
| 8 | Non-orthogonal multiple access (NOMA) for cellular future radio access | Y. Saito, Y. Kishiyama, A. Benjebbour, T. Nakamura, A. Li, K. Higuchi | IEEE VTC Spring 2013 | 10.1109/VTCSpring.2013.6692652 | Power-domain NOMA with SIC for cellular downlink | NOMA principle (Section 3.4) | VERIFY (title appears in two variants in records; DOI from a patent-office record) |
| 9 | Impact of user pairing on 5G nonorthogonal multiple-access downlink transmissions | Z. Ding, P. Fan, H. V. Poor | IEEE Trans. Veh. Technol., vol. 65, no. 8, pp. 6010-6023, 2016 | arXiv:1412.2799 | Fixed-power NOMA prefers pairing very different channels; cognitive-radio NOMA protects the weak user | Our "extreme" pairing and the rate-protecting idea behind adaptive NOMA | VERIFY |
| 10 | UAV communications based on non-orthogonal multiple access | Y. Liu, Z. Qin, Y. Cai, Y. Gao, G. Y. Li, A. Nallanathan | IEEE Wireless Commun., 2019 | arXiv:1809.05767 | Framework for NOMA-based UAV networks | Context for H3 | VERIFY |
| 11 | Multiple access for mobile-UAV enabled networks: joint trajectory design and resource allocation | F. Cui, Y. Cai, Z. Qin, M. Zhao, G. Y. Li | IEEE Trans. Commun., 2019 | Accepted manuscript at QMUL repository (handle 123456789/57662); DOI not found; no arXiv version found | Joint trajectory and resource allocation for OMA and NOMA, max-min fairness | A fair OMA reference must be optimised too (our `oma_opt`). Note: the reviewer called this "Qin et al."; Qin is the third author | VERIFY |
| 12 | Secure transmission via power allocation in NOMA-UAV networks with circular trajectory | X. Chen, Z. Yang, N. Zhao, Y. Chen, J. Wang, Z. Ding, F. R. Yu | IEEE Trans. Veh. Technol., vol. 69, no. 9, pp. 10033-10045, 2020 | 10.1109/TVT.2020.3005120 | NOMA power allocation for a UAV flying a circle, with a secrecy constraint | Circling (B7) combined with NOMA; their goal (secrecy) differs from ours | VERIFY (from a university repository record) |
| 13 | NOMA in UAV-aided cellular offloading: a machine learning approach | R. Zhong, X. Liu, Y. Liu, Y. Chen | arXiv 2020 | arXiv:2011.14776 | k-means + DQN for UAV 3D trajectory and power with NOMA users | Shows RL for UAV-NOMA is already published (book 11.2) | VERIFY (arXiv checked online) |
| 14 | AdaptSky: a DRL based resource allocation framework in NOMA-UAV networks | A. Benfaid, N. Adem, B. Khalfi | arXiv 2021 | arXiv:2107.01004 | Deep RL for NOMA power allocation and UAV placement | Same; compare its baselines with ours | VERIFY (arXiv checked online) |
| 15 | Trajectory design and power control for multi-UAV assisted wireless networks: a machine learning approach | X. Liu, Y. Liu, Y. Chen, L. Hanzo | arXiv 2018; journal version not confirmed (IEEE TVT recalled) | arXiv:1812.07665 | ML for multi-UAV trajectory and power with moving users | RL-for-UAV context; H4 | VERIFY |
| 16 | Efficient 3D aerial base station placement considering users mobility by reinforcement learning | R. Ghanavi, E. Kalantari, M. Sabbaghian, H. Yanikomeroglu, A. Yongacoglu | IEEE WCNC 2018 (per arXiv comment) | arXiv:1801.07472 | Q-learning placement of an aerial base station for moving users | Closest to our G5 task; compare its baselines | VERIFY (arXiv checked online) |
| 17 | Meta-reinforcement learning for trajectory design in wireless UAV networks | Y. Hu, M. Chen, W. Saad, H. V. Poor, S. Cui | arXiv 2020 (no journal reference listed) | arXiv:2005.12394 | Meta-RL lets an energy-limited UAV adapt its trajectory to new demand quickly | Adapting to unseen scenarios; our fresh-seed training | VERIFY (arXiv checked online) |
| 18 | Multi-agent reinforcement learning with action masking for UAV-enabled mobile communications | D. Rizvi, D. Boyle | arXiv 2023 | arXiv:2303.16737 | MARL with action masking for UAV base stations | Action design; H4 | VERIFY (arXiv checked online) |
| 19 | Two-layer reinforcement learning-assisted joint beamforming and trajectory optimization for multi-UAV downlink communications | R. Wang, E. M. Ghoura, O. Alhussein, Y. Yang, J. Ren, S. Xu, S. Muhaidat | arXiv, Jan. 2026 (v2 Apr. 2026) | arXiv:2601.12659 | Two time scales: fast GNN beamforming, slow multi-agent RL trajectories | Supports our "split by time scale" design (Section 6.1) and the hybrid timing AI | VERIFY (arXiv checked online) |
| 20 | Proximal policy optimization algorithms | J. Schulman, F. Wolski, P. Dhariwal, A. Radford, O. Klimov | arXiv 2017 | arXiv:1707.06347 | PPO | Our main learner | VERIFY (arXiv checked online) |
| 21 | Soft actor-critic: off-policy maximum entropy deep reinforcement learning with a stochastic actor | T. Haarnoja, A. Zhou, P. Abbeel, S. Levine | ICML 2018 | arXiv:1801.01290 | SAC | Our second learner (G4 Track 2) | VERIFY (arXiv checked online) |
| 22 | Asymmetric actor critic for image-based robot learning | L. Pinto, M. Andrychowicz, P. Welinder, W. Zaremba, P. Abbeel | arXiv 2017 | arXiv:1710.06542 | Critic sees the full state during training, actor sees only observations | Our training-only privileged critic (D-38) | VERIFY (arXiv checked online) |
| 23 | Stable-Baselines3: reliable reinforcement learning implementations | A. Raffin, A. Hill, A. Gleave, A. Kanervisto, M. Ernestus, N. Dormann | J. Mach. Learn. Res., vol. 22, no. 268, pp. 1-8, 2021 | https://jmlr.org/papers/v22/20-1364.html | The RL library we use | Implementation of PPO and SAC | VERIFY |
| 25 | Deep reinforcement learning that matters | P. Henderson, R. Islam, P. Bachman, J. Pineau, D. Precup, D. Meger | AAAI 2018 | arXiv:1709.06560 | Seed variance and reporting in deep RL | Several runs per version, pass marks fixed in advance | VERIFY (arXiv checked online) |
| 26 | Deep reinforcement learning at the edge of the statistical precipice | R. Agarwal, M. Schwarzer, P. S. Castro, A. Courville, M. G. Bellemare | NeurIPS 2021 | arXiv:2108.13264 | Interval estimates instead of point scores for RL results | Confidence intervals and paired comparisons | VERIFY (arXiv checked online) |

## Other references used in the report

| # | Reference | Why it is cited | Status |
|---|---|---|---|
| 24 | M. Towers et al., "Gymnasium: a standard interface for reinforcement learning environments", arXiv:2407.17032, 2024 | The environment interface | VERIFY (arXiv checked online) |
| 27 | S. A. W. Shah, T. Khattab, M. Z. Shakir, M. G. Khafagy, M. O. Hasna, "Small cell association with networked flying platforms: novel algorithms and performance bounds", arXiv:1802.01117, 2018 | Secondary source in which the Al-Hourani formulas and values were checked (book 10.2) | VERIFY (arXiv checked online) |
| 28 | S. A. W. Shah, T. Khattab, M. Z. Shakir, M. O. Hasna, "A distributed approach for networked flying platform association with small cells in 5G+ networks", arXiv:1705.03304, 2017 | Second secondary source for the Al-Hourani values (book 10.2) | VERIFY (arXiv checked online) |
| 29 | S. Holm, "A simple sequentially rejective multiple test procedure", Scand. J. Statist., 6(2), 65-70, 1979 | Holm correction (Table 5.3) | VERIFY (recalled, not checked online) |
| 30 | R. Jain, D. Chiu, W. Hawe, "A quantitative measure of fairness and discrimination for resource allocation in shared computer systems", DEC TR-301, 1984 | Jain's fairness index | VERIFY (recalled, not checked online) |
| 31 | J. Kennedy, R. Eberhart, "Particle swarm optimization", Proc. IEEE ICNN, 1995 | Pilot B4 | VERIFY (recalled, not checked online) |

## Found in the book but not in the matrix
- **HAL hal-04762084** (a NOMA-DQN battery-aware path-planning paper, book 11.2). The HAL page could not be opened on
  2026-10-23 (bot protection), so title, authors and venue are unknown. Not cited until a person retrieves it.
- **"A disaster-area UAV base-station study with NOMA pairing and power splitting"** (book 11.2): no title or link was recorded
  in the book. Not cited.

## Still to find (gaps in the matrix)
- A source for the regulatory altitude limit (India's Drone Rules 2021 / DGCA airspace map; commonly 120 m above ground for
  routine flights). Needed for Section 6.3 and future work item 5.
- A citable source (news or operator report) for tethered drone cell sites after disasters (book 11.3 mentions AT&T's "Flying
  COW" after Hurricane Maria, from 2017-2018 news).
- A source on NOMA standardisation in LTE ("MUST", Release 14), mentioned in book 11.3 from one survey.
- A paper that, like this project, compares RL against strong search baselines with paired statistics for UAV base stations
  (to check whether contribution 2 of book 11.2 is really new).
