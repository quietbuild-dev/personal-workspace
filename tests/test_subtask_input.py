import pytest

from workspace.subtask_input import parse_subtasks


def test_multiline_subtasks():
    assert parse_subtasks("  Research  \n\nDraft report\r\n Review  ") == (
        "Research",
        "Draft report",
        "Review",
    )
    assert parse_subtasks("") == ()


def test_invalid_subtasks_rejected_before_task_created():
    with pytest.raises(ValueError):
        parse_subtasks("\n", required=True)
    with pytest.raises(ValueError):
        parse_subtasks("long" * 31)
    with pytest.raises(ValueError):
        parse_subtasks("x\n" * 21)
