"""Safe demo creation and deterministic engineering comparison."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from scripts.create_advanced_demo import create_demo
from scripts.evaluate_advanced import benchmark
from workspace.advanced_repository import load_snapshot


class AdvancedDemoTests(unittest.TestCase):
    def test_demo_is_separate_persistent_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "study-demo.db"
            count, minutes = create_demo(file, datetime(2026, 11, 17, 8, 0))
            self.assertGreater(count, 0)
            self.assertGreater(minutes, 0)
            snapshot = load_snapshot(file)
            self.assertEqual(len(snapshot.steps), 5)
            self.assertEqual(sum(s.status == "planned" for s in snapshot.sessions), count)
            with self.assertRaises(FileExistsError):
                create_demo(file, datetime(2026, 11, 17, 8, 0))
            self.assertEqual(len(load_snapshot(file).steps), 5)

    def test_baseline_reports_real_measures(self):
        report = benchmark(3)
        self.assertGreater(report["preserved_work_minutes"], 0)
        self.assertGreaterEqual(
            report["preserved_unchanged_sessions"], report["baseline_unchanged_sessions"]
        )
        self.assertGreaterEqual(report["preserved_runtime_ms_median"], 0)


if __name__ == "__main__":
    unittest.main()
