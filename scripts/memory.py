import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = ROOT / "memory"
TEST_CASE_MEMORY = MEMORY_DIR / "test_cases.jsonl"
BEHAVIOR_MEMORY = MEMORY_DIR / "behaviors.jsonl"


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def tokens(text):
    return set(normalize(text).split())


def fingerprint(*values):
    value = "||".join(normalize(v) for v in values)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def save_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_csv(csv_path):
    required = [
        "Test Case ID", "Test case title", "Precondition",
        "Test steps", "Expected result", "Status", "Note"
    ]
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != required:
            raise ValueError(f"Invalid headers. Expected exactly: {required}")
        return list(reader)


def approve_csv(csv_path, ticket_name, reviewer):
    rows = read_csv(csv_path)
    if not rows:
        raise ValueError("CSV contains no test cases.")

    test_cases = load_jsonl(TEST_CASE_MEMORY)
    behaviors = load_jsonl(BEHAVIOR_MEMORY)

    by_memory_id = {r.get("memory_id"): r for r in test_cases}
    behavior_by_id = {r.get("behavior_id"): r for r in behaviors}
    approved = 0
    updated = 0

    for row in rows:
        tc_id = row["Test Case ID"].strip()
        title = row["Test case title"].strip()
        expected = row["Expected result"].strip()
        memory_id = f"{ticket_name}:{tc_id}"
        behavior_id = "behavior:" + fingerprint(title)

        existing = by_memory_id.get(memory_id)
        version = existing.get("behavior_version", 1) if existing else 1
        created_at = existing.get("created_at", now()) if existing else now()

        record = {
            "memory_id": memory_id,
            "ticket": ticket_name,
            "test_case_id": tc_id,
            "title": title,
            "behavior": f"{title}. Expected behavior: {expected.replace(chr(10), ' ')}",
            "precondition": row["Precondition"],
            "test_steps": row["Test steps"],
            "expected_result": expected,
            "status": "approved",
            "reviewer": reviewer,
            "tags": sorted(tokens(ticket_name + " " + title + " " + expected)),
            "behavior_id": behavior_id,
            "behavior_version": version,
            "created_at": created_at,
            "updated_at": now(),
        }
        by_memory_id[memory_id] = record
        if existing:
            updated += 1
        else:
            approved += 1

        behavior = behavior_by_id.get(behavior_id)
        if behavior:
            if normalize(behavior.get("expected_result", "")) != normalize(expected):
                behavior["version"] = int(behavior.get("version", 1)) + 1
                behavior["previous_expected_result"] = behavior.get("expected_result", "")
                behavior["expected_result"] = expected
                behavior["source_memory_ids"] = sorted(set(behavior.get("source_memory_ids", []) + [memory_id]))
                behavior["status"] = "active"
                behavior["updated_at"] = now()
                record["behavior_version"] = behavior["version"]
                by_memory_id[memory_id]["behavior_version"] = behavior["version"]
        else:
            behavior_by_id[behavior_id] = {
                "behavior_id": behavior_id,
                "canonical_title": title,
                "expected_result": expected,
                "version": 1,
                "status": "active",
                "source_memory_ids": [memory_id],
                "created_at": now(),
                "updated_at": now(),
            }

    save_jsonl(TEST_CASE_MEMORY, list(by_memory_id.values()))
    save_jsonl(BEHAVIOR_MEMORY, list(behavior_by_id.values()))

    print(f"Approved new: {approved}")
    print(f"Updated existing: {updated}")
    print(f"Test-case memory: {TEST_CASE_MEMORY}")
    print(f"Behavior memory: {BEHAVIOR_MEMORY}")


def search(query, limit=10):
    query_tokens = tokens(query)
    rows = [r for r in load_jsonl(TEST_CASE_MEMORY) if r.get("status") == "approved"]
    scored = []

    for row in rows:
        haystack = tokens(" ".join([
            row.get("ticket", ""), row.get("title", ""),
            row.get("behavior", ""), " ".join(row.get("tags", []))
        ]))
        overlap = len(query_tokens & haystack)
        if overlap:
            score = overlap / max(1, len(query_tokens))
            scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    for score, row in scored[:limit]:
        print(json.dumps({
            "score": round(score, 3),
            "memory_id": row["memory_id"],
            "ticket": row["ticket"],
            "test_case_id": row["test_case_id"],
            "title": row["title"],
            "behavior_version": row.get("behavior_version", 1),
            "reviewer": row.get("reviewer", ""),
        }, ensure_ascii=False))


def list_memory():
    rows = load_jsonl(TEST_CASE_MEMORY)
    if not rows:
        print("Test Case Memory is empty.")
        return
    for row in rows:
        print(f"{row.get('memory_id')} | {row.get('status')} | {row.get('title')}")
    print(f"\nTotal: {len(rows)}")


def main():
    parser = argparse.ArgumentParser(description="Manage AI-TLC approved test-case and behavior memory.")
    sub = parser.add_subparsers(dest="command", required=True)

    approve = sub.add_parser("approve", help="Approve a reviewed CSV into memory.")
    approve.add_argument("--csv", required=True)
    approve.add_argument("--ticket", required=True)
    approve.add_argument("--reviewer", default="human-qa")

    # Backward-compatible alias. It now means an explicit approval action.
    index = sub.add_parser("index", help="Backward-compatible alias for approve.")
    index.add_argument("--csv", required=True)
    index.add_argument("--ticket", required=True)
    index.add_argument("--reviewer", default="human-qa")

    search_cmd = sub.add_parser("search")
    search_cmd.add_argument("--query", required=True)
    search_cmd.add_argument("--limit", type=int, default=10)

    sub.add_parser("list")

    args = parser.parse_args()
    if args.command in {"approve", "index"}:
        approve_csv(Path(args.csv).resolve(), args.ticket, args.reviewer)
    elif args.command == "search":
        search(args.query, args.limit)
    elif args.command == "list":
        list_memory()


if __name__ == "__main__":
    main()
