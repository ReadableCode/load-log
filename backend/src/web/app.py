# %%
# Imports #

import os
import sys
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

# Ensure src/ on path when launched via `streamlit run src/web/app.py`
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import habits  # noqa: E402
import workouts  # noqa: E402
from db import bootstrap  # noqa: E402

# %%
# Setup #

st.set_page_config(page_title="Load Log", page_icon="🏋", layout="wide")


@st.cache_resource
def _bootstrap_once():
    bootstrap()
    return True


_bootstrap_once()

# %%
# Heatmap #

GH_EMPTY = "#ebedf0"
GH_DONE = "#216e39"
GH_FUTURE = "#f6f8fa"


def _heatmap_dataframe(completions: list[date], today: date) -> pd.DataFrame:
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=51)
    end = today + timedelta(days=(6 - today.weekday()))

    days = pd.date_range(start, end, freq="D")
    completed_set = {pd.Timestamp(c) for c in completions}

    df = pd.DataFrame({"date": days})
    df["dow"] = df["date"].dt.day_name().str[:3]
    df["week"] = ((df["date"] - pd.Timestamp(start)).dt.days // 7).astype(int)
    df["completed"] = df["date"].isin(completed_set)
    df["future"] = df["date"].dt.date > today
    df["is_today"] = df["date"].dt.date == today

    df["color"] = df.apply(
        lambda r: GH_DONE if r["completed"] else (GH_FUTURE if r["future"] else GH_EMPTY),
        axis=1,
    )
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    df["date_pretty"] = df["date"].dt.strftime("%a %b %-d, %Y")
    df["status"] = df["completed"].map({True: "Completed", False: "Not done"})
    return df


def build_heatmap(completions: list[date], today: date) -> alt.LayerChart:
    df = _heatmap_dataframe(completions, today)
    dow_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Month label per week: take the first day of each week and label it
    # only when the month changes from the previous week.
    week_starts = df[df["dow"] == "Mon"][["week", "date"]].copy()
    week_starts["month"] = week_starts["date"].dt.strftime("%b")
    week_starts["month_label"] = week_starts["month"].where(
        week_starts["month"] != week_starts["month"].shift(), ""
    )

    select_day = alt.selection_point(
        fields=["date_str"], name="day", on="click", empty=False, clear=False
    )

    rects = (
        alt.Chart(df)
        .mark_rect(stroke="white", strokeWidth=1, cornerRadius=2)
        .encode(
            x=alt.X("week:O", title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y("dow:O", sort=dow_order, title=None),
            color=alt.Color("color:N", scale=None, legend=None),
            stroke=alt.condition(
                "datum.is_today", alt.value("#ff8c00"), alt.value("white")
            ),
            strokeWidth=alt.condition("datum.is_today", alt.value(2), alt.value(1)),
            opacity=alt.condition(select_day, alt.value(1.0), alt.value(0.85)),
            tooltip=[
                alt.Tooltip("date_pretty:N", title="Date"),
                alt.Tooltip("status:N", title="Status"),
            ],
        )
        .add_params(select_day)
        .properties(height=150)
    )

    month_labels = (
        alt.Chart(week_starts)
        .mark_text(align="left", baseline="bottom", fontSize=11, color="#555")
        .encode(x=alt.X("week:O", axis=None), text="month_label:N")
        .properties(height=14)
    )

    return alt.vconcat(month_labels, rects).resolve_scale(x="shared")


# %%
# Habits Page #


def page_habits():
    st.header("Daily Habits")

    with st.sidebar:
        st.subheader("Add Habit")
        new_name = st.text_input("Name", key="new_habit_name")
        if st.button("Add", key="add_habit_btn") and new_name.strip():
            habits.add_habit(new_name.strip())
            st.rerun()

        st.divider()
        st.subheader("Your Habits")
        for h in habits.get_all_habits():
            cols = st.columns([4, 1])
            cols[0].write(h["name"])
            if cols[1].button("✕", key=f"del_{h['id']}"):
                habits.delete_habit(h["id"])
                st.rerun()

    all_habits = habits.get_all_habits()
    if not all_habits:
        st.info("Add your first habit using the sidebar.")
        return

    today = date.today()
    for h in all_habits:
        streak = habits.get_current_streak(h["id"])
        with st.expander(f"{h['name']}  •  streak: {streak}d", expanded=True):
            completions = habits.get_completions(h["id"], days=400)
            completed_set = set(completions)

            event = st.altair_chart(
                build_heatmap(completions, today),
                use_container_width=True,
                on_select="rerun",
                key=f"heatmap_{h['id']}",
            )

            picked = _selected_date_from_event(event) or today
            is_done = picked in completed_set
            done_str = "✓ completed" if is_done else "✗ not done"
            st.caption(
                f"Selected: **{picked.strftime('%a %b %-d, %Y')}** — {done_str} "
                "(click a cell to pick another day)"
            )

            cols = st.columns([1, 1])
            toggle_label = f"Uncheck {picked:%b %-d}" if is_done else f"Mark {picked:%b %-d}"
            if cols[0].button(toggle_label, key=f"toggle_{h['id']}", type="primary"):
                habits.toggle_completion(h["id"], picked)
                st.rerun()
            today_label = "Uncheck today" if today in completed_set else "Mark today"
            if cols[1].button(today_label, key=f"today_{h['id']}"):
                habits.toggle_completion(h["id"], today)
                st.rerun()


def _selected_date_from_event(event) -> date | None:
    """Extract the clicked date from an st.altair_chart on_select payload."""
    try:
        rows = event.selection.get("day", [])
    except AttributeError:
        return None
    if not rows:
        return None
    raw = rows[0].get("date_str") if isinstance(rows[0], dict) else None
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


# %%
# Workouts Page #


def _get_active_session_id() -> int | None:
    return st.session_state.get("active_session_id")


def _set_active_session_id(session_id: int | None) -> None:
    st.session_state["active_session_id"] = session_id


def page_workouts():
    st.header("Workout Tracker")

    with st.sidebar:
        st.subheader("Sessions")
        if st.button("➕ New Session"):
            s = workouts.create_session()
            _set_active_session_id(s["id"])
            st.rerun()

        for s in workouts.get_recent_sessions(limit=10):
            label = f"{s['session_date']} (#{s['id']})"
            if st.button(label, key=f"sess_{s['id']}"):
                _set_active_session_id(s["id"])
                st.rerun()

    session_id = _get_active_session_id()
    if session_id is None:
        st.info("Start a new session from the sidebar.")
        _render_history_section()
        return

    _render_active_session(session_id)
    st.divider()
    _render_history_section()


def _render_active_session(session_id: int) -> None:
    sets = workouts.get_session_sets(session_id)
    sessions = {s["id"]: s for s in workouts.get_recent_sessions(limit=50)}
    session = sessions.get(session_id, {"session_date": "?", "notes": ""})

    st.subheader(f"Session #{session_id} — {session['session_date']}")

    notes = st.text_input("Notes", value=session.get("notes", ""), key=f"notes_{session_id}")
    if st.button("Save notes", key=f"save_notes_{session_id}"):
        workouts.update_session_notes(session_id, notes)
        st.success("Saved.")

    exercises = workouts.get_all_exercises()
    names = [e["name"] for e in exercises]
    picked = st.selectbox(
        "Exercise (existing)",
        options=["— new exercise —"] + names,
        index=0,
    )
    if picked == "— new exercise —":
        exercise_name = st.text_input("New exercise name", key=f"new_ex_{session_id}")
    else:
        exercise_name = picked

    if exercise_name:
        ex = workouts.get_or_create_exercise(exercise_name) if exercise_name.strip() else None
        if ex:
            last = workouts.get_last_session_for_exercise(
                ex["id"], before_session_id=session_id
            )
            if last:
                st.caption(
                    f"Last time ({last[0]['session_date']}): "
                    + ", ".join(f"{s['reps']}×{s['weight_lbs']:g}" for s in last)
                )
            else:
                st.caption("No previous history for this exercise.")

            current_for_ex = [s for s in sets if s["exercise_id"] == ex["id"]]
            next_set_num = (
                max((s["set_number"] for s in current_for_ex), default=0) + 1
            )

            cols = st.columns([1, 1, 1])
            reps = cols[0].number_input(
                "Reps", min_value=1, max_value=100, value=8, step=1,
                key=f"reps_{session_id}_{ex['id']}",
            )
            weight = cols[1].number_input(
                "Weight (lbs)", min_value=0.0, max_value=2000.0, value=135.0, step=2.5,
                key=f"wt_{session_id}_{ex['id']}",
            )
            if cols[2].button(f"Log set #{next_set_num}", key=f"log_{session_id}_{ex['id']}"):
                workouts.add_set(session_id, ex["id"], next_set_num, int(reps), float(weight))
                st.rerun()

    if sets:
        st.write("**Logged this session:**")
        df = pd.DataFrame(sets)[
            ["exercise_name", "set_number", "reps", "weight_lbs"]
        ].rename(columns={"weight_lbs": "weight"})
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.write("**Suggestions for next session:**")
        by_ex: dict[int, str] = {}
        for s in sets:
            by_ex[s["exercise_id"]] = s["exercise_name"]
        for ex_id, ex_name in by_ex.items():
            suggestion = workouts.suggest_next_weight(ex_id, session_id)
            if suggestion is None:
                st.write(f"• {ex_name}: build a baseline next time")
            else:
                st.write(f"• {ex_name}: try **{suggestion:g} lbs**")


def _render_history_section() -> None:
    st.subheader("Exercise History")
    exercises = workouts.get_all_exercises()
    if not exercises:
        return
    pick = st.selectbox(
        "Exercise", options=[e["name"] for e in exercises], key="history_pick"
    )
    if not pick:
        return
    ex_id = next(e["id"] for e in exercises if e["name"] == pick)
    df = workouts.get_exercise_history(ex_id, limit=50)
    if df.empty:
        st.info("No logged sets yet.")
        return

    max_per_session = (
        df.groupby("session_date")["weight_lbs"].max().reset_index()
    )
    chart = (
        alt.Chart(max_per_session)
        .mark_line(point=True)
        .encode(
            x="session_date:T",
            y=alt.Y("weight_lbs:Q", title="Max weight (lbs)"),
            tooltip=["session_date:T", "weight_lbs:Q"],
        )
        .properties(height=250)
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(df, use_container_width=True, hide_index=True)


# %%
# Router #

PAGES = {
    "Habits": page_habits,
    "Workouts": page_workouts,
}

choice = st.sidebar.radio("Page", list(PAGES.keys()))
st.sidebar.divider()
PAGES[choice]()
