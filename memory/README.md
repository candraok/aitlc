# AI-TLC v5 Test Case Memory

`memory/` is the persistent approved QA knowledge base.

## Memory is not automatic

Generated test cases are **not approved memory** merely because CSV validation passes.

Lifecycle:

```text
Generate → Validate → Human QA Review → Approve → Memory
```

Approve a reviewed CSV:

```bash
python scripts/memory.py approve --csv output/SCRUM-491-test-cases.csv --ticket SCRUM-491 --reviewer "Candra"
```

`index` remains a backward-compatible alias for `approve`.

## What is stored

### `test_cases.jsonl`

Approved test-case records containing:

- memory ID
- source ticket
- test case ID/title
- behavior statement
- precondition
- steps
- expected result
- approval status
- reviewer
- tags
- behavior ID/version
- timestamps

### `behaviors.jsonl`

Behavior-level records used to make behavioral changes explicit and versionable.

## Search

```bash
python scripts/memory.py search --query "incentive edit window" --limit 10
```

Only records with `status=approved` are returned to the active retrieval flow.

## Important precedence

1. Current explicit requirement
2. Current technical/API/UI/database documentation
3. Approved memory
4. Older history

Memory is historical evidence, never a reason to override a new requirement.
