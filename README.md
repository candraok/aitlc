# AI-TLC v6 — Interactive AI-Driven Testing Life Cycle

AI-TLC v6 turns the test-case workflow into an interactive CLI so QA engineers do not need to remember multiple Python commands.

The primary entry point is:

```cmd
aitlc
```

The workflow is designed around four persistent layers:

```text
Ticket
  ↓
Memory + Active Regression
  ↓
Generate Test Cases
  ↓
Validate
  ↓
Human QA Review
  ├── Revise → regenerate → review again
  └── Approve
        ↓
     Memory
        ↓
     Regression selection
```

---

# 1. What v6 adds

## Interactive CLI

Instead of typing several commands manually:

```cmd
python scripts/generate_test_cases.py ...
python scripts/validate_csv.py ...
python scripts/memory.py approve ...
python scripts/regression.py add ...
```

you can run:

```cmd
aitlc
```

and follow the questions.

## Human review loop

After generation and validation, the CLI asks:

```text
1. Approve
2. Revise
3. Open CSV
4. Cancel
```

If `Revise` is selected, the QA can identify revision areas and provide additional instructions. The generator receives the previous CSV and the revision request so valid existing cases can be preserved while affected cases are modified or added.

## Memory approval

Approved cases can be explicitly saved into:

```text
memory/test_cases.jsonl
memory/behaviors.jsonl
```

Memory is historical/reusable QA knowledge. It is not automatically the active regression suite.

## Regression selection

After approval, the CLI asks:

```text
1. All test cases
2. Select specific test cases
3. None
```

This prevents every generated test case from automatically becoming regression coverage.

## AI provider fallback

Generation uses this provider chain:

```text
OpenAI
   ↓ failure
Gemini primary
   ↓ failure
Gemini fallback model
```

The provider and model used are printed after successful generation.

The Gemini integration uses the current Google GenAI Python SDK style (`from google import genai` and `client.models.generate_content(...)`). Google documents `generate_content` as the standard content-generation method and also supports JSON response configuration. See the official Gemini API documentation for current SDK/model details.

---

# 2. AI provider configuration

Create `.env` in the repository root.

Example:

```env
OPENAI_API_KEY=replace_with_your_openai_api_key
AITLC_MODEL=gpt-5.6-luna

GEMINI_API_KEY=replace_with_your_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODEL=gemini-3.7-flash

AITLC_REVIEWER=human-qa
```

**Never commit `.env` to Git.** It is already included in `.gitignore`.

### Security warning

If an API key is ever pasted into a chat, ticket, screenshot, Git commit, or public repository, treat it as exposed. Revoke/rotate that key and create a new one. Do not copy exposed keys into this README or source code.

---

# 3. Zero-to-Run Setup — Windows

## Step 1 — Install Python

Install Python 3.10+ from the official Python website.

During installation, enable:

```text
Add python.exe to PATH
```

Verify:

```cmd
python --version
python -m pip --version
```

If `python` is unavailable but `py` works, use `py` during setup.

## Step 2 — Install Git

Install Git for Windows if you want to clone/update the repository.

Verify:

```cmd
git --version
```

## Step 3 — Open the AI-TLC repository

Clone your repository or open the existing local clone:

```cmd
git clone https://github.com/candraok/aitlc.git
cd aitlc
```

If the repository is already cloned, simply:

```cmd
cd path\to\aitlc
```

## Step 4 — Create a virtual environment

```cmd
python -m venv .venv
```

Activate it:

```cmd
.venv\Scripts\activate
```

You should see something similar to:

```text
(.venv) C:\...\aitlc>
```

## Step 5 — Install dependencies

```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For the v6 CLI command, install the project itself:

```cmd
pip install -e .
```

Verify:

```cmd
aitlc --help
```

If Windows cannot find `aitlc`, use:

```cmd
python scripts/cli.py
```

You can also run:

```cmd
aitlc.bat
```

## Step 6 — Configure `.env`

Copy:

```text
.env.example
```

to:

```text
.env
```

Then add your own API keys.

## Step 7 — Verify the ticket

A ticket must exist as:

```text
ticket/TASK-1234.md
```

For example:

```text
ticket/
├── SCRUM-491.md
└── TASK-1234.md
```

---

# 4. Start the workflow

Run:

```cmd
aitlc
```

You will see:

```text
========================================
        AI-TLC Interactive CLI
========================================

What would you like to do?
  1. Process a ticket
  2. Search Memory
  3. View Regression Suite
  4. Validate Regression Suite
  5. Exit
```

Select:

```text
1. Process a ticket
```

Then enter:

```text
Ticket ID (example TASK-1234): TASK-1234
```

AI-TLC automatically reads:

```text
ticket/TASK-1234.md
```

---

# 5. What happens during ticket processing

The CLI performs these steps automatically:

```text
1. Find ticket/TASK-1234.md
2. Search approved Memory
3. Search active Regression
4. Compare historical/current behavior through the AI prompt
5. Generate test cases
6. Validate the generated CSV
7. Ask for Human QA review
```

Output:

```text
output/TASK-1234-test-cases.csv
```

The standard CSV columns are exactly:

```text
Test Case ID
Test case title
Precondition
Test steps
Expected result
Status
Note
```

`Status` and `Note` are blank for generated cases.

---

# 6. AI provider fallback

The generation engine follows this sequence:

```text
                    ┌─────────────┐
                    │   OpenAI    │
                    └──────┬──────┘
                           │
                      success?
                       /       \
                     YES        NO
                      │          │
                      ↓          ↓
                   return    Gemini primary
                                  │
                             success?
                              /       \
                            YES        NO
                             │          │
                             ↓          ↓
                          return    Gemini fallback
                                         │
                                    success?
                                     /     \
                                   YES      NO
                                    │        │
                                    ↓        ↓
                                  return   fail
```

If OpenAI is unavailable, the CLI prints the failure and attempts Gemini.

If the primary Gemini model also fails, it attempts `GEMINI_FALLBACK_MODEL`.

If all configured providers fail, generation stops and no invalid CSV is created.

The Gemini call is implemented using the Google GenAI Python SDK and JSON response configuration. Google documents the Python pattern as:

```python
from google import genai

client = genai.Client(api_key="...")
response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="...",
)
```

For JSON-oriented generation, the SDK supports a JSON response MIME type through `GenerateContentConfig`.

---

# 7. Review — Approve

If the generated test cases are correct, choose:

```text
Approve
```

The CLI then asks:

```text
Save approved test cases to Memory?
  1. Yes
  2. No
```

If `Yes`, the approved cases are stored in:

```text
memory/test_cases.jsonl
```

and behavior records are maintained in:

```text
memory/behaviors.jsonl
```

The reviewer is recorded in the memory metadata.

---

# 8. Regression selection

After memory approval, the CLI asks:

```text
What should be added to Master Regression?
  1. All test cases
  2. Select specific test cases
  3. None
```

## Option 1 — All

Use this only when every generated/approved case should be part of current regression.

## Option 2 — Select specific

The CLI displays the generated cases:

```text
1. TC001 - Verify valid request
2. TC002 - Verify invalid request
3. TC003 - Verify boundary value
4. TC004 - Verify unauthorized request
```

The QA can enter:

```text
1,3,4
```

Only those cases are promoted to:

```text
regression/master-regression.csv
```

## Option 3 — None

The cases remain in Memory if Memory approval was selected, but are not added to current regression.

---

# 9. Review — Revise

If the test cases are not ready, choose:

```text
Revise
```

AI-TLC asks for revision areas such as:

```text
1. Missing test scenarios
2. Incorrect expected result
3. Incorrect business rule
4. Missing negative cases
5. Missing edge/boundary cases
6. Duplicate test cases
7. Incorrect API coverage
8. Incorrect UI coverage
9. Incorrect database coverage
10. Regression coverage issue
11. Other
```

You can select multiple areas, for example:

```text
1,4,5
```

Then provide optional instructions:

```text
Additional revision instructions:
Add negative cases for invalid target values and preserve
existing regression behavior that was not explicitly changed.
```

The generator receives:

- current ticket
- historical Memory
- active Regression context
- previous generated CSV
- revision categories
- human revision instructions

It then regenerates the CSV and returns to validation/review.

The loop is:

```text
Generate
   ↓
Validate
   ↓
Review
  /  \
Revise Approve
  ↓      ↓
Generate Memory
  ↓      ↓
Review Regression
```

Valid existing cases should be preserved when the ticket and requirements still support them.

---

# 10. Search Memory from the CLI

From the main menu choose:

```text
Search Memory
```

Then enter a query such as:

```text
incentive slab edit window
```

This uses approved memory records to find historical QA knowledge.

The generator also performs its own memory retrieval automatically when processing a ticket.

---

# 11. View Regression

From the main menu choose:

```text
View Regression Suite
```

This displays the current approved regression cases from:

```text
regression/master-regression.csv
```

---

# 12. Validate Regression

From the main menu choose:

```text
Validate Regression Suite
```

Or directly:

```cmd
python scripts/regression.py validate
```

---

# 13. Manual commands remain available

The interactive CLI is the recommended interface, but the underlying commands remain available for automation/CI.

Generate:

```cmd
python scripts/generate_test_cases.py --ticket ticket/SCRUM-491.md
```

Validate generated CSV:

```cmd
python scripts/validate_csv.py output/SCRUM-491-test-cases.csv
```

Approve to Memory:

```cmd
python scripts/memory.py approve --csv output/SCRUM-491-test-cases.csv --ticket SCRUM-491 --reviewer "Candra"
```

Search Memory:

```cmd
python scripts/memory.py search --query "incentive slab"
```

Promote all to Regression:

```cmd
python scripts/regression.py add --csv output/SCRUM-491-test-cases.csv --all
```

Promote selected cases:

```cmd
python scripts/regression.py add --csv output/SCRUM-491-test-cases.csv --ids TC001,TC004,TC009
```

---

# 14. Recommended QA governance

AI-generated cases should not automatically become permanent QA knowledge.

Use this lifecycle:

```text
Generated
   ↓
Validated
   ↓
Human QA Review
   ↓
Approved
   ├──→ Memory
   └──→ Selected Regression
```

Memory is broader than Regression.

A test case can be useful historical knowledge without being required on every regression run.

When a new ticket overlaps existing functionality:

1. Search Memory.
2. Search active Regression.
3. Compare the current requirement with historical behavior.
4. If behavior is unchanged, preserve relevant existing regression behavior.
5. If behavior explicitly changes, update/add the affected tests.
6. Do not treat missing wording in the new ticket as proof that old behavior was removed.
7. If the requirement is ambiguous, keep the regression concern and send it to Human QA Review.

Current ticket requirements take precedence over historical memory when they explicitly change behavior.

---

# 15. Repository structure

```text
aitlc/
├── .aitlc/
│   └── config.yaml
├── .kiro/
│   └── steering/
│       └── aitlc-workflow.md
├── memory/
│   ├── README.md
│   ├── test_cases.jsonl
│   └── behaviors.jsonl
├── regression/
│   ├── README.md
│   ├── master-regression.csv
│   └── archive/
├── output/
├── prompts/
│   └── test-case-generation.md
├── scripts/
│   ├── __init__.py
│   ├── cli.py
│   ├── generate_test_cases.py
│   ├── memory.py
│   ├── regression.py
│   └── validate_csv.py
├── ticket/
│   ├── README.md
│   └── EXAMPLE-TICKET.md
├── .env.example
├── .gitignore
├── aitlc.bat
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

# 16. Troubleshooting

## `aitlc` is not recognized

Make sure the virtual environment is active:

```cmd
.venv\Scripts\activate
```

Then install the project:

```cmd
pip install -e .
```

Test:

```cmd
aitlc
```

Alternative:

```cmd
python scripts/cli.py
```

## OpenAI fails

Check:

```text
OPENAI_API_KEY
AITLC_MODEL
```

The CLI will automatically try Gemini if `GEMINI_API_KEY` is configured.

## Gemini fails

Check:

```text
GEMINI_API_KEY
GEMINI_MODEL
GEMINI_FALLBACK_MODEL
```

The CLI tries the primary Gemini model first and then the fallback model.

## All AI providers fail

The workflow stops without claiming that test cases were generated successfully. Check the printed provider errors, API credentials, model names, network connectivity, account limits, and provider availability.

## Ticket not found

The ticket must exist as:

```text
ticket/TASK-1234.md
```

## CSV validation fails

Do not promote the CSV to Memory or Regression until it passes validation and Human QA review.

---

# 17. Security

Never commit:

```text
.env
API keys
access tokens
passwords
secrets
```

If a secret is accidentally exposed, rotate/revoke it immediately and replace the local `.env` value.

---

# 18. End-to-end example

Start:

```cmd
aitlc
```

Select:

```text
1. Process a ticket
```

Enter:

```text
TASK-1234
```

AI-TLC then performs:

```text
✓ Ticket found
✓ Related Memory searched
✓ Related Regression searched
✓ Test cases generated
✓ CSV validated
```

Review:

```text
1. Approve
2. Revise
3. Open CSV
4. Cancel
```

If revision is required:

```text
Revise
→ select revision areas
→ enter optional instructions
→ regenerate
→ validate
→ review again
```

If approved:

```text
Approve
→ Save to Memory? Yes
→ Regression: All / Select / None
→ Validate Regression
→ Workflow completed
```

The final artifacts are:

```text
output/TASK-1234-test-cases.csv
memory/test_cases.jsonl
memory/behaviors.jsonl
regression/master-regression.csv
```
