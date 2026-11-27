"""Personal study preferences: local, editable, and used in scheduling."""

import sqlite3
from pathlib import Path

import streamlit as st

from workspace.repository import DEFAULT_DB_PATH
from workspace.study_breaks import BREAK_OPTIONS, get_break_minutes, set_break_minutes
from workspace.study_dna import (
    StudyDNA,
    custom_concentration,
    load_study_dna,
    save_study_dna,
)

CONCENTRATION_OPTIONS = {
    "early": "Early morning (06:00–10:00)",
    "midday": "Late morning / midday (10:00–14:00)",
    "afternoon": "Afternoon (14:00–18:00)",
    "evening": "Evening (18:00–23:00)",
    "varies": "No preferred time — fit study around my schedule",
    "custom": "Choose my focus hours (24-hour clock)",
}
FOCUS_CHOICES = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5)]
FOCUS_END_CHOICES = FOCUS_CHOICES + ["24:00"]
SESSION_OPTIONS = {
    "short": "25–30 minutes — shorter sessions",
    "balanced": "45–60 minutes — a balanced rhythm",
    "deep": "75–90 minutes — deeper focus",
    "flexible": "It depends on the task",
}
DISTRIBUTION_OPTIONS = {
    "steady": "Spread evenly",
    "batch": "Fewer study days",
    "none": "No preference",
}
FLEXIBILITY_OPTIONS = {
    "stable": "Keep my usual study times when possible",
    "moderate": "Move things if there's a clear benefit",
    "open": "I'm flexible — prioritize upcoming deadlines",
}


def _clock_minutes(text: str) -> int:
    hours, minutes = map(int, text.split(":"))
    return hours * 60 + minutes


def render_form(db_path: Path, *, onboarding=False) -> bool:
    """Return True after saving. The caller may rerun to refresh its dashboard."""
    current = load_study_dna(db_path) or StudyDNA()
    if onboarding:
        st.subheader("Make your workspace yours")
        st.caption("Four quick preferences. You can change everything later in Settings.")
    current_choice = (
        current.concentration
        if current.concentration in CONCENTRATION_OPTIONS else "custom"
    )
    # Keeping name and focus-time preferences in one interactive section avoids
    # splitting onboarding across the outer card and a separate form.
    name = st.text_input(
        "What should we call you? (optional)", value=current.name, max_chars=35,
        key="study_style_name",
    )
    a = st.selectbox(
        "When do you study best?", list(CONCENTRATION_OPTIONS),
        index=list(CONCENTRATION_OPTIONS).index(current_choice),
        format_func=CONCENTRATION_OPTIONS.get,
        key="study_style_concentration",
    )
    start_choice = end_choice = None
    if a == "custom":
        preferred = current.focus_window or (9 * 60, 13 * 60)
        left, right = st.columns(2, gap="small")
        with left:
            start_choice = st.selectbox(
                "Focus from", FOCUS_CHOICES,
                index=min(range(len(FOCUS_CHOICES)), key=lambda i: abs(
                    _clock_minutes(FOCUS_CHOICES[i]) - preferred[0]
                )),
            )
        with right:
            end_choice = st.selectbox(
                "Focus until", FOCUS_END_CHOICES,
                index=min(range(len(FOCUS_END_CHOICES)), key=lambda i: abs(
                    _clock_minutes(FOCUS_END_CHOICES[i]) - preferred[1]
                )),
            )
        st.caption("24-hour format · A preference, not a restriction.")
    b = st.selectbox(
        "How long can you usually focus comfortably?",
        list(SESSION_OPTIONS),
        index=list(SESSION_OPTIONS).index(current.session_length),
        format_func=SESSION_OPTIONS.get,
    )
    c = st.selectbox(
        "How do you prefer to spread your study time?",
        list(DISTRIBUTION_OPTIONS),
        index=list(DISTRIBUTION_OPTIONS).index(current.distribution),
        format_func=DISTRIBUTION_OPTIONS.get,
    )
    d = st.selectbox(
        "How flexible are your preferred study times?",
        list(FLEXIBILITY_OPTIONS),
        index=list(FLEXIBILITY_OPTIONS).index(current.flexibility),
        format_func=FLEXIBILITY_OPTIONS.get,
    )
    submit = st.button(
        "Save my preferences" if onboarding else "Save preferences",
        type="primary", key="study_style_save",
    )
    if submit:
        try:
            focus = (
                custom_concentration(
                    _clock_minutes(start_choice), _clock_minutes(end_choice)
                )
                if a == "custom" else a
            )
            save_study_dna(db_path, StudyDNA(name, focus, b, c, d))
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(f"Couldn't save your preferences: {exc}")
            return False
        st.toast("Preferences saved.")
        return True
    return False


def main():
    st.title("Settings")
    st.caption("Your settings stay on this computer.")
    st.subheader("My Study Style")
    if render_form(DEFAULT_DB_PATH):
        st.session_state.pop("goal_previews", None)
    st.markdown("#### Time between study sessions")
    current_gap = get_break_minutes(DEFAULT_DB_PATH)
    choice = st.selectbox(
        "Preferred break",
        BREAK_OPTIONS,
        index=BREAK_OPTIONS.index(current_gap),
        format_func=lambda minutes: (
            "No gap" if minutes == 0 else f"{minutes} minutes"
        ),
        help="The planner leaves empty time when it fits. Breaks never count as study.",
        key="preferred_study_break_minutes",
    )
    if st.button("Save break preference", key="save_study_breaks"):
        try:
            set_break_minutes(DEFAULT_DB_PATH, choice)
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
        else:
            st.session_state.pop("goal_previews", None)
            st.toast("Preference saved")
    st.caption("Your preferences guide suggestions. Deadlines and commitments come first.")


if __name__ == "__main__":
    main()
