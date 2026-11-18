"""Regression tests for human-readable planning UI and stable scheduling geometry."""

import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta

from workspace.advanced_planner import (
    FixedEvent,
    PlannerSnapshot,
    SavedSession,
    Slot,
    StudyStep,
    TimeWindow,
    make_revision,
)
from workspace.views.schedule_comparison import (
    before_after_html,
    changed_days,
    format_slot,
    schedule_changes,
)

DAY = date(2026, 11, 17)


class CalendarV3Tests(unittest.TestCase):
    def test_new_suggested_times_start_on_five_minute_boundaries(self):
        step = StudyStep(
            1, 2, "Maths assignment", "Focus time", "timed", 60, 60, False, DAY, 3, False
        )
        snapshot = PlannerSnapshot(
            (step,),
            (TimeWindow(1, DAY, 18 * 60, 20 * 60),),
            (),
            (),
            "example",
        )
        proposal = make_revision(snapshot, datetime(2026, 11, 17, 18, 44))
        self.assertEqual(proposal.slots[0].start, 18 * 60 + 45)
        self.assertEqual(proposal.slots[0].end, 19 * 60 + 45)
        self.assertEqual(proposal.shortfalls, ())

    def test_accepted_session_at_unusual_minute_is_preserved(self):
        tomorrow = DAY + timedelta(days=1)
        step = StudyStep(
            1, 2, "Maths assignment", "Focus time", "timed", 30, 30, False, tomorrow, 3, False
        )
        saved = SavedSession(9, 1, tomorrow, 18 * 60 + 44, 19 * 60 + 14, "planned", 0)
        snapshot = PlannerSnapshot(
            (step,),
            (TimeWindow(1, tomorrow, 18 * 60, 20 * 60),),
            (),
            (saved,),
            "example",
        )
        proposal = make_revision(snapshot, datetime(2026, 11, 17, 10, 0))
        self.assertEqual(proposal.slots, (Slot(1, tomorrow, 1124, 1154),))
        self.assertEqual(proposal.unchanged, 1)

    def test_side_by_side_preview_aligns_and_highlights_changes(self):
        step = StudyStep(
            1,
            2,
            'A <script>alert("x")</script>',
            "Focus time",
            "timed",
            60,
            60,
            False,
            DAY,
            3,
            False,
        )
        old = (Slot(1, DAY, 9 * 60, 10 * 60),)
        new = (Slot(1, DAY, 15 * 60, 16 * 60),)
        event = FixedEvent(1, "Class", DAY, 11 * 60, 12 * 60, "Lecture")
        content = before_after_html(DAY, (event,), old, new, {1: step})
        self.assertIn(">Before</h4>", content)
        self.assertIn(">After</h4>", content)
        self.assertIn("cmp-old", content)
        self.assertIn("cmp-new", content)
        self.assertIn("cmp-lecture", content)
        self.assertIn("&lt;script&gt;", content)
        self.assertNotIn("<script>alert(", content)
        self.assertNotIn("href=", content)
        self.assertEqual(changed_days(old, new), (DAY,))

    def test_conflicting_event_and_study_remain_visible_in_separate_lanes(self):
        step = StudyStep(1, 2, "Statistics", "Focus time", "timed", 60, 60, False, DAY, 3, False)
        event = FixedEvent(1, "Guest lecture", DAY, 540, 600, "Lecture")
        old = (Slot(1, DAY, 540, 600),)
        preview = before_after_html(DAY, (event,), old, (), {1: step})
        self.assertIn("right:50%", preview)
        self.assertIn("left:50%", preview)

    def test_changes_are_grouped_by_task_and_only_changed_items(self):
        task_a = StudyStep(1, 2, "Statistics", "Focus time", "timed", 60, 60, False, DAY, 3, False)
        task_b = replace(task_a, id=2, task_id=3, task_title="Economics")
        keep = Slot(2, DAY, 10 * 60, 11 * 60)
        old = (Slot(1, DAY, 9 * 60, 10 * 60), keep)
        new = (Slot(1, DAY + timedelta(days=1), 14 * 60, 15 * 60), keep)
        changes = schedule_changes(old, new, {1: task_a, 2: task_b})
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0], "Statistics")
        self.assertEqual(len(changes[0][2]), 1)
        self.assertEqual(len(changes[0][3]), 1)
        self.assertIn("Wed 18 Nov", format_slot(changes[0][3][0]))


if __name__ == "__main__":
    unittest.main()
