"""Run a specifically marked demo database in a separate native Windows desktop window.

The normal Personal Workspace desktop launcher is NOT changed. This demo launcher
refuses to run against any database without the safe demo marker.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
from pathlib import Path

from scripts import launch_desktop as desktop
from scripts.create_full_playground_demo import DEMO_MARKER


def _assert_demo(db_path: Path) -> None:
    if not db_path.is_file() or db_path.suffix.lower() != ".db":
        raise ValueError("Demo database not found. Generate it first.")
    if db_path.name.lower() == "workspace.db":
        raise ValueError("Refusing to launch against the personal database.")
    # Read-only verification: do not modify an untrusted or personal database.
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as conn:
        row = conn.execute("SELECT marker FROM pw_playground_demo").fetchone()
    if row is None or row[0] != DEMO_MARKER:
        raise ValueError("Not a verified playground demo database. Refusing to launch.")


def launch_demo(db_path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("The native desktop demo launcher requires Windows.")
    db_path = db_path.expanduser().resolve()
    _assert_demo(db_path)
    if not desktop.PYTHON.is_file():
        raise RuntimeError("Project .venv is missing. Check your virtual environment.")
    desktop.LOCAL_FILES.mkdir(parents=True, exist_ok=True)
    port = desktop._free_local_port()
    env = os.environ.copy()
    env["WORKSPACE_DB_PATH"] = str(db_path)
    command = [
        str(desktop.PYTHON), "-m", "streamlit", "run", str(desktop.PROJECT / "app.py"),
        "--server.headless=true", "--server.address=127.0.0.1",
        f"--server.port={port}", "--browser.serverAddress=127.0.0.1",
        "--browser.gatherUsageStats=false",
    ]
    print(f"Opening SAFE DEMO desktop window (not your personal database): {db_path}")
    server = None
    with desktop.LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n--- DEMO window: {db_path} ---\n")
        log.flush()
        try:
            server = subprocess.Popen(
                command, cwd=desktop.PROJECT, env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            desktop._wait_until_ready(server, port)
            desktop._open_embedded_window(f"http://127.0.0.1:{port}")
        finally:
            if server is not None and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    launch_demo(args.database)


if __name__ == "__main__":
    main()
