# AI-TLC v5 Regression Suite

`regression/master-regression.csv` is the current curated regression baseline.

## Memory vs Regression

- Memory answers: **What approved behavior/test cases have we known and tested before?**
- Regression answers: **What approved cases are currently required for regression?**

A case may exist in memory without being active regression.

## Explicit promotion

After Senior QA review and memory approval, promote only selected cases:

```bash
python scripts/regression.py add --csv output/SCRUM-491-test-cases.csv --ids TC001,TC004,TC009
```

Or, only when QA intentionally wants every case from that reviewed CSV:

```bash
python scripts/regression.py add --csv output/SCRUM-491-test-cases.csv --all
```

Running `add` without `--ids` or `--all` is rejected to prevent accidental promotion of an entire generated suite.

## Inspect and validate

```bash
python scripts/regression.py list
python scripts/regression.py validate
```

## Regression change principle

If a ticket explicitly changes an existing behavior, the affected active regression expectation must be updated after QA review. Do not keep contradictory old and new expectations active for the same behavior.
