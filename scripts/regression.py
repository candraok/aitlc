import argparse
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGRESSION_DIR = ROOT / "regression"
MASTER = REGRESSION_DIR / "master-regression.csv"

COLUMNS = [
    "Test Case ID",
    "Test case title",
    "Precondition",
    "Test steps",
    "Expected result",
    "Status",
    "Note",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def load_master():
    if not MASTER.exists():
        return []

    with MASTER.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_master(rows):
    REGRESSION_DIR.mkdir(parents=True, exist_ok=True)

    with MASTER.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def case_key(row):
    value = "||".join([
        row.get("Test case title", "").strip().lower(),
        row.get("Precondition", "").strip().lower(),
        row.get("Test steps", "").strip().lower(),
        row.get("Expected result", "").strip().lower(),
    ])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def add_csv(source, selected_ids=None, add_all=False):
    if not source.exists():
        raise FileNotFoundError(source)

    with source.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames != COLUMNS:
            raise ValueError(
                f"Invalid headers. Expected exactly: {COLUMNS}"
            )

        incoming = list(reader)

    if not add_all and not selected_ids:
        raise ValueError("Select cases explicitly with --ids TC001,TC002 or use --all after QA approval.")

    existing = load_master()
    existing_keys = {case_key(row) for row in existing}

    added = 0
    skipped = 0

    for row in incoming:
        if not add_all and row["Test Case ID"] not in selected_ids:
            continue
        key = case_key(row)

        if key in existing_keys:
            skipped += 1
            continue

        existing.append({
            "Test Case ID": row["Test Case ID"],
            "Test case title": row["Test case title"],
            "Precondition": row["Precondition"] or "None",
            "Test steps": row["Test steps"],
            "Expected result": row["Expected result"],
            "Status": "",
            "Note": "",
        })

        existing_keys.add(key)
        added += 1

    save_master(existing)

    print(f"Added: {added}")
    print(f"Skipped duplicates: {skipped}")
    print(f"Current regression cases: {len(existing)}")
    print(f"Updated: {MASTER}")


def list_cases():
    rows = load_master()

    if not rows:
        print("Regression suite is empty.")
        return

    for row in rows:
        print(
            f"{row['Test Case ID']} | "
            f"{row['Test case title']}"
        )

    print(f"\nTotal: {len(rows)}")


def validate():
    rows = load_master()
    errors = []
    ids = set()
    titles = set()

    for index, row in enumerate(rows, start=2):
        tc_id = row["Test Case ID"].strip()
        title = row["Test case title"].strip()

        if not tc_id:
            errors.append(f"Row {index}: Test Case ID is empty.")

        if tc_id in ids:
            errors.append(f"Row {index}: duplicate Test Case ID: {tc_id}")
        ids.add(tc_id)

        title_key = title.lower()
        if title_key in titles:
            errors.append(f"Row {index}: duplicate title: {title}")
        titles.add(title_key)

        if not row["Precondition"].strip():
            errors.append(f"Row {index}: Precondition is empty.")

        for field in ["Test steps", "Expected result"]:
            value = row[field].strip()
            if not value:
                errors.append(f"Row {index}: {field} is empty.")
                continue

            for line_number, line in enumerate(value.splitlines(), start=1):
                if not line.strip():
                    continue

                if not line.lstrip().split(".", 1)[0].isdigit():
                    errors.append(
                        f"Row {index}: {field} line {line_number} "
                        "is not numbered."
                    )

        if row["Status"].strip():
            errors.append(f"Row {index}: Status should be blank.")

        if row["Note"].strip():
            errors.append(f"Row {index}: Note should be blank.")

    if errors:
        print("FAIL: Regression validation failed.")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"PASS: Regression suite is valid ({len(rows)} cases).")
    print(f"Validated: {MASTER}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Manage the AI-TLC current regression suite."
    )

    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("--csv", required=True)
    group = add.add_mutually_exclusive_group(required=True)
    group.add_argument("--ids", help="Comma-separated approved test-case IDs to promote.")
    group.add_argument("--all", action="store_true", help="Promote all cases from the reviewed CSV.")

    sub.add_parser("list")
    sub.add_parser("validate")

    args = parser.parse_args()

    if args.command == "add":
        selected_ids = None
        if args.ids:
            selected_ids = {x.strip() for x in args.ids.split(",") if x.strip()}
        try:
            add_csv(Path(args.csv).resolve(), selected_ids=selected_ids, add_all=args.all)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            raise SystemExit(1)
    elif args.command == "list":
        list_cases()
    elif args.command == "validate":
        raise SystemExit(validate())


if __name__ == "__main__":
    main()
