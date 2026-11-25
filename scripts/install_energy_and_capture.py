"""Guarded and repeatable installer for the Energy Today + Smart Capture patch.

Only inserts imports and UI calls; does not replace existing modules or touch SQLite.
"""

import ast
import os
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _once(text: str, old: str, new: str, *, name: str) -> str:
    if new in text:
        return text
    if text.count(old) != 1:
        raise RuntimeError(
            f"{name}: expected insertion point not found exactly once. No files changed."
        )
    return text.replace(old, new, 1)


def planned_changes() -> dict[Path, str]:
    tasks_path = ROOT / "workspace/views/task_board.py"
    week_path = ROOT / "workspace/views/week.py"
    original_tasks = tasks_path.read_text(encoding="utf-8")
    original_week = week_path.read_text(encoding="utf-8")
    tasks = _once(
        original_tasks,
        "from workspace.views.home import _new_task, _suggestion, _task_rows\n",
        "from workspace.views.home import _new_task, _suggestion, _task_rows\n"
        "from workspace.views.smart_capture import render_smart_capture\n",
        name="Tasks import",
    )
    tasks = _once(
        tasks,
        '    with st.expander("+ Add a task", expanded=False):\n',
        '    render_smart_capture(categories, DEFAULT_DB_PATH)\n'
        '    with st.expander("+ Add a task", expanded=False):\n',
        name="Tasks page section",
    )
    week = _once(
        original_week,
        "from workspace.views.goal_preview import choose_goal_preview\n",
        "from workspace.views.energy_today import render_energy_today\n"
        "from workspace.views.goal_preview import choose_goal_preview\n",
        name="Calendar import",
    )
    week = _once(
        week,
        '        render_time_protection(snapshot, now, DEFAULT_DB_PATH)\n',
        '        render_energy_today(snapshot, now, DEFAULT_DB_PATH)\n'
        '        render_time_protection(snapshot, now, DEFAULT_DB_PATH)\n',
        name="Calendar section",
    )
    for name, source in ((str(tasks_path), tasks), (str(week_path), week)):
        ast.parse(source, filename=name)
    required = (
        "workspace/smart_capture.py",
        "workspace/energy_today.py",
        "workspace/views/smart_capture.py",
        "workspace/views/energy_today.py",
        "tests/test_energy_capture.py",
    )
    for rel in required:
        if not (ROOT / rel).is_file():
            raise RuntimeError(f"Missing patch component: {rel}. Re-extract ZIP first.")
    return {tasks_path: tasks, week_path: week}


def main() -> None:
    changes = planned_changes()
    pending = {p: s for p, s in changes.items() if p.read_text(encoding="utf-8") != s}
    if not pending:
        print("ALREADY INSTALLED: No files changed.")
        return
    downloads = Path.home() / "Downloads"
    backups = (
        downloads / "personal-workspace-feature-backups"
        / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    backups.mkdir(parents=True, exist_ok=True)
    for path in pending:
        shutil.copy2(path, backups / path.name)
    applied = []
    try:
        for path, source in pending.items():
            temp = path.with_suffix(path.suffix + ".energy-tmp")
            try:
                temp.write_text(source, encoding="utf-8")
                ast.parse(temp.read_text(encoding="utf-8"), filename=str(temp))
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
            applied.append(path)
    except Exception:
        for path in applied:
            shutil.copy2(backups / path.name, path)
        raise
    for path in pending:
        print(f"UPDATED: {path.relative_to(ROOT)}")
    print(f"Backups: {backups}")
    print("DONE: UI wiring installed. No database, theme, or planner core changed.")


if __name__ == "__main__":
    main()
