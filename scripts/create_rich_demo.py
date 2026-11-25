r"""Create a fuller, isolated sample week with lectures, commitments and study blocks.

Run in the project folder, e.g.:
    .\.venv\Scripts\python.exe -m scripts.create_rich_demo --output data\rich-unique.db

Never uses the personal workspace.db. Best run Wed evening Nov 25, 2026.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import Slot
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    load_snapshot,
    save_day_preferences,
    set_task_dependencies,
)
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task, edit_quick_task, linked_step_ids
from workspace.study_dna import set_required


def create_demo(db: Path, *, now: datetime | None = None) -> Path:
    now = now or datetime.now()
    db = db.resolve()
    personal_db = (Path.cwd() / "data" / "workspace.db").resolve()
    if db == personal_db or db.name.lower() == "workspace.db":
        raise ValueError("Refusing to modify a personal workspace.db")
    if db.exists():
        raise FileExistsError(f"Choose a new filename. Already exists: {db}")
    start = now.date() + timedelta(days=1) if now.hour >= 20 else now.date()
    sunday = start + timedelta(days=6 - start.weekday())
    days = [start + timedelta(days=i) for i in range((sunday - start).days + 1)]
    if len(days) < 4:
        raise ValueError("This example is built for a Wednesday-evening or earlier demo week.")
    db.parent.mkdir(parents=True, exist_ok=True)
    with db.open("xb"):
        pass
    try:
        # Four days of realistic available study time; more freedom than the
        # original demo, but never more than the user-set maximum per day.
        for day, cap in zip(days[:4], (300, 300, 270, 240)):
            save_day_preferences(db, day, cap, 8 * 60, 22 * 60)
        events = (
            (0, "Statistics lecture", 570, 660, "Lecture"),
            (0, "Group project meeting", 780, 840, "Appointment"),
            (0, "Gym", 1020, 1080, "Exercise"),
            (0, "Dinner with flatmates", 1170, 1260, "Social"),
            (1, "Programming lab", 600, 720, "Lecture"),
            (1, "Lunch with Mia", 750, 810, "Social"),
            (1, "Office hours", 900, 960, "Appointment"),
            (1, "Coffee with a friend", 1050, 1110, "Social"),
            (2, "Morning run", 540, 600, "Exercise"),
            (2, "Saturday brunch", 720, 810, "Social"),
            (2, "Groceries", 960, 1020, "Personal"),
            (2, "Movie night", 1170, 1290, "Social"),
            (3, "Sunday walk", 540, 600, "Exercise"),
            (3, "Laundry", 690, 750, "Personal"),
            (3, "Family call", 1020, 1080, "Personal"),
            (3, "Dinner plans", 1170, 1260, "Social"),
        )
        for offset, label, start_min, end_min, kind in events:
            add_fixed_event(db, label, days[offset], start_min, end_min, kind)

        tasks = []

        def add(name, category, due, priority, minutes, *, needed=True, timed=True):
            day = days[due] if due is not None else None
            ident = create_quick_task(
                db, TaskDraft(name, category, day, priority, minutes), schedule=timed
            )
            if day is not None:
                set_required(db, ident, needed)
            tasks.append(ident)
            return ident

        outline = add("SWE: report outline", "Software Engineering", 0, 3, 60)
        report = add("SWE: proofread and submit", "Software Engineering", 1, 3, 90)
        stats = add("Statistics: problem set", "Statistics", 1, 3, 120)
        add("ML: practice questions", "Machine Learning", 2, 2, 120)
        slides = add("SWE: presentation slides", "Software Engineering", 3, 2, 90)
        add("Algorithms: revision", "Algorithms", 3, 2, 90)
        set_task_dependencies(db, report, [outline])
        # Slides depend on the outline, not the unchecked report checklist;
        # both required deadlines remain plannable in this synthetic scenario.
        set_task_dependencies(db, slides, [outline])
        add_step(db, report, "Proofread figures and tables", "checklist")
        add_step(db, report, "Read the final version aloud", "checklist")
        add_step(db, slides, "Prepare algorithm comparison", "checklist")
        add_step(db, slides, "Rehearse the demo", "checklist")

        optional = add("Economics: optional reading", "Economics", 3, 1, 90, needed=False)
        add("ML: additional exercises", "Machine Learning", 3, 1, 120, needed=False)
        add("Algorithms: extra practice", "Algorithms", 3, 1, 75, needed=False)
        add("Send a course email", "Personal", 0, 1, 15, timed=False)
        add("Tidy notes", "Personal", None, 1, 25, timed=False)
        edit_quick_task(
            db,
            optional,
            TaskDraft("Economics: optional reading", "Economics", days[3], 1, 90),
            45,
        )  # Actual progress: 50% completed, not just scheduled.

        # Two already-approved sessions make the Before/After view and Undo
        # meaningful even before the user generates their next plan.
        steps = linked_step_ids(db)
        snap = load_snapshot(db)
        initial = (
            Slot(steps[outline], days[0], 840, 900),
            Slot(steps[stats], days[1], 810, 870),
        )
        proposal = proposal_from_slots(snap, now, initial)
        accept_revision(db, proposal, now)
    except Exception:
        db.unlink(missing_ok=True)
        raise
    print(f"DEMO_DB={db}")
    print(
        f"Created {len(events)} calendar events, {len(tasks)} tasks, and two accepted study blocks."
    )
    print("A task has recorded 50% progress for testing green progress indicators.")
    print("This is a new demo database. Your personal data was not opened.")
    return db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    create_demo(args.output)


if __name__ == "__main__":
    main()
