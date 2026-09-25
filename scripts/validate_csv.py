import argparse
import csv
import re
import sys
from pathlib import Path

COLUMNS = [
    "Test Case ID",
    "Test case title",
    "Precondition",
    "Test steps",
    "Expected result",
    "Status",
    "Note",
]


def validate(path: Path):
    errors = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != COLUMNS:
            errors.append(
                f"Headers do not match exactly.\nExpected: {COLUMNS}\nActual: {reader.fieldnames}"
            )

        rows = list(reader)

    ids = set()
    titles = set()

    for row_number, row in enumerate(rows, start=2):
        tc_id = (row.get("Test Case ID") or "").strip()
        title = (row.get("Test case title") or "").strip()
        precondition = (row.get("Precondition") or "").strip()
        steps = row.get("Test steps") or ""
        expected = row.get("Expected result") or ""
        status = row.get("Status") or ""
        note = row.get("Note") or ""

        if not tc_id:
            errors.append(f"Row {row_number}: Test Case ID is empty.")
        elif tc_id in ids:
            errors.append(f"Row {row_number}: duplicate Test Case ID '{tc_id}'.")
        ids.add(tc_id)

        title_key = re.sub(r"\s+", " ", title).lower()
        if not title:
            errors.append(f"Row {row_number}: Test case title is empty.")
        elif title_key in titles:
            errors.append(f"Row {row_number}: duplicate test-case title.")
        titles.add(title_key)

        if not precondition:
            errors.append(f"Row {row_number}: Precondition must not be empty; use 'None'.")

        if not steps.strip():
            errors.append(f"Row {row_number}: Test steps are empty.")
        else:
            step_lines = steps.splitlines()
            for i, line in enumerate(step_lines, start=1):
                if not re.match(r"^\d+\.\s+\S+", line):
                    errors.append(
                        f"Row {row_number}: step line {i} must look like '1. Action'."
                    )

        if not expected.strip():
            errors.append(f"Row {row_number}: Expected result is empty.")
        else:
            expected_lines = expected.splitlines()
            for i, line in enumerate(expected_lines, start=1):
                if not re.match(r"^\d+\.\s+\S+", line):
                    errors.append(
                        f"Row {row_number}: expected-result line {i} "
                        "must look like '1. Observable result'."
                    )

        if status.strip():
            errors.append(f"Row {row_number}: Status must be blank.")
        if note.strip():
            errors.append(f"Row {row_number}: Note must be blank.")

    return errors, len(rows)


def main():
    parser = argparse.ArgumentParser(description="Validate an AI-TLC CSV.")
    parser.add_argument("csv_file")
    args = parser.parse_args()

    path = Path(args.csv_file).resolve()

    if not path.exists():
        print(f"FAIL: File not found: {path}")
        return 1

    errors, count = validate(path)

    if errors:
        print("FAIL: AI-TLC CSV validation failed.")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"PASS: {count} test cases validated successfully.")
    print(f"CSV: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
