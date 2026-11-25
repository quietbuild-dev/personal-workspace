"""Safely attach Make Room for Life to the existing Calendar navigation.

Run from the repository root after extracting the feature ZIP. No source file
is overwritten: week.py gets only three small, verified insertions.
"""

from datetime import datetime
from pathlib import Path


def install() -> None:
    root = Path.cwd()
    week = root / "workspace" / "views" / "week.py"
    life_module = root / "workspace" / "life_planning.py"
    life_view = root / "workspace" / "views" / "life_time.py"
    for source in (week, life_module, life_view):
        if not source.is_file():
            raise SystemExit(f"Missing {source}. Extract the ZIP into the repository root.")
    source = week.read_text(encoding="utf-8")
    identifier = "from workspace.views.life_time import render_time_protection\n"
    if identifier in source:
        print("Make Room for Life is already integrated. No changes made.")
        return
    expected = (
        '    undo_last_plan,\n',
        'from workspace.views.goal_preview import choose_goal_preview\n',
        'from workspace.deadline_guarantees import check_required_coverage\n',
        '    if selected_week_start == monday:\n',
    )
    for anchor in expected:
        if source.count(anchor) != 1:
            raise SystemExit(
                f"Calendar structure differs from the supported source (anchor {anchor!r}). "
                "No changes made. Upload the latest main source ZIP for reconciliation."
            )
    updated = source.replace('    undo_last_plan,\n', '', 1)
    import_anchor = 'from workspace.views.goal_preview import choose_goal_preview\n'
    updated = updated.replace(import_anchor, import_anchor + identifier, 1)
    repo_anchor = 'from workspace.deadline_guarantees import check_required_coverage\n'
    updated = updated.replace(
        repo_anchor,
        repo_anchor
        + 'from workspace.life_planning import undo_last_plan_with_protection as undo_last_plan\n',
        1,
    )
    updated = updated.replace(
        '    if selected_week_start == monday:\n',
        '    if selected_week_start == monday:\n'
        '        render_time_protection(snapshot, now, DEFAULT_DB_PATH)\n',
        1,
    )
    backup_dir = root / "data" / "source-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / f"week-before-make-room-{stamp}.py.bak"
    backup.write_text(source, encoding="utf-8")
    week.write_text(updated, encoding="utf-8")
    print(f"INSTALLED: {week.relative_to(root)}")
    print(f"BACKUP: {backup}")
    print("Calendar source preserved; only the panel and Undo integration were added.")


if __name__ == "__main__":
    install()
