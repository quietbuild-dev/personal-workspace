"""One-time Study DNA onboarding and always-editable preferences."""

import sqlite3
from pathlib import Path

import streamlit as st

from workspace.repository import DEFAULT_DB_PATH
from workspace.study_dna import StudyDNA, load_study_dna, save_study_dna

CONCENTRATION_OPTIONS = {
    "early": "Early morning (6–10 AM)",
    "midday": "Late morning / midday (10 AM–2 PM)",
    "afternoon": "Afternoon (2–6 PM)",
    "evening": "Evening (6–11 PM)",
    "varies": "It varies — no strong preference",
}
SESSION_OPTIONS = {
    "short": "25–30 minutes — shorter sessions",
    "balanced": "45–60 minutes — a balanced rhythm",
    "deep": "75–90 minutes — deeper focus",
    "flexible": "It depends on the task",
}
DISTRIBUTION_OPTIONS = {
    "steady": "A little most days — keep the workload steady",
    "batch": "Concentrated study days — leave others lighter",
    "none": "No preference — choose what fits best",
}
FLEXIBILITY_OPTIONS = {
    "stable": "Keep my usual study times when possible",
    "moderate": "Move things if there's a clear benefit",
    "open": "I'm flexible — prioritize upcoming deadlines",
}


def render_form(db_path: Path, *, onboarding=False) -> bool:
    """Return True after saving. The caller may rerun to refresh its dashboard."""
    current = load_study_dna(db_path) or StudyDNA()
    if onboarding:
        st.subheader("Make your workspace yours")
        st.caption("Four quick preferences. You can change everything later in Settings.")
    with st.form("study_dna_onboarding" if onboarding else "study_dna_settings"):
        name = st.text_input(
            "What should we call you? (optional)", value=current.name, max_chars=35
        )
        a = st.selectbox(
            "When is your concentration at its best?",
            list(CONCENTRATION_OPTIONS),
            index=list(CONCENTRATION_OPTIONS).index(current.concentration),
            format_func=CONCENTRATION_OPTIONS.get,
        )
        b = st.selectbox(
            "How long can you usually focus comfortably?",
            list(SESSION_OPTIONS),
            index=list(SESSION_OPTIONS).index(current.session_length),
            format_func=SESSION_OPTIONS.get,
        )
        c = st.radio(
            "How do you prefer to spread your study time?",
            list(DISTRIBUTION_OPTIONS),
            index=list(DISTRIBUTION_OPTIONS).index(current.distribution),
            format_func=DISTRIBUTION_OPTIONS.get,
        )
        d = st.radio(
            "How flexible are your preferred study times?",
            list(FLEXIBILITY_OPTIONS),
            index=list(FLEXIBILITY_OPTIONS).index(current.flexibility),
            format_func=FLEXIBILITY_OPTIONS.get,
        )
        submit = st.form_submit_button(
            "Save my Study DNA" if onboarding else "Save preferences", type="primary"
        )
    if submit:
        try:
            save_study_dna(db_path, StudyDNA(name, a, b, c, d))
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(f"Couldn't save your preferences: {exc}")
            return False
        st.success("Study DNA saved. Your next schedule preview will use your preferences.")
        return True
    return False


def main():
    st.title("Settings")
    st.caption("Your preferences are stored only in this installation's local database.")
    st.subheader("Your Study DNA")
    if render_form(DEFAULT_DB_PATH):
        st.session_state.pop("goal_previews", None)
    st.info(
        "Your concentration, preferred session length and study-day style are soft "
        "preferences. Fixed events, study limits and deadlines always take precedence. "
        "Set your actual available hours in Calendar."
    )


if __name__ == "__main__":
    main()
