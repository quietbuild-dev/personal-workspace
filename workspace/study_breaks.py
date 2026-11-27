"""Preference for empty study gaps; never count breaks as study minutes."""

import sqlite3
from contextlib import closing
from pathlib import Path

BREAK_OPTIONS = (0, 5, 10, 15)


def _open(db_path: Path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_break_minutes(db_path: Path) -> int:
    from workspace.advanced_repository import initialize_advanced
    initialize_advanced(db_path)
    with closing(_open(db_path)) as conn:
        row = conn.execute(
            "SELECT minutes FROM study_break_preferences WHERE singleton=1"
        ).fetchone()
        return int(row[0]) if row else 5


def set_break_minutes(db_path: Path, minutes: int) -> None:
    if type(minutes) is not int or minutes not in BREAK_OPTIONS:
        raise ValueError("Choose 0, 5, 10, or 15 minutes between study sessions.")
    from workspace.advanced_repository import initialize_advanced
    initialize_advanced(db_path)
    with closing(_open(db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO study_break_preferences(singleton,minutes) VALUES(1,?) "
            "ON CONFLICT(singleton) DO UPDATE SET minutes=excluded.minutes",
            (minutes,),
        )


def prefer_study_gaps(snapshot, proposal, now, gap_minutes: int):
    """Improve proposed gaps without sacrificing feasibility, existing work or deadlines.

    This intentionally does not force gaps when a deadline or a commitment
    leaves no room. A break is empty calendar time, not a scheduled event.
    """
    if gap_minutes not in BREAK_OPTIONS or not gap_minutes:
        return proposal
    from workspace.advanced_planner import Slot, validate_revision
    from workspace.optimizer import proposal_from_slots

    saved = {
        Slot(s.step_id, s.day, s.start, s.end)
        for s in snapshot.sessions if s.status == "planned"
    }
    chosen = sorted(proposal.slots, key=lambda s: (s.day, s.start, s.end))
    for index in range(1, len(chosen)):
        previous, current = chosen[index - 1], chosen[index]
        if previous.day != current.day or current.start >= previous.end + gap_minutes:
            continue
        if current in saved:
            continue  # No silent change to accepted sessions.
        begin = previous.end + gap_minutes
        candidate = Slot(current.step_id, current.day, begin, begin + current.minutes)
        if candidate == current:
            continue
        trial = [*chosen]
        trial[index] = candidate
        revised = proposal_from_slots(snapshot, now, tuple(trial))
        try:
            validate_revision(snapshot, revised, now)
        except ValueError:
            continue
        chosen = sorted(trial, key=lambda s: (s.day, s.start, s.end))
    final = proposal_from_slots(snapshot, now, tuple(chosen))
    validate_revision(snapshot, final, now)
    return final
