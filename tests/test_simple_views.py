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
        self.ui.text_area.side_effect = lambda label, value="", **_: self.inputs.get(label, value)
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
        from contextlib import ExitStack

        # Earlier tests may have imported views using real Streamlit already.
        # Rebind cached views as well as newly imported pages for this run only.
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {"streamlit": self.ui}))
            stack.enter_context(patch("workspace.repository.DEFAULT_DB_PATH", self.db))
            for module_name, module in tuple(sys.modules.items()):
                if not module_name.startswith("workspace.views.") or module is None:
                    continue
                if hasattr(module, "st"):
                    stack.enter_context(patch.object(module, "st", self.ui))
                if hasattr(module, "DEFAULT_DB_PATH"):
                    stack.enter_context(patch.object(module, "DEFAULT_DB_PATH", self.db))
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

    def test_home_has_no_duplicate_task_forms_or_planning_buttons(self):
        self.run_page("workspace/views/home.py")
        expanders = [str(c.args[0]) for c in self.ui.expander.call_args_list]
        assert "Add a task" not in expanders
        assert "Manage tasks" not in expanders
        labels = [str(c.args[0]) for c in self.ui.button.call_args_list]
        assert "Plan my week" not in labels
        assert "Open calendar" not in labels
        markup = " ".join(str(c.args[0]) for c in self.ui.markdown.call_args_list)
        assert "Your week at a glance" in markup
        assert "What's due next" in markup

    def test_deadline_warning_is_visible_without_opening_an_expander(self):
        from datetime import date, timedelta

        from workspace.advanced_repository import save_week_preferences
        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        tomorrow = date.today() + timedelta(days=1)
        create_quick_task(
            self.db,
            TaskDraft("Prepare important report", deadline=tomorrow, estimate_minutes=90),
        )
        save_week_preferences(self.db, (tomorrow,), 30, 9 * 60, 13 * 60)
        self.run_page("workspace/views/home.py")
        markup = " ".join(str(c.args[0]) for c in self.ui.markdown.call_args_list)
        assert "Prepare important report" in markup
        assert "still needs a study slot" not in markup
        assert "Deadline radar" not in markup
        assert "Which deadlines need attention?" not in [
            str(c.args[0]) for c in self.ui.expander.call_args_list
        ]
        assert (
            "Fix my schedule" in [str(c.args[0]) for c in self.ui.button.call_args_list]
            or "What's due next" in markup
        )

    def test_undo_only_appears_for_a_reversible_accepted_plan(self):
        from datetime import date, datetime, timedelta

        from workspace.advanced_planner import make_revision
        from workspace.advanced_repository import (
            accept_revision,
            add_fixed_event,
            load_snapshot,
            plan_undo_status,
            save_week_preferences,
        )
        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        self.run_page("workspace/views/week.py")
        assert "↶ Undo last plan" not in [c.args[0] for c in self.ui.button.call_args_list]
        tomorrow = date.today() + timedelta(days=1)
        create_quick_task(self.db, TaskDraft("Review exam notes", deadline=tomorrow))
        save_week_preferences(self.db, (tomorrow,), 120, 9 * 60, 14 * 60)
        now = datetime.now()
        accept_revision(self.db, make_revision(load_snapshot(self.db), now), now)
        assert plan_undo_status(self.db) == "ready"
        self.ui.button.reset_mock()
        self.run_page("workspace/views/week.py")
        assert "↶ Undo last plan" in [c.args[0] for c in self.ui.button.call_args_list]
        add_fixed_event(self.db, "Gym", tomorrow, 17 * 60, 18 * 60, "Exercise")
        assert plan_undo_status(self.db) == "changed"
        self.ui.button.reset_mock()
        self.run_page("workspace/views/week.py")
        assert "↶ Undo last plan" not in [c.args[0] for c in self.ui.button.call_args_list]

    def test_add_task_is_one_form_and_auto_plannable(self):
        self.inputs["Task name"] = "Prepare economics"
        self.clicks.add("+ Add a task")
        self.run_page("workspace/views/task_board.py")
        self.clicks = {"Save task"}
        self.run_page("workspace/views/task_board.py")
        self.assertEqual([task.title for task in list_tasks(self.db)], ["Prepare economics"])
        self.assertEqual(len(load_snapshot(self.db).steps), 1)
        self.clicks.clear()
        self.run_page("workspace/views/task_board.py")

    def test_visible_task_details_do_not_require_expanding_more_options(self):
        self.clicks.add("+ Add a task")
        self.run_page("workspace/views/task_board.py")
        self.clicks.clear()
        self.run_page("workspace/views/task_board.py")
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

    def test_custom_category_is_reusable_from_tasks(self):
        from workspace.advanced_repository import list_task_categories

        self.inputs.update(
            {
                "Task name": "Prepare club meeting",
                "Category": "+ New category",
                "New category": "Student association",
            }
        )
        self.clicks.add("+ Add a task")
        self.run_page("workspace/views/task_board.py")
        self.clicks = {"Save task"}
        self.run_page("workspace/views/task_board.py")
        self.assertIn("Student association", list_task_categories(self.db))
        self.assertEqual(list_tasks(self.db)[0].category, "Student association")

    def test_editing_task_saves_and_closes_details(self):
        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        task_id = create_quick_task(self.db, TaskDraft("Study assignment"))
        self.ui.session_state["open_task_details"] = task_id
        self.ui.session_state["task_more_details_id"] = task_id
        self.inputs["Task name"] = "Study assignment revised"
        self.clicks.add("Save changes")
        self.run_page("workspace/views/task_board.py")
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
        self.ui.session_state["task_more_details_id"] = task_id
        self.run_page("workspace/views/task_board.py")
        self.assertTrue(
            any(
                "All checklist items are done" in str(call.args[0])
                for call in self.ui.info.call_args_list
            )
        )
        self.clicks.add("Mark task done")
        self.run_page("workspace/views/task_board.py")
        self.assertEqual(list_tasks(self.db)[0].status, "completed")

    def test_compact_hhmm_deadline_time_is_persisted(self):
        from datetime import date, timedelta

        self.inputs["Task name"] = "Submit lab report"
        self.inputs["Deadline"] = date.today() + timedelta(days=1)
        self.inputs["Due time"] = "17:35"
        self.clicks.add("+ Add a task")
        self.run_page("workspace/views/task_board.py")
        self.clicks = {"Save task"}
        self.run_page("workspace/views/task_board.py")
        self.assertEqual(load_snapshot(self.db).steps[0].deadline_minute, 17 * 60 + 35)

    def test_event_edit_from_calendar_selected_block(self):
        from datetime import date

        from workspace.advanced_repository import add_fixed_event

        event_id = add_fixed_event(self.db, "Old lecture", date.today(), 540, 600)
        self.ui.query_params = {"event": str(event_id)}
        self.inputs["Event name"] = "Updated lecture"
        self.clicks.add("Save changes")
        self.run_page("workspace/views/week.py")
        self.assertIn("Updated lecture", [event.title for event in load_snapshot(self.db).events])

    def test_deadline_risk_shows_rescue_comparison_in_calendar(self):
        from datetime import date

        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        create_quick_task(self.db, TaskDraft("Urgent assignment", deadline=date.today()))
        self.ui.session_state["calendar_review_open"] = True
        self.run_page("workspace/views/week.py")
        self.assertFalse(
            any("Rescue my week" in str(call.args[0]) for call in self.ui.markdown.call_args_list)
        )
        # Optional what-if tools are hidden until a plan is previewed.
        self.assertFalse(
            any(
                "What if I lose study time?" in str(call.args[0])
                for call in self.ui.popover.call_args_list
            )
        )
        labels = [call.args[0] for call in self.ui.button.call_args_list]
        self.assertIn("Preview schedule", labels)
        self.assertIn(
            "What matters most this week?",
            [call.args[0] for call in self.ui.selectbox.call_args_list],
        )

    def test_focus_view_opens_the_exact_task_in_tasks(self):
        from datetime import date

        from workspace.models import TaskDraft
        from workspace.quick_tasks import create_quick_task

        chosen = create_quick_task(self.db, TaskDraft("Due today", deadline=date.today()))
        self.clicks.add("Details")
        self.run_page("workspace/views/home.py")
        self.assertEqual(self.ui.session_state["open_task_details"], chosen)
        self.ui.switch_page.assert_not_called()

    def test_tasks_done_action_without_opening_editor(self):
        self.inputs["Task name"] = "Laundry"
        self.clicks.add("+ Add a task")
        self.run_page("workspace/views/task_board.py")
        self.clicks = {"Save task"}
        self.run_page("workspace/views/task_board.py")
        self.clicks = {"Done"}
        self.run_page("workspace/views/task_board.py")
        self.assertEqual(list_tasks(self.db)[0].status, "completed")
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 0)


if __name__ == "__main__":
    unittest.main()
