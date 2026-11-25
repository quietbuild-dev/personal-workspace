"""Create a separate, illustrative calendar database for Make Room for Life."""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import Slot, week_bounds
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
)
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.repository import DEFAULT_DB_PATH, create_task, initialize_database


def create_demo(path: Path, now: datetime | None = None) -> None:
    if now is None:
        now = datetime.now()
    path = path.expanduser().resolve()
    if path == Path(DEFAULT_DB_PATH).resolve():
        raise ValueError("The demo must not overwrite your personal database.")
    if path.exists():
        raise ValueError(
            "Choose a new database filename. An existing file will not be overwritten."
        )
    monday, _ = week_bounds(now.date())
    friday = monday + timedelta(days=4)
    if friday < now.date() or (friday == now.date() and now.hour >= 17):
        raise ValueError("Friday evening has passed this week. Choose a new demo next week.")
    thursday = monday + timedelta(days=3)
    if thursday <= now.date():
        thursday = now.date()
        if now.hour >= 15:
            raise ValueError("Not enough time remains before Friday for this demo scenario.")
    path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(path)
    initialize_advanced(path)
    task = create_task(path, TaskDraft("SWE project report", "University", friday, 3, 120))
    study_id = add_step(path, task.id, "Proofread and submit", "timed", 120)
    add_window(path, thursday, 14 * 60, 17 * 60)
    add_window(path, friday, 14 * 60, 22 * 60)
    add_fixed_event(path, "Statistics lecture", thursday, 9 * 60, 10 * 60, "Lecture")
    add_fixed_event(path, "Lunch with friends", friday, 12 * 60, 13 * 60, "Social")
    snapshot = load_snapshot(path)
    proposal = proposal_from_slots(snapshot, now, (Slot(study_id, friday, 17 * 60, 19 * 60),))
    accept_revision(path, proposal, now)
    print(f"DEMO_DB={path}")
    print("Friday 17:00-19:00 has study work; Thursday has space for rescheduling.")
    print("The personal database was not opened or modified.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    create_demo(args.output)


if __name__ == "__main__":
    main()
