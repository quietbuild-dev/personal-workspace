"""Seven-day booked-time breakdown for Home, using Calendar's event colors."""

from datetime import date, timedelta

from workspace.advanced_planner import week_bounds

COLORS = {
    "Study": "#BAA9D0",  # lavender
    "Lecture": "#8FAACB",  # blue
    "Social": "#D99EBB",  # dusty rose
    "Exercise": "#8AB9A6",  # sage
    "Personal": "#C8A99D",  # peach
}
ORDER = ("Study", "Lecture", "Social", "Exercise", "Personal")


def workload_breakdown(
    snapshot, today: date, category_colors: dict[str, str] | None = None,
) -> dict[date, dict[str, int]]:
    """Count accepted study blocks and fixed commitments, never draft plans.

    Figures are booked minutes rather than free-capacity estimates. Overlapping
    calendar items may count twice, which is disclosed in the chart caption.
    """
    monday, _ = week_bounds(today)
    categories = category_colors or COLORS
    rows = {
        monday + timedelta(days=offset): {name: 0 for name in categories}
        for offset in range(7)
    }
    for session in snapshot.sessions:
        if session.status == "planned" and session.day in rows:
            rows[session.day]["Study"] += session.end - session.start
    for event in snapshot.events:
        if event.day in rows:
            kind = (
                event.kind if event.kind in categories else
                "Personal" if event.kind == "Appointment" and "Personal" in categories else
                "Other"
            )
            rows[event.day].setdefault(kind, 0)
            rows[event.day][kind] += event.end - event.start
    return rows
