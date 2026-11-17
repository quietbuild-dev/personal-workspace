"""Reproducible scaling experiment builds valid, isolated in-memory inputs."""

import unittest

from scripts.evaluate_rescue import NOW, evaluate, example_snapshot
from workspace.advanced_planner import make_revision, validate_revision
from workspace.planning_insights import compare_plans


class RescueBenchmarkTests(unittest.TestCase):
    def test_synthetic_fixture_reproducible_and_has_a_conflict(self):
        left = example_snapshot(8)
        right = example_snapshot(8)
        self.assertEqual(left, right)
        self.assertTrue(left.sessions)
        self.assertTrue(left.events)
        comparison = compare_plans(left, NOW)
        self.assertTrue(comparison.preserve.changed)
        self.assertEqual(comparison.preserve.revision.fingerprint, left.fingerprint)

    def test_synthetic_proposals_revalidate_at_multiple_sizes(self):
        for count in (1, 8, 16, 32, 64):
            with self.subTest(count=count):
                snapshot = example_snapshot(count)
                for preserve in (True, False):
                    proposal = make_revision(snapshot, NOW, preserve_existing=preserve)
                    validate_revision(snapshot, proposal, NOW)

    def test_report_contains_both_strategies_without_real_database(self):
        rows = evaluate((8, 16), repeats=2)
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["strategy"] for r in rows}, {"preserve", "rebuild"})
        self.assertTrue(all(r["median_runtime_ms"] >= 0 for r in rows))
        self.assertTrue(all(r["scheduled_minutes"] >= 0 for r in rows))
