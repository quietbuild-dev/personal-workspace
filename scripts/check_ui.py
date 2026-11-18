"""Smoke-test registered Streamlit pages using the actual multipage entrypoint.

Runs Home and Calendar in a temporary SQLite database. This is a startup test,
not a replacement for exercising forms and session actions in a real browser.
"""

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from workspace.models import TaskDraft
from workspace.repository import create_task, initialize_database, save_availability

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = PROJECT_ROOT / "app.py"
CALENDAR_PAGE = "workspace/views/week.py"


def _assert_no_exceptions(app: AppTest, page: str) -> None:
    if app.exception:
        errors = [str(item.message) for item in app.exception]
        raise RuntimeError(f"UI exceptions in {page}: {errors}")
    print(f"OK: {page} loaded with sample data")


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "smoke.db"
        initialize_database(db_path)
        create_task(db_path, TaskDraft("Smoke-check sample", deadline=date.today()))
        save_availability(db_path, {date.today(): 60})

        # Register pages via st.navigation in the real app entrypoint.
        # The app's repository imports are resolved while this patch is active.
        with patch("workspace.repository.DEFAULT_DB_PATH", db_path):
            app = AppTest.from_file(str(ENTRYPOINT), default_timeout=20).run()
            _assert_no_exceptions(app, "Home")

            app.switch_page(CALENDAR_PAGE).run()
            _assert_no_exceptions(app, "Calendar")

    print("Both main pages loaded. Manual UI interaction checks are still required.")


if __name__ == "__main__":
    main()
