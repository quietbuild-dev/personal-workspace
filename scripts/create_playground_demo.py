"""Create a separate demo database for exploring Personal Workspace.

Never opens or overwrites the user's data/workspace.db. Run from project root:
python -m scripts.create_playground_demo --output data/study-playground.db
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import make_revision, week_bounds
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    load_snapshot,
    save_day_preferences,
)
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task
from workspace.repository import DEFAULT_DB_PATH


def create_playground(db_path: Path, now: datetime) -> dict[str, int]:
    """Return numbers for the demo; refuse to replace an existing or personal database."""
    path = db_path.resolve()
    if path == DEFAULT_DB_PATH.resolve():
        raise ValueError("Refusing to overwrite the personal workspace database.")
    if path.exists():
        raise FileExistsError(
            f"Demo already exists: {path}. Delete only this DEMO file to reset it."
        )
    if now.tzinfo is not None:
        raise ValueError("Use the computer's local, timezone-naive date/time.")
    path.parent.mkdir(parents=True, exist_ok=True)

    _, sunday = week_bounds(now.date())

    def day(offset: int) -> date:
        return min(now.date() + timedelta(days=offset), sunday)

    days = [now.date() + timedelta(days=i) for i in range((sunday - now.date()).days + 1)]

    # Dedicated consented study capacity and flexible preferred periods. Zero is a day off.
    targets = [90, 180, 150, 120, 150, 60, 0]
    preferences = [
        (18 * 60, 22 * 60),
        (9 * 60, 19 * 60),
        (12 * 60, 21 * 60),
        (9 * 60, 18 * 60),
        (10 * 60, 18 * 60),
        (10 * 60, 17 * 60),
        (10 * 60, 17 * 60),
    ]
    from workspace.quick_tasks import initialize_quick_tasks

    initialize_quick_tasks(path)
    try:
        for i, d in enumerate(days):
            # Today can only be scheduled after current time; future days have realistic windows.
            span = preferences[min(i, len(preferences) - 1)]
            if i == 0:
                start = max(span[0], ((now.hour * 60 + now.minute + 29) // 30) * 30)
                if start >= 22 * 60:
                    save_day_preferences(path, d, 0, 18 * 60, 22 * 60)
                else:
                    save_day_preferences(path, d, targets[i], start, 22 * 60)
            else:
                save_day_preferences(path, d, targets[min(i, len(targets) - 1)], *span)

        # Known real-life blocks. The planner derives free gaps from these.
        event_specs = [
            (1, "Statistics lecture", 10 * 60, 12 * 60, "Lecture"),
            (2, "Economics seminar", 13 * 60, 15 * 60, "Lecture"),
            (3, "Software Engineering lecture", 11 * 60, 13 * 60, "Lecture"),
            (1, "Gym session", 17 * 60, 18 * 60, "Exercise"),
            (2, "Association committee meeting", 18 * 60, 19 * 60, "Appointment"),
            (3, "Dinner with friends", 19 * 60, 21 * 60, "Social"),
            (4, "Brunch", 12 * 60, 13 * 60 + 30, "Social"),
            (4, "Groceries", 16 * 60, 17 * 60, "Personal"),
        ]
        for offset, title, start, end, kind in event_specs:
            candidate = now.date() + timedelta(days=offset)
            if candidate <= sunday:
                add_fixed_event(path, title, candidate, start, end, kind)

        task_specs = [
            (
                "Finish statistics problem set",
                "University",
                1,
                18 * 60,
                3,
                150,
                ["Finish questions 1-4", "Check solutions", "Submit assignment"],
            ),
            (
                "Economics midterm revision",
                "University",
                2,
                20 * 60,
                3,
                180,
                ["Revise Chapter 3", "Solve two past-paper questions"],
            ),
            (
                "Software Engineering report",
                "University",
                3,
                18 * 60,
                3,
                150,
                [
                    "Describe scheduling trade-offs",
                    "Run performance experiment",
                    "Draft conclusion",
                ],
            ),
            (
                "Prepare association presentation",
                "Student Association",
                4,
                17 * 60,
                2,
                90,
                ["Outline slides", "Review with team"],
            ),
            (
                "Revise calculus notes",
                "University",
                5,
                20 * 60,
                2,
                120,
                ["Review definitions", "Practice proofs"],
            ),
            ("Personal admin", "Personal", 5, 19 * 60, 1, 45, ["Pay bill", "Reply to email"]),
        ]
        for title, category, offset, due, priority, minutes, checks in task_specs:
            due_day = now.date() + timedelta(days=offset)
            task_id = create_quick_task(
                path,
                TaskDraft(title, category, due_day, priority, minutes),
                due_minute=due,
            )
            for check in checks:
                add_step(path, task_id, check, "checklist")

        before = load_snapshot(path)
        suggested = make_revision(before, now)
        if suggested.slots:
            accept_revision(path, suggested, now)

        # Introduce a realistic new lecture AFTER accepting the original schedule.
        # This creates a visible problem for the Rescue My Week comparison.
        saved = load_snapshot(path)
        future_sessions = sorted(
            [s for s in saved.sessions if s.status == "planned" and s.day > now.date()],
            key=lambda s: (s.day, s.start),
        )
        if future_sessions:
            target = future_sessions[0]
            add_fixed_event(
                path,
                "NEW: guest lecture (conflicts with study)",
                target.day,
                target.start,
                min(target.end, target.start + 60),
                "Lecture",
            )

        # A last-minute task is added after the original plan was accepted.
        # This makes the overload warnings and strategy trade-off visible.
        last_minute_id = create_quick_task(
            path,
            TaskDraft("NEW: surprise economics quiz", "University", day(3), 3, 60),
            due_minute=17 * 60,
        )
        add_step(path, last_minute_id, "Review the quiz topics", "checklist")

        snapshot = load_snapshot(path)
        return {
            "tasks": len({s.task_id for s in snapshot.steps}),
            "events": len(snapshot.events),
            "sessions": len(snapshot.sessions),
            "budget_days": len(snapshot.budgets),
        }
    except Exception:
        # The path is guaranteed not to have existed before this operation.
        path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/study-playground.db"))
    args = parser.parse_args()
    result = create_playground(args.output, datetime.now())
    print(f"Created a separate sample database at {args.output.resolve()}")
    print(
        f"{result['tasks']} tasks, {result['events']} events, "
        f"{result['sessions']} accepted study blocks, "
        f"{result['budget_days']} days of study preferences."
    )
    print("Personal data/workspace.db was not opened or modified.")


if __name__ == "__main__":
    main()
