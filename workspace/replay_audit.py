"""Optional forward-only plan approval journal using SQLite triggers.

No changes to optimizer or save APIs: once enabled, the existing atomic
`last_plan_undo` UPSERT automatically records accepted new plans and revisions.
It does not pretend to reconstruct events before the journal was enabled.
"""

from contextlib import closing
from datetime import date
from pathlib import Path

from workspace.advanced_planner import week_bounds
from workspace.advanced_repository import _connect, initialize_advanced


def enable_plan_history(db_path: Path) -> None:
    """Explicit opt-in: install SQLite triggers for *future* approved plans only."""
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS plan_approval_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                monday TEXT NOT NULL,
                sunday TEXT NOT NULL,
                had_previous_blocks INTEGER NOT NULL CHECK(had_previous_blocks IN (0,1))
            );
            CREATE TRIGGER IF NOT EXISTS history_plan_approval_insert
            AFTER INSERT ON last_plan_undo
            BEGIN
                INSERT INTO plan_approval_history(monday,sunday,had_previous_blocks)
                VALUES (NEW.monday,NEW.sunday,
                        CASE WHEN NEW.previous_sessions='[]' THEN 0 ELSE 1 END);
            END;
            CREATE TRIGGER IF NOT EXISTS history_plan_approval_update
            AFTER UPDATE ON last_plan_undo
            BEGIN
                INSERT INTO plan_approval_history(monday,sunday,had_previous_blocks)
                VALUES (NEW.monday,NEW.sunday,
                        CASE WHEN NEW.previous_sessions='[]' THEN 0 ELSE 1 END);
            END;
        """)


def approval_counts(db_path: Path, week_of: date) -> tuple[int, int] | None:
    """(approvals, approvals replacing previous blocks), or None if not enabled."""
    if type(week_of) is not date:
        raise ValueError("Choose a valid week.")
    if not db_path.is_file():
        return None
    with closing(_connect(db_path)) as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='plan_approval_history'"
        ).fetchone():
            return None
        monday, sunday = week_bounds(week_of)
        count = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(had_previous_blocks),0) "
            "FROM plan_approval_history WHERE monday=? AND sunday=?",
            (monday.isoformat(), sunday.isoformat()),
        ).fetchone()
        return int(count[0]), int(count[1])
