import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from ai_providers import generate_ai_response


ROOT = Path(__file__).resolve().parents[1]

PROMPT_FILE = (
    ROOT / "prompts" / "test-case-generation.md"
)

DEFAULT_OUTPUT_DIR = (
    ROOT / "output"
)


COLUMNS = [
    "Test Case ID",
    "Test case title",
    "Precondition",
    "Test steps",
    "Expected result",
    "Status",
    "Note",
]


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8"
    )


def extract_json(text: str) -> dict:
    """
    Extract JSON from AI response.

    Supports:
    - pure JSON
    - ```json ... ```
    - ``` ... ```
    """

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.I,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    return json.loads(text)


def normalize_numbered(items):
    """
    Normalize numbered test steps / expected results.

    Example input:

        [
            "1. Login",
            "2. Open page"
        ]

    Result:

        [
            "1. Login",
            "2. Open page"
        ]
    """

    if not isinstance(items, list):
        raise ValueError(
            "Expected a list of numbered strings."
        )

    normalized = []

    for index, item in enumerate(
        items,
        start=1,
    ):
        value = str(item).strip()

        value = re.sub(
            r"^\s*\d+\.\s*",
            "",
            value,
        )

        if not value:
            raise ValueError(
                "A numbered item is empty."
            )

        normalized.append(
            f"{index}. {value}"
        )

    return normalized


def validate_records(data):
    """
    Validate and normalize AI-generated test cases.
    """

    if (
        not isinstance(data, dict)
        or "test_cases" not in data
    ):
        raise ValueError(
            "AI output must contain "
            "a 'test_cases' array."
        )

    records = data["test_cases"]

    if not records:
        raise ValueError(
            "No test cases were generated."
        )

    normalized = []

    ids = set()
    titles = set()

    for index, item in enumerate(
        records,
        start=1,
    ):
        tc_id = (
            str(
                item.get(
                    "test_case_id",
                    "",
                )
            ).strip()
            or f"TC{index:03d}"
        )

        title = str(
            item.get(
                "test_case_title",
                "",
            )
        ).strip()

        precondition = (
            str(
                item.get(
                    "precondition",
                    "",
                )
            ).strip()
            or "None"
        )

        # --------------------------------------------------------
        # Validate duplicate ID
        # --------------------------------------------------------

        if tc_id in ids:
            raise ValueError(
                f"Duplicate Test Case ID: {tc_id}"
            )

        ids.add(tc_id)

        # --------------------------------------------------------
        # Validate title
        # --------------------------------------------------------

        if not title:
            raise ValueError(
                f"Test case {tc_id} has no title."
            )

        title_key = re.sub(
            r"\s+",
            " ",
            title,
        ).lower()

        if title_key in titles:
            raise ValueError(
                f"Duplicate test-case title: {title}"
            )

        titles.add(title_key)

        # --------------------------------------------------------
        # Normalize steps
        # --------------------------------------------------------

        steps = normalize_numbered(
            item.get(
                "test_steps",
                [],
            )
        )

        expected = normalize_numbered(
            item.get(
                "expected_result",
                [],
            )
        )

        normalized.append(
            {
                "Test Case ID": tc_id,
                "Test case title": title,
                "Precondition": precondition,
                "Test steps": "\n".join(steps),
                "Expected result": "\n".join(expected),
                "Status": "",
                "Note": "",
            }
        )

    return normalized


def write_csv(
    records,
    output_path: Path,
):
    """
    Write final test cases into CSV.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=COLUMNS,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(records)


def load_memory_context(
    query,
    limit=15,
):
    """
    Search historical approved test cases.
    """

    path = (
        ROOT
        / "memory"
        / "test_cases.jsonl"
    )

    if not path.exists():
        return []

    query_tokens = set(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            query.lower(),
        ).split()
    )

    matches = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        for line in file:

            if not line.strip():
                continue

            row = json.loads(line)

            # Only approved memory should be
            # used as historical knowledge.
            if row.get("status") not in {
                None,
                "",
                "approved",
            }:
                continue

            text = " ".join(
                [
                    row.get("ticket", ""),
                    row.get("title", ""),
                    row.get("behavior", ""),
                    " ".join(
                        row.get(
                            "tags",
                            [],
                        )
                    ),
                ]
            )

            row_tokens = set(
                re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    text.lower(),
                ).split()
            )

            overlap = len(
                query_tokens
                & row_tokens
            )

            if overlap:
                matches.append(
                    (
                        overlap
                        / max(
                            1,
                            len(query_tokens),
                        ),
                        row,
                    )
                )

    matches.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        row
        for _, row in matches[:limit]
    ]


def load_regression_context(
    query,
    limit=15,
):
    """
    Search active regression cases.
    """

    path = (
        ROOT
        / "regression"
        / "master-regression.csv"
    )

    if not path.exists():
        return []

    query_tokens = set(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            query.lower(),
        ).split()
    )

    matches = []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        for row in csv.DictReader(file):

            text = " ".join(
                [
                    row.get(
                        "Test Case ID",
                        "",
                    ),
                    row.get(
                        "Test case title",
                        "",
                    ),
                    row.get(
                        "Precondition",
                        "",
                    ),
                    row.get(
                        "Expected result",
                        "",
                    ),
                ]
            )

            row_tokens = set(
                re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    text.lower(),
                ).split()
            )

            overlap = len(
                query_tokens
                & row_tokens
            )

            if overlap:
                matches.append(
                    (
                        overlap
                        / max(
                            1,
                            len(query_tokens),
                        ),
                        row,
                    )
                )

    matches.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        row
        for _, row in matches[:limit]
    ]


def read_previous_output(
    path: Path,
    limit=60,
):
    """
    Load a previous generated CSV
    when revision mode is used.
    """

    if (
        not path
        or not path.exists()
    ):
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        rows = list(
            csv.DictReader(file)
        )

    return rows[:limit]


def build_prompt(
    ticket_text: str,
    memory_context,
    regression_context,
    previous_cases=None,
    revision="",
):
    """
    Build the complete AI-TLC prompt.
    """

    instructions = read_text(
        PROMPT_FILE
    )

    # ============================================================
    # MEMORY CONTEXT
    # ============================================================

    memory_text = (
        "No related historical "
        "test cases were found."
    )

    if memory_context:

        chunks = []

        for row in memory_context:

            chunks.append(
                f"""
Memory ID: {row.get('memory_id')}
Ticket: {row.get('ticket')}
Test Case ID: {row.get('test_case_id')}
Title: {row.get('title')}
Behavior: {row.get('behavior')}
Precondition: {row.get('precondition')}
Expected Result: {row.get('expected_result')}
Behavior Version: {row.get('behavior_version', 1)}
"""
            )

        memory_text = (
            "\n---\n".join(chunks)
        )

    # ============================================================
    # REGRESSION CONTEXT
    # ============================================================

    regression_text = (
        "No related active regression "
        "cases were found."
    )

    if regression_context:

        chunks = []

        for row in regression_context:

            chunks.append(
                f"""
Regression Test Case ID: {row.get('Test Case ID')}
Title: {row.get('Test case title')}
Precondition: {row.get('Precondition')}
Expected Result: {row.get('Expected result')}
"""
            )

        regression_text = (
            "\n---\n".join(chunks)
        )

    # ============================================================
    # REVISION CONTEXT
    # ============================================================

    revision_text = (
        "No revision requested."
    )

    if revision:

        revision_text = f"""
Revision requested by the human QA reviewer:

{revision}

Revision rules:
- Keep valid existing cases when they are still supported by the ticket.
- Modify only affected cases where practical.
- Add missing scenarios required by the revision.
- Remove or consolidate duplicates.
- Do not invent behavior not supported by the ticket or historical context.
"""

    # ============================================================
    # PREVIOUS GENERATED CASES
    # ============================================================

    previous_text = (
        "No previous generated CSV "
        "was supplied."
    )

    if previous_cases:

        chunks = []

        for row in previous_cases:

            chunks.append(
                f"""
Test Case ID: {row.get('Test Case ID')}
Title: {row.get('Test case title')}
Precondition: {row.get('Precondition')}
Steps:
{row.get('Test steps')}

Expected:
{row.get('Expected result')}
"""
            )

        previous_text = (
            "\n---\n".join(chunks)
        )

    # ============================================================
    # FINAL PROMPT
    # ============================================================

    return f"""
{instructions}

## Active Regression Suite Context

Use this as the current approved regression baseline.

If the ticket does not explicitly change a relevant behavior,
preserve its coverage.

If the ticket explicitly changes it,
update the affected expectation rather than keeping
contradictory active coverage.

{regression_text}


## Historical Test Case Memory

Use this memory as regression knowledge.

IMPORTANT:

- Existing memory represents previously tested behavior.
- Do not delete or ignore relevant existing behavior merely because the new ticket does not repeat it.
- If the new ticket explicitly changes behavior, the current ticket requirement takes precedence.
- If behavior appears unchanged, preserve relevant historical scenarios as regression coverage.
- Do not blindly copy irrelevant historical cases.
- Do not claim a behavior is unchanged unless the ticket and memory support that conclusion.
- If requirements conflict with memory, treat the current explicit requirement as authoritative and add/update regression coverage accordingly.

{memory_text}


## Previous Generated Test Cases

{previous_text}


## Revision Request

{revision_text}


## Current Ticket

{ticket_text}


## Final instruction

Return JSON only.

The response must have this structure:

{{
  "test_cases": [
    {{
      "test_case_id": "TC001",
      "test_case_title": "Example title",
      "precondition": "None",
      "test_steps": [
        "1. First step",
        "2. Second step"
      ],
      "expected_result": [
        "1. First expected result",
        "2. Second expected result"
      ]
    }}
  ]
}}

Rules:

- Return valid JSON only.
- Do not use Markdown.
- Do not use ```json.
- Every test case must contain test_steps.
- Every test case must contain expected_result.
- Test steps must be sequential.
- Expected results must be sequential.
- Do not create duplicate test cases.
"""


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate AI-TLC test cases "
            "with OpenAI -> Gemini -> Claude fallback."
        )
    )

    parser.add_argument(
        "--ticket",
        required=True,
    )

    parser.add_argument(
        "--output",
    )

    parser.add_argument(
        "--model",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--memory-limit",
        type=int,
        default=15,
    )

    parser.add_argument(
        "--revision",
        default="",
    )

    parser.add_argument(
        "--previous-output",
    )

    args = parser.parse_args()

    # ============================================================
    # TICKET
    # ============================================================

    ticket_path = (
        Path(args.ticket)
        .resolve()
    )

    if not ticket_path.exists():

        print(
            f"ERROR: Ticket not found: "
            f"{ticket_path}",
            file=sys.stderr,
        )

        return 1

    ticket_text = read_text(
        ticket_path
    )

    # ============================================================
    # MEMORY
    # ============================================================

    memory_context = (
        load_memory_context(
            ticket_text,
            args.memory_limit,
        )
    )

    # ============================================================
    # REGRESSION
    # ============================================================

    regression_context = (
        load_regression_context(
            ticket_text,
            args.memory_limit,
        )
    )

    # ============================================================
    # PREVIOUS OUTPUT
    # ============================================================

    previous_cases = []

    if args.previous_output:

        previous_cases = (
            read_previous_output(
                Path(
                    args.previous_output
                ).resolve()
            )
        )

    # ============================================================
    # BUILD PROMPT
    # ============================================================

    prompt = build_prompt(
        ticket_text,
        memory_context,
        regression_context,
        previous_cases,
        args.revision,
    )

    print(
        f"Related memory entries: "
        f"{len(memory_context)}"
    )

    print(
        f"Related regression entries: "
        f"{len(regression_context)}"
    )

    if previous_cases:

        print(
            "Previous generated cases supplied: "
            f"{len(previous_cases)}"
        )

    if args.revision:

        print(
            "Revision mode: enabled"
        )

    # ============================================================
    # DRY RUN
    # ============================================================

    if args.dry_run:

        print(prompt)

        return 0

    # ============================================================
    # LOAD ENVIRONMENT
    # ============================================================

    load_dotenv(
        ROOT / ".env"
    )

    openai_api_key = os.getenv(
        "OPENAI_API_KEY"
    )

    gemini_api_key = os.getenv(
        "GEMINI_API_KEY"
    )

    claude_api_key = os.getenv(
        "CLAUDE_API_KEY"
    )

    provider_order = os.getenv(
        "AITLC_PROVIDER_ORDER",
        "openai,gemini,claude",
    )

    # ============================================================
    # CHECK API KEYS
    # ============================================================

    if not any(
        [
            openai_api_key,
            gemini_api_key,
            claude_api_key,
        ]
    ):

        print(
            "ERROR: No AI API key is configured.",
            file=sys.stderr,
        )

        print(
            "Configure at least one of:",
            file=sys.stderr,
        )

        print(
            "OPENAI_API_KEY",
            file=sys.stderr,
        )

        print(
            "GEMINI_API_KEY",
            file=sys.stderr,
        )

        print(
            "CLAUDE_API_KEY",
            file=sys.stderr,
        )

        return 1

    # ============================================================
    # MODEL CONFIGURATION
    # ============================================================

    openai_model = (
        args.model
        or os.getenv(
            "AITLC_MODEL",
            "gpt-5.6-luna",
        )
    )

    gemini_model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash",
    )

    gemini_fallback_model = os.getenv(
        "GEMINI_FALLBACK_MODEL",
        "gemini-3.7-flash",
    )

    claude_model = os.getenv(
        "CLAUDE_MODEL",
        "claude-sonnet-4-6",
    )

    claude_max_tokens = int(
        os.getenv(
            "CLAUDE_MAX_TOKENS",
            "16000",
        )
    )

    # ============================================================
    # AI GENERATION
    # ============================================================

    try:

        raw, provider = generate_ai_response(
            prompt=prompt,

            provider_order=provider_order,

            openai_api_key=openai_api_key,
            openai_model=openai_model,

            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            gemini_fallback_model=gemini_fallback_model,

            claude_api_key=claude_api_key,
            claude_model=claude_model,
            claude_max_tokens=claude_max_tokens,
        )

    except Exception as exc:

        print(
            f"ERROR: AI generation failed: {exc}",
            file=sys.stderr,
        )

        return 1

    # ============================================================
    # JSON EXTRACTION + VALIDATION
    # ============================================================

    try:

        data = extract_json(
            raw
        )

        records = validate_records(
            data
        )

    except Exception as exc:

        print(
            f"ERROR: Invalid AI output: {exc}",
            file=sys.stderr,
        )

        print(
            "Raw AI response:",
            file=sys.stderr,
        )

        print(
            raw,
            file=sys.stderr,
        )

        return 1

    # ============================================================
    # CSV OUTPUT
    # ============================================================

    output_path = (
        Path(args.output).resolve()
        if args.output
        else (
            DEFAULT_OUTPUT_DIR
            / f"{ticket_path.stem}-test-cases.csv"
        )
    )

    write_csv(
        records,
        output_path,
    )

    # ============================================================
    # RESULT
    # ============================================================

    print(
        f"Generated {len(records)} test cases."
    )

    print(
        f"Provider: {provider}"
    )

    print(
        f"CSV: {output_path}"
    )

    print(
        ""
    )

    print(
        "Next step:"
    )

    print(
        "1. Review the generated CSV."
    )

    print(
        "2. Validate the CSV."
    )

    print(
        "3. Approve it before storing into memory."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )