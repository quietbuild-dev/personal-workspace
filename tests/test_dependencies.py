"""Dependency persistence, real progress, plan precedence and stale approvals."""

from dataclasses import replace
from datetime import timedelta

import pytest

from tests.test_optimizer import DAY, NOW, snapshot, step
from workspace.advanced_planner import (
    Slot,
    TaskDependency,
    TaskState,
    TimeWindow,
    make_revision,
    validate_revision,
)
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
    record_session,
    set_task_dependencies,
    set_timed_remaining,
    undo_last_plan,
)
from workspace.models import TaskDraft
from workspace.optimizer import optimize, proposal_from_slots
from workspace.quick_tasks import create_quick_task
from workspace.repository import delete_task, list_tasks


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    for title in ("Research", "Write", "Present"):
        create_quick_task(path, TaskDraft(title, deadline=DAY, estimate_minutes=30))
    add_window(path, DAY, 540, 720)
    return path


def test_additive_migration_and_edit_remove_dependencies(db):
    before = load_snapshot(db)
    tasks = list_tasks(db)
    initialize_advanced(db)
    assert load_snapshot(db) == before
    set_task_dependencies(db, 2, [1])
    assert load_snapshot(db).dependencies == (TaskDependency(2, 1),)
    set_task_dependencies(db, 2, [3])
    assert load_snapshot(db).dependencies == (TaskDependency(2, 3),)
    set_task_dependencies(db, 2, [])
    assert list_tasks(db) == tasks
    assert load_snapshot(db).steps == before.steps


@pytest.mark.parametrize("target,parents", [(1, [1]), (1, [999]), (999, []), (1, [2, 2])])
def test_invalid_reference_rejected(db, target, parents):
    before = load_snapshot(db)
    with pytest.raises(ValueError):
        set_task_dependencies(db, target, parents)
    assert load_snapshot(db) == before


def test_cycle_rolls_back_entire_edit(db):
    set_task_dependencies(db, 2, [1])
    set_task_dependencies(db, 3, [2])
    before = load_snapshot(db)
    with pytest.raises(ValueError, match="Circular"):
        set_task_dependencies(db, 1, [3])
    assert load_snapshot(db) == before


def test_delete_cascades_edges_and_invalidates_preview(db):
    set_task_dependencies(db, 2, [1])
    proposal = optimize(load_snapshot(db), NOW).revision
    delete_task(db, 1)
    assert load_snapshot(db).dependencies == ()
    with pytest.raises(StaleProposalError):
        accept_revision(db, proposal, NOW)


@pytest.mark.parametrize("engine", [make_revision, lambda s, n: optimize(s, n).revision])
def test_chain_schedules_in_order_without_marking_done(db, engine):
    set_task_dependencies(db, 2, [1])
    set_task_dependencies(db, 3, [2])
    snap = load_snapshot(db)
    proposal = engine(snap, NOW)
    assert proposal.planned_minutes == 90
    validate_revision(snap, proposal, NOW)
    blocks = {s.step_id: s for s in proposal.slots}
    assert blocks[1].end <= blocks[2].start < blocks[3].start
    accept_revision(db, proposal, NOW)
    assert [s.remaining_minutes for s in load_snapshot(db).steps] == [30, 30, 30]
    assert all(t.status == "pending" for t in list_tasks(db))
    assert undo_last_plan(db) == 0
    assert load_snapshot(db).sessions == ()


@pytest.mark.parametrize("engine", [make_revision, lambda s, n: optimize(s, n).revision])
def test_partial_prerequisite_cannot_release_child(engine):
    snap = snapshot(
        [step(1, 90), step(2, 30, 3)],
        [TimeWindow(1, DAY, 540, 600)],
        dependencies=(TaskDependency(2, 1),),
    )
    proposal = engine(snap, NOW)
    assert proposal.planned_minutes == 60
    assert all(s.step_id == 1 for s in proposal.slots)


def test_unchecked_checklist_and_unscheduled_legacy_task_block_children(db):
    set_task_dependencies(db, 2, [1])
    add_step(db, 1, "Get approval", "checklist")
    proposal = optimize(load_snapshot(db), NOW).revision
    assert all(s.step_id != 2 for s in proposal.slots)
    snap = snapshot(
        [step(2)],
        dependencies=(TaskDependency(2, 1),),
        task_states=(TaskState(1, False), TaskState(2, False)),
    )
    assert optimize(snap, NOW).revision.slots == ()


def test_actual_completion_releases_child_without_booking_prerequisite(db):
    set_task_dependencies(db, 2, [1])
    set_timed_remaining(db, 1, 0)
    proposal = optimize(load_snapshot(db), NOW).revision
    assert any(s.step_id == 2 for s in proposal.slots)
    assert all(s.step_id != 1 for s in proposal.slots)


def test_forged_reverse_order_rejected_and_dependency_edit_stales_preview(db):
    before = load_snapshot(db)
    proposal = optimize(before, NOW).revision
    set_task_dependencies(db, 2, [1])
    with pytest.raises(StaleProposalError):
        accept_revision(db, proposal, NOW)
    snap = load_snapshot(db)
    forged = proposal_from_slots(snap, NOW, (Slot(2, DAY, 540, 570), Slot(1, DAY, 570, 600)))
    with pytest.raises(ValueError, match="prerequisite"):
        accept_revision(db, forged, NOW)
    assert load_snapshot(db).sessions == ()


def test_reserved_prerequisite_is_not_actual_completion(db):
    set_task_dependencies(db, 2, [1])
    proposal = optimize(load_snapshot(db), NOW).revision
    accept_revision(db, proposal, NOW)
    sessions = {s.step_id: s for s in load_snapshot(db).sessions}
    later = NOW + timedelta(hours=12)
    with pytest.raises(ValueError, match="prerequisite completion"):
        record_session(db, sessions[2].id, "done", 30, now=later)
    record_session(db, sessions[1].id, "done", 10, now=later)
    snap = load_snapshot(db)
    assert next(s for s in snap.steps if s.id == 1).remaining_minutes == 20
    with pytest.raises(ValueError, match="prerequisite completion"):
        record_session(db, sessions[2].id, "done", 30, now=later)
    set_timed_remaining(db, 1, 0)
    record_session(db, sessions[2].id, "done", 30, now=later)


def test_cycle_in_external_snapshot_is_rejected():
    snap = snapshot([step(1), step(2)], dependencies=(TaskDependency(1, 2), TaskDependency(2, 1)))
    with pytest.raises(ValueError, match="Circular"):
        optimize(snap, NOW)
    with pytest.raises(ValueError, match="missing"):
        optimize(replace(snap, dependencies=(TaskDependency(1, 99),)), NOW)


def test_two_previews_cannot_overwrite_each_other_and_changed_graph_blocks_undo(db):
    snap = load_snapshot(db)
    first = optimize(snap, NOW, goal="deadlines").revision
    second = optimize(snap, NOW, goal="routine").revision
    accept_revision(db, first, NOW)
    with pytest.raises(StaleProposalError):
        accept_revision(db, second, NOW)
    set_task_dependencies(db, 2, [1])
    with pytest.raises(StaleProposalError):
        undo_last_plan(db)


def test_undo_cannot_restore_a_plan_that_breaks_new_dependencies(db):
    snap = load_snapshot(db)
    old = proposal_from_slots(snap, NOW, (Slot(2, DAY, 540, 570), Slot(1, DAY, 570, 600)))
    accept_revision(db, old, NOW)
    set_task_dependencies(db, 2, [1])
    safe = optimize(load_snapshot(db), NOW).revision
    accept_revision(db, safe, NOW)
    before = load_snapshot(db)
    with pytest.raises(ValueError, match="previous plan"):
        undo_last_plan(db, NOW)
    assert load_snapshot(db) == before
