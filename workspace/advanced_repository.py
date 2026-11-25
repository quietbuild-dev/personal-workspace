"""Additive SQLite tables and atomic accepted-schedule operations.

Legacy tasks remain in the original tasks table. Timed step work is stored
independently; a booked session never reduces remaining work until marked done.
"""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from workspace.advanced_planner import (
    DayBudget,
    DayPreference,
    FixedEvent,
    PlannerSnapshot,
    RevisionProposal,
    SavedSession,
    StudyStep,
    TaskDependency,
    TaskState,
    TimeWindow,
    accepted_conflicts,
    validate_revision,
)
from workspace.repository import initialize_database


class StaleProposalError(ValueError):
    """The saved planning inputs changed since a revision was generated."""


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_advanced(db_path: Path) -> None:
    """Idempotent non-destructive schema extension; existing tasks are untouched."""
    initialize_database(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS study_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                kind TEXT NOT NULL CHECK(kind IN ('timed', 'checklist')),
                estimate_minutes INTEGER NOT NULL CHECK(estimate_minutes >= 0),
                remaining_minutes INTEGER NOT NULL
                    CHECK(remaining_minutes BETWEEN 0 AND estimate_minutes),
                checked INTEGER NOT NULL DEFAULT 0 CHECK(checked IN (0,1)),
                CHECK((kind = 'checklist' AND estimate_minutes = 0 AND remaining_minutes = 0)
                      OR (kind = 'timed' AND estimate_minutes > 0 AND checked = 0))
            );
            CREATE TABLE IF NOT EXISTS task_dependencies (
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                prerequisite_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                PRIMARY KEY(task_id, prerequisite_id),
                CHECK(task_id != prerequisite_id)
            );
            CREATE TABLE IF NOT EXISTS time_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                start_minute INTEGER NOT NULL,
                end_minute INTEGER NOT NULL,
                CHECK(start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute),
                UNIQUE(day, start_minute, end_minute)
            );
            CREATE TABLE IF NOT EXISTS fixed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                day TEXT NOT NULL,
                start_minute INTEGER NOT NULL,
                end_minute INTEGER NOT NULL,
                CHECK(start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute)
            );
            CREATE TABLE IF NOT EXISTS scheduled_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step_id INTEGER NOT NULL REFERENCES study_steps(id) ON DELETE CASCADE,
                day TEXT NOT NULL,
                start_minute INTEGER NOT NULL,
                end_minute INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'planned'
                    CHECK(status IN ('planned', 'missed', 'done')),
                actual_minutes INTEGER NOT NULL DEFAULT 0 CHECK(actual_minutes >= 0),
                CHECK(start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute)
            );
            CREATE TABLE IF NOT EXISTS day_study_budgets (
                day TEXT PRIMARY KEY,
                minutes INTEGER NOT NULL CHECK(minutes BETWEEN 0 AND 840)
            );
            CREATE TABLE IF NOT EXISTS task_deadline_times (
                task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                minute INTEGER NOT NULL CHECK(minute BETWEEN 0 AND 1439)
            );
            CREATE TABLE IF NOT EXISTS task_categories (
                name TEXT PRIMARY KEY CHECK(length(trim(name)) BETWEEN 1 AND 40)
            );
            CREATE TABLE IF NOT EXISTS fixed_event_kinds (
                event_id INTEGER PRIMARY KEY REFERENCES fixed_events(id) ON DELETE CASCADE,
                kind TEXT NOT NULL CHECK(kind IN
                    ('Lecture', 'Appointment', 'Personal', 'Social', 'Exercise', 'Other'))
            );
            CREATE TABLE IF NOT EXISTS day_focus_preferences (
                day TEXT PRIMARY KEY,
                start_minute INTEGER NOT NULL,
                end_minute INTEGER NOT NULL,
                CHECK(start_minute >= 0 AND end_minute <= 1440
                      AND start_minute < end_minute)
            );
            CREATE TABLE IF NOT EXISTS last_plan_undo (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                expected_fingerprint TEXT NOT NULL,
                monday TEXT NOT NULL,
                sunday TEXT NOT NULL,
                previous_sessions TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_study_steps_task ON study_steps(task_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_week ON scheduled_sessions(day, status);
        """)
        conn.execute(
            "INSERT OR IGNORE INTO task_categories(name) "
            "SELECT DISTINCT category FROM tasks WHERE length(trim(category)) BETWEEN 1 AND 40"
        )
        conn.executemany(
            "INSERT OR IGNORE INTO task_categories(name) VALUES (?)",
            [(name,) for name in ("University", "Personal", "Home", "Work", "Social", "Exercise")],
        )


def _valid_title(title: str) -> str:
    if type(title) is not str or not 1 <= len(title.strip()) <= 120:
        raise ValueError("Provide a title between 1 and 120 characters.")
    return title.strip()


def _valid_interval(day: date, start: int, end: int) -> None:
    if type(day) is not date:
        raise ValueError("A real calendar date is required.")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= 1440:
        raise ValueError("Enter a valid time interval within one day.")


def add_step(db_path: Path, task_id: int, title: str, kind: str, minutes: int = 0) -> int:
    _valid_title(title)
    if type(task_id) is not int or task_id <= 0:
        raise ValueError("Choose a valid parent task.")
    if kind not in ("timed", "checklist"):
        raise ValueError("Step type must be timed or checklist.")
    if (
        type(minutes) is not int
        or (kind == "timed" and not 1 <= minutes <= 100000)
        or (kind == "checklist" and minutes != 0)
    ):
        raise ValueError("Timed steps require positive minutes; checklists require zero.")
    with closing(_connect(db_path)) as conn, conn:
        row = conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None or row["status"] != "pending":
            raise ValueError("Create steps under an open task. Reopen completed tasks first.")
        cursor = conn.execute(
            "INSERT INTO study_steps(task_id,title,kind,estimate_minutes,remaining_minutes) "
            "VALUES (?,?,?,?,?)",
            (task_id, title.strip(), kind, minutes, minutes),
        )
        return cursor.lastrowid


def set_checklist_done(db_path: Path, step_id: int, done: bool) -> None:
    if type(done) is not bool or type(step_id) is not int or step_id <= 0:
        raise ValueError("Invalid checklist operation.")
    with closing(_connect(db_path)) as conn, conn:
        result = conn.execute(
            "UPDATE study_steps SET checked=? WHERE id=? AND kind='checklist'",
            (int(done), step_id),
        )
        if result.rowcount != 1:
            raise ValueError("This checklist step no longer exists.")


def set_timed_remaining(db_path: Path, step_id: int, remaining: int) -> None:
    if type(step_id) is not int or step_id <= 0 or type(remaining) is not int or remaining < 0:
        raise ValueError("Remaining work must be a nonnegative whole number.")
    with closing(_connect(db_path)) as conn, conn:
        result = conn.execute(
            "UPDATE study_steps SET remaining_minutes=? WHERE id=? AND kind='timed' "
            "AND estimate_minutes >= ?",
            (remaining, step_id, remaining),
        )
        if result.rowcount != 1:
            raise ValueError("Step not found, or remaining time exceeds its estimate.")


def save_day_budgets(db_path: Path, budgets: dict[date, int]) -> None:
    """Atomically save opt-in daily study budgets without modifying legacy windows."""
    if not isinstance(budgets, dict) or not budgets:
        raise ValueError("Choose at least one calendar day to update.")
    for day, minutes in budgets.items():
        if type(day) is not date or type(minutes) is not int or not 0 <= minutes <= 840:
            raise ValueError("Study time must be whole minutes between 0 and 14 hours.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.executemany(
            "INSERT INTO day_study_budgets(day,minutes) VALUES (?,?) "
            "ON CONFLICT(day) DO UPDATE SET minutes=excluded.minutes",
            [(day.isoformat(), amount) for day, amount in budgets.items()],
        )


def clear_day_budget(db_path: Path, day: date) -> None:
    """Restore legacy explicit windows for a date without deleting them."""
    if type(day) is not date:
        raise ValueError("A real calendar day is required.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("DELETE FROM day_study_budgets WHERE day=?", (day.isoformat(),))


def add_window(db_path: Path, day: date, start: int, end: int) -> int:
    _valid_interval(day, start, end)
    with closing(_connect(db_path)) as conn, conn:
        try:
            cursor = conn.execute(
                "INSERT INTO time_windows(day,start_minute,end_minute) VALUES(?,?,?)",
                (day.isoformat(), start, end),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("That availability window already exists.") from exc
        return cursor.lastrowid


EVENT_KINDS = ("Lecture", "Appointment", "Personal", "Social", "Exercise", "Other")


def add_fixed_event(
    db_path: Path,
    title: str,
    day: date,
    start: int,
    end: int,
    kind: str = "Appointment",
) -> int:
    title = _valid_title(title)
    _valid_interval(day, start, end)
    if kind not in EVENT_KINDS:
        raise ValueError("Choose a supported event category.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO fixed_events(title,day,start_minute,end_minute) VALUES(?,?,?,?)",
            (title, day.isoformat(), start, end),
        )
        event_id = cursor.lastrowid
        conn.execute("INSERT INTO fixed_event_kinds(event_id,kind) VALUES(?,?)", (event_id, kind))
        return event_id


def update_fixed_event(
    db_path: Path,
    event_id: int,
    title: str,
    day: date,
    start: int,
    end: int,
    kind: str = "Appointment",
) -> None:
    title = _valid_title(title)
    _valid_interval(day, start, end)
    if type(event_id) is not int or event_id <= 0 or kind not in EVENT_KINDS:
        raise ValueError("Choose a valid event and category.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        result = conn.execute(
            "UPDATE fixed_events SET title=?,day=?,start_minute=?,end_minute=? WHERE id=?",
            (title, day.isoformat(), start, end, event_id),
        )
        if result.rowcount != 1:
            raise ValueError("This event no longer exists.")
        conn.execute(
            "INSERT INTO fixed_event_kinds(event_id,kind) VALUES(?,?) "
            "ON CONFLICT(event_id) DO UPDATE SET kind=excluded.kind",
            (event_id, kind),
        )


def list_task_categories(db_path: Path) -> tuple[str, ...]:
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        return tuple(
            row[0]
            for row in conn.execute("SELECT name FROM task_categories ORDER BY name COLLATE NOCASE")
        )


def list_task_due_times(db_path: Path) -> dict[int, int]:
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        return {
            row["task_id"]: row["minute"]
            for row in conn.execute("SELECT task_id,minute FROM task_deadline_times")
        }


def save_day_preferences(
    db_path: Path,
    day: date,
    minutes: int,
    start: int,
    end: int,
) -> None:
    """One atomic date-specific study preference and cap; 0 means time off."""
    _valid_interval(day, start, end)
    if type(minutes) is not int or not 0 <= minutes <= 840:
        raise ValueError("Choose a study-time budget between 0 and 14 hours.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO day_study_budgets(day,minutes) VALUES (?,?) "
            "ON CONFLICT(day) DO UPDATE SET minutes=excluded.minutes",
            (day.isoformat(), minutes),
        )
        conn.execute(
            "INSERT INTO day_focus_preferences(day,start_minute,end_minute) VALUES (?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET "
            "start_minute=excluded.start_minute,end_minute=excluded.end_minute",
            (day.isoformat(), start, end),
        )


def save_week_preferences(
    db_path: Path,
    days: tuple[date, ...],
    minutes: int,
    start: int,
    end: int,
) -> None:
    """Set several dates in one transaction; never modify accepted sessions."""
    if not days or len(set(days)) != len(days):
        raise ValueError("Choose at least one distinct calendar date.")
    for day in days:
        _valid_interval(day, start, end)
    if type(minutes) is not int or not 0 <= minutes <= 840:
        raise ValueError("Choose a daily study budget between 0 and 14 hours.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.executemany(
            "INSERT INTO day_study_budgets(day,minutes) VALUES (?,?) "
            "ON CONFLICT(day) DO UPDATE SET minutes=excluded.minutes",
            [(day.isoformat(), minutes) for day in days],
        )
        conn.executemany(
            "INSERT INTO day_focus_preferences(day,start_minute,end_minute) VALUES (?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET "
            "start_minute=excluded.start_minute,end_minute=excluded.end_minute",
            [(day.isoformat(), start, end) for day in days],
        )


def clear_day_preferences(db_path: Path, day: date) -> None:
    if type(day) is not date:
        raise ValueError("Choose a valid date.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("DELETE FROM day_study_budgets WHERE day=?", (day.isoformat(),))
        conn.execute("DELETE FROM day_focus_preferences WHERE day=?", (day.isoformat(),))


def delete_window(db_path: Path, window_id: int) -> None:
    _delete_by_id(db_path, "time_windows", window_id)


def delete_fixed_event(db_path: Path, event_id: int) -> None:
    _delete_by_id(db_path, "fixed_events", event_id)


def _delete_by_id(db_path: Path, table: str, row_id: int) -> None:
    # Table name is internal and from a closed set, never passed from the UI.
    if table not in {"time_windows", "fixed_events"} or type(row_id) is not int or row_id <= 0:
        raise ValueError("Invalid row to remove.")
    with closing(_connect(db_path)) as conn, conn:
        if conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,)).rowcount != 1:
            raise ValueError("This item no longer exists.")


def _fetch_snapshot(conn: sqlite3.Connection) -> PlannerSnapshot:
    """Read all planning inputs consistently and calculate an optimistic-lock token."""
    parent_rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    step_rows = conn.execute("SELECT * FROM study_steps ORDER BY id").fetchall()
    window_rows = conn.execute("SELECT * FROM time_windows ORDER BY id").fetchall()
    event_rows = conn.execute("SELECT * FROM fixed_events ORDER BY id").fetchall()
    session_rows = conn.execute("SELECT * FROM scheduled_sessions ORDER BY id").fetchall()
    budget_rows = conn.execute("SELECT * FROM day_study_budgets ORDER BY day").fetchall()
    deadline_rows = conn.execute("SELECT * FROM task_deadline_times ORDER BY task_id").fetchall()
    kind_rows = conn.execute("SELECT * FROM fixed_event_kinds ORDER BY event_id").fetchall()
    preference_rows = conn.execute("SELECT * FROM day_focus_preferences ORDER BY day").fetchall()
    dependency_rows = conn.execute(
        "SELECT * FROM task_dependencies ORDER BY task_id, prerequisite_id"
    ).fetchall()
    # Include original task fields: editing a parent's deadline or priority invalidates proposals.
    payload = [
        [dict(row) for row in rows]
        for rows in (
            parent_rows,
            step_rows,
            window_rows,
            event_rows,
            session_rows,
            budget_rows,
            deadline_rows,
            kind_rows,
            preference_rows,
            dependency_rows,
        )
    ]
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    parents = {row["id"]: row for row in parent_rows}
    due_times = {row["task_id"]: row["minute"] for row in deadline_rows}
    kinds = {row["event_id"]: row["kind"] for row in kind_rows}
    steps = tuple(
        StudyStep(
            id=row["id"],
            task_id=row["task_id"],
            task_title=parents[row["task_id"]]["title"],
            title=row["title"],
            kind=row["kind"],
            estimate_minutes=row["estimate_minutes"],
            remaining_minutes=row["remaining_minutes"],
            checked=bool(row["checked"]),
            deadline=date.fromisoformat(parents[row["task_id"]]["deadline"])
            if parents[row["task_id"]]["deadline"]
            else None,
            priority=parents[row["task_id"]]["priority"],
            parent_completed=parents[row["task_id"]]["status"] == "completed",
            deadline_minute=due_times.get(row["task_id"]),
        )
        for row in step_rows
    )
    windows = tuple(
        TimeWindow(
            row["id"], date.fromisoformat(row["day"]), row["start_minute"], row["end_minute"]
        )
        for row in window_rows
    )
    events = tuple(
        FixedEvent(
            row["id"],
            row["title"],
            date.fromisoformat(row["day"]),
            row["start_minute"],
            row["end_minute"],
            kinds.get(row["id"], "Appointment"),
        )
        for row in event_rows
    )
    sessions = tuple(
        SavedSession(
            row["id"],
            row["step_id"],
            date.fromisoformat(row["day"]),
            row["start_minute"],
            row["end_minute"],
            row["status"],
            row["actual_minutes"],
        )
        for row in session_rows
    )
    budgets = tuple(
        DayBudget(date.fromisoformat(row["day"]), row["minutes"]) for row in budget_rows
    )
    preferences = tuple(
        DayPreference(date.fromisoformat(row["day"]), row["start_minute"], row["end_minute"])
        for row in preference_rows
    )
    dependencies = tuple(
        TaskDependency(r["task_id"], r["prerequisite_id"]) for r in dependency_rows
    )
    states = tuple(TaskState(r["id"], r["status"] == "completed") for r in parent_rows)
    return PlannerSnapshot(
        steps, windows, events, sessions, fingerprint, budgets, preferences, dependencies, states
    )


def set_task_dependencies(db_path: Path, task_id: int, prerequisite_ids) -> None:
    """Atomically replace one task's prerequisites after reference and cycle checks."""
    from workspace.dependencies import dependency_context

    ids = tuple(prerequisite_ids)
    if (
        type(task_id) is not int
        or task_id <= 0
        or any(type(i) is not int or i <= 0 for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Choose distinct valid prerequisite tasks.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = {r[0] for r in conn.execute("SELECT id FROM tasks")}
        if task_id not in existing or not set(ids) <= existing:
            raise ValueError("A dependency references a missing task.")
        if task_id in ids:
            raise ValueError("A task cannot depend on itself.")
        conn.execute("DELETE FROM task_dependencies WHERE task_id=?", (task_id,))
        conn.executemany(
            "INSERT INTO task_dependencies(task_id,prerequisite_id) VALUES (?,?)",
            [(task_id, parent) for parent in ids],
        )
        dependency_context(_fetch_snapshot(conn))  # Exceptions roll back the whole replacement.


def load_snapshot(db_path: Path) -> PlannerSnapshot:
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        conn.execute("BEGIN")
        snapshot = _fetch_snapshot(conn)
        conn.rollback()
        return snapshot


def accept_revision(db_path: Path, proposal: RevisionProposal, now: datetime) -> int:
    """Compare current state, revalidate, replace planned week in one SQLite transaction.

    Done and missed session history is retained. No writes happen on preview/reject.
    """
    if not isinstance(proposal, RevisionProposal):
        raise ValueError("An explicit revision proposal is required.")
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            latest = _fetch_snapshot(conn)
            if latest.fingerprint != proposal.fingerprint:
                raise StaleProposalError(
                    "Planning data changed since the preview. Regenerate before accepting."
                )
            validate_revision(latest, proposal, now)
            # Retain the actual database row IDs of unchanged sessions, not just
            # their visual positions. Delete and insert only the differences.
            previous = {
                (session.step_id, session.day, session.start, session.end): session.id
                for session in latest.sessions
                if session.status == "planned" and proposal.monday <= session.day <= proposal.sunday
            }
            desired = {(slot.step_id, slot.day, slot.start, slot.end) for slot in proposal.slots}
            before_rows = conn.execute(
                "SELECT id,step_id,day,start_minute,end_minute,status,actual_minutes "
                "FROM scheduled_sessions WHERE status='planned' AND day BETWEEN ? AND ? "
                "ORDER BY id",
                (proposal.monday.isoformat(), proposal.sunday.isoformat()),
            ).fetchall()
            conn.executemany(
                "DELETE FROM scheduled_sessions WHERE id=?",
                [(row_id,) for key, row_id in previous.items() if key not in desired],
            )
            conn.executemany(
                "INSERT INTO scheduled_sessions(step_id,day,start_minute,end_minute) "
                "VALUES (?,?,?,?)",
                [
                    (step_id, day.isoformat(), start, end)
                    for step_id, day, start, end in sorted(desired - previous.keys())
                ],
            )
            after_fingerprint = _fetch_snapshot(conn).fingerprint
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
            conn.commit()
            return len(proposal.slots)
        except Exception:
            conn.rollback()
            raise


def undo_last_plan(db_path: Path, now: datetime | None = None) -> int:
    """Atomically restore the previous accepted week only if still safe.

    Any change to tasks, events, preferences or sessions after acceptance
    invalidates undo. A restoration that would create conflicts is rejected.
    """
    if now is None:
        now = datetime.now()
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM last_plan_undo WHERE singleton=1").fetchone()
            if row is None:
                raise ValueError("There is no recent plan change to undo.")
            current = _fetch_snapshot(conn)
            if current.fingerprint != row["expected_fingerprint"]:
                raise StaleProposalError(
                    "Your calendar changed since this plan was accepted. "
                    "Review a fresh proposal instead of overwriting newer work."
                )
            saved = json.loads(row["previous_sessions"])
            conn.execute(
                "DELETE FROM scheduled_sessions WHERE status='planned' AND day BETWEEN ? AND ?",
                (row["monday"], row["sunday"]),
            )
            conn.executemany(
                "INSERT INTO scheduled_sessions "
                "(id,step_id,day,start_minute,end_minute,status,actual_minutes) "
                "VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        entry["id"],
                        entry["step_id"],
                        entry["day"],
                        entry["start_minute"],
                        entry["end_minute"],
                        entry["status"],
                        entry["actual_minutes"],
                    )
                    for entry in saved
                ],
            )
            restored = _fetch_snapshot(conn)
            if accepted_conflicts(restored, now):
                raise ValueError(
                    "The previous plan now conflicts with existing commitments "
                    "or preferences. Please review a new suggestion instead."
                )
            conn.execute("DELETE FROM last_plan_undo WHERE singleton=1")
            conn.commit()
            return len(saved)
        except Exception:
            conn.rollback()
            raise


def has_undo_plan(db_path: Path) -> bool:
    """Show Undo only while the immediately previous plan can be restored."""
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT expected_fingerprint FROM last_plan_undo WHERE singleton=1"
        ).fetchone()
        return bool(row and _fetch_snapshot(conn).fingerprint == row[0])


def record_session(
    db_path: Path,
    session_id: int,
    status: str,
    actual_minutes: int = 0,
    *,
    now: datetime | None = None,
) -> None:
    """Missed work remains outstanding; done work reduces only that timed step."""
    if type(session_id) is not int or session_id <= 0 or status not in ("done", "missed"):
        raise ValueError("Choose a planned session and a valid result.")
    if (
        type(actual_minutes) is not int
        or (status == "missed" and actual_minutes != 0)
        or (status == "done" and actual_minutes <= 0)
    ):
        raise ValueError(
            "Completed sessions need positive actual minutes; missed sessions use zero."
        )
    if now is None:
        now = datetime.now()
    if not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError("Use a local datetime without timezone information.")
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT s.status, s.step_id, s.day, s.start_minute, s.end_minute, "
                "s.end_minute - s.start_minute AS duration, "
                "t.remaining_minutes FROM scheduled_sessions s "
                "JOIN study_steps t ON t.id=s.step_id WHERE s.id=?",
                (session_id,),
            ).fetchone()
            if row is None or row["status"] != "planned":
                raise ValueError("This session is no longer pending. Refresh and try again.")
            when = date.fromisoformat(row["day"])
            now_minute = now.hour * 60 + now.minute
            if when > now.date() or (
                when == now.date()
                and (
                    row["end_minute"] > now_minute
                    if status == "missed"
                    else row["start_minute"] > now_minute
                )
            ):
                raise ValueError("You cannot complete or miss a session before it begins or ends.")
            if status == "done":
                from workspace.dependencies import prerequisite_ready

                snapshot = _fetch_snapshot(conn)
                task_id = next(s.task_id for s in snapshot.steps if s.id == row["step_id"])
                if any(
                    e.task_id == task_id and not prerequisite_ready(snapshot, e.prerequisite_id)
                    for e in snapshot.dependencies
                ):
                    raise ValueError(
                        "Record prerequisite completion before this dependent session. "
                        "Reserved time alone is not completed work."
                    )
                if actual_minutes > row["remaining_minutes"]:
                    raise ValueError("Completed minutes exceed remaining step work.")
                conn.execute(
                    "UPDATE study_steps SET remaining_minutes=remaining_minutes-? WHERE id=?",
                    (actual_minutes, row["step_id"]),
                )
            conn.execute(
                "UPDATE scheduled_sessions SET status=?,actual_minutes=? WHERE id=?",
                (status, actual_minutes, session_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rename_step(db_path: Path, step_id: int, title: str) -> None:
    title = _valid_title(title)
    if type(step_id) is not int or step_id <= 0:
        raise ValueError("Choose a valid step.")
    with closing(_connect(db_path)) as conn, conn:
        result = conn.execute("UPDATE study_steps SET title=? WHERE id=?", (title, step_id))
        if result.rowcount != 1:
            raise ValueError("Step no longer exists.")


def delete_step(db_path: Path, step_id: int) -> None:
    """Explicitly deleting a step also deletes its associated session history."""
    if type(step_id) is not int or step_id <= 0:
        raise ValueError("Choose a valid step.")
    with closing(_connect(db_path)) as conn, conn:
        if conn.execute("DELETE FROM study_steps WHERE id=?", (step_id,)).rowcount != 1:
            raise ValueError("Step no longer exists.")
