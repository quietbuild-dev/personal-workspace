"""Explicit, reversible cleanup of outdated *planned* study blocks.

Completing a task may leave previously accepted study rows behind.  Those rows
must not enter a revision for active work; nor may a preview silently delete them.
The user can review and remove them with a guarded, undoable transaction.
"""

import json
from contextlib import closing
from datetime import datetime
from pathlib import Path

from workspace.advanced_planner import PlannerSnapshot, SavedSession, week_bounds
from workspace.advanced_repository import (
    StaleProposalError,
    _connect,
    _fetch_snapshot,
    initialize_advanced,
)


def outdated_planned_sessions(snapshot: PlannerSnapshot, now: datetime) -> tuple[SavedSession, ...]:
    """Find only this week's planned rows whose study step is no longer active."""
    monday, sunday = week_bounds(now.date())
    active = {
        step.id
        for step in snapshot.steps
        if step.kind == "timed" and not step.parent_completed and step.remaining_minutes > 0
    }
    return tuple(
        session
        for session in snapshot.sessions
        if session.status == "planned"
        and monday <= session.day <= sunday
        and session.step_id not in active
    )


def _undo_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS last_stale_booking_cleanup ("
        "singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
        "expected_fingerprint TEXT NOT NULL, previous_sessions TEXT NOT NULL)"
    )


def remove_outdated_bookings(
    db_path: Path,
    now: datetime,
    expected_fingerprint: str,
    session_ids: tuple[int, ...],
) -> int:
    """Delete only reviewed inactive planned rows; preserve their exact data for Undo."""
    if not session_ids or len(set(session_ids)) != len(session_ids):
        raise ValueError("Select outdated study blocks to remove.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            snapshot = _fetch_snapshot(conn)
            if snapshot.fingerprint != expected_fingerprint:
                raise StaleProposalError("Calendar changed. Review outdated bookings again.")
            stale = outdated_planned_sessions(snapshot, now)
            stale_ids = {session.id for session in stale}
            if set(session_ids) != stale_ids:
                raise ValueError("Review the latest outdated study blocks before removing them.")
            rows = conn.execute(
                "SELECT id,step_id,day,start_minute,end_minute,status,actual_minutes "
                "FROM scheduled_sessions WHERE id IN ("
                + ",".join("?" for _ in session_ids)
                + ") ORDER BY id",
                session_ids,
            ).fetchall()
            if len(rows) != len(session_ids) or any(row["status"] != "planned" for row in rows):
                raise StaleProposalError("One of these bookings has changed. Review again.")
            conn.executemany(
                "DELETE FROM scheduled_sessions WHERE id=? AND status='planned'",
                [(session_id,) for session_id in session_ids],
            )
            _undo_table(conn)
            fingerprint = _fetch_snapshot(conn).fingerprint
            conn.execute(
                "INSERT INTO last_stale_booking_cleanup"
                "(singleton,expected_fingerprint,previous_sessions) VALUES (1,?,?) "
                "ON CONFLICT(singleton) DO UPDATE SET "
                "expected_fingerprint=excluded.expected_fingerprint,"
                "previous_sessions=excluded.previous_sessions",
                (fingerprint, json.dumps([dict(row) for row in rows])),
            )
            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise


def outdated_undo_available(db_path: Path) -> bool:
    """Only advertise Undo when no other saved planner data changed afterward."""
    with closing(_connect(db_path)) as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='last_stale_booking_cleanup'"
        ).fetchone():
            return False
        row = conn.execute(
            "SELECT expected_fingerprint FROM last_stale_booking_cleanup WHERE singleton=1"
        ).fetchone()
        return bool(row and row[0] == _fetch_snapshot(conn).fingerprint)


def undo_outdated_cleanup(db_path: Path) -> int:
    """Restore precisely the removed rows when the calendar is still unchanged."""
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='last_stale_booking_cleanup'"
            ).fetchone():
                raise ValueError("There is no outdated-booking cleanup to undo.")
            row = conn.execute(
                "SELECT expected_fingerprint,previous_sessions "
                "FROM last_stale_booking_cleanup WHERE singleton=1"
            ).fetchone()
            if row is None:
                raise ValueError("There is no outdated-booking cleanup to undo.")
            if _fetch_snapshot(conn).fingerprint != row["expected_fingerprint"]:
                raise StaleProposalError("Calendar changed since cleanup. Undo is no longer safe.")
            records = json.loads(row["previous_sessions"])
            conn.executemany(
                "INSERT INTO scheduled_sessions "
                "(id,step_id,day,start_minute,end_minute,status,actual_minutes) "
                "VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        item["id"],
                        item["step_id"],
                        item["day"],
                        item["start_minute"],
                        item["end_minute"],
                        item["status"],
                        item["actual_minutes"],
                    )
                    for item in records
                ],
            )
            conn.execute("DELETE FROM last_stale_booking_cleanup WHERE singleton=1")
            conn.commit()
            return len(records)
        except Exception:
            conn.rollback()
            raise
