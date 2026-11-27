"""Finite, deterministic daily/weekly/monthly/yearly event series.

Series are materialized as ordinary fixed events for compatibility with the
existing scheduler, export, import and views. Each occurrence is editable on
its own; removing one does not remove the other occurrences.
"""

import calendar
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from workspace.advanced_repository import _connect, _event_category_choice, initialize_advanced

FREQUENCIES = ("Never", "Daily", "Weekly", "Monthly", "Yearly")


def occurrences(start: date, until: date, frequency: str) -> tuple[date, ...]:
    if type(start) is not date or type(until) is not date or not start <= until:
        raise ValueError("Repeat end date must be on or after the first event.")
    if (until - start).days > 731:
        raise ValueError("Limit recurring event series to two years.")
    if frequency not in FREQUENCIES:
        raise ValueError("Choose a supported repeat interval.")
    if frequency == "Never":
        return (start,)
    result = []
    current = start
    index = 0
    while current <= until:
        result.append(current)
        if len(result) >= 732:
            break
        index += 1
        if frequency == "Daily":
            current = start + timedelta(days=index)
        elif frequency == "Weekly":
            current = start + timedelta(weeks=index)
        else:
            month_index = start.year * 12 + start.month - 1
            month_index += index * (12 if frequency == "Yearly" else 1)
            year, month_zero = divmod(month_index, 12)
            month = month_zero + 1
            day = min(start.day, calendar.monthrange(year, month)[1])
            current = date(year, month, day)
    return tuple(result)


def _setup(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS recurring_event_series ("
        "id INTEGER PRIMARY KEY, frequency TEXT NOT NULL,"
        "first_day TEXT NOT NULL, until_day TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS recurring_event_instances ("
        "event_id INTEGER PRIMARY KEY REFERENCES fixed_events(id) ON DELETE CASCADE,"
        "series_id INTEGER NOT NULL REFERENCES recurring_event_series(id) ON DELETE CASCADE)"
    )


def add_recurring_event(
    db_path: Path,
    title: str,
    day: date,
    start: int,
    end: int,
    kind: str,
    frequency: str,
    until: date,
    notes: str = "",
) -> tuple[int, ...]:
    from workspace.advanced_repository import _valid_event_notes, _valid_interval, _valid_title

    notes = _valid_event_notes(notes)

    title = _valid_title(title)
    _valid_interval(day, start, end)
    days = occurrences(day, until, frequency)
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            _setup(conn)
            stored, override = _event_category_choice(conn, kind)
            series_id = None
            if frequency != "Never":
                series_id = conn.execute(
                    "INSERT INTO recurring_event_series(frequency,first_day,until_day) "
                    "VALUES (?,?,?)",
                    (frequency, day.isoformat(), until.isoformat()),
                ).lastrowid
            ids = []
            for current in days:
                event_id = conn.execute(
                    "INSERT INTO fixed_events(title,day,start_minute,end_minute) VALUES (?,?,?,?)",
                    (title, current.isoformat(), start, end),
                ).lastrowid
                conn.execute(
                    "INSERT INTO fixed_event_kinds(event_id,kind) VALUES (?,?)",
                    (event_id, stored),
                )
                if override:
                    conn.execute(
                        "INSERT INTO event_category_overrides(event_id,category) VALUES (?,?)",
                        (event_id, override),
                    )
                if notes:
                    conn.execute(
                        "INSERT INTO fixed_event_notes(event_id,notes) VALUES (?,?)",
                        (event_id, notes),
                    )
                if series_id is not None:
                    conn.execute(
                        "INSERT INTO recurring_event_instances(event_id,series_id) VALUES (?,?)",
                        (event_id, series_id),
                    )
                ids.append(event_id)
            conn.commit()
            return tuple(ids)
        except Exception:
            conn.rollback()
            raise


def series_info(db_path: Path, event_id: int) -> tuple[int, str, int] | None:
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        _setup(conn)
        row = conn.execute(
            "SELECT s.id,s.frequency,(SELECT COUNT(*) FROM recurring_event_instances "
            "WHERE series_id=s.id) FROM recurring_event_series s "
            "JOIN recurring_event_instances i ON i.series_id=s.id "
            "WHERE i.event_id=?",
            (event_id,),
        ).fetchone()
        conn.commit()
        return tuple(row) if row else None


def delete_recurring_series(db_path: Path, event_id: int) -> int:
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            _setup(conn)
            row = conn.execute(
                "SELECT series_id FROM recurring_event_instances WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if not row:
                raise ValueError("This event is not part of a recurring series.")
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT event_id FROM recurring_event_instances WHERE series_id=?", row
                )
            ]
            conn.executemany("DELETE FROM fixed_events WHERE id=?", [(i,) for i in ids])
            conn.execute("DELETE FROM recurring_event_series WHERE id=?", row)
            conn.commit()
            return len(ids)
        except Exception:
            conn.rollback()
            raise
