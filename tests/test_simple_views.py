"""Lightweight Streamlit page control tests; not a browser/pixel test."""

import runpy
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

from workspace.advanced_repository import load_snapshot
from workspace.repository import list_tasks

ROOT = Path(__file__).resolve().parents[1]


class FakeRerun(BaseException):
    pass


class SimplePageSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "workspace.db"
        self.ui = MagicMock()
        self.ui.session_state = {}
        self.ui.container.side_effect = lambda **_: nullcontext()
        self.ui.expander.side_effect = lambda *_, **__: nullcontext()
        self.ui.popover.side_effect = lambda *_, **__: nullcontext()
        self.ui.segmented_control.side_effect = lambda label, options, default="Day", **_: default
        self.ui.radio.side_effect = lambda label, options, **_: list(options)[0]
        self.ui.query_params = {}
        self.ui.form.side_effect = lambda *_, **__: nullcontext()
        self.ui.columns.side_effect = lambda cols, **_: (
            [self.ui] * (cols if type(cols) is int else len(cols))
        )
        self.ui.time_input.side_effect = lambda label, value=None, **_: value
        self.ui.rerun.side_effect = FakeRerun()
        self.ui.stop.side_effect = AssertionError("Page stopped")
        self.ui.text_input.side_effect = lambda label, value="", **_: self.inputs.get(label, value)
        self.ui.number_input.side_effect = lambda label, value=0, **_: self.inputs.get(label, value)
        self.ui.date_input.side_effect = lambda label, value=None, **_: self.inputs.get(
            label, value
        )
        self.ui.checkbox.side_effect = lambda label, value=False, **_: self.inputs.get(label, value)
        self.ui.selectbox.side_effect = lambda label, options, index=0, **_: self.inputs.get(
            label, list(options)[index]
        )
        self.ui.form_submit_button.side_effect = lambda label, **_: label in self.clicks
        self.ui.button.side_effect = lambda label, disabled=False, **_: (
            label in self.clicks and not disabled
        )
        self.clicks = set()
        self.inputs = {}

    def run_page(self, page):
        with patch.dict(sys.modules, {"streamlit": self.ui}):
            with patch("workspace.repository.DEFAULT_DB_PATH", self.db):
                try:
                    runpy.run_path(str(ROOT / page), run_name="__main__")
                except FakeRerun:
                    pass
        # Error callouts may legitimately describe at-risk assignments.
        # Exceptions and rejected persistence are covered by the integration suite.

    def test_empty_home_week_render_without_exception(self):
        self.run_page("workspace/views/home.py")
        self.run_page("workspace/views/week.py")
        self.assertTrue(
            any("wp-calendar" in str(call.args[0]) for call in self.ui.markdown.call_args_list)
        )

    def test_quick_add_is_one_field_and_auto_plannable(self):
        self.inputs["Task name"] = "Prepare economics"
        self.clicks.add("Save task")
        self.run_page("workspace/views/home.py")
        self.assertEqual([task.title for task in list_tasks(self.db)], ["Prepare economics"])
        self.assertEqual(len(load_snapshot(self.db).steps), 1)
        self.clicks.clear()
        self.run_page("workspace/views/home.py")

    def test_visible_task_details_do_not_require_expanding_more_options(self):
        self.run_page("workspace/views/home.py")
        input_labels = [call.args[0] for call in self.ui.text_input.call_args_list]
        number_labels = [call.args[0] for call in self.ui.number_input.call_args_list]
        select_labels = [call.args[0] for call in self.ui.selectbox.call_args_list]
        self.assertIn("Task name", input_labels)
        self.assertIn("Hours", number_labels)
        self.assertIn("Minutes", number_labels)
        self.assertIn("Priority", select_labels)
        self.assertIn("Category", select_labels)
        self.assertIn(
            "Deadline",
            [call.args[0] for call in self.ui.date_input.call_args_list],
        )
        self.assertFalse(
            any("Add details" in str(call) for call in self.ui.expander.call_args_list)
        )

    def test_daily_study_budget_can_be_saved_from_week(self):
        from datetime import date

        today = date.today()
        self.inputs["Study hours"] = 1
        self.inputs["Study hours"] = 1.5
        self.clicks.add("Save preference")
        self.run_page("workspace/views/week.py")
        self.assertEqual({b.day: b.minutes for b in load_snapshot(self.db).budgets}[today], 90)

    def test_custom_category_is_reusable_from_home(self):
        from workspace.advanced_repository import list_task_categories

        self.inputs.update(
            {
                "Task name": "Prepare club meeting",
                "Category": "+ New category",
                "New category": "Student association",
            }
        )
        self.clicks.add("Save task")
        self.run_page("workspace/views/home.py")
        self.assertIn("Student association", list_task_categories(self.db))
        self.assertEqual(list_tasks(self.db)[0].category, "Student association")

    def test_editing_task_saves_and_closes_details(self):
        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        task_id = create_quick_task(self.db, TaskDraft("Study assignment"))
        self.ui.session_state["open_task_details"] = task_id
        self.inputs["Task name"] = "Study assignment revised"
        self.clicks.add("Save changes")
        self.run_page("workspace/views/home.py")
        self.assertFalse(self.ui.session_state.get("open_task_details"))
        self.assertEqual(list_tasks(self.db)[0].title, "Study assignment revised")

    def test_completed_checklist_offers_to_complete_task(self):
        from workspace.advanced_repository import add_step, set_checklist_done
        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        task_id = create_quick_task(self.db, TaskDraft("Finish reading"))
        step_id = add_step(self.db, task_id, "Read the final chapter", "checklist")
        set_checklist_done(self.db, step_id, True)
        self.ui.session_state["open_task_details"] = task_id
        self.run_page("workspace/views/home.py")
        self.assertTrue(
            any(
                "All checklist items are done" in str(call.args[0])
                for call in self.ui.info.call_args_list
            )
        )
        self.clicks.add("Mark task done")
        self.run_page("workspace/views/home.py")
        self.assertEqual(list_tasks(self.db)[0].status, "completed")

    def test_compact_hhmm_deadline_time_is_persisted(self):
        from datetime import date, timedelta

        self.inputs["Task name"] = "Submit lab report"
        self.inputs["Deadline"] = date.today() + timedelta(days=1)
        self.inputs["Due time"] = "17:35"
        self.clicks.add("Save task")
        self.run_page("workspace/views/home.py")
        self.assertEqual(load_snapshot(self.db).steps[0].deadline_minute, 17 * 60 + 35)

    def test_event_edit_from_calendar_selected_block(self):
        from datetime import date

        from workspace.advanced_repository import add_fixed_event

        event_id = add_fixed_event(self.db, "Old lecture", date.today(), 540, 600)
        self.ui.query_params = {"event": str(event_id)}
        self.inputs["Event name"] = "Updated lecture"
        self.clicks.add("Update event")
        self.run_page("workspace/views/week.py")
        self.assertIn("Updated lecture", [event.title for event in load_snapshot(self.db).events])

    def test_deadline_risk_shows_rescue_comparison_in_calendar(self):
        from datetime import date

        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        create_quick_task(self.db, TaskDraft("Urgent assignment", deadline=date.today()))
        self.run_page("workspace/views/week.py")
        self.assertTrue(
            any("Rescue my week" in str(call.args[0]) for call in self.ui.markdown.call_args_list)
        )
        self.assertTrue(
            any(
                "What if I lose study time?" in str(call.args[0])
                for call in self.ui.popover.call_args_list
            )
        )
        self.assertTrue(
            any(
                call.args[0] == "Choose your approach"
                for call in self.ui.segmented_control.call_args_list
            )
        )

    def test_home_done_action_without_opening_editor(self):
        self.inputs["Task name"] = "Laundry"
        self.clicks.add("Save task")
        self.run_page("workspace/views/home.py")
        self.clicks = {"Done"}
        self.run_page("workspace/views/home.py")
        self.assertEqual(list_tasks(self.db)[0].status, "completed")
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 0)


if __name__ == "__main__":
    unittest.main()
