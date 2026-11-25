"""Progress must not confuse study time reserved with work actually done."""

from types import SimpleNamespace

from workspace.task_progress import progress_details, progress_html


def task(remaining, status="pending", estimate=120):
    return SimpleNamespace(remaining_minutes=remaining, estimate_minutes=estimate, status=status)


def test_progress_from_logged_work_only():
    assert progress_details(task(90)) == (25, "Work completed")
    assert progress_details(task(120)) == (0, "Work completed")
    assert progress_details(task(120, "completed")) == (100, "Completed")


def test_checklist_fallback_is_clearly_labelled():
    steps = [SimpleNamespace(checked=True), SimpleNamespace(checked=False)]
    assert progress_details(task(120), steps) == (50, "Checklist completed")
    assert progress_details(task(90), steps) == (50, "Checklist completed")


def test_progress_markup_has_aria_and_no_false_completed_claim():
    html = progress_html(task(60))
    assert 'aria-valuenow="50"' in html
    assert "width:50%" in html
    assert "50% work completed" in html
    assert "pw-task-completion" in html


def test_completed_session_reduces_timed_step_not_parent_task():
    step = SimpleNamespace(kind="timed", estimate_minutes=120, remaining_minutes=30)
    # Parent task still says 120 left until task-level completion is updated.
    assert progress_details(task(120), timed_steps=[step]) == (75, "Work completed")
    assert 'aria-valuenow="75"' in progress_html(task(120), timed_steps=[step])
