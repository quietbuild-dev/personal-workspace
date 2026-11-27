"""Local task progress preferences and honest progress displays.

Self-reported percentages affect only the task progress indicator; they must
never silently reduce remaining study work or mark a deadline as fulfilled.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from html import escape
from pathlib import Path

MODES = ("auto", "checklist", "time", "manual")
MODE_LABELS = {
    "auto": "Automatic (checklist first)",
    "checklist": "Completed subtasks",
    "time": "Recorded study time",
    "manual": "My own percentage",
}


@dataclass(frozen=True)
class ProgressPreference:
    mode: str = "auto"
    manual_percent: int = 0


def initialize_progress(db_path: Path) -> None:
    """Add a small, non-destructive per-task table to an existing workspace."""
    from workspace.repository import initialize_database

    initialize_database(db_path)
    with closing(sqlite3.connect(db_path, timeout=10)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS task_progress_preferences (
                task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                mode TEXT NOT NULL CHECK(mode IN ('auto','checklist','time','manual')),
                manual_percent INTEGER NOT NULL DEFAULT 0
                    CHECK(manual_percent BETWEEN 0 AND 100)
            )"""
        )


def load_progress_preferences(db_path: Path) -> dict[int, ProgressPreference]:
    initialize_progress(db_path)
    with closing(sqlite3.connect(db_path, timeout=10)) as conn:
        return {
            row[0]: ProgressPreference(row[1], row[2])
            for row in conn.execute(
                "SELECT task_id,mode,manual_percent FROM task_progress_preferences"
            )
        }


def save_progress_preference(
    db_path: Path, task_id: int, mode: str, manual_percent: int = 0
) -> None:
    if type(task_id) is not int or task_id <= 0:
        raise ValueError("Choose a valid task.")
    if mode not in MODES:
        raise ValueError("Choose a supported progress method.")
    if type(manual_percent) is not int or not 0 <= manual_percent <= 100:
        raise ValueError("Progress must be a whole percentage from 0 to 100.")
    initialize_progress(db_path)
    with closing(sqlite3.connect(db_path, timeout=10)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone() is None:
            raise ValueError("This task no longer exists.")
        conn.execute(
            """INSERT INTO task_progress_preferences(task_id,mode,manual_percent)
               VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE SET
               mode=excluded.mode,manual_percent=excluded.manual_percent""",
            (task_id, mode, manual_percent),
        )


def progress_details(task, checklist=(), timed_steps=(), preference=None):
    """Return a meaningful display percentage and the source of that value."""
    if task.status == "completed":
        return 100, "Completed"
    pref = preference or ProgressPreference()
    items = tuple(checklist)
    timed = tuple(step for step in timed_steps if step.kind == "timed")
    # The user's explicit tracking choice wins. Auto preserves old tasks'
    # checklist-first behavior, but adding subtasks cannot override manual mode.
    if pref.mode == "manual":
        return pref.manual_percent, "My progress estimate"
    if pref.mode == "checklist" or (pref.mode == "auto" and items):
        checked = sum(bool(item.checked) for item in items)
        return (round(100 * checked / len(items)) if items else 0), "Checklist completed"
    if timed:
        estimate = max(1, sum(int(step.estimate_minutes) for step in timed))
        remaining = sum(int(step.remaining_minutes) for step in timed)
    else:
        estimate = max(1, int(task.estimate_minutes))
        remaining = int(task.remaining_minutes)
    remaining = min(estimate, max(0, remaining))
    return round(100 * (estimate - remaining) / estimate), "Work completed"


def progress_html(task, checklist=(), timed_steps=(), preference=None):
    """Accessible sage progress bar, never calculated from *booked* study time."""
    pct, meaning = progress_details(task, checklist, timed_steps, preference)
    items = tuple(checklist)
    if items and task.status != "completed" and meaning == "Checklist completed":
        checked = sum(bool(item.checked) for item in items)
        label = f"{checked} of {len(items)} subtasks complete · {pct}%"
    else:
        label = f"{pct}% {meaning.lower()}"
    return (
        '<div class="pw-task-completion" role="progressbar" '
        f'aria-label="{escape(label, quote=True)}" '
        f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{pct}">'
        f'<span style="width:{pct}%"></span></div>'
        f'<div class="pw-task-completion-caption">{escape(label)}</div>'
    )


def tracking_choice(task, task_mode: str | None, preference=None, checklist=()) -> str:
    """Visible, persistent creation/edit choice; never inferred from *new* subtasks.

    Older tasks without explicit preferences retain their old behavior.
    """
    if task_mode == "simple":
        return "Simple to-do"
    pref = preference or ProgressPreference()
    if pref.mode == "checklist" or (pref.mode == "auto" and checklist):
        return "Subtasks"
    return "Progress bar"
