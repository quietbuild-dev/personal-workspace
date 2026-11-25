"""The richer showcase is isolated, reproducible and has meaningful data."""

from datetime import datetime

import pytest

from scripts.create_rich_demo import create_demo
from workspace.advanced_repository import has_undo_plan, load_snapshot
from workspace.repository import list_tasks


def test_rich_demo_starts_with_commitments_and_accepted_study(tmp_path):
    dest = tmp_path / "student-sample.db"
    create_demo(dest, now=datetime(2026, 11, 25, 21))
    snapshot = load_snapshot(dest)
    assert len(snapshot.events) == 16
    assert len(snapshot.sessions) == 2
    assert len(list_tasks(dest)) == 11
    assert has_undo_plan(dest)
    assert any(t.remaining_minutes < t.estimate_minutes for t in list_tasks(dest))
    with pytest.raises(FileExistsError):
        create_demo(dest, now=datetime(2026, 11, 25, 21))


def test_demo_refuses_personal_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        create_demo(tmp_path / "data" / "workspace.db", now=datetime(2026, 11, 25, 21))
