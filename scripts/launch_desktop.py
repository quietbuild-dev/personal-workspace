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
APP_USER_MODEL_ID = "QuietBuild.PersonalWorkspace.Desktop"
WINDOW_TITLE = "Personal Workspace"


def _set_windows_app_identity() -> None:
    """Separate this GUI process from the generic Python taskbar group."""
    if os.name != "nt":
        return
    set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    set_app_id.argtypes = [ctypes.c_wchar_p]
    set_app_id.restype = ctypes.c_long
    # A nonzero HRESULT means the OS did not accept the identity. Keep the
    # application usable if Windows declines this cosmetic setting.
    if set_app_id(APP_USER_MODEL_ID) != 0:
        _record_icon_note("Windows did not accept the Personal Workspace AppUserModelID")


def _record_icon_note(note: str) -> None:
    """Provide diagnostic context without letting an icon failure stop the app."""
    try:
        LOCAL_FILES.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(f"Desktop icon: {note}\n")
    except OSError:
        pass


def _set_native_window_icon(icon_path: Path) -> None:
    """Give the actual WinForms window large and small taskbar/titlebar icons.

    A Windows shortcut icon is not automatically inherited by pythonw.exe.
    Set WM_SETICON on the visible, process-owned WebView2 window instead.
    """
    if os.name != "nt" or not icon_path.is_file():
        return

    try:
        user32 = ctypes.windll.user32
        find_window = user32.FindWindowW
        find_window.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        find_window.restype = ctypes.c_void_p
        handle = find_window(None, WINDOW_TITLE)
        if not handle:
            _record_icon_note("Could not find the native app window")
            return

        get_window_pid = user32.GetWindowThreadProcessId
        get_window_pid.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        get_window_pid.restype = ctypes.c_ulong
        pid = ctypes.c_ulong()
        get_window_pid(handle, ctypes.byref(pid))
        if pid.value != os.getpid():
            _record_icon_note("Native window was not owned by this launcher process")
            return

        get_metric = user32.GetSystemMetrics
        get_metric.argtypes = [ctypes.c_int]
        get_metric.restype = ctypes.c_int
        load_icon = user32.LoadImageW
        load_icon.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        load_icon.restype = ctypes.c_void_p
        send = user32.SendMessageW
        send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        send.restype = ctypes.c_ssize_t

        # Windows chooses separate icon sizes for the title bar and taskbar.
        for icon_kind, metric_x, metric_y in ((1, 11, 12), (0, 49, 50)):
            image = load_icon(
                None,
                str(icon_path),
                1,  # IMAGE_ICON
                get_metric(metric_x),
                get_metric(metric_y),
                0x0010,  # LR_LOADFROMFILE
            )
            if image:
                send(handle, 0x0080, icon_kind, image)  # WM_SETICON
            else:
                _record_icon_note(f"Windows could not load icon size {icon_kind}")
    except (AttributeError, OSError, ValueError) as error:
        _record_icon_note(f"Could not apply taskbar icon: {error}")



def _open_embedded_window(url: str) -> None:
    """Display Streamlit without launching Edge or sharing its extensions/profile."""
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "The desktop window component is missing. From the project folder run:\n"
            ".\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt"
        ) from exc

    # Set process identity BEFORE any GUI appears, so the taskbar does not
    # treat our desktop window as a generic pythonw.exe application.
    _set_windows_app_identity()

    window = webview.create_window(
        WINDOW_TITLE,
        url=url,
        width=1280,
        height=820,
        min_size=(850, 560),
        background_color="#14141A",
        text_select=True,
    )
    # The GUI event loop exits when the app window closes. Do not silently
    # fall back to legacy Internet Explorer or a regular Edge browser.
    icon_path = PROJECT / "assets" / "personal-workspace.ico"
    options = {"gui": "edgechromium", "debug": False, "private_mode": True}
    if icon_path.is_file():
        # pywebview 6.2+ accepts the icon; explicitly set WM_SETICON as well
        # because the Windows taskbar may otherwise retain pythonw.exe's icon.
        options["icon"] = str(icon_path)
        if window is not None:
            window.events.shown += lambda: _set_native_window_icon(icon_path)
    webview.start(**options)


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
