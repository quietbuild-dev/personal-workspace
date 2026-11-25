"""Guarded, repeatable installer: Schedule Lab + Weekly Replay + .ics Import.

Only adds imports and render calls to existing Home and Calendar pages, and
appends tzdata to requirements for Windows IANA timezone compatibility.
Backups go to Downloads; no database files or planner core modules are edited.
"""

import ast
import os
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _once(source: str, old: str, new: str, label: str) -> str:
    if new in source:
        return source
    if source.count(old) != 1:
        raise RuntimeError(f"{label}: expected anchor missing or ambiguous. No files changed.")
    return source.replace(old, new, 1)


def planned_changes() -> dict[Path, str]:
    home_path = ROOT / "workspace/views/home.py"
    week_path = ROOT / "workspace/views/week.py"
    requirements = ROOT / "requirements.txt"
    for rel in (
        "workspace/schedule_lab.py",
        "workspace/views/schedule_lab.py",
        "workspace/weekly_replay.py",
        "workspace/replay_audit.py",
        "workspace/views/weekly_replay.py",
        "workspace/calendar_import.py",
        "workspace/views/calendar_import.py",
        "tests/test_schedule_lab_replay_import.py",
        "scripts/create_scheduler_lab_demo.py",
    ):
        path = ROOT / rel
        if not path.is_file():
            raise RuntimeError(f"Missing patch component: {rel}. Extract the ZIP again.")
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    home = home_path.read_text(encoding="utf-8")
    week = week_path.read_text(encoding="utf-8")
    if "from workspace.views.weekly_replay import render_weekly_replay\n" not in home:
        home = _once(
            home,
            "from workspace.views.settings import render_form\n",
            "from workspace.views.settings import render_form\n"
            "from workspace.views.weekly_replay import render_weekly_replay\n",
            "Home replay import",
        )
    home = _once(
        home,
        "    render_deadline_runway(overview, now)\n",
        "    render_deadline_runway(overview, now)\n"
        "    render_weekly_replay(overview.advanced, now, DEFAULT_DB_PATH)\n",
        "Home replay section",
    )
    week = _once(
        week,
        "from workspace.views.energy_today import render_energy_today\n",
        "from workspace.views.calendar_import import render_calendar_import\n"
        "from workspace.views.energy_today import render_energy_today\n",
        "Calendar import module",
    )
    week = _once(
        week,
        "from workspace.views.weekly_calendar import _agenda, calendar_html, study_label\n",
        "from workspace.views.schedule_lab import render_schedule_lab\n"
        "from workspace.views.weekly_calendar import _agenda, calendar_html, study_label\n",
        "Calendar lab module",
    )
    week = _once(
        week,
        "    if selected_week_start == monday:\n"
        "        render_energy_today(snapshot, now, DEFAULT_DB_PATH)\n",
        "    render_calendar_import(snapshot, DEFAULT_DB_PATH)\n"
        "    if selected_week_start == monday:\n"
        "        render_schedule_lab(snapshot, now, DEFAULT_DB_PATH)\n"
        "        render_energy_today(snapshot, now, DEFAULT_DB_PATH)\n",
        "Calendar import and lab sections",
    )
    for filename, source in ((str(home_path), home), (str(week_path), week)):
        ast.parse(source, filename=filename)
    req = requirements.read_text(encoding="utf-8")
    if not any(line.strip().lower().startswith("tzdata") for line in req.splitlines()):
        req = req.rstrip("\r\n") + "\ntzdata>=2025.2,<2028\n"
    return {home_path: home, week_path: week, requirements: req}


def main() -> None:
    planned = planned_changes()
    pending = {path: source for path, source in planned.items()
               if path.read_text(encoding="utf-8") != source}
    if not pending:
        print("ALREADY INSTALLED: No files changed.")
        return
    downloads = Path.home() / "Downloads"
    backups = downloads / "personal-workspace-feature-backups" / (
        "scheduler-replay-import-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )
    backups.mkdir(parents=True, exist_ok=False)
    for path in pending:
        shutil.copy2(path, backups / path.name)
    applied = []
    try:
        for path, source in pending.items():
            temp = path.with_suffix(path.suffix + ".triple-tmp")
            try:
                temp.write_text(source, encoding="utf-8")
                if path.suffix == ".py":
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
    print("DONE: Three panels installed. No database or optimizer core modified.")
    print("NEXT: Install dependencies, run Ruff and pytest, then inspect the app.")


if __name__ == "__main__":
    main()
