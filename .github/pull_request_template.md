## What this changes
<!-- 2-3 lines: what you built or fixed, and why. -->

## Which hypothesis / gate does it serve?
<!-- H1 / H2 / H3 / H4, or G1..G7, or "tooling". Every experiment must serve one. -->

## Checklist (all must be ticked before review)
- [ ] I ran it locally and it works: `python -m pytest` and `python -m ruff check .`
- [ ] I added or updated tests for the behaviour I changed
- [ ] No magic numbers in the code: values live in `config.yaml`
- [ ] Physics/parameter changes name their source (paper) or are labelled "engineering assumption"
- [ ] I can explain every line in this PR without notes (viva rule)
- [ ] I updated `CLAUDE.md` / README if the state or the commands changed

## How I tested it
<!-- Commands run and what you saw. Paste numbers or a screenshot. -->
