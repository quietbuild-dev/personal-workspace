"""Create a reproducible, clearly separate example database; never replace a file."""

import argparse
from datetime import date, timedelta
from pathlib import Path

from workspace.models import TaskDraft
from workspace.planner import week_bounds
from workspace.repository import (
    DEFAULT_DB_PATH,
    create_task,
    initialize_database,
    save_availability,
    update_task,
)


def build_demo(db_path: Path, today: date) -> None:
    if db_path.resolve() == DEFAULT_DB_PATH.resolve():
        raise ValueError("The demo destination cannot be the active personal database.")
    if db_path.exists():
        raise FileExistsError(f"Destination already exists: {db_path}. Nothing was overwritten.")
    _, sunday = week_bounds(today)
    tomorrow = min(today + timedelta(days=1), sunday)
    soon = min(today + timedelta(days=2), sunday)

    initialize_database(db_path)
    create_task(db_path, TaskDraft("Prepare course presentation", "University", tomorrow, 3, 150))
    create_task(db_path, TaskDraft("Review algorithm notes", "University", today, 2, 90))
    create_task(db_path, TaskDraft("Read software engineering chapter", "University", soon, 1, 80))
    create_task(db_path, TaskDraft("Organize personal files", "Personal", None, 1, 50))
    create_task(
        db_path, TaskDraft("Later project planning", "Work", today + timedelta(days=12), 2, 100)
    )
    create_task(
        db_path, TaskDraft("Past-due reference", "University", today - timedelta(days=2), 3, 40)
    )
    completed_draft = TaskDraft("Submit weekly notes", "University", soon, 2, 35)
    completed = create_task(db_path, completed_draft)
    update_task(db_path, completed.id, completed_draft, 0)
    days = {
        today + timedelta(days=i): amount
        for i, amount in enumerate([90, 80, 60])
        if today + timedelta(days=i) <= sunday
    }
    save_availability(db_path, days)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/demo-workspace.db"))
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=date.today(),
        help="Fixed demo anchor date in YYYY-MM-DD form (default: today)",
    )
    arguments = parser.parse_args()
    try:
        build_demo(arguments.output, arguments.today)
    except (FileExistsError, ValueError) as error:
        parser.exit(1, f"Demo not created: {error}\n")
    print(f"Created demo database: {arguments.output.resolve()}")
    print("Your existing personal database was not changed.")


if __name__ == "__main__":
    main()
