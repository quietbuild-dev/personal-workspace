"""Day-specific study budgets and the compact calendar; no browser required."""

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from workspace.advanced_planner import (
    DayBudget,
    Slot,
    accepted_conflicts,
    effective_windows,
    hourly_workload,
    make_revision,
    validate_revision,
)
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    add_window,
    clear_day_budget,
    load_snapshot,
    record_session,
    save_day_budgets,
)
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task

# Test the pure HTML builder without requiring Streamlit in the test environment.
calendar_path = Path(__file__).resolve().parents[1] / "workspace/views/weekly_calendar.py"
calendar_spec = importlib.util.spec_from_file_location("day_budget_calendar_test", calendar_path)
calendar_module = importlib.util.module_from_spec(calendar_spec)
with patch.dict(sys.modules, {"streamlit": MagicMock()}):
    calendar_spec.loader.exec_module(calendar_module)
calendar_html = calendar_module.calendar_html

TUESDAY = date(2026, 11, 17)
WEDNESDAY = TUESDAY + timedelta(days=1)
NOW = datetime(2026, 11, 17, 8, 0)


class DailyBudgetIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "workspace.db"
        create_quick_task(self.path, TaskDraft("Economics", "University", WEDNESDAY, 3, 120))

    def test_budget_creates_gaps_around_lectures_without_manual_windows(self):
        save_day_budgets(self.path, {TUESDAY: 120, WEDNESDAY: 0})
        add_fixed_event(self.path, "Lecture", TUESDAY, 9 * 60, 11 * 60)
        add_fixed_event(self.path, "Appointment", TUESDAY, 12 * 60, 14 * 60)
        snapshot = load_snapshot(self.path)
        self.assertEqual(snapshot.windows, ())
        self.assertEqual(snapshot.budgets, (DayBudget(TUESDAY, 120), DayBudget(WEDNESDAY, 0)))
        proposal = make_revision(snapshot, NOW)
        self.assertEqual(proposal.planned_minutes, 120)
        self.assertEqual(
            [(slot.day, slot.start, slot.end) for slot in proposal.slots],
            [(TUESDAY, 480, 540), (TUESDAY, 660, 720)],
        )
        self.assertEqual(proposal.shortfalls, ())
        validate_revision(snapshot, proposal, NOW)

    def test_day_zero_overrides_old_windows_but_preserves_them(self):
        add_window(self.path, TUESDAY, 13 * 60, 16 * 60)
        save_day_budgets(self.path, {TUESDAY: 0})
        self.assertEqual(len(load_snapshot(self.path).windows), 1)
        self.assertFalse(effective_windows(load_snapshot(self.path)))
        self.assertFalse(make_revision(load_snapshot(self.path), NOW).slots)
        clear_day_budget(self.path, TUESDAY)
        snapshot = load_snapshot(self.path)
        self.assertEqual(snapshot.budgets, ())
        self.assertEqual(make_revision(snapshot, NOW).planned_minutes, 120)

    def test_repeating_is_not_automatic_and_preserves_existing_tasks(self):
        save_day_budgets(self.path, {TUESDAY: 75})
        snapshot = load_snapshot(self.path)
        self.assertEqual(len(snapshot.steps), 1)
        self.assertFalse(
            any(w.day == TUESDAY + timedelta(days=7) for w in effective_windows(snapshot))
        )
        save_day_budgets(self.path, {WEDNESDAY: 45})
        second = load_snapshot(self.path)
        self.assertEqual({b.day: b.minutes for b in second.budgets}, {TUESDAY: 75, WEDNESDAY: 45})
        self.assertEqual(len(second.steps), 1)

    def test_budget_accepted_and_change_makes_proposals_stale(self):
        save_day_budgets(self.path, {TUESDAY: 120})
        first = make_revision(load_snapshot(self.path), NOW)
        self.assertEqual(accept_revision(self.path, first, NOW), 1)
        saved = load_snapshot(self.path)
        old_ids = {s.id for s in saved.sessions}
        revision = make_revision(saved, NOW)
        save_day_budgets(self.path, {TUESDAY: 60})
        self.assertTrue(accepted_conflicts(load_snapshot(self.path), NOW))
        with self.assertRaises(StaleProposalError):
            accept_revision(self.path, revision, NOW)
        current = load_snapshot(self.path)
        self.assertEqual({s.id for s in current.sessions}, old_ids)
        new_revision = make_revision(current, NOW)
        self.assertEqual(new_revision.planned_minutes, 60)
        self.assertEqual(new_revision.shortfalls[0].minutes, 60)
        accept_revision(self.path, new_revision, NOW)
        self.assertEqual(len(load_snapshot(self.path).sessions), 1)

    def test_completed_time_counts_against_daily_budget(self):
        save_day_budgets(self.path, {TUESDAY: 90, WEDNESDAY: 90})
        first = make_revision(load_snapshot(self.path), NOW)
        self.assertEqual(
            [(s.day, s.minutes) for s in first.slots],
            [(TUESDAY, 90), (WEDNESDAY, 30)],
        )
        accept_revision(self.path, first, NOW)
        session = next(s for s in load_snapshot(self.path).sessions if s.day == TUESDAY)
        record_session(self.path, session.id, "done", 40, now=datetime(2026, 11, 17, 10, 0))
        snapshot = load_snapshot(self.path)
        next_plan = make_revision(snapshot, datetime(2026, 11, 17, 10, 0))
        self.assertEqual(next_plan.planned_minutes, 80)
        self.assertEqual(sum(s.minutes for s in next_plan.slots if s.day == TUESDAY), 50)
        self.assertEqual(hourly_workload(snapshot, datetime(2026, 11, 17, 10, 0))[TUESDAY][0], 50)

    def test_reject_forged_over_budget_and_invalid_inputs(self):
        save_day_budgets(self.path, {TUESDAY: 60})
        snapshot = load_snapshot(self.path)
        initial = make_revision(snapshot, NOW)
        self.assertEqual(initial.planned_minutes, 60)
        bad = replace(initial, slots=(Slot(snapshot.steps[0].id, TUESDAY, 480, 600),))
        with self.assertRaisesRegex(ValueError, "budget"):
            validate_revision(snapshot, bad, NOW)
        for bad_value in (-1, 841, 1.5, True, "two hours"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaises(ValueError):
                    save_day_budgets(self.path, {TUESDAY: bad_value})
        with closing(sqlite3.connect(self.path)) as conn, conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE day_study_budgets SET minutes=-5")


class CalendarHtmlTests(unittest.TestCase):
    def test_daily_and_weekly_alignment_with_time_gutter(self):
        event = SimpleNamespace(day=TUESDAY, start=9 * 60, end=10 * 60, title="Lecture")
        slot = Slot(7, TUESDAY, 10 * 60, 11 * 60)
        steps = {7: SimpleNamespace(title="Study economics")}
        daily = calendar_html((event,), (slot,), steps, TUESDAY, TUESDAY, today=TUESDAY)
        weekly = calendar_html((event,), (slot,), steps, TUESDAY, TUESDAY + timedelta(days=6))
        self.assertIn("--days:1", daily)
        self.assertIn("--days:7", weekly)
        self.assertEqual(daily.count('class="wp-day-name'), 1)
        self.assertEqual(weekly.count('class="wp-day-name'), 7)
        self.assertIn("Lecture", daily)
        self.assertIn("Study economics", daily)
        self.assertIn("09:00", daily)
        self.assertIn("10:00", daily)
        self.assertIn("wp-study", daily)
        self.assertIn("wp-fixed", daily)

    def test_escapes_user_titles_and_refuses_long_range(self):
        event = SimpleNamespace(
            day=TUESDAY, start=600, end=660, title='<script>alert("x")</script>'
        )
        content = calendar_html((event,), (), {}, TUESDAY, TUESDAY)
        self.assertNotIn("<script>", content)
        self.assertIn("&lt;script&gt;", content)
        with self.assertRaises(ValueError):
            calendar_html((), (), {}, TUESDAY, TUESDAY + timedelta(days=8))


if __name__ == "__main__":
    unittest.main()
