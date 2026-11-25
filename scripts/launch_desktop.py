"""Launch Streamlit inside a native Windows WebView2 desktop window.

Only the launch mechanism changes. All app data and planning code remain untouched.
"""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"
LOCAL_FILES = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "PersonalWorkspace"
LOG_PATH = LOCAL_FILES / "desktop-server.log"


def _open_embedded_window(url: str) -> None:
    """Display Streamlit without launching Edge or sharing its extensions/profile."""
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "The desktop window component is missing. From the project folder run:\n"
            ".\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt"
        ) from exc

    webview.create_window(
        "Personal Workspace",
        url=url,
        width=1280,
        height=820,
        min_size=(850, 560),
        background_color="#14141A",
        text_select=True,
    )
    # The GUI event loop exits when the app window closes. Do not silently
    # fall back to legacy Internet Explorer or a regular Edge browser.
    webview.start(gui="edgechromium", debug=False, private_mode=True)


def _free_local_port() -> int:
    """Use a fresh loopback port rather than conflicting with an existing demo."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(process: subprocess.Popen, port: int, timeout: float = 45) -> None:
    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError("The local app server stopped during startup.")
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.35)
    raise RuntimeError("The local app did not start. Please check the desktop-server.log file.")


def _show_problem(message: str) -> None:
    text = f"{message}\n\nDetails were saved to:\n{LOG_PATH}"
    ctypes.windll.user32.MessageBoxW(0, text, "Personal Workspace", 0x10)


def launch() -> None:
    if os.name != "nt":
        raise RuntimeError("This desktop launcher supports Windows only.")
    if not PYTHON.is_file():
        raise RuntimeError(
            "Python virtual environment not found. Run the existing setup "
            "instructions in README.md first."
        )

    LOCAL_FILES.mkdir(parents=True, exist_ok=True)
    port = _free_local_port()
    url = f"http://127.0.0.1:{port}"

    # Ensure this starts the normal personal workspace, never a demo database.
    env = os.environ.copy()
    env.pop("WORKSPACE_DB_PATH", None)

    command = [
        str(PYTHON),
        "-m",
        "streamlit",
        "run",
        str(PROJECT / "app.py"),
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--browser.serverAddress=127.0.0.1",
        "--browser.gatherUsageStats=false",
    ]

    server = None
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n--- Personal Workspace desktop start {time.ctime()} ---\n")
        log.flush()
        try:
            server = subprocess.Popen(
                command,
                cwd=PROJECT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            _wait_until_ready(server, port)

            # Embedded WebView2 has its own app window. The user's normal
            # Edge profile, extension onboarding, and sign-in are not involved.
            _open_embedded_window(url)
        finally:
            if server is not None and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


if __name__ == "__main__":
    try:
        launch()
    except Exception as exc:
        LOCAL_FILES.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(traceback.format_exc() + "\n")
        if os.name == "nt":
            _show_problem(str(exc))
        else:
            raise
