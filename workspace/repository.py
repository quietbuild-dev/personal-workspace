"""SQLite task storage. Each operation closes its connection."""

import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from workspace.models import Task, TaskDraft, revise_task

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "WORKSPACE_DB_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "workspace.db"),
    )
)


def initialize_database(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                category TEXT NOT NULL CHECK(length(trim(category)) BETWEEN 1 AND 40),
                deadline TEXT,
                priority INTEGER NOT NULL CHECK(priority IN (1, 2, 3)),
                estimate_minutes INTEGER NOT NULL CHECK(estimate_minutes > 0),
                remaining_minutes INTEGER NOT NULL
                    CHECK(remaining_minutes BETWEEN 0 AND estimate_minutes),
                status TEXT NOT NULL CHECK(status IN ('pending', 'completed')),
                created_at TEXT NOT NULL,
                completed_at TEXT,
                CHECK(
                    (status = 'pending' AND remaining_minutes > 0 AND completed_at IS NULL)
                    OR
                    (status = 'completed' AND remaining_minutes = 0 AND completed_at IS NOT NULL)
                )
            )
        """)
        # Additive migration: existing task rows and their IDs are left unchanged.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS daily_availability (
                day TEXT PRIMARY KEY,
                available_minutes INTEGER NOT NULL
                    CHECK(available_minutes BETWEEN 0 AND 1440)
            )
        """)


def _to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        category=row["category"],
        deadline=date.fromisoformat(row["deadline"]) if row["deadline"] else None,
        priority=row["priority"],
        estimate_minutes=row["estimate_minutes"],
        remaining_minutes=row["remaining_minutes"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def create_task(db_path: Path, draft: TaskDraft) -> Task:
    # Constructing a draft validates input before a write is attempted.
    validated = TaskDraft(
        draft.title, draft.category, draft.deadline, draft.priority, draft.estimate_minutes
    )
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            """INSERT INTO tasks
               (title, category, deadline, priority, estimate_minutes, remaining_minutes,
                status, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, NULL)""",
            (
                validated.title,
                validated.category,
                validated.deadline.isoformat() if validated.deadline else None,
                validated.priority,
                validated.estimate_minutes,
                validated.estimate_minutes,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _to_task(row)


def list_tasks(db_path: Path = DEFAULT_DB_PATH) -> list[Task]:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
        return [_to_task(row) for row in rows]


def update_task(db_path: Path, task_id: int, draft: TaskDraft, remaining_minutes: int) -> Task:
    """Edit an existing record atomically, preserving its ID and creation time."""
    if type(task_id) is not int or not 1 <= task_id <= 2**63 - 1:
        raise ValueError("Task ID must be a positive integer.")
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        # Read and write in the same transaction, including completion timestamps.
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("This task no longer exists. Refresh the page.")
        revised = revise_task(_to_task(row), draft, remaining_minutes)
        if revised.status == "completed" and _has_unfinished_steps(connection, task_id):
            raise ValueError("Complete all checklist and timed steps before completing this task.")
        connection.execute(
            """UPDATE tasks SET title = ?, category = ?, deadline = ?, priority = ?,
               estimate_minutes = ?, remaining_minutes = ?, status = ?, completed_at = ?
               WHERE id = ?""",
            (
                revised.title,
                revised.category,
                revised.deadline.isoformat() if revised.deadline else None,
                revised.priority,
                revised.estimate_minutes,
                revised.remaining_minutes,
                revised.status,
                revised.completed_at.isoformat() if revised.completed_at else None,
                revised.id,
            ),
        )
        return revised


def set_task_completion(db_path: Path, task_id: int, *, completed: bool) -> Task:
    """Set completion directly from a list without editing task details.

    Reopening a completed task restores its full estimate, because the schema
    does not retain the remaining minutes from before completion. Users can
    subsequently refine remaining work in the edit form.
    """
    _validate_task_id(task_id)
    if type(completed) is not bool:
        raise ValueError("Completion must be true or false.")
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("This task no longer exists. Refresh the page.")
        current = _to_task(row)
        if (current.status == "completed") == completed:
            return current  # A repeated action must not change timestamps or work.
        if completed and _has_unfinished_steps(connection, task_id):
            raise ValueError("Complete all checklist and timed steps before completing this task.")
        remaining = 0 if completed else current.estimate_minutes
        draft = TaskDraft(
            current.title,
            current.category,
            current.deadline,
            current.priority,
            current.estimate_minutes,
        )
        revised = revise_task(current, draft, remaining)
        connection.execute(
            """UPDATE tasks SET remaining_minutes = ?, status = ?, completed_at = ?
               WHERE id = ?""",
            (
                revised.remaining_minutes,
                revised.status,
                revised.completed_at.isoformat() if revised.completed_at else None,
                task_id,
            ),
        )
        return revised


def _has_unfinished_steps(connection: sqlite3.Connection, task_id: int) -> bool:
    """Legacy databases without study_steps continue to work as before."""
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='study_steps'"
    ).fetchone()
    if not exists:
        return False
    row = connection.execute(
        "SELECT 1 FROM study_steps WHERE task_id=? "
        "AND ((kind='checklist' AND checked=0) OR "
        "(kind='timed' AND remaining_minutes>0)) LIMIT 1",
        (task_id,),
    ).fetchone()
    return row is not None


def _validate_task_id(task_id: int) -> None:
    if type(task_id) is not int or not 1 <= task_id <= 2**63 - 1:
        raise ValueError("Task ID must be a positive integer.")


def delete_task(db_path: Path, task_id: int) -> None:
    """Delete one task; an unknown ID is an error, not a silent success."""
    _validate_task_id(task_id)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cursor.rowcount != 1:
            raise ValueError("This task no longer exists. Refresh the page.")


def _validate_availability(values: dict[date, int]) -> None:
    for day, minutes in values.items():
        if type(day) is not date:
            raise ValueError("Availability keys must be calendar dates.")
        if type(minutes) is not int or not 0 <= minutes <= 1440:
            raise ValueError("Available minutes must be a whole number from 0 to 1440.")


def save_availability(db_path: Path, values: dict[date, int]) -> None:
    """Atomically upsert actual calendar dates; never repeats capacity weekly."""
    _validate_availability(values)  # Validate everything before writing anything.
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.executemany(
            """INSERT INTO daily_availability (day, available_minutes) VALUES (?, ?)
               ON CONFLICT(day) DO UPDATE SET available_minutes = excluded.available_minutes""",
            [(day.isoformat(), minutes) for day, minutes in values.items()],
        )


def load_availability(db_path: Path, start: date, end: date) -> dict[date, int]:
    """Return every date in [start, end], with missing entries set to zero."""
    from datetime import timedelta

    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("Provide an inclusive range of calendar dates in order.")
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT day, available_minutes FROM daily_availability WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    values = {date.fromisoformat(day): minutes for day, minutes in rows}
    output: dict[date, int] = {}
    day = start
    while day <= end:
        output[day] = values.get(day, 0)
        day += timedelta(days=1)
    return output
