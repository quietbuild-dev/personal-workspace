"""Protect a personal time window and preview deadline-safe study replanning.

No writes occur during a preview. Approval commits the event and revised study
sessions together in one SQLite transaction, including an undo record.
"""

import json
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from workspace.advanced_planner import (
    FixedEvent,
    PlannerSnapshot,
    RevisionProposal,
    Slot,
    accepted_conflicts,
    validate_revision,
    week_bounds,
)
from workspace.advanced_repository import (
    StaleProposalError,
    _connect,
    _fetch_snapshot,
    initialize_advanced,
    undo_last_plan,
)
from workspace.deadline_guarantees import check_required_coverage
from workspace.optimizer import optimize
from workspace.study_dna import StudyDNA

PROTECTED_TITLE = "Personal time (protected)"


@dataclass(frozen=True)
class LifePreview:
    fingerprint: str
    day: date
    start: int
    end: int
    revision: RevisionProposal
    before: tuple[Slot, ...]
    required_ids: frozenset[int]
    feasible: bool
    explanation: str
    solver_message: str

    @property
    def changed(self) -> int:
        return len(set(self.before) ^ set(self.revision.slots))


def _validate_window(snapshot: PlannerSnapshot, day: date, start: int, end: int, now: datetime):
    if not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError("Use a local calendar time.")
    _, sunday = week_bounds(now.date())
    if type(day) is not date or not now.date() <= day <= sunday:
        raise ValueError("Choose a future date in the current planning week.")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= 1440:
        raise ValueError("Choose a valid start and finish time.")
    if end - start < 30:
        raise ValueError("Protect at least 30 minutes.")
    if day == now.date() and start <= now.hour * 60 + now.minute:
        raise ValueError("The protected time must start in the future.")
    for event in snapshot.events:
        if event.day == day and event.start < end and start < event.end:
            raise ValueError(
                f"'{event.title}' is a fixed commitment during this time. "
                "Edit or move that event first; this tool only moves study sessions."
            )
    for session in snapshot.sessions:
        if (
            session.status == "done"
            and session.day == day
            and session.start < end
            and start < session.end
        ):
            raise ValueError("Completed study time already occupies part of this period.")


def _virtual_snapshot(snapshot: PlannerSnapshot, day: date, start: int, end: int):
    return replace(
        snapshot,
        events=snapshot.events
        + (FixedEvent(-1, PROTECTED_TITLE, day, start, end, "Personal"),),
    )


def _previous_slots(snapshot: PlannerSnapshot, now: datetime):
    _, sunday = week_bounds(now.date())
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    return tuple(
        Slot(item.step_id, item.day, item.start, item.end)
        for item in snapshot.sessions
        if item.status == "planned"
        and now.date() <= item.day <= sunday
        and (item.day != now.date() or item.start >= cutoff)
    )


def _required_preservation(snapshot, before, proposal, must_ids, now):
    required = check_required_coverage(snapshot, proposal, now, must_ids)
    if not required.complete:
        return (
            False,
            f"{required.outstanding_minutes // 60}h "
            f"{required.outstanding_minutes % 60}m of required deadline work would be unscheduled. "
            "Try a shorter protected period or add study availability.",
        )
    steps = {step.id: step for step in snapshot.steps}
    old = {}
    new = {}
    for slot in before:
        old[slot.step_id] = old.get(slot.step_id, 0) + slot.minutes
    for slot in proposal.slots:
        new[slot.step_id] = new.get(slot.step_id, 0) + slot.minutes
    for step_id, count in old.items():
        step = steps.get(step_id)
        if (
            step is not None
            and step.deadline is not None
            and step.deadline <= proposal.sunday
            and new.get(step_id, 0) < count
        ):
            return (
                False,
                f"Moving study time would reduce coverage for '{step.task_title}'. "
                "Try a different time window.",
            )
    return True, "Required deadlines and previously booked deadline work are preserved."


def preview_time_protection(
    snapshot: PlannerSnapshot,
    now: datetime,
    day: date,
    start: int,
    end: int,
    *,
    dna: StudyDNA | None = None,
    required_ids: frozenset[int] = frozenset(),
) -> LifePreview:
    """Build a read-only proposal. Never label a shortfall as feasible."""
    if not isinstance(required_ids, frozenset):
        raise ValueError("Required task IDs must be a frozen set.")
    _validate_window(snapshot, day, start, end, now)
    virtual = _virtual_snapshot(snapshot, day, start, end)
    result = optimize(
        virtual,
        now,
        goal="routine",
        dna=dna,
        require_task_ids=required_ids,
        time_limit=3.0,
    )
    validate_revision(virtual, result.revision, now)
    before = _previous_slots(snapshot, now)
    feasible, explanation = _required_preservation(
        snapshot, before, result.revision, required_ids, now
    )
    return LifePreview(
        snapshot.fingerprint,
        day,
        start,
        end,
        result.revision,
        before,
        required_ids,
        feasible,
        explanation,
        result.message,
    )


def _life_marker(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS last_life_plan_undo ("
        "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
        "expected_fingerprint TEXT NOT NULL, "
        "event_id INTEGER NOT NULL)"
    )


def accept_time_protection(db_path: Path, preview: LifePreview, now: datetime) -> int:
    """Atomically save a protected event, study plan, and compatible Undo record."""
    if not isinstance(preview, LifePreview) or not preview.feasible:
        raise ValueError("Only a feasible, reviewed personal-time plan can be saved.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            _life_marker(conn)
            latest = _fetch_snapshot(conn)
            if latest.fingerprint != preview.fingerprint:
                raise StaleProposalError("Your calendar changed. Preview personal time again.")
            _validate_window(latest, preview.day, preview.start, preview.end, now)
            if preview.revision.fingerprint != latest.fingerprint:
                raise StaleProposalError("Your preview is no longer current.")
            virtual = _virtual_snapshot(latest, preview.day, preview.start, preview.end)
            validate_revision(virtual, preview.revision, now)
            still_feasible, explanation = _required_preservation(
                latest,
                _previous_slots(latest, now),
                preview.revision,
                preview.required_ids,
                now,
            )
            if not still_feasible:
                raise ValueError(explanation)
            proposal = preview.revision
            previous = {
                (session.step_id, session.day, session.start, session.end): session.id
                for session in latest.sessions
                if session.status == "planned"
                and proposal.monday <= session.day <= proposal.sunday
            }
            desired = {(slot.step_id, slot.day, slot.start, slot.end) for slot in proposal.slots}
            before_rows = conn.execute(
                "SELECT id,step_id,day,start_minute,end_minute,status,actual_minutes "
                "FROM scheduled_sessions WHERE status='planned' AND day BETWEEN ? AND ? "
                "ORDER BY id",
                (proposal.monday.isoformat(), proposal.sunday.isoformat()),
            ).fetchall()
            event_id = conn.execute(
                "INSERT INTO fixed_events(title,day,start_minute,end_minute) "
                "VALUES (?,?,?,?)",
                (PROTECTED_TITLE, preview.day.isoformat(), preview.start, preview.end),
            ).lastrowid
            conn.execute(
                "INSERT INTO fixed_event_kinds(event_id,kind) VALUES (?,?)",
                (event_id, "Personal"),
            )
            conn.executemany(
                "DELETE FROM scheduled_sessions WHERE id=?",
                [(item_id,) for key, item_id in previous.items() if key not in desired],
            )
            conn.executemany(
                "INSERT INTO scheduled_sessions(step_id,day,start_minute,end_minute) "
                "VALUES (?,?,?,?)",
                [
                    (step_id, day.isoformat(), start, finish)
                    for step_id, day, start, finish in sorted(desired - previous.keys())
                ],
            )
            saved_snapshot = _fetch_snapshot(conn)
            if accepted_conflicts(saved_snapshot, now):
                raise ValueError("The protected schedule conflicts with existing obligations.")
            after_fingerprint = saved_snapshot.fingerprint
            conn.execute(
                "INSERT INTO last_plan_undo "
                "(singleton,expected_fingerprint,monday,sunday,previous_sessions) "
                "VALUES (1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET "
                "expected_fingerprint=excluded.expected_fingerprint, "
                "monday=excluded.monday,sunday=excluded.sunday, "
                "previous_sessions=excluded.previous_sessions",
                (
                    after_fingerprint,
                    proposal.monday.isoformat(),
                    proposal.sunday.isoformat(),
                    json.dumps([dict(row) for row in before_rows]),
                ),
            )
            conn.execute(
                "INSERT INTO last_life_plan_undo(singleton,expected_fingerprint,event_id) "
                "VALUES (1,?,?) ON CONFLICT(singleton) DO UPDATE SET "
                "expected_fingerprint=excluded.expected_fingerprint,"
                "event_id=excluded.event_id",
                (after_fingerprint, event_id),
            )
            conn.commit()
            return event_id
        except Exception:
            conn.rollback()
            raise


def undo_last_plan_with_protection(db_path: Path, now: datetime | None = None) -> int:
    """Undo a protected window and associated study revision together when relevant."""
    if now is None:
        now = datetime.now()
    initialize_advanced(db_path)
    fallback = False
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            marker_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='last_life_plan_undo'"
            ).fetchone()
            if not marker_exists:
                fallback = True
            else:
                marker = conn.execute(
                    "SELECT expected_fingerprint,event_id FROM last_life_plan_undo "
                    "WHERE singleton=1"
                ).fetchone()
                row = conn.execute(
                    "SELECT * FROM last_plan_undo WHERE singleton=1"
                ).fetchone()
                if row is None or marker is None or marker[0] != row["expected_fingerprint"]:
                    fallback = True
                else:
                    current = _fetch_snapshot(conn)
                    if current.fingerprint != row["expected_fingerprint"]:
                        raise StaleProposalError(
                            "The calendar changed since this plan was saved. "
                            "Review a new plan instead of overwriting later edits."
                        )
                    conn.execute("DELETE FROM fixed_events WHERE id=?", (marker[1],))
                    saved = json.loads(row["previous_sessions"])
                    conn.execute(
                        "DELETE FROM scheduled_sessions "
                        "WHERE status='planned' AND day BETWEEN ? AND ?",
                        (row["monday"], row["sunday"]),
                    )
                    conn.executemany(
                        "INSERT INTO scheduled_sessions "
                        "(id,step_id,day,start_minute,end_minute,status,actual_minutes) "
                        "VALUES (?,?,?,?,?,?,?)",
                        [
                            (
                                item["id"], item["step_id"], item["day"],
                                item["start_minute"], item["end_minute"],
                                item["status"], item["actual_minutes"],
                            )
                            for item in saved
                        ],
                    )
                    restored = _fetch_snapshot(conn)
                    if accepted_conflicts(restored, now):
                        raise ValueError(
                            "The previous schedule is no longer safe to restore."
                        )
                    conn.execute("DELETE FROM last_plan_undo WHERE singleton=1")
                    conn.execute("DELETE FROM last_life_plan_undo WHERE singleton=1")
                    conn.commit()
                    return len(saved)
            conn.rollback()
        except Exception:
            conn.rollback()
            raise
    if fallback:
        return undo_last_plan(db_path, now)
    raise ValueError("Unable to find a reversible plan.")
