# The UAV-NOMA Project Book

This book records everything the project has done, from the first run of the dataset generator to the latest experiment:
what was built, why each decision was taken, what came out (with the real numbers), what went wrong, and what is still open.
It is written so that a new team member, the guide, or an examiner can follow the whole story without the chat history.

**PDF version.** [`UAV-NOMA-Project-Book.pdf`](UAV-NOMA-Project-Book.pdf), rebuilt with `python docs/book/build_pdf.py`.

**How it is kept up to date.** After every step of work (a new feature, an experiment, a decision, a merge) the relevant
chapters are updated in the same pull request: the journal gets a dated entry, the decision log gets a new numbered decision,
and results go into the results chapters with their exact numbers. Old entries are never rewritten to look better: if a result
turned out wrong, a later entry says so.

**Reading guide.** Each technical idea is explained twice: first in plain words, then in the scientific terms you will need in
the report and the viva. Chapter 12 is a glossary of every term.

## Chapters

| # | Chapter | What is in it |
|---|---|---|
| 1 | [The project](01-the-project.md) | The problem, the idea, the hypotheses, the gates, the team, what "done" means |
| 2 | [Journal](02-journal.md) | Day-by-day record of everything we did, with outputs |
| 3 | [Decision log](03-decisions.md) | Every decision: the question, the options, what was chosen, by whom, and why |
| 4 | [The simulator](04-simulator.md) | The physics: crowds, movement, buildings, the radio channel, NOMA, energy |
| 5 | [The dataset](05-dataset.md) | The generated tables, the Excel file, what is in every column, versions |
| 6 | [The game and the AI](06-game-and-ai.md) | The Gymnasium environment, the controls, the reward, the training pipeline |
| 7 | [Baselines and their results](07-baselines.md) | The simple pilots and every comparison table; the location-information and anticipation studies; the Kathmandu case study |
| 8 | [AI experiments](08-ai-experiments.md) | Every training run, what it showed, and the diagnosis of each failure; the hybrid timing AI; the AI under wrong physics |
| 9 | [Engineering](09-engineering.md) | Repository, branches, pull requests, tests, CI, every command, troubleshooting |
| 10 | [What is verified and what is not](10-verification.md) | Parameters checked against papers, assumptions, known gaps |
| 11 | [Outlook](11-outlook.md) | Roadmap, novelty and related work, the real-world gap, hardware path, business track |
| 12 | [Glossary](12-glossary.md) | Every term in plain words |
| 13 | [**NOMA in this project**](13-noma.md) | What NOMA is, where it sits, NOMA vs OMA measured in the game, its limits and next steps |
| 14 | [A senior engineer's plan, reviewed](14-expert-plan.md) | How an expert would solve the problem, an independent review, the agreed next steps |

**Start here for NOMA:** [Chapter 13](13-noma.md).

Figures are in [`figures/`](figures/) and animations in [`figures/gifs/`](figures/gifs/). Each caption says which dataset version
or run produced it.

## The project in five sentences
After a disaster, phone towers are down; a drone carrying a radio can act as a temporary tower. We built a simulator of
survivors in crowds, collapsed buildings, a battery-limited drone and a NOMA radio link, so that strategies for flying the drone
can be compared in software before any real flight. We built seven simple, non-AI pilots and compared them fairly on hundreds
of scenarios. We are training an AI pilot that learns by itself, and we report honestly where it wins and where it loses.
The project is a simulation-based planning tool, not a digital twin and not a real flight system (yet).
