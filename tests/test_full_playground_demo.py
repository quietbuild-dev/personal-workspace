"""Safety and usability checks for the stand-alone comprehensive demo fixture."""

import sqlite3
from datetime import datetime

import pytest

from scripts.create_full_playground_demo import DEMO_MARKER, create_demo
from scripts.launch_playground_desktop import _assert_demo
from workspace.advanced_repository import load_snapshot
from workspace.calendar_import import parse_ics
from workspace.repository import list_tasks
from workspace.weekly_replay import weekly_replay


def test_playground_has_realistic_tasks_events_replay_and_import(tmp_path):
    db = tmp_path / "my-playground.db"
    now = datetime(2026, 11, 26, 20, 0)
    result = create_demo(db, now=now)
    assert result["tasks"] >= 16
    assert result["events"] >= 45
    assert db.exists()
    _assert_demo(db)
    tasks = list_tasks(db)
    snapshot = load_snapshot(db)
    assert any("Birthday" in event.title for event in snapshot.events)
    assert any(event.kind == "Lecture" for event in snapshot.events)
    assert any(event.kind == "Social" for event in snapshot.events)
    assert any("Software Engineering" in task.category for task in tasks)
    assert any(session.status == "planned" for session in snapshot.sessions)
    last_week = weekly_replay(snapshot, now.date())
    # Current week has a study booking; last week has recorded completed and missed.
    assert last_week.booked_minutes > 0
    from datetime import timedelta
    previous = weekly_replay(snapshot, now.date() - timedelta(days=7))
    assert previous.finished_minutes == 55
    assert previous.missed_minutes == 60
    ics = parse_ics(result["ics"].read_bytes())
    assert len(ics.events) == 2
    assert not ics.warnings


def test_playground_never_overwrites_files(tmp_path):
    db = tmp_path / "once.db"
    db.write_bytes(b"preserve me")
    with pytest.raises(FileExistsError):
        create_demo(db, now=datetime(2026, 11, 26, 20, 0))
    assert db.read_bytes() == b"preserve me"


def test_personal_database_name_rejected(tmp_path):
    with pytest.raises(ValueError):
        create_demo(tmp_path / "workspace.db", now=datetime(2026, 11, 26, 20, 0))


def test_demo_launcher_refuses_unmarked_database(tmp_path):
    bad = tmp_path / "not-demo.db"
    with sqlite3.connect(bad) as conn:
        conn.execute("CREATE TABLE pw_playground_demo (marker TEXT NOT NULL, generated_at TEXT)")
        conn.execute("INSERT INTO pw_playground_demo VALUES('not-a-demo','today')")
    with pytest.raises(ValueError, match="Not a verified"):
        _assert_demo(bad)


def test_demo_marker_is_consistent(tmp_path):
    db = tmp_path / "tagged.db"
    create_demo(db, now=datetime(2026, 11, 29, 19, 0))
    with sqlite3.connect(db) as conn:
        marker = conn.execute("SELECT marker FROM pw_playground_demo").fetchone()[0]
    assert marker == DEMO_MARKER
    _assert_demo(db)
