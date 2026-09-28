import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from ai_providers import (
    generate_ai_response,
)


ROOT = Path(__file__).resolve().parents[1]

PROMPT_FILE = (
    ROOT
    / "prompts"
    / "test-case-generation.md"
)

DEFAULT_OUTPUT_DIR = (
    ROOT
    / "output"
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


SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}


# ============================================================
# FILE HELPERS
# ============================================================

def read_text(path: Path) -> str:

    return path.read_text(
        encoding="utf-8"
    )


def resolve_repo_path(
    reference,
    base_path=None,
):
    """
    Resolve design/ticket references.

    Priority:
    1. Absolute path
    2. Relative to repository root
    3. Relative to ticket directory
    """

    path = Path(
        reference.strip()
    )

    if path.is_absolute():

        return path.resolve()

    candidates = []

    candidates.append(
        ROOT / path
    )

    if base_path:

        candidates.append(
            base_path / path
        )

    for candidate in candidates:

        if candidate.exists():

            return candidate.resolve()

    return (
        ROOT / path
    ).resolve()


# ============================================================
# DESIGN REFERENCES
# ============================================================

def extract_design_references(
    ticket_text,
    ticket_path,
):
    """
    Read image references from the ticket.

    Expected format:

    ## UI Design References

    - design/TASK-1002/update-web.png
    - design/TASK-1002/update-mobile.png

    Also supports:

    ## Design References

    - design/TASK-1002/example.png
    """

    lines = ticket_text.splitlines()

    references = []

    inside_design_section = False

    for line in lines:

        stripped = line.strip()

        # ----------------------------------------------------
        # Detect section
        # ----------------------------------------------------

        if stripped.startswith("#"):

            heading = stripped.lstrip(
                "#"
            ).strip().lower()

            inside_design_section = (
                "ui design reference" in heading
                or
                "design reference" in heading
                or
                "figma reference" in heading
                or
                "screenshot reference" in heading
            )

            continue

        if not inside_design_section:
            continue

        # ----------------------------------------------------
        # Read markdown bullet
        # ----------------------------------------------------

        match = re.match(
            r"^[-*]\s+(.+)$",
            stripped,
        )

        if not match:
            continue

        value = match.group(1).strip()

        # Remove markdown link wrapper:
        #
        # [Screenshot](design/TASK-1002/a.png)

        markdown_link = re.match(
            r"^\[.*?\]\((.+?)\)$",
            value,
        )

        if markdown_link:

            value = markdown_link.group(1).strip()

        # Ignore URLs for now.
        # This implementation handles repository files.

        if re.match(
            r"^https?://",
            value,
            re.I,
        ):

            print(
                "[DESIGN] External URL detected "
                f"but not loaded: {value}"
            )

            continue

        path = resolve_repo_path(
            value,
            ticket_path.parent,
        )

        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_IMAGE_EXTENSIONS:

            continue

        if path not in references:

            references.append(path)

    return references


def validate_design_references(
    image_paths,
):
    """
    Validate all design references.
    """

    valid = []

    for image_path in image_paths:

        if not image_path.exists():

            raise FileNotFoundError(
                "Design image referenced by ticket "
                f"does not exist: {image_path}"
            )

        if not image_path.is_file():

            raise ValueError(
                "Design reference is not a file: "
                f"{image_path}"
            )

        valid.append(
            image_path
        )

    return valid


# ============================================================
# JSON
# ============================================================

def extract_json(text: str) -> dict:

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

    return json.loads(
        text
    )


# ============================================================
# TEST CASE NORMALIZATION
# ============================================================

def normalize_numbered(items):

    if not isinstance(
        items,
        list,
    ):

        raise ValueError(
            "Expected a list of numbered strings."
        )

    normalized = []

    for index, item in enumerate(
        items,
        start=1,
    ):

        value = str(
            item
        ).strip()

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

    if (
        not isinstance(data, dict)
        or
        "test_cases" not in data
    ):

        raise ValueError(
            "AI output must contain "
            "a 'test_cases' array."
        )

    records = data[
        "test_cases"
    ]

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

        tc_id = str(
            item.get(
                "test_case_id",
                "",
            )
        ).strip()

        if not tc_id:

            tc_id = (
                f"TC{index:03d}"
            )

        title = str(
            item.get(
                "test_case_title",
                "",
            )
        ).strip()

        precondition = str(
            item.get(
                "precondition",
                "",
            )
        ).strip()

        if not precondition:

            precondition = "None"

        # ----------------------------------------------------
        # Duplicate ID
        # ----------------------------------------------------

        if tc_id in ids:

            raise ValueError(
                "Duplicate Test Case ID: "
                f"{tc_id}"
            )

        ids.add(
            tc_id
        )

        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

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
                "Duplicate test-case title: "
                f"{title}"
            )

        titles.add(
            title_key
        )

        # ----------------------------------------------------
        # Steps / expected
        # ----------------------------------------------------

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
                "Test steps": "\n".join(
                    steps
                ),
                "Expected result": "\n".join(
                    expected
                ),
                "Status": "",
                "Note": "",
            }
        )

    return normalized


# ============================================================
# CSV
# ============================================================

def write_csv(
    records,
    output_path: Path,
):

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

        writer.writerows(
            records
        )


# ============================================================
# MEMORY
# ============================================================

def load_memory_context(
    query,
    limit=15,
):

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

            row = json.loads(
                line
            )

            if row.get(
                "status"
            ) not in {
                None,
                "",
                "approved",
            }:

                continue

            text = " ".join(
                [
                    row.get(
                        "ticket",
                        "",
                    ),
                    row.get(
                        "title",
                        "",
                    ),
                    row.get(
                        "behavior",
                        "",
                    ),
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
                &
                row_tokens
            )

            if overlap:

                matches.append(
                    (
                        overlap
                        /
                        max(
                            1,
                            len(
                                query_tokens
                            ),
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
        for _, row
        in matches[:limit]
    ]


# ============================================================
# REGRESSION
# ============================================================

def load_regression_context(
    query,
    limit=15,
):

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

        for row in csv.DictReader(
            file
        ):

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
                &
                row_tokens
            )

            if overlap:

                matches.append(
                    (
                        overlap
                        /
                        max(
                            1,
                            len(
                                query_tokens
                            ),
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
        for _, row
        in matches[:limit]
    ]


# ============================================================
# PREVIOUS OUTPUT
# ============================================================

def read_previous_output(
    path: Path,
    limit=60,
):

    if (
        not path
        or
        not path.exists()
    ):

        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        rows = list(
            csv.DictReader(
                file
            )
        )

    return rows[:limit]


# ============================================================
# PROMPT
# ============================================================

def build_prompt(
    ticket_text,
    memory_context,
    regression_context,
    design_context,
    previous_cases=None,
    revision="",
):

    instructions = read_text(
        PROMPT_FILE
    )

    # --------------------------------------------------------
    # Memory
    # --------------------------------------------------------

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
            "\n---\n"
            .join(chunks)
        )

    # --------------------------------------------------------
    # Regression
    # --------------------------------------------------------

    regression_text = (
        "No related active "
        "regression cases were found."
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
            "\n---\n"
            .join(chunks)
        )

    # --------------------------------------------------------
    # Design
    # --------------------------------------------------------

    if design_context:

        design_text = "\n".join(
            [
                f"- {path}"
                for path
                in design_context
            ]
        )

    else:

        design_text = (
            "No UI design images "
            "were supplied."
        )

    # --------------------------------------------------------
    # Previous cases
    # --------------------------------------------------------

    previous_text = (
        "No previous generated "
        "CSV was supplied."
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
            "\n---\n"
            .join(chunks)
        )

    # --------------------------------------------------------
    # Revision
    # --------------------------------------------------------

    revision_text = (
        "No revision requested."
    )

    if revision:

        revision_text = f"""
Revision requested by the human QA reviewer:

{revision}

Revision rules:

- Keep valid existing cases when they are still supported.
- Modify affected cases where practical.
- Add missing scenarios required by the revision.
- Remove or consolidate duplicates.
- Do not invent behavior unsupported by ticket,
  historical context, or design evidence.
"""

    # --------------------------------------------------------
    # Final prompt
    # --------------------------------------------------------

    return f"""
{instructions}

## Active Regression Suite Context

Use this as the current approved regression baseline.

If the ticket does not explicitly change a relevant
behavior, preserve the relevant regression coverage.

If the ticket explicitly changes a behavior, update
the affected expectation.

{regression_text}

## Historical Test Case Memory

Use this memory as regression knowledge.

IMPORTANT:

- Existing memory represents previously tested behavior.
- Do not ignore relevant historical behavior merely
  because the current ticket does not repeat it.
- If the new ticket explicitly changes behavior,
  the current ticket takes precedence.
- If historical behavior appears applicable,
  preserve it as regression coverage.
- Do not blindly copy irrelevant historical cases.
- If applicability is ambiguous, flag it for human QA.
- Do not invent behavior from silence.

{memory_text}

## UI / FIGMA / SCREENSHOT DESIGN REFERENCES

The following images are attached to this request:

{design_text}

IMPORTANT DESIGN RULES:

- Read every supplied design image carefully.
- Treat the images as design evidence, not automatically
  as business requirements.
- Identify visible UI elements such as:
  fields, labels, required indicators, buttons,
  tabs, dropdowns, dialogs, error states, navigation,
  disabled states, and mobile/web differences.
- Generate UI test cases for relevant visible behavior.
- If a design observation conflicts with an explicit
  ticket requirement, the explicit requirement takes
  precedence.
- Do not invent backend behavior merely from visual design.
- Do not assume that every visible element requires a
  separate test case if it belongs to the same coherent
  test objective.
- When design evidence is used, mention the design source
  in the Note field if appropriate.
- Compare web and mobile screenshots when both exist.
- Identify relevant responsive or platform-specific
  behavior.
- If an important design behavior is ambiguous,
  preserve it as a human QA review concern.

## Previous Generated Test Cases

{previous_text}

## Revision Request

{revision_text}

## Current Ticket

{ticket_text}

## Final Generation Rules

Generate the complete production-oriented test suite.

The test suite must combine:

1. Current ticket requirements.
2. Applicable historical test behavior.
3. Active regression coverage.
4. Relevant UI/design evidence.
5. Positive scenarios.
6. Negative scenarios.
7. Edge cases.
8. Boundary cases.
9. Realistic customer/user scenarios.
10. Relevant frontend behavior.

Historical behavior may be inherited from previous features
even when the current ticket does not repeat the rule,
provided there is no evidence that the behavior changed.

Do not blindly copy historical cases.

Return JSON only.

Every test case must contain:

- test_case_id
- test_case_title
- precondition
- test_steps
- expected_result
- status
- note

Status must be an empty string.

Note must be an empty string unless the prompt requires
design or review metadata.

Every test step must be one numbered item.

Every expected-result item must be one numbered item.
"""


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate AI-TLC test cases using "
            "OpenAI, Gemini, and Claude with "
            "optional UI design images."
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
        "--provider-order",
        help=(
            "Override AITLC_PROVIDER_ORDER. "
            "Example: claude,gemini,openai"
        ),
    )

    parser.add_argument(
        "--mode",
        choices=[
            "cloud",
            "offline",
            "hybrid",
        ],
        default="cloud",
        help=(
            "Generation mode: "
            "cloud, offline, or hybrid."
        ),
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

    # --------------------------------------------------------
    # Ticket
    # --------------------------------------------------------

    ticket_path = Path(
        args.ticket
    ).resolve()

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

    # --------------------------------------------------------
    # Design images
    # --------------------------------------------------------

    try:

        design_images = (
            extract_design_references(
                ticket_text,
                ticket_path,
            )
        )

        design_images = (
            validate_design_references(
                design_images
            )
        )

    except Exception as exc:

        print(
            f"ERROR: Design reference error: {exc}",
            file=sys.stderr,
        )

        return 1

    # --------------------------------------------------------
    # Memory
    # --------------------------------------------------------

    memory_context = (
        load_memory_context(
            ticket_text,
            args.memory_limit,
        )
    )

    # --------------------------------------------------------
    # Regression
    # --------------------------------------------------------

    regression_context = (
        load_regression_context(
            ticket_text,
            args.memory_limit,
        )
    )

    # --------------------------------------------------------
    # Previous generated cases
    # --------------------------------------------------------

    previous_cases = []

    if args.previous_output:

        previous_output_path = (
            Path(
                args.previous_output
            ).resolve()
        )

        previous_cases = (
            read_previous_output(
                previous_output_path
            )
        )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = build_prompt(
        ticket_text=ticket_text,
        memory_context=memory_context,
        regression_context=regression_context,
        design_context=design_images,
        previous_cases=previous_cases,
        revision=args.revision,
    )

    print(
        f"Related memory entries: "
        f"{len(memory_context)}"
    )

    print(
        f"Related regression entries: "
        f"{len(regression_context)}"
    )

    print(
        f"Design images: "
        f"{len(design_images)}"
    )

    for image_path in design_images:

        print(
            f"  - {image_path}"
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

    # --------------------------------------------------------
    # Dry run
    # --------------------------------------------------------

    if args.dry_run:

        print(
            prompt
        )

        return 0

    # --------------------------------------------------------
    # Environment
    # --------------------------------------------------------

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

    cloud_provider_order = (
        args.provider_order
        or
        os.getenv(
            "AITLC_PROVIDER_ORDER",
            "openai,gemini,claude",
        )
    )

    if args.mode == "cloud":
        provider_order = cloud_provider_order

    elif args.mode == "offline":
        provider_order = "ollama"

    elif args.mode == "hybrid":
        provider_order = (
            f"{cloud_provider_order},ollama"
        )

    else:
        raise ValueError(
            f"Unsupported generation mode: "
            f"{args.mode}"
        )

    print(
        f"Generation mode: {args.mode}"
    )

    print(
        f"Effective provider order: "
        f"{provider_order}"
    )

    if args.mode == "offline":
        print(
            "[AI] Offline mode selected."
        )
        print(
            "[AI] Cloud providers will NOT be called."
        )
        print(
            "[AI] Using Ollama only."
        )

    elif args.mode == "hybrid":
        print(
            "[AI] Hybrid mode selected."
        )
        print(
            "[AI] Cloud providers will be tried "
            "according to AITLC_PROVIDER_ORDER."
        )
        print(
            "[AI] Ollama will be used only after "
            "all cloud providers fail."
        )

    else:
        print(
            "[AI] Cloud mode selected."
        )
        print(
            "[AI] Provider order: "
            f"{cloud_provider_order}"
        )

    # --------------------------------------------------------
    # Models
    # --------------------------------------------------------

    openai_model = (
        args.model
        or
        os.getenv(
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

    ollama_host = os.getenv(
        "OLLAMA_HOST",
        "http://localhost:11434",
    )

    ollama_model = os.getenv(
        "OLLAMA_MODEL",
        "gemma4",
    )

    ollama_vision_model = os.getenv(
        "OLLAMA_VISION_MODEL",
        ollama_model,
    )

    ollama_timeout = int(
        os.getenv(
            "OLLAMA_TIMEOUT",
            "600",
        )
    )

    ollama_num_ctx = int(
        os.getenv(
            "OLLAMA_NUM_CTX",
            "32768",
        )
    )

    ollama_temperature = float(
        os.getenv(
            "OLLAMA_TEMPERATURE",
            "0",
        )
    )

    # --------------------------------------------------------
    # AI generation
    # --------------------------------------------------------

    try:

        raw, provider = (
            generate_ai_response(
                try:
    raw, provider = (
        generate_ai_response(
                prompt=prompt,
                provider_order=provider_order,

                openai_api_key=openai_api_key,
                openai_model=openai_model,

                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                gemini_fallback_model=(
                    gemini_fallback_model
                ),

                claude_api_key=claude_api_key,
                claude_model=claude_model,
                claude_max_tokens=(
                    claude_max_tokens
                ),

                ollama_host=ollama_host,
                ollama_model=ollama_model,
                ollama_vision_model=(
                    ollama_vision_model
                ),
                ollama_timeout=ollama_timeout,
                ollama_num_ctx=ollama_num_ctx,
                ollama_temperature=(
                    ollama_temperature
                ),

                image_paths=design_images,
            )
        )

    except Exception as exc:

        print(
            f"ERROR: AI generation failed: {exc}",
            file=sys.stderr,
        )

        return 1
            )
        )

    except Exception as exc:

        print(
            f"ERROR: AI generation failed: {exc}",
            file=sys.stderr,
        )

        return 1

    # --------------------------------------------------------
    # Validate AI output
    # --------------------------------------------------------

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
            raw,
            file=sys.stderr,
        )

        return 1

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output_path = (
        Path(
            args.output
        ).resolve()
        if args.output
        else
        DEFAULT_OUTPUT_DIR
        /
        f"{ticket_path.stem}-test-cases.csv"
    )

    write_csv(
        records,
        output_path,
    )

    print(
        f"Generated {len(records)} test cases."
    )

    print(
        f"Provider: {provider}"
    )

    print(
        f"CSV: {output_path}"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )