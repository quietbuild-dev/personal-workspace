"""SQLite task storage. Each operation closes its connection."""

import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from workspace.models import Task, TaskDraft, revise_task

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "workspace.db"


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


def update_task(
    db_path: Path, task_id: int, draft: TaskDraft, remaining_minutes: int
) -> Task:
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
