"""Fixed-date planner behavior and invariants; no Streamlit or database."""

import random
import unittest
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from workspace.models import Task
from workspace.planner import generate_plan, week_bounds

TODAY = date(2026, 11, 11)  # Wednesday


def make_task(task_id, minutes, deadline=None, priority=2, completed=False):
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        category="University",
        deadline=deadline,
        priority=priority,
        estimate_minutes=max(1, minutes),
        remaining_minutes=0 if completed else minutes,
        status="completed" if completed else "pending",
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 11, 9, tzinfo=timezone.utc) if completed else None,
    )


class PlannerTests(unittest.TestCase):
    def test_week_bounds_monday_sunday_and_new_week(self):
        self.assertEqual(week_bounds(TODAY), (date(2026, 11, 9), date(2026, 11, 15)))
        self.assertEqual(week_bounds(date(2026, 11, 15)), (date(2026, 11, 9), date(2026, 11, 15)))
        self.assertEqual(week_bounds(date(2026, 11, 16)), (date(2026, 11, 16), date(2026, 11, 22)))

    def test_splitting_and_inclusive_deadlines(self):
        task = make_task(1, 90, date(2026, 11, 12))
        result = generate_plan([task], {TODAY: 40, TODAY + timedelta(days=1): 50}, TODAY)
        self.assertEqual(
            [(a.day, a.minutes) for a in result.allocations],
            [(TODAY, 40), (date(2026, 11, 12), 50)],
        )
        self.assertEqual(result.unallocated, ())

    def test_deadline_precedes_priority(self):
        early = make_task(1, 80, date(2026, 11, 12), priority=1)
        later = make_task(2, 80, date(2026, 11, 13), priority=3)
        result = generate_plan([later, early], {TODAY: 80}, TODAY)
        self.assertEqual([a.task_id for a in result.allocations], [1])
        self.assertEqual(result.unallocated[0].task_id, 2)

    def test_equal_deadline_uses_priority_then_stable_id(self):
        one = make_task(1, 10, date(2026, 11, 14), priority=3)
        two = make_task(2, 10, date(2026, 11, 14), priority=3)
        low = make_task(3, 10, date(2026, 11, 14), priority=1)
        result = generate_plan([low, two, one], {TODAY: 30}, TODAY)
        self.assertEqual([a.task_id for a in result.allocations], [1, 2, 3])

    def test_undated_is_after_dated_and_future_backlog_is_not_shortfall(self):
        undated = make_task(1, 20)
        later = make_task(2, 20, date(2026, 11, 23))
        due = make_task(3, 20, date(2026, 11, 14))
        result = generate_plan([undated, later, due], {TODAY: 20}, TODAY)
        self.assertEqual([a.task_id for a in result.allocations], [3])
        self.assertEqual(
            [(u.task_id, u.reason) for u in result.unallocated],
            [(2, "outside_current_plan"), (1, "outside_current_plan")],
        )

    def test_overdue_not_scheduled_and_completed_ignored(self):
        overdue = make_task(1, 40, TODAY - timedelta(days=1))
        completed = make_task(2, 100, TODAY, completed=True)
        result = generate_plan([overdue, completed], {TODAY: 100}, TODAY)
        self.assertFalse(result.allocations)
        self.assertEqual(
            [(u.task_id, u.minutes, u.reason) for u in result.unallocated], [(1, 40, "overdue")]
        )

    def test_deadline_shortfall_even_with_capacity_after_deadline(self):
        result = generate_plan(
            [make_task(1, 90, TODAY)], {TODAY: 25, TODAY + timedelta(days=1): 200}, TODAY
        )
        self.assertEqual(result.allocations[0].minutes, 25)
        self.assertEqual(result.unallocated[0].minutes, 65)
        self.assertEqual(result.unallocated[0].reason, "insufficient_capacity_before_deadline")

    def test_zero_capacity_and_no_recurring_next_week(self):
        result = generate_plan([make_task(1, 30)], {TODAY - timedelta(days=7): 200}, TODAY)
        self.assertEqual(result.allocations, ())
        self.assertEqual(result.unallocated[0].minutes, 30)

    def test_sunday_only_and_monday_rollover(self):
        sunday = date(2026, 11, 15)
        monday = sunday + timedelta(days=1)
        tasks = [make_task(1, 50)]
        sunday_plan = generate_plan(tasks, {sunday: 25, monday: 50}, sunday)
        monday_plan = generate_plan(tasks, {sunday: 25, monday: 50}, monday)
        self.assertEqual([(a.day, a.minutes) for a in sunday_plan.allocations], [(sunday, 25)])
        self.assertEqual([(a.day, a.minutes) for a in monday_plan.allocations], [(monday, 50)])

    def test_deterministic_for_shuffled_inputs(self):
        tasks = [make_task(i, i * 10, TODAY + timedelta(days=i % 4)) for i in range(1, 8)]
        capacity = {TODAY + timedelta(days=i): 45 for i in range(5)}
        expected = generate_plan(tasks, capacity, TODAY)
        random.Random(101).shuffle(tasks)
        self.assertEqual(generate_plan(tasks, capacity, TODAY), expected)
        self.assertEqual(generate_plan(tasks, capacity, TODAY), expected)

    def test_invalid_capacities_rejected(self):
        for val in (-1, 1441, 2.5, True, "60", None):
            with self.subTest(val=val), self.assertRaises(ValueError):
                generate_plan([], {TODAY: val}, TODAY)
        with self.assertRaises(ValueError):
            generate_plan([], {"Wednesday": 40}, TODAY)

    def test_duplicate_ids_and_inconsistent_pending_rejected(self):
        task = make_task(1, 10)
        with self.assertRaises(ValueError):
            generate_plan([task, task], {}, TODAY)
        with self.assertRaises(ValueError):
            generate_plan([replace(task, remaining_minutes=0)], {}, TODAY)

    def test_invariants_over_many_seeded_examples(self):
        randomizer = random.Random(12345)
        for _ in range(200):
            capacities = {TODAY + timedelta(days=i): randomizer.randrange(0, 130) for i in range(5)}
            tasks = [
                make_task(
                    i,
                    randomizer.randrange(1, 180),
                    (
                        None
                        if randomizer.randrange(5) == 0
                        else TODAY + timedelta(days=randomizer.randrange(-3, 10))
                    ),
                    randomizer.randrange(1, 4),
                )
                for i in range(1, 26)
            ]
            result = generate_plan(tasks, capacities, TODAY)
            allocated_day = defaultdict(int)
            allocated_task = defaultdict(int)
            residual = defaultdict(int)
            by_id = {t.id: t for t in tasks}
            for a in result.allocations:
                self.assertGreater(a.minutes, 0)
                self.assertGreaterEqual(a.day, TODAY)
                self.assertLessEqual(a.day, week_bounds(TODAY)[1])
                self.assertTrue(
                    by_id[a.task_id].deadline is None or a.day <= by_id[a.task_id].deadline
                )
                allocated_day[a.day] += a.minutes
                allocated_task[a.task_id] += a.minutes
            for day, minutes in allocated_day.items():
                self.assertLessEqual(minutes, capacities.get(day, 0))
            for u in result.unallocated:
                residual[u.task_id] += u.minutes
                self.assertGreater(u.minutes, 0)
            for t in tasks:
                self.assertEqual(allocated_task[t.id] + residual[t.id], t.remaining_minutes)


if __name__ == "__main__":
    unittest.main()
