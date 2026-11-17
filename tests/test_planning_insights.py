"""Read-only comparisons, deadline explanations and safe what-if previews."""

import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import make_revision, validate_revision
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    add_step,
    initialize_advanced,
    load_snapshot,
    save_week_preferences,
)
from workspace.models import TaskDraft
from workspace.planning_insights import (
    compare_plans,
    explain_comparison,
    scenario_unavailable,
)
from workspace.quick_tasks import create_quick_task
from workspace.repository import create_task, initialize_database

TUESDAY = date(2026, 11, 17)
WEDNESDAY = TUESDAY + timedelta(days=1)
NEXT_WEEK = TUESDAY + timedelta(days=7)
NOW = datetime(2026, 11, 17, 8, 0)


class PlanningInsightsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "insights.db"
        initialize_database(self.db)

    def _task(self, title, deadline, minutes=120):
        return create_quick_task(self.db, TaskDraft(title, "University", deadline, 3, minutes))

    def test_deadline_risk_aggregates_steps_under_parent_task(self):
        initialize_advanced(self.db)
        task = create_task(
            self.db, TaskDraft("Economics assignment", "University", TUESDAY, 3, 120)
        ).id
        add_step(self.db, task, "Proof", "timed", 45)
        add_step(self.db, task, "Examples", "timed", 30)
        # No budget or windows => neither study step can be placed.
        comparison = compare_plans(load_snapshot(self.db), NOW)
        risks = comparison.preserve.risks
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].title, "Economics assignment")
        self.assertEqual(risks[0].unscheduled_minutes, 75)
        self.assertEqual(comparison.preserve.due_shortfall_minutes, 75)
        self.assertEqual(comparison.rebuild.due_shortfall_minutes, 75)

    def test_later_deadline_is_not_false_alarm(self):
        self._task("Exam next week", NEXT_WEEK)
        comparison = compare_plans(load_snapshot(self.db), NOW)
        self.assertEqual(comparison.preserve.risks, ())
        self.assertEqual(comparison.preserve.outside_week_minutes, 120)

    def test_scenario_only_changes_a_copy_of_inputs(self):
        self._task("Statistics", WEDNESDAY)
        save_week_preferences(self.db, (TUESDAY, WEDNESDAY), 120, 9 * 60, 12 * 60)
        before = load_snapshot(self.db)
        normal = compare_plans(before, NOW).preserve
        simulated = scenario_unavailable(before, NOW, TUESDAY, 9 * 60, 12 * 60)
        changed = compare_plans(simulated, NOW).preserve
        self.assertEqual(load_snapshot(self.db), before)
        self.assertEqual(before.events, ())
        self.assertEqual(len(simulated.events), 1)
        self.assertNotEqual(simulated.fingerprint, before.fingerprint)
        self.assertEqual(changed.scheduled_minutes, normal.scheduled_minutes)
        self.assertTrue(all(s.day != TUESDAY for s in changed.revision.slots))
        validate_revision(simulated, changed.revision, NOW)
        with self.assertRaises(StaleProposalError):
            accept_revision(self.db, changed.revision, NOW)
        self.assertFalse(load_snapshot(self.db).sessions)

    def test_unavailability_exposes_deadline_risk_without_writing(self):
        self._task("Submit by Tuesday", TUESDAY, 120)
        save_week_preferences(self.db, (TUESDAY,), 120, 9 * 60, 11 * 60)
        before = load_snapshot(self.db)
        original = compare_plans(before, NOW).preserve
        simulated = scenario_unavailable(before, NOW, TUESDAY, 9 * 60, 11 * 60)
        result = compare_plans(simulated, NOW).preserve
        self.assertEqual(original.due_shortfall_minutes, 0)
        self.assertEqual(result.due_shortfall_minutes, 120)
        self.assertEqual(result.risks[0].title, "Submit by Tuesday")
        self.assertEqual(load_snapshot(self.db), before)

    def test_after_new_lecture_both_strategies_validate_and_are_explained(self):
        self._task("Task A", WEDNESDAY)
        self._task("Task B", WEDNESDAY)
        save_week_preferences(self.db, (TUESDAY, WEDNESDAY), 120, 9 * 60, 12 * 60)
        initial = load_snapshot(self.db)
        accept_revision(self.db, make_revision(initial, NOW), NOW)
        add_fixed_event(self.db, "New lecture", TUESDAY, 9 * 60, 10 * 60, "Lecture")
        current = load_snapshot(self.db)
        comparison = compare_plans(current, NOW)
        validate_revision(current, comparison.preserve.revision, NOW)
        validate_revision(current, comparison.rebuild.revision, NOW)
        self.assertGreaterEqual(
            comparison.preserve.revision.unchanged,
            comparison.rebuild.revision.unchanged,
        )
        self.assertTrue(explain_comparison(comparison))
        self.assertEqual(load_snapshot(self.db), current)

    def test_reject_invalid_scenarios(self):
        snapshot = load_snapshot(self.db)
        for day, start, end in (
            (TUESDAY - timedelta(days=1), 480, 600),
            (TUESDAY, 600, 600),
            (TUESDAY, -1, 600),
            (NEXT_WEEK, 480, 600),
        ):
            with self.subTest(day=day, start=start, end=end):
                with self.assertRaises(ValueError):
                    scenario_unavailable(snapshot, NOW, day, start, end)
        with self.assertRaisesRegex(ValueError, "already passed"):
            scenario_unavailable(snapshot, datetime(2026, 11, 17, 18, 0), TUESDAY, 480, 600)

    def test_scenario_snapshot_does_not_mutate_user_schedules(self):
        self._task("Assignment", WEDNESDAY, 120)
        save_week_preferences(self.db, (TUESDAY,), 120, 9 * 60, 12 * 60)
        accept_revision(self.db, make_revision(load_snapshot(self.db), NOW), NOW)
        original = load_snapshot(self.db)
        hypothetical = scenario_unavailable(original, NOW, TUESDAY, 540, 660)
        comparison = compare_plans(hypothetical, NOW)
        self.assertEqual(load_snapshot(self.db).sessions, original.sessions)
        self.assertGreaterEqual(comparison.preserve.moved_or_removed, 1)
        # A direct accept of any simulated revision fails stale-preview checks.
        with self.assertRaises(StaleProposalError):
            accept_revision(self.db, comparison.preserve.revision, NOW)
