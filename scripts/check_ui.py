"""Optional Streamlit page smoke test. Requires Streamlit in your local .venv.

Runs pages in a disposable database and reports uncaught exceptions. This does
NOT replace manual interaction tests or a real browser walkthrough.
"""

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from workspace.models import TaskDraft
from workspace.repository import create_task, initialize_database, save_availability

PAGES = (
    "workspace/views/dashboard.py",
    "workspace/views/tasks.py",
    "workspace/views/planner.py",
)


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "smoke.db"
        initialize_database(db_path)
        create_task(db_path, TaskDraft("Smoke-check sample", deadline=date.today()))
        save_availability(db_path, {date.today(): 60})
        # The Streamlit scripts import the repository constant at execution time.
        with patch("workspace.repository.DEFAULT_DB_PATH", db_path):
            for filename in PAGES:
                app = AppTest.from_file(filename, default_timeout=20).run()
                if app.exception:
                    errors = [str(item.message) for item in app.exception]
                    raise RuntimeError(f"UI exceptions in {filename}: {errors}")
                print(f"OK: {filename} loaded with sample data")
    print("All three page smoke checks passed. Manual UI checks are still required.")


if __name__ == "__main__":
    main()
