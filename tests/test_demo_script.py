"""Demo data are reproducible and cannot overwrite the active DB or an existing file."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.create_demo_db import build_demo
from workspace.overview import load_overview
from workspace.repository import DEFAULT_DB_PATH


class DemoScriptTests(unittest.TestCase):
    def test_demo_has_real_scenario_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "demo.db"
            build_demo(destination, date(2026, 11, 11))
            summary = load_overview(destination, date(2026, 11, 11))
            self.assertEqual(len(summary.tasks), 7)
            self.assertEqual(summary.metrics.due_week_completed, 1)
            self.assertGreater(summary.metrics.overdue_minutes, 0)
            self.assertGreater(len(summary.plan.allocations), 0)
            with self.assertRaises(FileExistsError):
                build_demo(destination, date(2026, 11, 11))
            self.assertEqual(len(load_overview(destination, date(2026, 11, 11)).tasks), 7)

    def test_demo_rejects_active_database_path(self):
        with self.assertRaises(ValueError):
            build_demo(DEFAULT_DB_PATH, date(2026, 11, 11))


if __name__ == "__main__":
    unittest.main()
