"""Dashboard definition tests with a fixed week and explicit data."""

import unittest
from datetime import date, timedelta

from tests.test_planner import TODAY, make_task
from workspace.metrics import calculate_metrics, format_minutes
from workspace.planner import generate_plan


class MetricsTests(unittest.TestCase):
    def metrics(self, tasks, availability=None, today=TODAY):
        availability = availability or {}
        return calculate_metrics(tasks, generate_plan(tasks, availability, today),
                                 availability, today)

    def test_empty_state_uses_na_not_fake_percentage(self):
        metrics = self.metrics([])
        self.assertEqual(metrics.open_tasks, 0)
        self.assertEqual(metrics.remaining_minutes, 0)
        self.assertEqual(metrics.due_week_total, 0)
        self.assertIsNone(metrics.completion_percentage)
        self.assertEqual(len(metrics.workload), 5)  # Wednesday through Sunday
        self.assertEqual(metrics.today_allocations, ())

    def test_completion_cohort_is_due_week_not_completed_this_week(self):
        monday = date(2026, 11, 9)
        tasks = [make_task(1, 10, monday, completed=True),
                 make_task(2, 25, date(2026, 11, 15)),
                 make_task(3, 40, date(2026, 11, 16), completed=True),
                 make_task(4, 55, None)]
        metrics = self.metrics(tasks)
        self.assertEqual((metrics.due_week_completed, metrics.due_week_total), (1, 2))
        self.assertEqual(metrics.completion_percentage, 50)
        self.assertEqual(metrics.open_tasks, 2)
        self.assertEqual(metrics.remaining_minutes, 80)

    def test_deadline_shortfall_uses_eligible_dates_not_weekly_total(self):
        tasks = [make_task(1, 100, TODAY)]
        metrics = self.metrics(tasks, {TODAY: 30, TODAY + timedelta(days=1): 200})
        self.assertEqual(metrics.deadline_shortfall_minutes, 70)
        self.assertEqual(metrics.workload[0].planned_minutes, 30)
        self.assertEqual(metrics.workload[1].available_minutes, 200)
        self.assertIn("1h 10m", metrics.insight)
        self.assertIn("deadlines", metrics.insight)

    def test_overdue_warning_takes_precedence_and_ordering(self):
        tasks = [make_task(1, 60, TODAY - timedelta(days=1)),
                 make_task(2, 20, TODAY + timedelta(days=2)),
                 make_task(3, 40, TODAY + timedelta(days=1))]
        metrics = self.metrics(tasks)
        self.assertEqual(metrics.overdue_minutes, 60)
        self.assertEqual([t.id for t in metrics.overdue_tasks], [1])
        self.assertEqual([t.id for t in metrics.upcoming_tasks], [3, 2])
        self.assertTrue(metrics.insight.startswith("1h 00m of overdue"))

    def test_today_focus_matches_planner_order(self):
        tasks = [make_task(3, 40, TODAY, priority=1),
                 make_task(2, 20, TODAY, priority=3)]
        metrics = self.metrics(tasks, {TODAY: 100})
        self.assertEqual([a.task_id for a in metrics.today_allocations], [2, 3])
        self.assertEqual([a.minutes for a in metrics.today_allocations], [20, 40])

    def test_outside_plan_does_not_count_as_deadline_shortfall(self):
        tasks = [make_task(1, 200, date(2026, 11, 29))]
        metrics = self.metrics(tasks)
        self.assertEqual(metrics.outside_plan_minutes, 200)
        self.assertEqual(metrics.deadline_shortfall_minutes, 0)
        self.assertIn("future feasibility", metrics.insight)

    def test_unused_capacity_insight_and_formatting(self):
        metrics = self.metrics([], {TODAY: 125})
        self.assertIn("2h 05m", metrics.insight)
        self.assertEqual(format_minutes(0), "0m")
        self.assertEqual(format_minutes(65), "1h 05m")


if __name__ == "__main__":
    unittest.main()
