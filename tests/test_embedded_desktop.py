"""Tests for the native Windows desktop window adapter (no Windows UI required)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
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
        self.assertEqual(calls[1][0], "start")
        self.assertEqual(calls[1][1]["gui"], "edgechromium")
        self.assertFalse(calls[1][1]["debug"])
        self.assertTrue(calls[1][1]["private_mode"])
        expected_icon = launch_desktop.PROJECT / "assets" / "personal-workspace.ico"
        if expected_icon.is_file():
            self.assertEqual(calls[1][1]["icon"], str(expected_icon))
        else:
            self.assertNotIn("icon", calls[1][1])

    def test_passes_existing_brand_icon_to_windows_webview(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        calls = []
        fake = types.ModuleType("webview")
        fake.create_window = lambda *args, **kwargs: None
        fake.start = lambda **kwargs: calls.append(kwargs)
        with TemporaryDirectory() as temp:
            project = Path(temp)
            icon = project / "assets" / "personal-workspace.ico"
            icon.parent.mkdir()
            icon.write_bytes(b"existing brand icon")
            with patch.object(launch_desktop, "PROJECT", project):
                with patch.dict(sys.modules, {"webview": fake}):
                    launch_desktop._open_embedded_window("http://127.0.0.1:8123")
            self.assertEqual(calls[0]["icon"], str(icon))

    def test_missing_webview_has_installation_instruction(self):
        with patch.dict(sys.modules, {"webview": None}):
            with self.assertRaisesRegex(RuntimeError, "pip install -r requirements-dev.txt"):
                launch_desktop._open_embedded_window("http://127.0.0.1:8123")


class WindowsBrandingTests(TestCase):
    def test_process_app_identity_is_set_before_window_creation(self):
        calls = []
        fake = types.ModuleType("webview")
        fake.create_window = lambda *args, **kwargs: calls.append("create")
        fake.start = lambda **kwargs: calls.append("start")
        with patch.object(launch_desktop, "_set_windows_app_identity") as identity:
            identity.side_effect = lambda: calls.append("identity")
            with patch.dict(sys.modules, {"webview": fake}):
                launch_desktop._open_embedded_window("http://127.0.0.1:8123")
        self.assertEqual(calls[:2], ["identity", "create"])

    def test_native_icon_is_applied_when_webview_window_is_shown(self):
        handlers = []

        class Event:
            def __iadd__(self, handler):
                handlers.append(handler)
                return self

        fake_window = types.SimpleNamespace(events=types.SimpleNamespace(shown=Event()))
        fake = types.ModuleType("webview")
        fake.create_window = lambda *args, **kwargs: fake_window
        fake.start = lambda **kwargs: None
        with TemporaryDirectory() as temp:
            project = Path(temp)
            icon = project / "assets" / "personal-workspace.ico"
            icon.parent.mkdir()
            icon.write_bytes(b"fixture icon")
            with patch.object(launch_desktop, "PROJECT", project):
                with patch.object(launch_desktop, "_set_native_window_icon") as apply_icon:
                    with patch.dict(sys.modules, {"webview": fake}):
                        launch_desktop._open_embedded_window("http://127.0.0.1:8123")
                    self.assertEqual(len(handlers), 1)
                    handlers[0]()
                    apply_icon.assert_called_once_with(icon)

    def test_non_windows_native_icon_update_is_safe(self):
        with patch.object(launch_desktop.os, "name", "posix"):
            launch_desktop._set_native_window_icon(Path("/missing/icon.ico"))
