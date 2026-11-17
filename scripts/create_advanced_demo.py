"""Create a separate, safe-to-delete hourly-planner demonstration database.

Usage: python -m scripts.create_advanced_demo --output data/study-demo.db
Refuses to overwrite an existing file (including personal databases).
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import make_revision, week_bounds
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
)
from workspace.models import TaskDraft
from workspace.repository import create_task


def create_demo(path: Path, now: datetime) -> tuple[int, int]:
    if path.exists():
        raise FileExistsError(f"Demo file already exists: {path}. Choose a new output path.")
    if now.tzinfo is not None:
        raise ValueError("Use a local time without timezone information.")
    path.parent.mkdir(parents=True, exist_ok=True)
    initialize_advanced(path)
    try:
        today = now.date()
        _, sunday = week_bounds(today)
        exam = create_task(
            path, TaskDraft("Prepare for economics exam", "Economics", sunday, 3, 180)
        )
        add_step(path, exam.id, "Download past papers", "checklist")
        add_step(path, exam.id, "Revise Chapter 3", "timed", 60)
        add_step(path, exam.id, "Practice past questions", "timed", 90)
        personal = create_task(path, TaskDraft("Life administration", "Personal", None, 2, 45))
        add_step(path, personal.id, "Pay utility bill", "checklist")
        add_step(path, personal.id, "Household planning", "timed", 45)
        # Date-specific windows. Favor tomorrow to avoid generating a schedule in the past.
        for n in range(min(3, (sunday - today).days + 1)):
            day = today + timedelta(days=n)
            start = 9 * 60 if day > today else max(9 * 60, now.hour * 60 + now.minute + 15)
            if start < 19 * 60:
                add_window(path, day, start, 19 * 60)
                add_fixed_event(
                    path,
                    "Lecture / appointment" if n == 0 else "Fixed commitment",
                    day,
                    14 * 60,
                    15 * 60,
                )
        snapshot = load_snapshot(path)
        preview = make_revision(snapshot, now)
        accept_revision(path, preview, now)
        return len(preview.slots), sum(s.minutes for s in preview.slots)
    except Exception:
        # All data is demo-only, and the file did not exist before this operation.
        path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data") / "study-demo.db")
    args = parser.parse_args()
    count, minutes = create_demo(args.output, datetime.now())
    print(f"Created separate demo database at {args.output}")
    print(f"Accepted {count} timetable sessions ({minutes} minutes).")
    print("Your regular data/workspace.db was not opened or modified.")
    print("To view: set WORKSPACE_DB_PATH to the demo file, then launch Streamlit.")


if __name__ == "__main__":
    main()
