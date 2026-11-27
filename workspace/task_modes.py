"""Optional task display modes. No change to task estimates or study scheduling."""

import sqlite3
from contextlib import closing
from pathlib import Path

MODES = ("simple", "progress")


def _connect(db_path: Path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_task_modes(db_path: Path) -> None:
    from workspace.repository import initialize_database

    initialize_database(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS task_display_modes ("
            "task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,"
            "mode TEXT NOT NULL CHECK(mode IN ('simple', 'progress')))"
        )


def load_task_modes(db_path: Path) -> dict[int, str]:
    initialize_task_modes(db_path)
    with closing(_connect(db_path)) as conn:
        return dict(conn.execute("SELECT task_id, mode FROM task_display_modes"))


def save_task_mode(db_path: Path, task_id: int, mode: str) -> None:
    if type(task_id) is not int or task_id <= 0 or mode not in MODES:
        raise ValueError("Choose a valid task display mode.")
    initialize_task_modes(db_path)
    with closing(_connect(db_path)) as conn, conn:
        if not conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise ValueError("Task no longer exists.")
        conn.execute(
            "INSERT INTO task_display_modes(task_id,mode) VALUES (?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET mode=excluded.mode",
            (task_id, mode),
        )


def is_simple_task(task, steps=(), modes=None) -> bool:
    explicit = (modes or {}).get(task.id)
    if explicit is not None:
        return explicit == "simple"
    # Unscheduled errands from older versions have no timed or checklist steps.
    return not any(step.task_id == task.id for step in steps)


def suggest_simple_title(title: str) -> bool:
    """Conservative convenience hint; users always confirm or override it."""
    import re

    return bool(re.match(
        r"\s*(?:buy|email|send|call|text|pick up|book|pay|collect|order|"
        r"reply|message|return|print|post)\b", title, flags=re.I,
    ))
