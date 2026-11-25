"""Study DNA settings remain local, editable and backwards-compatible."""

from datetime import date, timedelta

import pytest

from workspace.advanced_planner import Slot
from workspace.models import TaskDraft
from workspace.repository import create_task, delete_task, initialize_database, list_tasks
from workspace.study_dna import (
    StudyDNA,
    load_study_dna,
    preferred_overlap_minutes,
    required_task_ids,
    save_study_dna,
    set_required,
)


def test_preferences_stay_in_one_database_and_are_editable(tmp_path):
    alice, mia = tmp_path / "alice.db", tmp_path / "mia.db"
    for path in (alice, mia):
        initialize_database(path)
    assert load_study_dna(alice) is None
    save_study_dna(alice, StudyDNA("Alice", "evening", "deep", "batch", "stable"))
    assert load_study_dna(mia) is None
    assert load_study_dna(alice).focus_window == (1080, 1380)
    save_study_dna(alice, StudyDNA("Alice", "midday", "short", "steady", "open"))
    assert load_study_dna(alice).minimum_session == 25
    assert load_study_dna(alice).concentration == "midday"


def test_study_dna_validation():
    with pytest.raises(ValueError):
        StudyDNA(name="z" * 36)
    with pytest.raises(ValueError):
        StudyDNA(concentration="all-night")
    with pytest.raises(ValueError):
        StudyDNA(flexibility="never")


def test_required_tasks_default_to_deadlines_and_can_be_overridden(tmp_path):
    path = tmp_path / "workspace.db"
    initialize_database(path)
    due = date.today() + timedelta(days=2)
    first = create_task(path, TaskDraft("Exam prep", deadline=due))
    later = create_task(path, TaskDraft("Optional reading"))
    assert required_task_ids(path, list_tasks(path)) == {first.id}
    set_required(path, first.id, False)
    set_required(path, later.id, True)
    assert required_task_ids(path, list_tasks(path)) == {later.id}
    delete_task(path, later.id)
    assert required_task_ids(path, list_tasks(path)) == frozenset()


def test_preferred_minutes_use_real_overlap_not_whole_session():
    slots = (Slot(1, date.today(), 550, 640), Slot(2, date.today(), 800, 860))
    assert preferred_overlap_minutes(slots, (600, 900)) == 40 + 60
    assert preferred_overlap_minutes(slots, None) == 0
