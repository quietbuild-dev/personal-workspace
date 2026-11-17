"""Presentation checks: chart geometry and accessible text agree with saved data."""

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from workspace.advanced_planner import FixedEvent, Slot, StudyStep, TimeWindow


class CalendarPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The chart is pure Plotly; fake Streamlit in environments without its UI package.
        path = Path(__file__).resolve().parents[1] / "workspace/views/weekly_calendar.py"
        spec = importlib.util.spec_from_file_location("isolated_calendar_presentation", path)
        cls.calendar = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"streamlit": MagicMock()}):
            spec.loader.exec_module(cls.calendar)

    def setUp(self):
        self.monday = date(2026, 11, 9)
        self.sunday = date(2026, 11, 15)
        self.day = date(2026, 11, 13)
        self.steps = {
            2: StudyStep(
                2,
                1,
                "Economics exam",
                "Revise Chapter 3 carefully",
                "timed",
                90,
                90,
                False,
                self.sunday,
                3,
                False,
            )
        }
        self.events = (FixedEvent(1, "Lecture", self.day, 14 * 60, 15 * 60),)
        self.slots = (Slot(2, self.day, 9 * 60, 10 * 60 + 30),)
        self.windows = (TimeWindow(1, self.day, 8 * 60, 17 * 60),)

    def test_week_grid_has_seven_readable_day_columns_and_time_rows(self):
        fig = self.calendar._chart(
            self.events,
            self.slots,
            self.steps,
            self.monday,
            self.sunday,
            title="Accepted week",
            windows=self.windows,
        )
        self.assertEqual(len(fig.layout.xaxis.ticktext), 7)
        self.assertEqual(fig.layout.xaxis.ticktext[0], "Mon 09")
        self.assertEqual(fig.layout.xaxis.ticktext[4], "Fri 13")
        self.assertGreater(fig.layout.yaxis.range[0], fig.layout.yaxis.range[1])
        self.assertTrue(all(":" in text for text in fig.layout.yaxis.ticktext))
        self.assertEqual([trace.name for trace in fig.data], ["Fixed commitment", "Study session"])
        self.assertIn("Revise Chapter 3 carefully", fig.data[1].hovertemplate)
        self.assertIn("09:00-10:30", fig.data[1].hovertemplate)
        self.assertGreaterEqual(len(fig.layout.shapes), 1)
        self.assertTrue(any("Revise Chapter" in ann.text for ann in fig.layout.annotations))

    def test_full_agenda_includes_timed_work_and_fixed_commitments(self):
        entries = self.calendar._agenda(
            self.events, self.slots, self.steps, self.monday, self.sunday
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0][3], "Study")
        self.assertIn("Economics exam / Revise Chapter 3 carefully", entries[0][4])
        self.assertEqual(entries[1][3], "Fixed")
        self.assertEqual(entries[1][4], "Lecture")

    def test_range_includes_early_or_late_sessions(self):
        low, high = self.calendar._calendar_bounds(
            (),
            (Slot(2, self.day, 6 * 60, 23 * 60),),
            (),
            self.monday,
            self.sunday,
        )
        self.assertEqual(low, 5 * 60)
        self.assertEqual(high, 24 * 60)


if __name__ == "__main__":
    unittest.main()
