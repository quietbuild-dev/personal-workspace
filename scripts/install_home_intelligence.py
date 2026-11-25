"""Add two small Home panels without replacing any existing Home implementation.

Run from the project root after extracting the feature ZIP. Idempotent and
strict about structure: unknown versions stop without modifying Home.
"""

from datetime import datetime
from pathlib import Path

IMPORT = "from workspace.views.home_briefing import render_daily_briefing, render_deadline_runway\n"
ANCHOR_IMPORT = "from workspace.views.settings import render_form\n"
ANCHOR_TOP = "    upcoming = sum(\n"
ANCHOR_BOTTOM = "    st.markdown(_weekly_workload(overview, now.date()), unsafe_allow_html=True)\n"


def install(root: Path | None = None) -> bool:
    root = Path.cwd() if root is None else Path(root)
    page = root / "workspace" / "views" / "home.py"
    for file in (
        page,
        root / "workspace" / "home_intelligence.py",
        root / "workspace" / "views" / "home_briefing.py",
    ):
        if not file.is_file():
            raise ValueError(f"Missing {file}. Extract patch into project root first.")
    original = page.read_text(encoding="utf-8")
    if IMPORT in original:
        print("Daily Briefing and Deadline Runway already installed. No change made.")
        return False
    for anchor in (ANCHOR_IMPORT, ANCHOR_TOP, ANCHOR_BOTTOM):
        if original.count(anchor) != 1:
            raise ValueError(
                f"Unrecognized Home version (anchor {anchor.strip()!r}). "
                "No changes made. Upload your current main ZIP for reconciliation."
            )
    revised = original.replace(ANCHOR_IMPORT, ANCHOR_IMPORT + IMPORT, 1)
    revised = revised.replace(
        ANCHOR_TOP, "    render_daily_briefing(overview, now)\n" + ANCHOR_TOP, 1
    )
    revised = revised.replace(
        ANCHOR_BOTTOM,
        ANCHOR_BOTTOM + "    render_deadline_runway(overview, now)\n",
        1,
    )
    backup_dir = root / "data" / "source-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / f"home-before-briefing-runway-{timestamp}.py.bak"
    backup.write_text(original, encoding="utf-8")
    page.write_text(revised, encoding="utf-8")
    print(f"INSTALLED: {page.relative_to(root)}")
    print(f"BACKUP: {backup}")
    print("Only one import and two render calls were added to Home.")
    return True


if __name__ == "__main__":
    install()
