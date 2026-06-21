# %%
# Imports #

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import altair as alt
import pandas as pd
import requests
import streamlit as st

# Ensure src/ on path when launched via `streamlit run src/web/app.py`
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# The app talks to PostgREST over HTTP via the shared api_client — no direct
# Postgres. (The TUI uses the same client.)
import api_client  # noqa: E402

# %%
# Setup #

st.set_page_config(page_title="Load Log", page_icon="🏋", layout="wide")


# %%
# Auth #


def _token() -> str:
    """The current user's JWT. Login gating guarantees it exists by the time any
    page renders, so callers can assume a non-empty token."""
    return st.session_state["jwt"]


def require_login() -> bool:
    """Render the login form when unauthenticated. Returns True once a JWT is in
    session_state, False while the login form is still showing."""
    if st.session_state.get("jwt"):
        return True

    st.title("Load Log")
    st.caption("Sign in to continue.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        try:
            token = api_client.login(username, password)
        except requests.HTTPError:
            st.error("Invalid username or password.")
            return False
        except requests.RequestException:
            st.error("Could not reach the auth service. Try again shortly.")
            return False
        st.session_state["jwt"] = token
        st.rerun()
    return False


def browser_today() -> date:
    """Today's date in the *browser's* timezone, not the server's.

    Streamlit runs server-side, so `date.today()` would use the container's clock
    (UTC by default) and roll over to "tomorrow" in the evening for CST users.
    `st.context.timezone` reports the viewer's IANA zone from the browser; we fall
    back to the process-local date only if it's unavailable/unknown.
    """
    tz_name = getattr(st.context, "timezone", None)
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return date.today()


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
    token = _token()

    with st.sidebar:
        st.subheader("Add Habit")
        new_name = st.text_input("Name", key="new_habit_name")
        if st.button("Add", key="add_habit_btn") and new_name.strip():
            api_client.add_habit(token, new_name.strip())
            st.rerun()

        st.divider()
        st.subheader("Your Habits")
        for h in api_client.get_all_habits(token):
            cols = st.columns([4, 1])
            cols[0].write(h["name"])
            if cols[1].button("✕", key=f"del_{h['id']}"):
                api_client.delete_habit(token, h["id"])
                st.rerun()

    all_habits = api_client.get_all_habits(token)
    if not all_habits:
        st.info("Add your first habit using the sidebar.")
        return

    today = browser_today()
    for h in all_habits:
        streak = api_client.get_current_streak(token, h["id"], today=today)
        with st.expander(f"{h['name']}  •  streak: {streak}d", expanded=True):
            completions = api_client.get_completions(token, h["id"], days=400)
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
                api_client.toggle_completion(_token(), h["id"], picked)
                st.rerun()
            today_label = "Uncheck today" if today in completed_set else "Mark today"
            if cols[1].button(today_label, key=f"today_{h['id']}"):
                api_client.toggle_completion(_token(), h["id"], today)
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
# Volume Heatmap #


def build_volume_heatmap(volumes: dict[date, float], today: date) -> alt.LayerChart:
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=51)
    end = today + timedelta(days=(6 - today.weekday()))

    days = pd.date_range(start, end, freq="D")
    df = pd.DataFrame({"date": days})
    df["dow"] = df["date"].dt.day_name().str[:3]
    df["week"] = ((df["date"] - pd.Timestamp(start)).dt.days // 7).astype(int)
    df["future"] = df["date"].dt.date > today
    df["is_today"] = df["date"].dt.date == today
    df["volume"] = df["date"].dt.date.map(lambda d: volumes.get(d, 0.0))
    df["volume_or_null"] = df.apply(
        lambda r: None if r["future"] else r["volume"], axis=1
    )
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    df["date_pretty"] = df["date"].dt.strftime("%a %b %-d, %Y")

    dow_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

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
            color=alt.Color(
                "volume_or_null:Q",
                title="Volume (lbs)",
                scale=alt.Scale(
                    range=[
                        GH_EMPTY,
                        "#9be9a8",
                        "#40c463",
                        "#30a14e",
                        GH_DONE,
                    ],
                    type="threshold",
                    domain=_volume_thresholds(volumes),
                ),
                legend=alt.Legend(orient="bottom"),
            ),
            stroke=alt.condition(
                "datum.is_today", alt.value("#ff8c00"), alt.value("white")
            ),
            strokeWidth=alt.condition("datum.is_today", alt.value(2), alt.value(1)),
            opacity=alt.condition(select_day, alt.value(1.0), alt.value(0.9)),
            tooltip=[
                alt.Tooltip("date_pretty:N", title="Date"),
                alt.Tooltip("volume:Q", title="Volume (lbs)", format=",.0f"),
            ],
        )
        .add_params(select_day)
        .properties(height=160)
    )

    month_labels = (
        alt.Chart(week_starts)
        .mark_text(align="left", baseline="bottom", fontSize=11, color="#555")
        .encode(x=alt.X("week:O", axis=None), text="month_label:N")
        .properties(height=14)
    )

    return alt.vconcat(month_labels, rects).resolve_scale(x="shared")


def _volume_thresholds(volumes: dict[date, float]) -> list[float]:
    """Quartile cutoffs for the 5-shade scale. Fall back to defaults when sparse."""
    values = [v for v in volumes.values() if v > 0]
    if len(values) < 4:
        return [1, 1000, 3000, 6000]
    s = pd.Series(values)
    return [
        max(1.0, float(s.quantile(0.0))),
        float(s.quantile(0.33)),
        float(s.quantile(0.66)),
        float(s.quantile(1.0)),
    ]


# %%
# Workouts Page #


def page_workouts():
    st.header("Workouts")
    token = _token()

    today = browser_today()
    volumes = api_client.get_volume_by_date(token, days=400)

    event = st.altair_chart(
        build_volume_heatmap(volumes, today),
        use_container_width=True,
        on_select="rerun",
        key="workout_heatmap",
    )
    picked = _selected_date_from_event(event) or st.session_state.get(
        "workout_picked_date", today
    )
    if isinstance(picked, str):
        picked = date.fromisoformat(picked)
    st.session_state["workout_picked_date"] = picked.isoformat()

    today_volume = volumes.get(picked, 0.0)
    st.caption(
        f"Selected: **{picked.strftime('%a %b %-d, %Y')}** — "
        f"volume **{today_volume:,.0f} lbs**  •  click another cell to jump"
    )

    _render_day(picked)
    st.divider()
    _render_history_section()


def _render_day(picked: date) -> None:
    token = _token()
    sets = api_client.get_sets_for_date(token, picked)

    exercises = api_client.get_all_exercises(token)
    names = [e["name"] for e in exercises]
    cols = st.columns([3, 2])
    typed = cols[0].text_input(
        "New exercise (or pick one →)", key=f"new_ex_{picked.isoformat()}"
    )
    picked_existing = cols[1].selectbox(
        "Existing", options=["—"] + names, index=0, key=f"pick_ex_{picked.isoformat()}"
    )
    exercise_name = typed.strip() or (picked_existing if picked_existing != "—" else "")

    if not exercise_name:
        st.info("Enter or pick an exercise to start logging sets.")
        _show_set_table(picked, sets)
        return

    ex = api_client.get_or_create_exercise(token, exercise_name)
    last = api_client.get_last_workout_for_exercise(token, ex["id"], before_date=picked)
    if last:
        st.caption(
            f"Last time ({last[0]['workout_date']}): "
            + ", ".join(f"{s['reps']}×{s['weight_lbs']:g}" for s in last)
        )
    else:
        st.caption("No previous history for this exercise.")

    # Prefill reps/weight from the most recent set the user has already logged
    # for this exercise on the selected day; fall back to the previous workout
    # so set 1 starts at the right place too.
    today_for_ex = [s for s in sets if s["exercise_id"] == ex["id"]]
    if today_for_ex:
        source = today_for_ex[-1]
        default_reps, default_weight = source["reps"], float(source["weight_lbs"])
    elif last:
        default_reps, default_weight = last[-1]["reps"], float(last[-1]["weight_lbs"])
    else:
        default_reps, default_weight = 8, 135.0

    with st.form(key=f"set_form_{picked.isoformat()}_{ex['id']}", clear_on_submit=False):
        c1, c2 = st.columns([1, 1])
        reps = c1.number_input(
            "Reps", min_value=1, max_value=100, value=int(default_reps), step=1
        )
        weight = c2.number_input(
            "Weight (lbs)", min_value=0.0, max_value=2000.0,
            value=float(default_weight), step=2.5,
        )
        submitted = st.form_submit_button("Log set (or press Enter)", type="primary")
        if submitted:
            api_client.add_set(token, picked, ex["id"], int(reps), float(weight))
            st.rerun()

    _show_set_table(picked, sets)

    if sets:
        st.write("**Progressive-overload suggestions:**")
        seen: set[int] = set()
        for s in sets:
            if s["exercise_id"] in seen:
                continue
            seen.add(s["exercise_id"])
            suggestion = api_client.suggest_next_weight(token, s["exercise_id"], picked)
            if suggestion is None:
                st.write(f"• {s['exercise_name']}: build a baseline next time")
            else:
                st.write(f"• {s['exercise_name']}: next session try **{suggestion:g} lbs**")


def _show_set_table(picked: date, sets: list[dict]) -> None:
    """Render an editable table of the day's sets. Inline edits to reps/weight
    persist on commit (tab-out or Enter); clicking 🗑 on a row deletes it.
    Triggers st.rerun() when any change is committed.
    """
    if not sets:
        st.caption("No sets logged on this day yet.")
        return

    st.write(
        "**Sets logged on this day** — edit reps/weight in place, or click 🗑 to delete:"
    )

    df = pd.DataFrame(sets)[
        ["id", "exercise_name", "set_number", "reps", "weight_lbs"]
    ]
    edited = st.data_editor(
        df,
        column_config={
            "id": None,
            "exercise_name": st.column_config.TextColumn("Exercise", disabled=True),
            "set_number": st.column_config.NumberColumn("Set", disabled=True),
            "reps": st.column_config.NumberColumn(
                "Reps", required=True, min_value=1, max_value=100, step=1, format="%d",
            ),
            "weight_lbs": st.column_config.NumberColumn(
                "Weight (lbs)", required=True, min_value=0.0, max_value=2000.0, step=2.5,
            ),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"sets_editor_{picked.isoformat()}",
    )

    orig_ids = {int(i) for i in df["id"]}
    surviving = edited.dropna(subset=["id"])
    new_ids = {int(i) for i in surviving["id"]}

    token = _token()
    changed = False
    for sid in orig_ids - new_ids:
        api_client.delete_set(token, sid)
        changed = True

    orig_map = {int(r["id"]): r for _, r in df.iterrows()}
    new_map = {int(r["id"]): r for _, r in surviving.iterrows()}
    for sid in orig_ids & new_ids:
        if (
            int(orig_map[sid]["reps"]) != int(new_map[sid]["reps"])
            or float(orig_map[sid]["weight_lbs"]) != float(new_map[sid]["weight_lbs"])
        ):
            api_client.update_set(
                token,
                sid,
                int(new_map[sid]["reps"]),
                float(new_map[sid]["weight_lbs"]),
            )
            changed = True

    if changed:
        st.rerun()


def _render_history_section() -> None:
    token = _token()
    st.subheader("Exercise History")
    exercises = api_client.get_all_exercises(token)
    if not exercises:
        return
    pick = st.selectbox(
        "Exercise", options=[e["name"] for e in exercises], key="history_pick"
    )
    if not pick:
        return
    ex_id = next(e["id"] for e in exercises if e["name"] == pick)
    df = api_client.get_exercise_history(token, ex_id, limit_days=365)
    if df.empty:
        st.info("No logged sets yet.")
        return

    max_per_day = df.groupby("workout_date")["weight_lbs"].max().reset_index()
    chart = (
        alt.Chart(max_per_day)
        .mark_line(point=True)
        .encode(
            x=alt.X("workout_date:T", title="Date"),
            y=alt.Y("weight_lbs:Q", title="Max weight (lbs)"),
            tooltip=["workout_date:T", "weight_lbs:Q"],
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

if require_login():
    if st.sidebar.button("Log out", key="logout_btn"):
        st.session_state.pop("jwt", None)
        st.rerun()
    choice = st.sidebar.radio("Page", list(PAGES.keys()))
    st.sidebar.divider()
    PAGES[choice]()
