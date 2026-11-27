"""Per-installation Study DNA: optional, local, and safe to edit at any time.

This module has no Streamlit dependency; preferences are soft scheduling goals,
not rigid restrictions on when a person is permitted to work.
"""

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

CONCENTRATION = {
    "early": (6 * 60, 10 * 60),
    "midday": (10 * 60, 14 * 60),
    "afternoon": (14 * 60, 18 * 60),
    "evening": (18 * 60, 23 * 60),
    "varies": None,
}
SESSION_LENGTHS = {"short": 25, "balanced": 45, "deep": 75, "flexible": 25}
DISTRIBUTIONS = ("steady", "batch", "none")
FLEXIBILITY = ("stable", "moderate", "open")


def custom_focus_range(value: str) -> tuple[int, int] | None:
    """Parse custom:HHMM-HHMM; custom focus hours are soft preferences."""
    match = re.fullmatch(r"custom:(\d{2})(\d{2})-(\d{2})(\d{2})", value)
    if not match:
        return None
    start_h, start_m, end_h, end_m = map(int, match.groups())
    if start_h > 23 or start_m > 59 or end_h > 24 or end_m > 59:
        return None
    if end_h == 24 and end_m != 0:
        return None
    start = 60 * start_h + start_m
    end = 60 * end_h + end_m
    return (start, end) if 0 <= start < end <= 1440 else None


def custom_concentration(start: int, end: int) -> str:
    """Store 24-hour focus times without changing the existing SQLite schema."""
    if not (isinstance(start, int) and isinstance(end, int)
            and 0 <= start < end <= 1440):
        raise ValueError("Focus finish time must be after the start time.")
    return f"custom:{start // 60:02d}{start % 60:02d}-{end // 60:02d}{end % 60:02d}"


@dataclass(frozen=True)
class StudyDNA:
    name: str = ""
    concentration: str = "varies"
    session_length: str = "balanced"
    distribution: str = "steady"
    flexibility: str = "moderate"

    def __post_init__(self):
        if not isinstance(self.name, str) or len(self.name.strip()) > 35:
            raise ValueError("Display name must contain at most 35 characters.")
        if (self.concentration not in CONCENTRATION
                and custom_focus_range(self.concentration) is None):
            raise ValueError("Choose a valid concentration window.")
        if self.session_length not in SESSION_LENGTHS:
            raise ValueError("Choose a valid session length.")
        if self.distribution not in DISTRIBUTIONS:
            raise ValueError("Choose a valid workload distribution.")
        if self.flexibility not in FLEXIBILITY:
            raise ValueError("Choose a valid schedule flexibility.")
        object.__setattr__(self, "name", self.name.strip())

    @property
    def focus_window(self) -> tuple[int, int] | None:
        return (
            CONCENTRATION[self.concentration]
            if self.concentration in CONCENTRATION
            else custom_focus_range(self.concentration)
        )

    @property
    def minimum_session(self) -> int:
        return SESSION_LENGTHS[self.session_length]


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS study_dna (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            display_name TEXT NOT NULL,
            concentration TEXT NOT NULL,
            session_length TEXT NOT NULL,
            distribution TEXT NOT NULL,
            flexibility TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_requirement (
            task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
            must_finish INTEGER NOT NULL CHECK(must_finish IN (0, 1))
        )
    """)


def load_study_dna(db_path: Path) -> StudyDNA | None:
    with closing(_connect(db_path)) as conn, conn:
        _schema(conn)
        record = conn.execute("""
            SELECT display_name, concentration, session_length, distribution, flexibility
            FROM study_dna WHERE id = 1
        """).fetchone()
    return StudyDNA(*record) if record else None


def save_study_dna(db_path: Path, profile: StudyDNA) -> None:
    if not isinstance(profile, StudyDNA):
        raise TypeError("StudyDNA profile required.")
    with closing(_connect(db_path)) as conn, conn:
        _schema(conn)
        conn.execute(
            """
            INSERT INTO study_dna(id, display_name, concentration, session_length,
                                  distribution, flexibility)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name=excluded.display_name,
                concentration=excluded.concentration,
                session_length=excluded.session_length,
                distribution=excluded.distribution,
                flexibility=excluded.flexibility
        """,
            (
                profile.name,
                profile.concentration,
                profile.session_length,
                profile.distribution,
                profile.flexibility,
            ),
        )


def set_required(db_path: Path, task_id: int, must_finish: bool) -> None:
    if not isinstance(task_id, int) or task_id < 1 or type(must_finish) is not bool:
        raise ValueError("Expected a task ID and a yes/no requirement.")
    with closing(_connect(db_path)) as conn, conn:
        _schema(conn)
        conn.execute(
            """
            INSERT INTO task_requirement(task_id, must_finish) VALUES (?, ?)
            ON CONFLICT(task_id) DO UPDATE SET must_finish=excluded.must_finish
        """,
            (task_id, int(must_finish)),
        )


def required_task_ids(db_path: Path, tasks) -> frozenset[int]:
    """Deadline-bearing tasks default to required, unless individually overridden."""
    with closing(_connect(db_path)) as conn, conn:
        _schema(conn)
        flags = dict(conn.execute("SELECT task_id, must_finish FROM task_requirement"))
    return frozenset(
        task.id
        for task in tasks
        if task.status != "completed" and bool(flags.get(task.id, task.deadline is not None))
    )


def task_is_required(db_path: Path, task) -> bool:
    return task.id in required_task_ids(db_path, (task,))


def preferred_overlap_minutes(slots, focus_window: tuple[int, int] | None) -> int:
    if focus_window is None:
        return 0
    lo, hi = focus_window
    return sum(max(0, min(s.end, hi) - max(s.start, lo)) for s in slots)
