"""Create synthetic goal/dependency review data; refuse to overwrite any existing file."""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import week_bounds
from workspace.advanced_repository import add_fixed_event, add_window, set_task_dependencies
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task


def create_demo(path, now):
    # Exclusive create is also safe against another process creating the path.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb"):
        pass
    _, sunday = week_bounds(now.date())
    tasks = [
        ("Short assignment due soon", 1, 120, now.date()),
        ("Important project", 3, 240, sunday),
        ("Research report", 2, 60, sunday),
        ("Write report after research", 2, 60, sunday),
    ]
    ids = [
        create_quick_task(path, TaskDraft(title, "Demo", due, priority, minutes))
        for title, priority, minutes, due in tasks
    ]
    set_task_dependencies(path, ids[3], [ids[2]])
    for offset in range((sunday - now.date()).days + 1):
        day = now.date() + timedelta(days=offset)
        start = max(540, now.hour * 60 + now.minute + 10) if offset == 0 else 540
        if start < 1320:
            add_window(path, day, start, min(start + 90, 1320))
        if offset > 0:
            add_fixed_event(path, "Example lecture", day, 600, 630, "Lecture")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/optimizer-demo.db"))
    args = parser.parse_args()
    create_demo(args.output, datetime.now())
    print(f"Synthetic review data created: {args.output.resolve()}")


if __name__ == "__main__":
    main()
