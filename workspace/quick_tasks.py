"""Atomic quick-task workflow on top of the existing task and study-step schemas.

An automatically-created timed step represents a quick task's schedulable work.
The extra link table distinguishes it from user-created detailed timed steps, so
normal completion and editing never silently change independently added steps.
"""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from workspace.advanced_repository import add_step, initialize_advanced
from workspace.models import TaskDraft, revise_task
from workspace.repository import (
    _to_task,
    _validate_task_id,
    set_task_completion,
    update_task,
)


def initialize_quick_tasks(db_path: Path) -> None:
    """Additive migration; no old task or accepted session is rewritten."""
    initialize_advanced(db_path)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS quick_task_links (
                task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                step_id INTEGER NOT NULL UNIQUE REFERENCES study_steps(id) ON DELETE CASCADE
            )"""
        )


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _validated(draft: TaskDraft) -> TaskDraft:
    return TaskDraft(
        draft.title, draft.category, draft.deadline, draft.priority, draft.estimate_minutes
    )


def _validate_due_time(draft: TaskDraft, due_minute: int | None) -> None:
    if due_minute is not None and (
        type(due_minute) is not int or not 0 <= due_minute <= 1439 or draft.deadline is None
    ):
        raise ValueError("A deadline time needs a due date and a valid HH:MM time.")


def _write_due_time(conn: sqlite3.Connection, task_id: int, due_minute: int | None) -> None:
    if due_minute is None:
        conn.execute("DELETE FROM task_deadline_times WHERE task_id=?", (task_id,))
    else:
        conn.execute(
            "INSERT INTO task_deadline_times(task_id,minute) VALUES (?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET minute=excluded.minute",
            (task_id, due_minute),
        )


def create_quick_task(
    db_path: Path,
    draft: TaskDraft,
    *,
    due_minute: int | None = None,
    schedule: bool = True,
) -> int:
    """Create a task; optionally add a timed planning step atomically."""
    validated = _validated(draft)
    _validate_due_time(validated, due_minute)
    initialize_quick_tasks(db_path)
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            """INSERT INTO tasks
               (title,category,deadline,priority,estimate_minutes,remaining_minutes,
                status,created_at,completed_at)
               VALUES (?,?,?,?,?,?,'pending',?,NULL)""",
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
        task_id = cursor.lastrowid
        if schedule:
            step_id = conn.execute(
                """INSERT INTO study_steps
                   (task_id,title,kind,estimate_minutes,remaining_minutes,checked)
                   VALUES (?,'Focus time','timed',?,?,0)""",
                (task_id, validated.estimate_minutes, validated.estimate_minutes),
            ).lastrowid
            conn.execute(
                "INSERT INTO quick_task_links(task_id,step_id) VALUES (?,?)", (task_id, step_id)
            )
        conn.execute(
            "INSERT OR IGNORE INTO task_categories(name) VALUES (?)", (validated.category,)
        )
        _write_due_time(conn, task_id, due_minute)
        return task_id


def linked_step_ids(db_path: Path) -> dict[int, int]:
    initialize_quick_tasks(db_path)
    with closing(_connect(db_path)) as conn:
        return {
            row["task_id"]: row["step_id"]
            for row in conn.execute("SELECT task_id, step_id FROM quick_task_links")
        }


def enable_quick_planning(db_path: Path, task_id: int) -> bool:
    """Opt existing legacy task into hourly scheduling without altering its contents.

    Returns False when already linked. Never double-schedules a task with existing
    custom timed steps: those steps already represent its schedulable work.
    """
    _validate_task_id(task_id)
    initialize_quick_tasks(db_path)
    with closing(_connect(db_path)) as conn, conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task is None or task["status"] != "pending":
            raise ValueError("Choose an open task to schedule.")
        if conn.execute("SELECT 1 FROM quick_task_links WHERE task_id=?", (task_id,)).fetchone():
            return False
        if conn.execute(
            "SELECT 1 FROM study_steps WHERE task_id=? AND kind='timed'", (task_id,)
        ).fetchone():
            raise ValueError("This task already has detailed timed study steps.")
        step_id = conn.execute(
            """INSERT INTO study_steps
               (task_id,title,kind,estimate_minutes,remaining_minutes,checked)
               VALUES (?,'Focus time','timed',?,?,0)""",
            (task_id, task["estimate_minutes"], task["remaining_minutes"]),
        ).lastrowid
        conn.execute(
            "INSERT INTO quick_task_links(task_id,step_id) VALUES (?,?)", (task_id, step_id)
        )
        return True


def _other_unfinished(conn: sqlite3.Connection, task_id: int, auto_step_id: int) -> bool:
    return bool(
        conn.execute(
            """SELECT 1 FROM study_steps WHERE task_id=? AND id!=?
               AND ((kind='checklist' AND checked=0) OR
                    (kind='timed' AND remaining_minutes>0)) LIMIT 1""",
            (task_id, auto_step_id),
        ).fetchone()
    )


_UNSET = object()


def edit_quick_task(
    db_path: Path,
    task_id: int,
    draft: TaskDraft,
    remaining: int,
    *,
    due_minute: int | None | object = _UNSET,
) -> None:
    """Synchronize a task's estimate, remaining work and optional deadline time."""
    _validate_task_id(task_id)
    validated = _validated(draft)
    if due_minute is not _UNSET:
        _validate_due_time(validated, due_minute)
    initialize_quick_tasks(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            link = conn.execute(
                "SELECT step_id FROM quick_task_links WHERE task_id=?", (task_id,)
            ).fetchone()
            if link is None:
                conn.rollback()
                update_task(db_path, task_id, validated, remaining)
                with closing(_connect(db_path)) as update_conn, update_conn:
                    update_conn.execute(
                        "INSERT OR IGNORE INTO task_categories(name) VALUES (?)",
                        (validated.category,),
                    )
                    if due_minute is not _UNSET:
                        _write_due_time(update_conn, task_id, due_minute)
                return
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("This task no longer exists.")
            revised = revise_task(_to_task(row), validated, remaining)
            if revised.status == "completed" and _other_unfinished(conn, task_id, link["step_id"]):
                raise ValueError("Complete other checklist and timed steps first.")
            other_work = conn.execute(
                """SELECT COALESCE(SUM(estimate_minutes),0) AS estimates,
                          COALESCE(SUM(remaining_minutes),0) AS remaining
                   FROM study_steps WHERE task_id=? AND id!=? AND kind='timed'""",
                (task_id, link["step_id"]),
            ).fetchone()
            auto_estimate = revised.estimate_minutes - other_work["estimates"]
            auto_remaining = revised.remaining_minutes - other_work["remaining"]
            if auto_estimate <= 0 or not 0 <= auto_remaining <= auto_estimate:
                raise ValueError(
                    "The task must leave enough estimated and remaining time "
                    "for its detailed steps."
                )
            conn.execute(
                """UPDATE study_steps SET estimate_minutes=?, remaining_minutes=?
                   WHERE id=? AND kind='timed'""",
                (auto_estimate, auto_remaining, link["step_id"]),
            )
            conn.execute(
                """UPDATE tasks SET title=?,category=?,deadline=?,priority=?,
                   estimate_minutes=?,remaining_minutes=?,status=?,completed_at=? WHERE id=?""",
                (
                    revised.title,
                    revised.category,
                    revised.deadline.isoformat() if revised.deadline else None,
                    revised.priority,
                    revised.estimate_minutes,
                    revised.remaining_minutes,
                    revised.status,
                    revised.completed_at.isoformat() if revised.completed_at else None,
                    task_id,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO task_categories(name) VALUES (?)", (validated.category,)
            )
            if due_minute is not _UNSET:
                _write_due_time(conn, task_id, due_minute)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def toggle_quick_task(db_path: Path, task_id: int, completed: bool) -> None:
    """Quick completion closes ONLY the linked automatic step, not custom steps."""
    _validate_task_id(task_id)
    if type(completed) is not bool:
        raise ValueError("Completion must be true or false.")
    initialize_quick_tasks(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            link = conn.execute(
                "SELECT step_id FROM quick_task_links WHERE task_id=?", (task_id,)
            ).fetchone()
            if link is None:
                conn.rollback()
                set_task_completion(db_path, task_id, completed=completed)
                return
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("This task no longer exists.")
            current = _to_task(row)
            if (current.status == "completed") == completed:
                conn.rollback()
                return
            if completed and _other_unfinished(conn, task_id, link["step_id"]):
                raise ValueError("Complete other checklist and timed steps first.")
            if completed:
                remaining = 0
            else:
                # Previously completed detailed steps stay completed on reopening.
                auto = conn.execute(
                    "SELECT estimate_minutes FROM study_steps WHERE id=?", (link["step_id"],)
                ).fetchone()
                remaining = auto["estimate_minutes"]
            draft = TaskDraft(
                current.title,
                current.category,
                current.deadline,
                current.priority,
                current.estimate_minutes,
            )
            revised = revise_task(current, draft, remaining)
            conn.execute(
                "UPDATE study_steps SET remaining_minutes=? WHERE id=?",
                (remaining, link["step_id"]),
            )
            conn.execute(
                "UPDATE tasks SET remaining_minutes=?,status=?,completed_at=? WHERE id=?",
                (
                    remaining,
                    revised.status,
                    revised.completed_at.isoformat() if revised.completed_at else None,
                    task_id,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def restore_just_completed_task(db_path: Path, task_id: int, previous_remaining: int) -> None:
    """Reopen an immediately completed task with its previous work estimate.

    The quick-linked timed step is restored in the same transaction; ordinary
    Reopen deliberately resets to full estimated time, but this action does not.
    """
    _validate_task_id(task_id)
    if type(previous_remaining) is not int or previous_remaining <= 0:
        raise ValueError("There is no earlier work estimate to restore.")
    initialize_quick_tasks(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status,estimate_minutes FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None or row["status"] != "completed":
                raise ValueError("This task changed. Reopen it from the task list instead.")
            if previous_remaining > row["estimate_minutes"]:
                raise ValueError("The estimate changed. Reopen this task manually.")
            link = conn.execute(
                "SELECT step_id FROM quick_task_links WHERE task_id=?", (task_id,)
            ).fetchone()
            if link:
                step = conn.execute(
                    "SELECT estimate_minutes FROM study_steps WHERE id=?", (link["step_id"],)
                ).fetchone()
                if step is None or previous_remaining > step["estimate_minutes"]:
                    raise ValueError("This task's study steps changed. Reopen it manually.")
                conn.execute(
                    "UPDATE study_steps SET remaining_minutes=? WHERE id=?",
                    (previous_remaining, link["step_id"]),
                )
            conn.execute(
                "UPDATE tasks SET remaining_minutes=?,status='pending',completed_at=NULL "
                "WHERE id=?",
                (previous_remaining, task_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def add_detailed_timed_step(db_path: Path, task_id: int, title: str, minutes: int) -> int:
    """Split an auto focus block into two parts instead of double-counting work.

    On legacy tasks without an auto step, preserve the original add_step behavior.
    """
    _validate_task_id(task_id)
    if type(title) is not str or not 1 <= len(title.strip()) <= 120:
        raise ValueError("Provide a step title between 1 and 120 characters.")
    if type(minutes) is not int or minutes <= 0:
        raise ValueError("Provide a positive whole-minute step duration.")
    initialize_quick_tasks(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            linked = conn.execute(
                "SELECT step_id FROM quick_task_links WHERE task_id=?", (task_id,)
            ).fetchone()
            if linked is None:
                conn.rollback()
                return add_step(db_path, task_id, title, "timed", minutes)
            row = conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "pending":
                raise ValueError("Create timed steps under an open task.")
            auto = conn.execute(
                "SELECT estimate_minutes,remaining_minutes FROM study_steps WHERE id=?",
                (linked["step_id"],),
            ).fetchone()
            if (
                auto is None
                or minutes >= auto["estimate_minutes"]
                or minutes > auto["remaining_minutes"]
            ):
                raise ValueError(
                    "The detailed step must fit within remaining Focus time; "
                    "increase the task estimate first if needed."
                )
            conn.execute(
                """UPDATE study_steps SET estimate_minutes=estimate_minutes-?,
                   remaining_minutes=remaining_minutes-? WHERE id=?""",
                (minutes, minutes, linked["step_id"]),
            )
            step_id = conn.execute(
                """INSERT INTO study_steps
                   (task_id,title,kind,estimate_minutes,remaining_minutes,checked)
                   VALUES (?,?,'timed',?,?,0)""",
                (task_id, title.strip(), minutes, minutes),
            ).lastrowid
            conn.commit()
            return step_id
        except Exception:
            conn.rollback()
            raise
