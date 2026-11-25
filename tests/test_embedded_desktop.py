"""Tests for the native Windows desktop window adapter (no Windows UI required)."""

from __future__ import annotations

import sys
import types
from unittest import TestCase
from unittest.mock import patch

from scripts import launch_desktop


class EmbeddedDesktopTests(TestCase):
    def test_uses_embedded_webview_without_opening_edge(self):
        calls = []
        fake = types.ModuleType("webview")

        def create_window(*args, **kwargs):
            calls.append(("window", args, kwargs))

        def start(**kwargs):
            calls.append(("start", kwargs))

        fake.create_window = create_window
        fake.start = start
        with patch.dict(sys.modules, {"webview": fake}):
            launch_desktop._open_embedded_window("http://127.0.0.1:8123")

        self.assertEqual(calls[0][0], "window")
        self.assertEqual(calls[0][1], ("Personal Workspace",))
        self.assertEqual(calls[0][2]["url"], "http://127.0.0.1:8123")
        self.assertEqual(
            calls[1],
            ("start", {"gui": "edgechromium", "debug": False, "private_mode": True}),
        )

    def test_missing_webview_has_installation_instruction(self):
        with patch.dict(sys.modules, {"webview": None}):
            with self.assertRaisesRegex(RuntimeError, "pip install -r requirements-dev.txt"):
                launch_desktop._open_embedded_window("http://127.0.0.1:8123")
