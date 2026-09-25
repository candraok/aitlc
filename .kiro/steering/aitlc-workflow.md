# AI-TLC v5 Workflow Steering Rules

## Purpose

AI-TLC transforms feature tickets into production-oriented QA test cases and maintains two persistent knowledge layers:

- `memory/` = approved historical test cases and behavior knowledge.
- `regression/` = the current curated regression baseline.

## Mandatory lifecycle

```text
Ticket
  ↓
Search approved Memory + active Regression
  ↓
Compare existing behavior with current requirements
  ↓
Generate / update test cases
  ↓
Validate CSV
  ↓
Human QA review
  ↓
Approve
  ├── Memory: approved reusable behavior
  └── Regression: explicitly selected cases only
```

## Source-of-truth precedence

1. Current Feature Details / Acceptance Criteria
2. Current technical/API/UI/database documentation
3. Approved current test-case memory
4. Older historical information

Memory and regression never override an explicit current requirement.

## Memory rules

- Only human-approved cases are retrieved as active memory.
- Approved cases are versioned by behavior where possible.
- A behavior change creates a new behavior version; do not silently erase history.
- Unrelated historical cases must not be copied into a new suite.
- Ambiguous behavior must be surfaced for human QA review.

## Regression rules

- `master-regression.csv` is curated, not an automatic dump of generated cases.
- Promotion requires explicit case selection or an explicit `--all` command after QA approval.
- A test can be in memory but not regression.
- When behavior changes, update the active regression expectation rather than keeping contradictory active cases.

## Required quality gate

A ticket is not complete until:

- generation succeeds
- CSV validation passes
- human QA review is completed
- approved reusable cases are stored in memory
- regression candidates are explicitly selected when applicable
