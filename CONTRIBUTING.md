# How we work

1. **Never push to `main`.** It is protected. Start every piece of work on your own branch:
       git checkout main && git pull
       git checkout -b yourname/what-it-does
2. **Commit small and often**, one working thing per commit.
3. **Before pushing**, run both and fix everything they report:
       python -m ruff check .
       python -m pytest -q --cov
4. **Open a pull request** into `main` and fill in the template. CI must be green (lint, tests on Python 3.11
   and 3.12, coverage >= 80% on `make_dataset.py` + `uav_env.py`, and a smoke run of the dataset generator).
5. **The owner reviews and merges.** Only after approval does it go into `main`. Push fixes to the same
   branch. A new push dismisses the old approval.
6. **If the physics or a parameter changes**, the tests change in the same PR, and the source is cited.
7. Stuck for more than 2 hours: message the team.
