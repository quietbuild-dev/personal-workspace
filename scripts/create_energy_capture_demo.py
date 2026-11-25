"""Create an isolated focus-mode demo DB; never replace an existing file."""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import Slot, week_bounds
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_window,
    load_snapshot,
)
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task
from workspace.repository import DEFAULT_DB_PATH


def create_demo(path: Path, now: datetime | None = None):
    if now is None:
        now = datetime.now()
    path = path.expanduser().resolve()
    if path == DEFAULT_DB_PATH.resolve():
        raise ValueError("The demo cannot use your personal database.")
    if path.exists():
        raise ValueError("The demo file already exists. Choose a new filename.")
    day = now.date() + timedelta(days=1)
    if day > week_bounds(now.date())[1]:
        raise ValueError("There is no future day left in this planning week; try next week.")
    deadline = min(day + timedelta(days=1), week_bounds(now.date())[1])
    task_id = create_quick_task(
        path, TaskDraft("Algorithms exam preparation", "University", deadline, 3, 120)
    )
    add_window(path, day, 10 * 60, 14 * 60)
    add_fixed_event(path, "Statistics lecture", day, 9 * 60, 10 * 60, "Lecture")
    snapshot = load_snapshot(path)
    step = next(step.id for step in snapshot.steps if step.task_id == task_id)
    proposal = proposal_from_slots(snapshot, now, (Slot(step, day, 600, 720),))
    accept_revision(path, proposal, now)
    print(f"DEMO_DB={path}")
    print(f"FOCUS_DAY={day.isoformat()}")
    print("Expected: one saved 2h study session, which Low energy previews as five shorter blocks.")
    print("Your personal database is untouched.")
    return day


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    create_demo(arguments.output)


if __name__ == "__main__":
    main()
