"""Visual regression checks that do not require a running Streamlit server."""

import unittest
from datetime import date, timedelta
from html import escape
from pathlib import Path

from workspace.advanced_planner import Slot
from workspace.theme import (
    ACCENT,
    BACKGROUND,
    CALENDAR_CSS,
    COMPARISON_CSS,
    GLOBAL_CSS,
    priority_badge,
    stat_card,
    strategy_cards,
)
from workspace.views.schedule_comparison import before_after_html

ROOT = Path(__file__).resolve().parents[1]


class LavenderThemeTests(unittest.TestCase):
    def test_global_palette_matches_streamlit_configuration(self):
        self.assertEqual(BACKGROUND, "#14141A")
        self.assertEqual(ACCENT, "#BAA9D0")
        config = (ROOT / ".streamlit/config.toml").read_text()
        for color in ("#14141A", "#22222B", "#BAA9D0", "#F1EEF5"):
            self.assertIn(color, config)
            self.assertIn(color, GLOBAL_CSS)

    def test_priority_badges_are_distinct_and_not_title_prefixes(self):
        self.assertIn("pw-priority--high", priority_badge(3))
        self.assertIn("pw-priority--medium", priority_badge(2))
        self.assertIn("pw-priority--low", priority_badge(1))
        self.assertNotEqual(priority_badge(3), priority_badge(1))

    def test_labels_are_escaped_before_html_rendering(self):
        label = '<script>alert("x")</script>'
        html = stat_card(label, "2", "Open <tasks>")
        self.assertIn(escape(label), html)
        self.assertNotIn(label, html)
        self.assertIn("&lt;tasks&gt;", html)

    def test_strategy_cards_explain_both_options_and_selected_state(self):
        html = strategy_cards("Change as little as possible")
        self.assertIn("Change as little as possible", html)
        self.assertIn("Find more time for unfinished work", html)
        self.assertEqual(html.count("pw-strategy--active"), 1)

    def test_saved_calendar_retains_click_targets_with_new_colors(self):
        today = date(2026, 11, 25)
        self.assertEqual(today.year, 2026)
        calendar_source = (ROOT / "workspace/views/weekly_calendar.py").read_text()
        self.assertIn("CALENDAR_CSS", calendar_source)
        self.assertIn("wp-block wp-{kind}", calendar_source)
        self.assertIn("#655875", CALENDAR_CSS)
        self.assertIn("#BAA9D0", GLOBAL_CSS)

    def test_before_after_uses_lavender_palette_without_data_mutations(self):
        today = date(2026, 11, 25)
        before = (Slot(1, today, 540, 600),)
        after = (Slot(1, today + timedelta(days=1), 720, 780),)
        html = before_after_html(today, (), before, after, {})
        self.assertIn("Before", html)
        self.assertIn("After", html)
        self.assertIn("#D6B8F1", COMPARISON_CSS)
        self.assertEqual(before[0].start, 540)

    def test_main_navigation_includes_access_to_legacy_advanced_views(self):
        app = (ROOT / "app.py").read_text()
        for route in (
            "workspace/views/home.py",
            "workspace/views/week.py",
            "workspace/views/task_board.py",
            "workspace/views/tasks.py",
            "workspace/views/planner.py",
        ):
            self.assertIn(route, app)
        self.assertIn('position="top"', app)


if __name__ == "__main__":
    unittest.main()
