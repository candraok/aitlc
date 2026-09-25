import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
PROMPT_FILE = ROOT / "prompts" / "test-case-generation.md"
DEFAULT_OUTPUT_DIR = ROOT / "output"

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
    return path.read_text(encoding="utf-8")


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def normalize_numbered(items):
    if not isinstance(items, list):
        raise ValueError("Expected a list of numbered strings.")
    normalized = []
    for index, item in enumerate(items, start=1):
        value = str(item).strip()
        value = re.sub(r"^\s*\d+\.\s*", "", value)
        if not value:
            raise ValueError("A numbered item is empty.")
        normalized.append(f"{index}. {value}")
    return normalized


def validate_records(data):
    if not isinstance(data, dict) or "test_cases" not in data:
        raise ValueError("AI output must contain a 'test_cases' array.")

    records = data["test_cases"]
    if not records:
        raise ValueError("No test cases were generated.")

    normalized = []
    ids = set()
    titles = set()

    for index, item in enumerate(records, start=1):
        tc_id = str(item.get("test_case_id", "")).strip() or f"TC{index:03d}"
        title = str(item.get("test_case_title", "")).strip()
        precondition = str(item.get("precondition", "")).strip() or "None"

        if tc_id in ids:
            raise ValueError(f"Duplicate Test Case ID: {tc_id}")
        ids.add(tc_id)

        if not title:
            raise ValueError(f"Test case {tc_id} has no title.")

        title_key = re.sub(r"\s+", " ", title).lower()
        if title_key in titles:
            raise ValueError(f"Duplicate test-case title: {title}")
        titles.add(title_key)

        steps = normalize_numbered(item.get("test_steps", []))
        expected = normalize_numbered(item.get("expected_result", []))

        normalized.append({
            "Test Case ID": tc_id,
            "Test case title": title,
            "Precondition": precondition,
            "Test steps": "\n".join(steps),
            "Expected result": "\n".join(expected),
            "Status": "",
            "Note": "",
        })

    return normalized


def write_csv(records, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=COLUMNS,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(records)


def load_memory_context(query, limit=15):
    path = ROOT / "memory" / "test_cases.jsonl"
    if not path.exists():
        return []

    query_tokens = set(re.sub(r"[^a-z0-9]+", " ", query.lower()).split())
    matches = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("status") not in {None, "", "approved"}:
                continue
            text = " ".join([
                row.get("ticket", ""),
                row.get("title", ""),
                row.get("behavior", ""),
                " ".join(row.get("tags", [])),
            ])
            row_tokens = set(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())
            overlap = len(query_tokens & row_tokens)
            if overlap:
                matches.append((overlap / max(1, len(query_tokens)), row))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in matches[:limit]]


def load_regression_context(query, limit=15):
    path = ROOT / "regression" / "master-regression.csv"
    if not path.exists():
        return []

    query_tokens = set(re.sub(r"[^a-z0-9]+", " ", query.lower()).split())
    matches = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            text = " ".join([
                row.get("Test Case ID", ""),
                row.get("Test case title", ""),
                row.get("Precondition", ""),
                row.get("Expected result", ""),
            ])
            row_tokens = set(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())
            overlap = len(query_tokens & row_tokens)
            if overlap:
                matches.append((overlap / max(1, len(query_tokens)), row))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in matches[:limit]]


def read_previous_output(path: Path, limit=60):
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[:limit]


def build_prompt(ticket_text: str, memory_context, regression_context, previous_cases=None, revision=""):
    instructions = read_text(PROMPT_FILE)

    memory_text = "No related historical test cases were found."
    if memory_context:
        chunks = []
        for row in memory_context:
            chunks.append(
                f"""Memory ID: {row.get('memory_id')}
Ticket: {row.get('ticket')}
Test Case ID: {row.get('test_case_id')}
Title: {row.get('title')}
Behavior: {row.get('behavior')}
Precondition: {row.get('precondition')}
Expected Result: {row.get('expected_result')}
Behavior Version: {row.get('behavior_version', 1)}
"""
            )
        memory_text = "\n---\n".join(chunks)

    regression_text = "No related active regression cases were found."
    if regression_context:
        chunks = []
        for row in regression_context:
            chunks.append(
                f"""Regression Test Case ID: {row.get('Test Case ID')}
Title: {row.get('Test case title')}
Precondition: {row.get('Precondition')}
Expected Result: {row.get('Expected result')}
"""
            )
        regression_text = "\n---\n".join(chunks)

    revision_text = "No revision requested."
    if revision:
        revision_text = f"""Revision requested by the human QA reviewer:
{revision}

Revision rules:
- Keep valid existing cases when they are still supported by the ticket.
- Modify only affected cases where practical.
- Add missing scenarios required by the revision.
- Remove or consolidate duplicates.
- Do not invent behavior not supported by the ticket or historical context.
"""

    previous_text = "No previous generated CSV was supplied."
    if previous_cases:
        chunks = []
        for row in previous_cases:
            chunks.append(
                f"""Test Case ID: {row.get('Test Case ID')}
Title: {row.get('Test case title')}
Precondition: {row.get('Precondition')}
Steps:
{row.get('Test steps')}
Expected:
{row.get('Expected result')}
"""
            )
        previous_text = "\n---\n".join(chunks)

    return f"""{instructions}

## Active Regression Suite Context

Use this as the current approved regression baseline. If the ticket does not explicitly change a relevant behavior, preserve its coverage. If the ticket explicitly changes it, update the affected expectation rather than keeping contradictory active coverage.

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

Return JSON only. Ensure every test case has numbered test steps and numbered expected-result items.
"""


def generate_with_openai(api_key, model, prompt):
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model=model, input=prompt)
    return response.output_text


def generate_with_gemini(api_key, model, prompt):
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return response.text


def generate_ai_response(prompt, openai_api_key, openai_model, gemini_api_key, gemini_model, gemini_fallback_model):
    openai_error = None

    if openai_api_key:
        try:
            print(f"[AI] Trying OpenAI: {openai_model}")
            raw = generate_with_openai(openai_api_key, openai_model, prompt)
            print("[AI] OpenAI generation successful.")
            return raw, f"OpenAI/{openai_model}"
        except Exception as exc:
            openai_error = exc
            print(f"[AI] OpenAI failed: {exc}", file=sys.stderr)
    else:
        print("[AI] OPENAI_API_KEY is not configured. Skipping OpenAI.")

    if not gemini_api_key:
        raise RuntimeError(
            f"OpenAI failed and GEMINI_API_KEY is not configured. OpenAI error: {openai_error}"
        )

    gemini_error = None
    try:
        print(f"[AI] Falling back to Gemini: {gemini_model}")
        raw = generate_with_gemini(gemini_api_key, gemini_model, prompt)
        print("[AI] Gemini primary generation successful.")
        return raw, f"Gemini/{gemini_model}"
    except Exception as exc:
        gemini_error = exc
        print(f"[AI] Gemini primary failed: {exc}", file=sys.stderr)

    if gemini_fallback_model:
        try:
            print(f"[AI] Falling back to secondary Gemini: {gemini_fallback_model}")
            raw = generate_with_gemini(gemini_api_key, gemini_fallback_model, prompt)
            print("[AI] Gemini secondary generation successful.")
            return raw, f"Gemini/{gemini_fallback_model}"
        except Exception as exc:
            raise RuntimeError(
                "All configured AI providers failed.\n"
                f"OpenAI error: {openai_error}\n"
                f"Gemini primary error: {gemini_error}\n"
                f"Gemini fallback error: {exc}"
            ) from exc

    raise RuntimeError(
        f"OpenAI and Gemini primary failed.\nOpenAI: {openai_error}\nGemini: {gemini_error}"
    )


def main():
    parser = argparse.ArgumentParser(description="Generate AI-TLC test cases with OpenAI -> Gemini fallback.")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--output")
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--memory-limit", type=int, default=15)
    parser.add_argument("--revision", default="")
    parser.add_argument("--previous-output")
    args = parser.parse_args()

    ticket_path = Path(args.ticket).resolve()
    if not ticket_path.exists():
        print(f"ERROR: Ticket not found: {ticket_path}", file=sys.stderr)
        return 1

    ticket_text = read_text(ticket_path)
    memory_context = load_memory_context(ticket_text, args.memory_limit)
    regression_context = load_regression_context(ticket_text, args.memory_limit)
    previous_cases = read_previous_output(Path(args.previous_output).resolve()) if args.previous_output else []
    prompt = build_prompt(ticket_text, memory_context, regression_context, previous_cases, args.revision)

    print(f"Related memory entries: {len(memory_context)}")
    print(f"Related regression entries: {len(regression_context)}")
    if previous_cases:
        print(f"Previous generated cases supplied: {len(previous_cases)}")
    if args.revision:
        print("Revision mode: enabled")

    if args.dry_run:
        print(prompt)
        return 0

    load_dotenv(ROOT / ".env")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not openai_api_key and not gemini_api_key:
        print("ERROR: Neither OPENAI_API_KEY nor GEMINI_API_KEY is configured.", file=sys.stderr)
        return 1

    openai_model = args.model or os.getenv("AITLC_MODEL", "gpt-5.6-luna")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    gemini_fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.7-flash")

    try:
        raw, provider = generate_ai_response(
            prompt,
            openai_api_key,
            openai_model,
            gemini_api_key,
            gemini_model,
            gemini_fallback_model,
        )
    except Exception as exc:
        print(f"ERROR: AI generation failed: {exc}", file=sys.stderr)
        return 1

    try:
        data = extract_json(raw)
        records = validate_records(data)
    except Exception as exc:
        print(f"ERROR: Invalid AI output: {exc}", file=sys.stderr)
        print(raw, file=sys.stderr)
        return 1

    output_path = Path(args.output).resolve() if args.output else DEFAULT_OUTPUT_DIR / f"{ticket_path.stem}-test-cases.csv"
    write_csv(records, output_path)
    print(f"Generated {len(records)} test cases.")
    print(f"Provider: {provider}")
    print(f"CSV: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
