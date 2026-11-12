"""Basic page/control paths through a Streamlit stand-in (NOT browser verification).

This test runs without Streamlit installed and checks that view code invokes the
correct real SQLite operations. A real Streamlit smoke check remains necessary.
"""

import runpy
import sys
import tempfile
import unittest
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from workspace.models import TaskDraft
from workspace.repository import (
    create_task,
    initialize_database,
    list_tasks,
    load_availability,
)


class UIRefresh(Exception):
    """Stand-in for Streamlit stopping execution for a rerun."""


class ViewLogicTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "view.db"
        initialize_database(self.db)
        self.ui = MagicMock()
        self.ui.session_state = {}
        self.ui.container.side_effect = lambda **_: nullcontext()
        self.ui.form.side_effect = lambda *_, **__: nullcontext()
        self.ui.columns.side_effect = lambda count, **_: [nullcontext()] * (
            count if type(count) is int else len(count)
        )
        self.ui.rerun.side_effect = UIRefresh()
        self.ui.stop.side_effect = RuntimeError("Page stopped on unexpected error")
        self.click = set()
        self.values = {}

        def selectbox(label, options, index=0, key=None, **_):
            selection = self.values.get(label)
            if selection not in options:
                selection = self.ui.session_state.get(key) if key else None
            if selection not in options:
                selection = list(options)[index]
            if key:
                self.ui.session_state[key] = selection
            return selection

        self.ui.selectbox.side_effect = selectbox
        self.ui.text_input.side_effect = lambda label, value="", key=None, **_: self.values.get(
            key, self.values.get(label, value)
        )
        self.ui.number_input.side_effect = lambda label, value=0, key=None, **_: self.values.get(
            key, self.values.get(label, value)
        )
        self.ui.date_input.side_effect = lambda label, value=None, key=None, **_: self.values.get(
            key, self.values.get(label, value)
        )
        self.ui.checkbox.side_effect = lambda label, value=False, key=None, **_: self.values.get(
            key, self.values.get(label, value)
        )
        self.ui.form_submit_button.side_effect = lambda label, **_: label in self.click
        self.ui.button.side_effect = lambda label, disabled=False, **_: (
            label in self.click and not disabled
        )

    def run_page(self, filename):
        with patch.dict(sys.modules, {"streamlit": self.ui}):
            with patch("workspace.repository.DEFAULT_DB_PATH", self.db):
                try:
                    runpy.run_path(filename, run_name="__main__")
                except UIRefresh:
                    return
        self.ui.error.assert_not_called()

    def test_empty_dashboard_and_planner_render(self):
        self.run_page("workspace/views/dashboard.py")
        self.ui.plotly_chart.assert_called_once()
        self.assertIn("N/A", [call.args[1] for call in self.ui.metric.call_args_list])
        self.run_page("workspace/views/planner.py")

    def test_create_and_filter_task(self):
        self.values["Title"] = "First saved task"
        self.click.add("Save task")
        self.run_page("workspace/views/tasks.py")
        self.assertEqual([task.title for task in list_tasks(self.db)], ["First saved task"])
        self.click.clear()
        self.values["Status"] = "Completed"  # Nothing matches.
        self.run_page("workspace/views/tasks.py")

    def test_completion_and_reopening_forms(self):
        saved = create_task(self.db, TaskDraft("Existing", estimate_minutes=80))
        self.click.add("Mark completed")
        self.run_page("workspace/views/tasks.py")
        self.assertEqual(list_tasks(self.db)[0].status, "completed")
        self.click = {"Save changes"}
        self.values[f"edit_{saved.id}_1_remaining"] = 20
        self.run_page("workspace/views/tasks.py")
        self.assertEqual(list_tasks(self.db)[0].remaining_minutes, 20)
        self.assertEqual(list_tasks(self.db)[0].status, "pending")

    def test_delete_requires_confirmation_and_updates_saved_data(self):
        saved = create_task(self.db, TaskDraft("Delete me"))
        self.click.add("Delete task permanently")
        self.run_page("workspace/views/tasks.py")
        self.assertEqual([t.id for t in list_tasks(self.db)], [saved.id])
        self.values[f"delete_confirm_{saved.id}"] = True
        self.run_page("workspace/views/tasks.py")
        self.assertEqual(list_tasks(self.db), [])

    def test_task_switching_and_stale_selected_id(self):
        first = create_task(self.db, TaskDraft("One"))
        second = create_task(self.db, TaskDraft("Two"))
        self.ui.session_state["selected_task_id"] = 99999
        self.run_page("workspace/views/tasks.py")
        self.assertIn(self.ui.session_state["selected_task_id"], {first.id, second.id})
        self.values["Choose a task"] = first.id
        self.run_page("workspace/views/tasks.py")
        self.assertEqual(self.ui.session_state["selected_task_id"], first.id)

    def test_availability_save_updates_real_db(self):
        self.click.add("Save availability")
        self.values["availability_" + date.today().isoformat()] = 120
        self.run_page("workspace/views/planner.py")
        self.assertEqual(load_availability(self.db, date.today(), date.today()),
                         {date.today(): 120})


if __name__ == "__main__":
    unittest.main()
