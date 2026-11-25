"""Pure read-only before/after schedule previews and task-grouped changes."""

from collections import defaultdict
from datetime import date
from html import escape

from workspace.advanced_planner import Slot, format_time
from workspace.theme import COMPARISON_CSS


def study_label(step) -> str:
    if step is None:
        return "Study"
    if not getattr(step, "task_title", None):
        return step.title
    if step.title == "Focus time":
        return step.task_title
    return f"{step.task_title} / {step.title}"


def schedule_changes(previous: tuple[Slot, ...], proposed: tuple[Slot, ...], steps: dict):
    """Group additions/removals by assignment, ignoring unchanged blocks.

    Pairing is presentation-only; it never claims that a particular block has
    been moved if a task was split into different-length pieces.
    """
    before = set(previous)
    after = set(proposed)
    groups = defaultdict(lambda: {"old": [], "new": []})
    for slot in before - after:
        groups[slot.step_id]["old"].append(slot)
    for slot in after - before:
        groups[slot.step_id]["new"].append(slot)
    result = []
    for step_id, values in groups.items():
        step = steps.get(step_id)
        values["old"].sort(key=lambda s: (s.day, s.start))
        values["new"].sort(key=lambda s: (s.day, s.start))
        result.append((study_label(step), step_id, tuple(values["old"]), tuple(values["new"])))
    return tuple(sorted(result, key=lambda item: (item[0].lower(), item[1])))


def changed_days(previous, proposed):
    """Days actually affected by a scheduling proposal."""
    return tuple(sorted({slot.day for slot in set(previous) ^ set(proposed)}))


def format_slot(slot: Slot) -> str:
    return f"{slot.day:%a %d %b} {format_time(slot.start)}–{format_time(slot.end)}"


def _minute_bounds(day: date, events, previous, proposed):
    selected = [(e.start, e.end) for e in events if e.day == day] + [
        (s.start, s.end) for s in (*previous, *proposed) if s.day == day
    ]
    if not selected:
        return 8 * 60, 20 * 60
    return min(8 * 60, min(s for s, _ in selected)), max(20 * 60, max(e for _, e in selected))


def _column(day, events, slots, other, steps, lower, upper, title):
    scale = 0.60
    height = int((upper - lower) * scale)
    html = [f'<section class="cmp-panel"><h4>{title}</h4><div class="cmp-axis">']
    for minute in range((lower // 60) * 60, upper, 60):
        y = (minute - lower) * scale
        if y < 0:
            continue
        html.append(f'<span class="cmp-tick" style="top:{y:.1f}px">{format_time(minute)}</span>')
    html.append(f'<div class="cmp-canvas" style="height:{height}px">')
    for minute in range((lower // 60 + 1) * 60, upper, 60):
        y = (minute - lower) * scale
        html.append(f'<div class="cmp-line" style="top:{y:.1f}px"></div>')
    for event in events:
        if event.day != day:
            continue
        y, block_height = (event.start - lower) * scale, max(9, (event.end - event.start) * scale)
        event_type = escape(getattr(event, "kind", "Appointment").lower())
        when = f"{format_time(event.start)}–{format_time(event.end)}"
        conflict = any(
            slot.day == day and slot.start < event.end and event.start < slot.end for slot in slots
        )
        lane = "right:50%;" if conflict else ""
        html.append(
            f'<div class="cmp-event cmp-{event_type}" '
            f'style="top:{y:.1f}px;height:{block_height:.1f}px;{lane}" '
            f'title="{escape(event.title, quote=True)} | {when}">'
            f"{escape(event.title)}<small>{when}</small></div>"
        )
    for slot in slots:
        if slot.day != day:
            continue
        y, block_height = (slot.start - lower) * scale, max(9, (slot.end - slot.start) * scale)
        state = "same" if slot in other else "old" if title == "Before" else "new"
        label = study_label(steps.get(slot.step_id))
        when = f"{format_time(slot.start)}–{format_time(slot.end)}"
        conflict = any(
            event.day == day and event.start < slot.end and slot.start < event.end
            for event in events
        )
        lane = "left:50%;" if conflict else ""
        html.append(
            f'<div class="cmp-event cmp-study cmp-{state}" '
            f'style="top:{y:.1f}px;height:{block_height:.1f}px;{lane}" '
            f'title="{escape(label, quote=True)} | {when}">'
            f"{escape(label)}<small>{when}</small></div>"
        )
    html.append("</div></div></section>")
    return "".join(html)


def before_after_html(day, events, previous, proposed, steps) -> str:
    """Render both plans on the same vertical time scale with no external links."""
    if not isinstance(day, date):
        raise ValueError("Select a calendar date.")
    lower, upper = _minute_bounds(day, events, previous, proposed)
    style = """<style>
    .cmp-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;color:#e3ebe5}
    .cmp-panel{min-width:0;overflow:hidden;border:1px solid #36433c;border-radius:10px;
    background:#171d1b}
    .cmp-panel h4{font-size:14px;letter-spacing:.01em;padding:11px 15px;margin:0;
    border-bottom:1px solid #36433c}
    .cmp-axis{position:relative;padding-left:45px;}
    .cmp-tick{position:absolute;left:5px;font-size:10px;color:#9eaea4;transform:translateY(-50%)}
    .cmp-canvas{position:relative;border-left:1px solid #425047;margin:0 6px 8px 0}
    .cmp-line{position:absolute;left:0;right:0;border-top:1px solid #2d3632}
    .cmp-event{position:absolute;left:5px;right:5px;border-radius:5px;overflow:hidden;
      z-index:1;box-sizing:border-box;padding:3px 5px;font-size:11px;font-weight:600;
      line-height:1.2;overflow-wrap:anywhere;border-left:3px solid #bdcfbe}
    .cmp-event small{display:block;font-weight:400;font-size:10px;opacity:.85}
    .cmp-study{background:#506c56;color:#f4faf5;border-color:#aac9ae}
    .cmp-old{background:#3f4a48;color:#e5ebe6;border:1px dashed #9caaa1;
    border-left:3px solid #b3c1b6}
    .cmp-new{background:#668b70;color:#fff;border-left:3px solid #c2e6c9}
    .cmp-same{opacity:.55}
    .cmp-lecture{background:#425e76;color:#eef6ff;border-color:#95bbdf}
    .cmp-social{background:#744F65;color:#fff5f9;border-color:#D99EBB}
    .cmp-exercise{background:#48695d;color:#edfff2;border-color:#90cbb2}
    .cmp-appointment,.cmp-other,.cmp-personal{background:#5d5b58;color:#fff;border-color:#a6a19a}
    @media(max-width:560px){.cmp-layout{gap:5px}.cmp-event{font-size:9px;padding:2px}
    .cmp-event small{display:none}}
    </style>"""
    return (
        style
        + COMPARISON_CSS
        + f'<div class="cmp-layout" aria-label="Before and after calendar for {day:%d %B}">'
        + _column(day, events, previous, proposed, steps, lower, upper, "Before")
        + _column(day, events, proposed, previous, steps, lower, upper, "After")
        + "</div>"
    )
