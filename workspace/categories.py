"""Shared task/event categories; additive SQLite schema and stable pastel colors."""

import colorsys
import sqlite3
from contextlib import closing
from pathlib import Path

DEFAULT_CATEGORIES = (
    "Study",
    "Lecture",
    "Social",
    "Exercise",
    "Personal",
    "Errands",
    "Home",
    "Other",
)
DEFAULT_COLORS = {
    "Study": "#BAA9D0",
    "Lecture": "#8FAACB",
    "Social": "#D99EBB",
    "Exercise": "#8AB9A6",
    "Personal": "#C8A99D",
    "Errands": "#E3C69F",
    "Other": "#B5B3C9",
    "Home": "#B5C9B8",
    "Appointment": "#98A6BD",
}
PALETTE = (
    "#B2C9D9",
    "#DDB6C3",
    "#C1B1DC",
    "#ADC8B0",
    "#E0C19E",
    "#A9C7C2",
    "#D5B4A9",
    "#C2BEDC",
    "#C7CEA5",
    "#D0B9CF",
    "#AFCAE0",
    "#D8C3AF",
    "#B5C6D7",
    "#D4B7BD",
    "#BDD2C6",
    "#E4CFB2",
    "#CDBAD5",
    "#BAD3D6",
)


def _connection(db_path: Path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _setup(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS workspace_categories (
        name TEXT PRIMARY KEY COLLATE NOCASE,
        color TEXT NOT NULL UNIQUE CHECK(length(color) = 7)
    )""")
    for name, color in DEFAULT_COLORS.items():
        conn.execute(
            "INSERT OR IGNORE INTO workspace_categories(name,color) VALUES (?,?)",
            (name, color),
        )


def _next_color(used):
    for color in PALETTE:
        if color.lower() not in used:
            return color
    # Distinct deterministic pastels even after the curated palette is exhausted.
    for index in range(1024):
        hue = (index * 0.61803398875) % 1.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.78, 0.32)
        color = "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))
        if color.lower() not in used:
            return color
    raise ValueError("No available category colors remain.")


def _save(conn, name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Choose a category name.")
    name = name.strip()
    if not 1 <= len(name) <= 40 or any(ord(c) < 32 for c in name):
        raise ValueError("Category names must be 1–40 characters.")
    row = conn.execute(
        "SELECT name FROM workspace_categories WHERE name=? COLLATE NOCASE", (name,)
    ).fetchone()
    if row:
        return row[0]
    used = {row[0].lower() for row in conn.execute("SELECT color FROM workspace_categories")}
    color = _next_color(used)
    conn.execute("INSERT INTO workspace_categories(name,color) VALUES (?,?)", (name, color))
    return name


def create_category(db_path: Path, name: str) -> str:
    """Persist a reusable category; repeated names reuse the existing color."""
    from workspace.advanced_repository import initialize_advanced

    initialize_advanced(db_path)
    with closing(_connection(db_path)) as conn, conn:
        _setup(conn)
        saved = _save(conn, name)
        conn.execute("INSERT OR IGNORE INTO task_categories(name) VALUES (?)", (saved,))
        return saved


def list_categories(db_path: Path) -> tuple[str, ...]:
    from workspace.advanced_repository import initialize_advanced

    initialize_advanced(db_path)
    with closing(_connection(db_path)) as conn, conn:
        _setup(conn)
        for (name,) in conn.execute("SELECT name FROM task_categories").fetchall():
            _save(conn, name)
        all_names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM workspace_categories ORDER BY name COLLATE NOCASE"
            )
        ]
    legacy_defaults = {"Appointment", "University", "Work"}
    return DEFAULT_CATEGORIES + tuple(
        name for name in all_names if name not in DEFAULT_CATEGORIES and name not in legacy_defaults
    )


def category_colors(db_path: Path) -> dict[str, str]:
    list_categories(db_path)
    with closing(_connection(db_path)) as conn:
        return dict(conn.execute("SELECT name,color FROM workspace_categories"))
