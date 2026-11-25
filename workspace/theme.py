"""Smoky Lavender presentation system.

Keep colors and reusable visual elements here. This module does not read or
change application state; the planner and repository remain independent of UI.
"""

from html import escape

BACKGROUND = "#14141A"
SURFACE = "#22222B"
ELEVATED = "#2C2A36"
ACCENT = "#BAA9D0"
TEXT = "#F1EEF5"
MUTED = "#A8A4B3"
BORDER = "#393640"

PRIORITY = {
    3: ("High", "#E0A0A5"),
    2: ("Medium", "#D9BD94"),
    1: ("Low", "#A8B1BB"),
}

# Used by both saved calendar blocks and read-only plan comparisons.
# These colors identify a type of event, never its priority.
EVENT_COLORS = {
    "study": ("#655875", "#DDC5F0", "#FBF7FF"),
    "lecture": ("#455A75", "#8FAACB", "#F4F8FF"),
    "social": ("#744F65", "#D99EBB", "#FFF5F9"),
    "exercise": ("#3C5D55", "#8AB9A6", "#F1FFF8"),
    "personal": ("#66564E", "#C8A99D", "#FFF7F4"),
    "appointment": ("#4A5667", "#98A6BD", "#F2F4FA"),
    "other": ("#4F5260", "#A6A8B7", "#F6F5FA"),
}

GLOBAL_CSS = """
<style>
:root {
    --pw-bg:#14141A; --pw-card:#22222B; --pw-elevated:#2C2A36;
    --pw-accent:#BAA9D0; --pw-text:#F1EEF5; --pw-muted:#A8A4B3;
    --pw-border:#393640; --pw-high:#E0A0A5; --pw-mid:#D9BD94;
    --pw-low:#A8B1BB;
}
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"] {background:#14141A!important;color:#F1EEF5;}
[data-testid="stHeader"] {background:rgba(20,20,26,.97)!important;
    border-bottom:1px solid #393640;}
[data-testid="stMainBlockContainer"], .block-container {
    max-width:1320px!important; padding-top:2rem!important;
    padding-bottom:4rem!important;
}
[data-testid="stSidebar"] {background:#1B1A23!important;
    border-right:1px solid #393640;}
[data-testid="stSidebar"] * {color:#F1EEF5;}
[data-testid="stTopNav"] {background:#14141A!important;}
[data-testid="stTopNav"] a, [data-testid="stTopNav"] button {
    color:#A8A4B3!important;font-weight:580;letter-spacing:.01em;
}
[data-testid="stTopNav"] a:hover, [data-testid="stTopNav"] button:hover {
    color:#F1EEF5!important;
}
/* Keep Settings apart from core pages in the native top navigation.
   CSS only: no replacement of Streamlit's routing or keyboard navigation. */
[data-testid="stTopNav"] li:has(a[href*="settings"]),
[data-testid="stTopNav"] [role="listitem"]:has(a[href*="settings"]) {
    margin-left:auto!important;
}

/* Align Settings and the following Advanced dropdown to the header's right.
   Streamlit top navigation uses rc-overflow-item divs, not li elements. */
@media (min-width: 960px) {
    .stAppHeader [data-testid="stTopNav"],
    .stAppHeader nav:has(.rc-overflow) {
        flex: 1 1 auto !important;
        width: 100% !important;
        max-width: none !important;
        min-width: 0 !important;
    }
    .stAppHeader .rc-overflow {
        width: 100% !important;
        flex: 1 1 auto !important;
        display: flex !important;
        min-width: 0 !important;
    }
    .stAppHeader .rc-overflow > .rc-overflow-item:has(a[href*="settings"]),
    .stAppHeader [data-testid="stTopNav"] .rc-overflow > .rc-overflow-item:has(a[href*="settings"]),
    .stAppHeader .rc-overflow > [role="listitem"]:has(a[href*="settings"]),
    /* Fallback for Streamlit builds that wrap navigation labels differently. */
    .stAppHeader .rc-overflow > .rc-overflow-item:nth-child(4) {
        margin-left: auto !important;
    }
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-color:#393640!important;border-radius:17px!important;
    background:#22222B!important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-color:#393640!important;border-radius:17px!important;
}
[data-testid="stExpander"] {border:1px solid #393640!important;
    background:#22222B!important;border-radius:15px!important;overflow:hidden;}
[data-testid="stExpander"] summary {font-weight:600;color:#F1EEF5;}
[data-testid="stPopover"] button, [data-testid="stExpander"] button {
    border-color:#393640;
}
.stButton > button, .stFormSubmitButton > button, .stPageLink a,
[data-testid="stPopover"] > button {
    border-radius:11px!important;min-height:40px;
    border:1px solid #514A60!important;
    background:#2C2A36!important;color:#F1EEF5!important;
    font-weight:620!important;transition:background .16s,transform .16s,border-color .16s;
}
.stButton > button:hover, .stFormSubmitButton > button:hover,
.stPageLink a:hover, [data-testid="stPopover"] > button:hover {
    border-color:#BAA9D0!important;background:#373140!important;
    transform:translateY(-1px);
}
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background:#BAA9D0!important;color:#201B28!important;
    border-color:#BAA9D0!important;
}
[data-testid="stPageLink"] a {background:#BAA9D0!important;
    color:#201B28!important;border-color:#BAA9D0!important;}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background:#D2C1E5!important;
}
.stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible,
.stPageLink a:focus-visible, input:focus-visible, textarea:focus-visible {
    outline:2px solid #BAA9D0!important;outline-offset:2px;
}
[data-baseweb="input"] > div, [data-baseweb="select"] > div,
[data-baseweb="textarea"] > div, [data-testid="stDateInput"] input,
[data-testid="stNumberInput"] input {
    border:1px solid #514A60!important;border-radius:10px!important;
    background:#2C2A36!important;color:#F1EEF5!important;
    min-height:41px;font-size:.95rem!important;
}
[data-baseweb="input"] > div:focus-within,
[data-baseweb="select"] > div:focus-within {
    border-color:#BAA9D0!important;
}
/* Each Rescue strategy is one keyboard-accessible clickable surface. */
.st-key-pw_strategy_0 button, .st-key-pw_strategy_1 button,
.st-key-pw_strategy_selected_0 button, .st-key-pw_strategy_selected_1 button {
    width:100%!important;min-height:107px!important;text-align:left!important;
    justify-content:flex-start!important;align-items:center!important;
    background:#22222B!important;border:1px solid #514A60!important;
    padding:18px 20px!important;white-space:pre-line!important;
    font-size:.9rem!important;line-height:1.6!important;
}
.st-key-pw_strategy_0 button p, .st-key-pw_strategy_1 button p,
.st-key-pw_strategy_selected_0 button p,
.st-key-pw_strategy_selected_1 button p {
    text-align:left!important;white-space:pre-line!important;
}
.st-key-pw_strategy_selected_0 button,
.st-key-pw_strategy_selected_1 button {
    background:#302A3A!important;border:2px solid #BAA9D0!important;
}
.st-key-pw_strategy_0 button:hover, .st-key-pw_strategy_1 button:hover,
.st-key-pw_strategy_selected_0 button:hover,
.st-key-pw_strategy_selected_1 button:hover {
    border-color:#BAA9D0!important;background:#373140!important;
}
[data-testid="stSegmentedControl"] {background:#22222B;border-radius:12px;}
[data-testid="stMarkdownContainer"] h1 {font-size:2.05rem;letter-spacing:-.045em;}
[data-testid="stMarkdownContainer"] h2 {font-size:1.52rem;letter-spacing:-.03em;}
[data-testid="stMarkdownContainer"] h3 {font-size:1.17rem;letter-spacing:-.018em;}
[data-testid="stCaptionContainer"], small {color:#A8A4B3;}
hr {border-color:#393640!important;}
.pw-hero {padding:12px 0 12px;}
.pw-eyebrow {font-size:.73rem;letter-spacing:.15em;text-transform:uppercase;
    font-weight:700;color:#BAA9D0;margin-bottom:11px;}
.pw-hero h1 {font-size:clamp(1.9rem,3.2vw,2.85rem);line-height:1.12;
    letter-spacing:-.055em;color:#F1EEF5;margin:0 0 11px;font-weight:750;}
.pw-hero p {margin:0;color:#A8A4B3;font-size:.98rem;line-height:1.6;}
.pw-stat {min-height:130px;background:#22222B;border:1px solid #393640;
    border-radius:16px;padding:20px 22px;margin:6px 0 15px;
    box-shadow:0 11px 28px rgba(0,0,0,.11);}
.pw-stat-label {color:#A8A4B3;font-size:.78rem;font-weight:620;
    letter-spacing:.018em;}
.pw-stat-value {font-size:2.05rem;font-weight:760;letter-spacing:-.045em;
    color:#F1EEF5;margin-top:9px;line-height:1.2;}
.pw-stat-note {color:#A8A4B3;font-size:.76rem;margin-top:7px;}
.pw-card {background:#22222B;border:1px solid #393640;
    border-radius:16px;padding:20px 22px;margin-bottom:16px;}
.pw-card h3 {color:#F1EEF5;font-size:1.14rem;margin:0 0 5px;
    letter-spacing:-.025em;}
.pw-section-note {font-size:.83rem;color:#A8A4B3;margin:0 0 18px;}
.pw-task-preview {padding:13px 0;border-bottom:1px solid #393640;}
.pw-task-preview:last-child {border-bottom:0;padding-bottom:3px;}
.pw-task-title {color:#F1EEF5;font-size:.95rem;font-weight:650;
    line-height:1.4;overflow-wrap:anywhere;}
.pw-task-meta {color:#A8A4B3;font-size:.77rem;line-height:1.5;margin-top:6px;}
.pw-task-head {display:flex;justify-content:space-between;gap:12px;align-items:center;}
.pw-priority {display:inline-block;white-space:nowrap;font-size:.69rem;
    border:1px solid currentColor;border-radius:25px;padding:3px 10px;
    font-weight:720;letter-spacing:.025em;}
.pw-priority--high {color:#E0A0A5;background:rgba(224,160,165,.08);}
.pw-priority--medium {color:#D9BD94;background:rgba(217,189,148,.08);}
.pw-priority--low {color:#A8B1BB;background:rgba(168,177,187,.08);}
.pw-progress {height:5px;border-radius:10px;background:#393640;
    overflow:hidden;margin-top:10px;}
.pw-progress > span {display:block;height:100%;border-radius:10px;
    background:#BAA9D0;}
/* Logged work is green; it is not the same as reserved calendar time. */
.pw-task-completion {height:8px;border-radius:50px;background:#353842;
    overflow:hidden;margin-top:10px;}
.pw-task-completion > span {display:block;height:100%;border-radius:50px;
    background:linear-gradient(90deg,#55AA80,#89D7A7);}
.pw-task-completion-caption {color:#A8C9B6;font-size:.73rem;
    margin-top:5px;letter-spacing:.01em;}
/* Hide Streamlit's non-interactive heading anchor links in the desktop UI. */
[data-testid="stHeaderActionElements"] {display:none!important;}

/* Compact category label: appears on hover, disappears on mouseout.
   Keyboard users can also see it when focusing a segment. */
.pw-workbar-track {position:relative;overflow:visible!important;}
.pw-workbar-track:has(.pw-workbar-segment:hover),
.pw-workbar-track:has(.pw-workbar-segment:focus-visible) {z-index:30;}
.pw-workbar-segment {position:relative;cursor:help;}
.pw-workbar-segment:first-child {border-radius:0 0 7px 7px;}
.pw-workbar-segment:hover,.pw-workbar-segment:focus-visible {
    z-index:35;filter:brightness(1.08);
}
.pw-workbar-segment:focus-visible {outline:2px solid #F1EEF5;outline-offset:1px;}
.pw-workbar-tooltip {
    display:none;position:absolute;z-index:40;left:50%;bottom:calc(100% + 5px);
    transform:translateX(-50%);padding:4px 7px;border-radius:7px;
    background:#373140;color:#F1EEF5;border:1px solid #514A60;
    box-shadow:0 5px 12px rgba(0,0,0,.24);font-size:.70rem;
    line-height:1.2;white-space:nowrap;pointer-events:none;
}
.pw-workbar-segment:hover > .pw-workbar-tooltip,
.pw-workbar-segment:focus-visible > .pw-workbar-tooltip {display:block;}
.pw-workday:first-child .pw-workbar-tooltip {left:0;transform:none;}
.pw-workday:last-child .pw-workbar-tooltip {left:auto;right:0;transform:none;}

.pw-workload {display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:9px;
    align-items:end;margin-top:19px;}
.pw-workday {min-width:0;text-align:center;}
.pw-workbar-track {height:92px;max-width:76px;margin-left:auto;margin-right:auto;
    background:#2C2A36;border-radius:9px;
    display:flex;align-items:flex-end;overflow:hidden;margin-bottom:8px;}
.pw-workbar-track {flex-direction:column;align-items:stretch;justify-content:flex-end;}
.pw-workbar-segment {width:100%;flex:none;min-height:1px;}
.pw-workbar-segment:last-child {border-radius:7px 7px 0 0;}
.pw-workbar-fill {width:100%;border-radius:6px 6px 0 0;
    background:linear-gradient(180deg,#BAA9D0,#847296);}
.pw-workday-label {font-size:.7rem;font-weight:650;color:#A8A4B3;}
.pw-workday-value {font-size:.72rem;color:#A8A4B3;margin-top:6px;
    white-space:normal;line-height:1.25;}
.pw-insight {padding:16px 19px;background:#26232F;
    border:1px solid #51485F;border-left:3px solid #BAA9D0;
    border-radius:13px;margin:10px 0 13px;}
.pw-insight strong {display:block;color:#F1EEF5;font-size:.92rem;margin-bottom:4px;}
.pw-insight p {color:#BDB7C9;font-size:.83rem;line-height:1.55;margin:0;}
.pw-review-stats {display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 16px;}
.pw-review-stat {background:#2C2A36;border:1px solid #393640;
    padding:10px 14px;border-radius:10px;flex:1;min-width:120px;}
.pw-review-stat strong {display:block;color:#F1EEF5;font-size:1.07rem;}
.pw-review-stat span {display:block;color:#A8A4B3;font-size:.72rem;margin-top:3px;}
.pw-legend {display:flex;gap:15px;flex-wrap:wrap;margin:10px 0 3px;
    font-size:.77rem;color:#A8A4B3;}
.pw-legend i {width:9px;height:9px;display:inline-block;
    margin-right:6px;border-radius:3px;}
@media(max-width:780px) {
  .pw-hero h1 {font-size:1.85rem;}
  .pw-stat {min-height:112px;padding:15px;}
  .pw-stat-value {font-size:1.75rem;}
  [data-testid="stMainBlockContainer"],.block-container {padding-top:1.15rem!important;}
}
@media(prefers-reduced-motion:reduce) {
  .stButton > button,.stFormSubmitButton > button,.stPageLink a {transition:none;}
}
</style>
"""

CALENDAR_CSS = """
<style>
.wp-scroll {background:#1A1921!important;border-color:#393640!important;
    border-radius:15px!important;box-shadow:0 12px 30px rgba(0,0,0,.10);}
.wp-calendar {color:#F1EEF5!important;}
.wp-day-name {background:#22222B;color:#BEB7CA!important;
    border-color:#393640!important;letter-spacing:.02em;font-size:12px;}
.wp-gutter {background:#22222B;border-color:#393640!important;}
.wp-today {color:#F1EEF5!important;background:#393144!important;
    box-shadow:inset 0 -2px 0 #BAA9D0;}
.wp-clock {color:#A8A4B3!important;}
.wp-day-column {border-color:#393640!important;
    background-image:linear-gradient(to bottom,#34303D 1px,transparent 1px)!important;}
.wp-scroll .wp-calendar .wp-block {border-radius:8px!important;
    box-shadow:0 1px 5px rgba(0,0,0,.18);padding:6px 7px!important;
    font-size:11.5px!important;transition:filter .15s,box-shadow .15s;}
.wp-scroll .wp-calendar .wp-block:hover {filter:brightness(1.18);
    box-shadow:0 3px 10px rgba(0,0,0,.24);}
.wp-scroll .wp-calendar .wp-study,
.wp-scroll .wp-calendar a.wp-study:link,
.wp-scroll .wp-calendar a.wp-study:visited {
    background:#655875!important;border-color:#DDC5F0!important;color:#FBF7FF!important;}
.wp-scroll .wp-calendar .wp-lecture,
.wp-scroll .wp-calendar a.wp-lecture:link,
.wp-scroll .wp-calendar a.wp-lecture:visited {
    background:#455A75!important;border-color:#8FAACB!important;color:#F4F8FF!important;}
.wp-scroll .wp-calendar .wp-social,
.wp-scroll .wp-calendar a.wp-social:link,
.wp-scroll .wp-calendar a.wp-social:visited {
    background:#744F65!important;border-color:#D99EBB!important;color:#FFF5F9!important;}
.wp-scroll .wp-calendar .wp-exercise,
.wp-scroll .wp-calendar a.wp-exercise:link {
    background:#3C5D55!important;border-color:#8AB9A6!important;color:#F1FFF8!important;}
.wp-scroll .wp-calendar .wp-personal,
.wp-scroll .wp-calendar a.wp-personal:link {
    background:#66564E!important;border-color:#C8A99D!important;color:#FFF7F4!important;}
.wp-scroll .wp-calendar .wp-appointment,
.wp-scroll .wp-calendar a.wp-appointment:link {
    background:#4A5667!important;border-color:#98A6BD!important;color:#F2F4FA!important;}
.wp-scroll .wp-calendar .wp-other,
.wp-scroll .wp-calendar a.wp-other:link {
    background:#4F5260!important;border-color:#A6A8B7!important;color:#F6F5FA!important;}
.wp-scroll .wp-calendar .wp-block-title {font-weight:700!important;
    letter-spacing:-.01em;color:inherit!important;}
.wp-scroll .wp-calendar .wp-next {color:inherit!important;opacity:.82;}
.wp-scroll .wp-calendar .wp-high {color:#4D232A!important;
    background:#F2CFD4!important;border-color:#E0A0A5!important;}
.wp-scroll .wp-calendar .wp-medium {color:#49371D!important;
    background:#F0DFC0!important;border-color:#D9BD94!important;}
.wp-scroll .wp-calendar .wp-low {color:#263038!important;
    background:#D3DDE6!important;border-color:#A8B1BB!important;}
</style>
"""

COMPARISON_CSS = """
<style>
.cmp-layout {color:#F1EEF5!important;gap:14px!important;}
.cmp-panel {background:#22222B!important;border-color:#393640!important;
    border-radius:14px!important;}
.cmp-panel h4 {border-color:#393640!important;color:#F1EEF5!important;
    background:#2C2A36;font-size:.92rem!important;}
.cmp-tick {color:#A8A4B3!important;}
.cmp-canvas {border-color:#514A60!important;}
.cmp-line {border-color:#393640!important;}
.cmp-event {border-radius:7px!important;}
.cmp-study {background:#655875!important;color:#FBF7FF!important;
    border-color:#DDC5F0!important;}
.cmp-old {background:#3A3541!important;color:#CFC6DB!important;
    border:1px dashed #9889A9!important;border-left:3px solid #9889A9!important;}
.cmp-new {background:#6F5B83!important;color:#FFF9FF!important;
    border-left:3px solid #D6B8F1!important;}
.cmp-same {opacity:.52!important;}
.cmp-lecture {background:#455A75!important;color:#F4F8FF!important;
    border-color:#8FAACB!important;}
.cmp-social {background:#744F65!important;color:#FFF5F9!important;
    border-color:#D99EBB!important;}
.cmp-exercise {background:#3C5D55!important;color:#F1FFF8!important;
    border-color:#8AB9A6!important;}
.cmp-personal {background:#66564E!important;color:#FFF7F4!important;
    border-color:#C8A99D!important;}
.cmp-appointment,.cmp-other {background:#4A5667!important;
    color:#F2F4FA!important;border-color:#98A6BD!important;}
</style>
"""


def apply_theme() -> None:
    """Apply the theme from the entrypoint, so all routed pages share it."""
    import streamlit as st

    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def priority_badge(priority: int) -> str:
    """Return an HTML badge; only the caller controls whether the markup is rendered."""
    label = PRIORITY.get(priority, PRIORITY[1])[0]
    name = label.lower()
    return f'<span class="pw-priority pw-priority--{name}">{label}</span>'


def stat_card(label: str, value: str, note: str) -> str:
    return (
        '<div class="pw-stat">'
        f'<div class="pw-stat-label">{escape(label)}</div>'
        f'<div class="pw-stat-value">{escape(value)}</div>'
        f'<div class="pw-stat-note">{escape(note)}</div></div>'
    )


def insight_card(title: str, explanation: str) -> str:
    return (
        '<div class="pw-insight">'
        f"<strong>{escape(title)}</strong><p>{escape(explanation)}</p></div>"
    )
