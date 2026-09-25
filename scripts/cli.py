import csv
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(script, *args):
    command = [sys.executable, str(SCRIPTS / script), *map(str, args)]
    return subprocess.run(command, cwd=ROOT).returncode


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def choose(prompt, options):
    print(f"\n{prompt}")
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")
    while True:
        value = input("Select: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(options):
            return int(value) - 1
        print("Please enter one of the listed numbers.")


def select_ids(csv_path):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []

    print("\nAvailable test cases:")
    for i, row in enumerate(rows, 1):
        print(f"  {i:>3}. {row.get('Test Case ID')} - {row.get('Test case title')}")

    while True:
        raw = input("\nEnter case numbers separated by comma (example: 1,3,5): ").strip()
        try:
            indexes = [int(x.strip()) for x in raw.split(",") if x.strip()]
            if not indexes or any(i < 1 or i > len(rows) for i in indexes):
                raise ValueError
            selected = []
            for i in indexes:
                tc_id = rows[i - 1].get("Test Case ID")
                if tc_id and tc_id not in selected:
                    selected.append(tc_id)
            return selected
        except ValueError:
            print("Invalid selection. Use numbers from the list, e.g. 1,3,5.")


def open_csv(path):
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        print(f"Opened: {path}")
    except Exception as exc:
        print(f"Could not open automatically: {exc}")
        print(f"CSV: {path}")


def validate(output):
    return run_script("validate_csv.py", str(output)) == 0


def revise_loop(ticket_path, output_path):
    categories = [
        "Missing test scenarios",
        "Incorrect expected result",
        "Incorrect business rule",
        "Missing negative cases",
        "Missing edge/boundary cases",
        "Duplicate test cases",
        "Incorrect API coverage",
        "Incorrect UI coverage",
        "Incorrect database coverage",
        "Regression coverage issue",
        "Other",
    ]

    selected = []
    print("\nSelect revision areas. Enter numbers separated by comma.")
    for i, item in enumerate(categories, 1):
        print(f"  {i:>2}. {item}")
    while True:
        raw = input("Revision areas: ").strip()
        try:
            nums = [int(x.strip()) for x in raw.split(",") if x.strip()]
            if not nums or any(n < 1 or n > len(categories) for n in nums):
                raise ValueError
            selected = [categories[n - 1] for n in nums]
            break
        except ValueError:
            print("Invalid selection. Example: 1,4,5")

    details = input("Additional revision instructions (optional): ").strip()
    revision = "Areas: " + ", ".join(selected)
    if details:
        revision += "\nAdditional instructions: " + details

    revision_output = output_path.with_name(output_path.stem + ".revision.csv")
    rc = run_script(
        "generate_test_cases.py",
        "--ticket", str(ticket_path),
        "--output", str(revision_output),
        "--revision", revision,
        "--previous-output", str(output_path),
    )
    if rc != 0:
        return False

    if not validate(revision_output):
        print("Revision CSV failed validation. The previously validated CSV is still preserved.")
        try:
            revision_output.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    revision_output.replace(output_path)
    return True


def process_ticket():
    ticket_id = ask("Ticket ID (example TASK-1234)")
    if not ticket_id:
        print("Ticket ID is required.")
        return

    ticket_path = ROOT / "ticket" / f"{ticket_id}.md"
    if not ticket_path.exists():
        print(f"ERROR: Ticket not found: {ticket_path}")
        print("Create the ticket markdown file under ticket/ first.")
        return

    output_path = ROOT / "output" / f"{ticket_id}-test-cases.csv"
    print(f"\n✓ Ticket found: {ticket_path}")
    print("\n=== Generating Test Cases ===")
    if run_script("generate_test_cases.py", "--ticket", str(ticket_path), "--output", str(output_path)) != 0:
        return

    if not validate(output_path):
        print("\nGeneration completed but validation failed. Please revise the CSV manually or use the revise flow.")
        return

    while True:
        print(f"\nCSV: {output_path}")
        action = choose("Test case generation completed. What would you like to do?", [
            "Approve",
            "Revise",
            "Open CSV",
            "Cancel",
        ])

        if action == 2:
            open_csv(output_path)
            continue
        if action == 3:
            print("Workflow cancelled. Generated CSV was kept in output/.")
            return
        if action == 1:
            if not revise_loop(ticket_path, output_path):
                print("Revision failed. Returning to review with the previous CSV kept.")
                continue
            continue

        # Approve
        reviewer = ask("Reviewer name", os.getenv("AITLC_REVIEWER", "human-qa"))
        print("\n=== Save Approved Test Cases to Memory ===")
        memory_choice = choose("Save approved test cases to Memory?", ["Yes", "No"])
        if memory_choice == 0:
            if run_script("memory.py", "approve", "--csv", str(output_path), "--ticket", ticket_id, "--reviewer", reviewer) != 0:
                print("Memory approval failed. Regression promotion was skipped.")
                return
        else:
            print("Memory update skipped.")

        print("\n=== Regression Promotion ===")
        regression_choice = choose("What should be added to Master Regression?", [
            "All test cases",
            "Select specific test cases",
            "None",
        ])

        if regression_choice == 0:
            rc = run_script("regression.py", "add", "--csv", str(output_path), "--all")
            if rc != 0:
                return
        elif regression_choice == 1:
            ids = select_ids(output_path)
            if ids:
                rc = run_script("regression.py", "add", "--csv", str(output_path), "--ids", ",".join(ids))
                if rc != 0:
                    return
            else:
                print("No cases selected.")
        else:
            print("No test cases added to regression.")

        run_script("regression.py", "validate")
        print("\n========================================")
        print("AI-TLC workflow completed")
        print("========================================")
        print(f"Ticket     : {ticket_id}")
        print(f"Output CSV : {output_path}")
        return


def main():
    while True:
        print("\n========================================")
        print("        AI-TLC Interactive CLI")
        print("========================================")
        choice = choose("What would you like to do?", [
            "Process a ticket",
            "Search Memory",
            "View Regression Suite",
            "Validate Regression Suite",
            "Exit",
        ])

        if choice == 0:
            process_ticket()
        elif choice == 1:
            query = ask("Search query")
            if query:
                run_script("memory.py", "search", "--query", query)
        elif choice == 2:
            run_script("regression.py", "list")
        elif choice == 3:
            run_script("regression.py", "validate")
        else:
            print("Goodbye.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
