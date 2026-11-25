"""Scheduling diagnostics, honest weekly replay and safe offline .ics import."""

from datetime import date, datetime

import pytest

from workspace.advanced_planner import Slot
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
    record_session,
)
from workspace.calendar_import import (
    MAX_FILE_BYTES,
    eligibility,
    import_selected,
    imported_keys,
    parse_ics,
)
from workspace.life_planning import preview_time_protection
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.repository import create_task, initialize_database
from workspace.schedule_lab import (
    explanation_factors,
    moved_session_summary,
    schedule_health,
    stress_test,
)
from workspace.weekly_replay import weekly_replay

NOW = datetime(2026, 11, 25, 9, 0)
WED = date(2026, 11, 25)
THU = date(2026, 11, 26)
FRI = date(2026, 11, 27)


def ics(*lines):
    content = ("BEGIN:VCALENDAR", "VERSION:2.0", *lines, "END:VCALENDAR")
    return ("\r\n".join(content) + "\r\n").encode()


def event(uid="a", title="Talk", start="20261126T140000", end="20261126T150000"):
    return ["BEGIN:VEVENT", "UID:" + uid, "SUMMARY:" + title,
            "DTSTART:" + start, "DTEND:" + end, "END:VEVENT"]


def prepared(tmp_path):
    db = tmp_path / "project.db"
    initialize_database(db)
    initialize_advanced(db)
    task = create_task(db, TaskDraft("Statistics", "University", FRI, 3, 120))
    step = add_step(db, task.id, "Study chapter", "timed", 120)
    add_window(db, THU, 10 * 60, 14 * 60)
    add_window(db, FRI, 17 * 60, 20 * 60)
    snap = load_snapshot(db)
    accept_revision(db, proposal_from_slots(snap, NOW, (Slot(step, FRI, 17 * 60, 19 * 60),)), NOW)
    return db, task, step


def test_stress_test_is_read_only_and_moves_study(tmp_path):
    db, task, _ = prepared(tmp_path)
    before = load_snapshot(db)
    preview = stress_test(
        before, NOW, FRI, 17 * 60, 21 * 60,
        required_ids=frozenset({task.id}),
    )
    assert load_snapshot(db) == before
    assert preview.feasible
    removed, added = moved_session_summary(preview)
    assert removed and added
    assert any(slot.day == THU for slot in added)
    assert all(not (s.day == FRI and s.start < 21 * 60 and s.end > 17 * 60)
               for s in preview.revision.slots)


def test_stress_does_not_claim_infeasible_is_safe(tmp_path):
    db, task, _ = prepared(tmp_path)
    add_fixed_event(db, "Busy all Thursday", THU, 10 * 60, 14 * 60)
    preview = preview_time_protection(
        load_snapshot(db), NOW, FRI, 17 * 60, 21 * 60,
        required_ids=frozenset({task.id}),
    )
    assert not preview.feasible


def test_schedule_health_counts_unbooked_deadline_and_short_breaks(tmp_path):
    db, _, step = prepared(tmp_path)
    before = schedule_health(load_snapshot(db), NOW)
    assert before.unreserved_deadline_minutes == 0
    assert before.active_deadline_steps == 1
    assert before.insufficient_breaks == 0
    from workspace.advanced_repository import set_timed_remaining
    set_timed_remaining(db, step, 120)
    assert schedule_health(load_snapshot(db), NOW).unreserved_deadline_minutes == 0


def test_explanation_factors_are_grounded(tmp_path):
    db, _, _ = prepared(tmp_path)
    snap = load_snapshot(db)
    reasons = explanation_factors(snap, snap.sessions[0], NOW)
    assert any("Priority: High" in r for r in reasons)
    assert any("deadline" in r.lower() for r in reasons)
    assert any("commitment" in r for r in reasons)


def test_weekly_replay_separates_booked_from_actual(tmp_path):
    db, _, _ = prepared(tmp_path)
    snap = load_snapshot(db)
    session_id = snap.sessions[0].id
    record_session(db, session_id, "done", 90, now=datetime(2026, 11, 27, 20))
    replay = weekly_replay(load_snapshot(db), FRI)
    assert replay.booked_minutes == 120
    assert replay.finished_minutes == 90
    assert replay.missed_minutes == 0
    assert replay.pending_minutes == 0
    assert replay.days[4].finished_minutes == 90
    assert replay.subjects[0].name == "Statistics"


def test_weekly_replay_is_empty_for_another_week(tmp_path):
    db, _, _ = prepared(tmp_path)
    assert weekly_replay(load_snapshot(db), date(2026, 11, 16)).booked_minutes == 0


def test_ics_parses_timed_and_unfolded_text():
    payload = ics(*event(title="SWE\\, part 1"))
    parsed = parse_ics(payload)
    assert parsed.events[0].title == "SWE, part 1"
    assert parsed.events[0].day == THU
    assert parsed.events[0].start == 840
    assert parsed.events[0].end == 900
    assert not parsed.warnings


def test_ics_all_day_and_timezone():
    all_day = ["BEGIN:VEVENT", "UID:holiday", "SUMMARY:Holiday",
               "DTSTART;VALUE=DATE:20261126", "DTEND;VALUE=DATE:20261127", "END:VEVENT"]
    timed = ["BEGIN:VEVENT", "UID:zone", "SUMMARY:Local meeting",
             "DTSTART;TZID=Europe/Rome:20261126T140000",
             "DTEND;TZID=Europe/Rome:20261126T150000", "END:VEVENT"]
    parsed = parse_ics(ics(*all_day, *timed))
    assert len(parsed.events) == 2
    assert parsed.events[0].all_day
    assert parsed.events[0].end == 1440
    assert not parsed.events[1].all_day


def test_ics_recurring_and_multiday_are_reported_not_silently_imported():
    recurring = ["BEGIN:VEVENT", "UID:repeat", "RRULE:FREQ=WEEKLY", "SUMMARY:Class",
                 "DTSTART:20261126T100000", "DTEND:20261126T110000", "END:VEVENT"]
    overnight = event("night", "Late", "20261126T230000", "20261127T010000")
    parsed = parse_ics(ics(*recurring, *overnight))
    assert not parsed.events
    assert len(parsed.warnings) == 2
    assert "Recurring" in parsed.warnings[0]
    assert "Overnight" in parsed.warnings[1]


def test_ics_bad_file_and_event_limits():
    with pytest.raises(ValueError, match="complete iCalendar"):
        parse_ics(b"garbage")
    with pytest.raises(ValueError, match="1.5 MB"):
        parse_ics(b"x" * (MAX_FILE_BYTES + 1))
    parsed = parse_ics(ics(*event(), *event()))
    assert len(parsed.events) == 1
    assert any("duplicate UID" in msg for msg in parsed.warnings)


def test_ics_import_is_atomic_and_tracks_duplicate_uids(tmp_path):
    db, _, _ = prepared(tmp_path)
    original = load_snapshot(db)
    parsed = parse_ics(ics(*event()))
    assert eligibility(original, parsed.events[0], imported_keys(db)) == "Ready"
    assert not imported_keys(db)
    assert import_selected(
        db, parsed.events, frozenset({parsed.events[0].key}), original.fingerprint,
        kind="Lecture",
    ) == 1
    after = load_snapshot(db)
    assert len(after.events) == len(original.events) + 1
    assert after.events[-1].kind == "Lecture"
    assert eligibility(after, parsed.events[0], imported_keys(db)) == "Already imported"
    with pytest.raises(ValueError, match="Already imported"):
        import_selected(db, parsed.events, frozenset({parsed.events[0].key}), after.fingerprint)
    assert load_snapshot(db) == after


def test_ics_import_rejects_stale_preview(tmp_path):
    db, _, _ = prepared(tmp_path)
    snapshot = load_snapshot(db)
    entries = parse_ics(ics(*event())).events
    add_fixed_event(db, "New lecture", THU, 9 * 60, 10 * 60)
    before = load_snapshot(db)
    with pytest.raises(StaleProposalError):
        import_selected(db, entries, frozenset({entries[0].key}), snapshot.fingerprint)
    assert load_snapshot(db) == before


def test_ics_import_rejects_existing_planned_study_conflicts(tmp_path):
    db, _, _ = prepared(tmp_path)
    snapshot = load_snapshot(db)
    entries = parse_ics(ics(*event(start="20261127T173000", end="20261127T180000"))).events
    assert eligibility(snapshot, entries[0], imported_keys(db)) == "Overlaps accepted study"
    with pytest.raises(ValueError, match="accepted study"):
        import_selected(db, entries, frozenset({entries[0].key}), snapshot.fingerprint)
    assert load_snapshot(db) == snapshot


def test_ics_import_selected_overlaps_abort_entire_transaction(tmp_path):
    db, _, _ = prepared(tmp_path)
    snapshot = load_snapshot(db)
    entries = parse_ics(ics(*event("first"), *event(
        "second", "Other", "20261126T143000", "20261126T153000"
    ))).events
    with pytest.raises(ValueError, match="Two selected events overlap"):
        import_selected(db, entries, frozenset(e.key for e in entries), snapshot.fingerprint)
    assert load_snapshot(db) == snapshot


def test_ics_receipt_removed_when_event_is_deleted(tmp_path):
    from workspace.advanced_repository import delete_fixed_event

    db, _, _ = prepared(tmp_path)
    snapshot = load_snapshot(db)
    entries = parse_ics(ics(*event())).events
    import_selected(db, entries, frozenset({entries[0].key}), snapshot.fingerprint)
    event_id = load_snapshot(db).events[-1].id
    delete_fixed_event(db, event_id)
    assert not imported_keys(db)


def test_ics_unsupported_timezone_warns():
    lines = ["BEGIN:VEVENT", "UID:bad", "SUMMARY:Weird",
             "DTSTART;TZID=Not/AZone:20261126T120000",
             "DTEND;TZID=Not/AZone:20261126T130000", "END:VEVENT"]
    result = parse_ics(ics(*lines))
    assert not result.events
    assert "Unrecognized timezone" in result.warnings[0]


def test_opt_in_plan_history_tracks_future_approved_replans_only(tmp_path):
    from workspace.replay_audit import approval_counts, enable_plan_history

    db, _, step = prepared(tmp_path)
    assert approval_counts(db, FRI) is None
    enable_plan_history(db)
    enable_plan_history(db)
    assert approval_counts(db, FRI) == (0, 0)
    before = load_snapshot(db)
    change = proposal_from_slots(before, NOW, (Slot(step, THU, 10 * 60, 12 * 60),))
    accept_revision(db, change, NOW)
    assert approval_counts(db, FRI) == (1, 1)
    back = load_snapshot(db)
    accept_revision(
        db, proposal_from_slots(back, NOW, (Slot(step, FRI, 17 * 60, 19 * 60),)), NOW
    )
    assert approval_counts(db, FRI) == (2, 2)
    assert approval_counts(db, date(2026, 11, 18)) == (0, 0)


def test_plan_history_initial_approval_is_not_a_replan(tmp_path):
    from workspace.replay_audit import approval_counts, enable_plan_history

    db = tmp_path / "initial-plan.db"
    initialize_database(db)
    initialize_advanced(db)
    task = create_task(db, TaskDraft("Essay", "University", FRI, 3, 60))
    step = add_step(db, task.id, "Draft", "timed", 60)
    add_window(db, THU, 10 * 60, 11 * 60)
    enable_plan_history(db)
    snap = load_snapshot(db)
    accept_revision(db, proposal_from_slots(snap, NOW, (Slot(step, THU, 600, 660),)), NOW)
    assert approval_counts(db, FRI) == (1, 0)


def test_demo_uses_isolated_files_and_all_three_features(tmp_path):
    from scripts.create_scheduler_lab_demo import create_demo
    from workspace.replay_audit import approval_counts

    db = tmp_path / "test-demo.db"
    out, ics_path = create_demo(db, NOW)
    snap = load_snapshot(out)
    assert weekly_replay(snap, WED.replace(day=18)).finished_minutes == 55
    assert schedule_health(snap, NOW).active_deadline_steps >= 1
    assert len(parse_ics(ics_path.read_bytes()).events) == 2
    assert approval_counts(out, WED) is None
    with pytest.raises(ValueError, match="already exist"):
        create_demo(db, NOW)
