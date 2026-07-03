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
# Theme tokens #

# One place for every color the app uses. `.streamlit/config.toml` carries the
# same values for Streamlit's own chrome; the Altair theme and injected CSS
# below consume these, so charts, tiles, and widgets read as one system.
BG = "#0d0d0d"  # page plane
SURFACE = "#141413"  # cards / sidebar / forms
INK = "#fafaf7"
INK_SECONDARY = "#c3c2b7"
INK_MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"
ACCENT = "#3987e5"  # primary series blue
ACCENT_SOFT = "#86b6ef"  # light blue for text accents (eyebrow, brand)
SERIES_AQUA = "#199e70"  # second chart series (validated CVD-safe next to ACCENT)
TODAY_RING = "#ff8c00"

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# GitHub-dark activity ramp for the heatmaps
GH_EMPTY = "#242424"
GH_FUTURE = "#161616"
GH_DONE = "#26a641"
GH_RAMP = ["#0e4429", "#006d32", "#26a641", "#39d353"]


@alt.theme.register("load_log_dark", enable=True)
def _load_log_dark() -> alt.theme.ThemeConfig:
    """Dark Altair theme matching the app palette. Charts are rendered with
    theme=None on st.altair_chart so this (not Streamlit's default) applies."""
    return {
        "config": {
            "background": "transparent",
            "font": FONT,
            "view": {"stroke": None},
            "axis": {
                "labelColor": INK_MUTED,
                "titleColor": INK_SECONDARY,
                "gridColor": GRID,
                "domainColor": AXIS,
                "tickColor": AXIS,
                "labelFontSize": 11,
                "titleFontSize": 12,
                "titleFontWeight": 500,
            },
            "legend": {
                "labelColor": INK_SECONDARY,
                "titleColor": INK_MUTED,
                "labelFontSize": 12,
            },
        }
    }


def _inject_css() -> None:
    """Global CSS: page glow, stat tiles, headers, and card-styled widgets."""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
                radial-gradient(1100px 500px at 18% -12%, #14202f 0%, rgba(13, 13, 13, 0) 60%),
                {BG};
        }}
        h1, h2, h3 {{ letter-spacing: -0.02em; }}
        [data-testid="stHeader"] {{ background: transparent; }}

        [data-testid="stSidebar"] {{
            background: {SURFACE};
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }}
        [data-testid="stExpander"] {{
            background: {SURFACE};
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 12px;
        }}
        [data-testid="stForm"] {{
            background: {SURFACE};
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 12px;
        }}

        .ll-brand {{
            font-size: 1.05rem;
            font-weight: 700;
            color: {INK};
            padding: 0.25rem 0 0.5rem;
        }}
        .ll-brand span {{ color: {ACCENT_SOFT}; }}

        .ll-header {{ margin: 0 0 0.9rem 0; }}
        .ll-eyebrow {{
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.18em;
            color: {ACCENT_SOFT};
            font-weight: 700;
        }}
        .ll-header h1 {{ font-size: 1.9rem; margin: 0.05rem 0 0.15rem; }}
        .ll-header p {{ color: {INK_MUTED}; margin: 0; font-size: 0.92rem; }}

        .ll-tiles {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
            gap: 0.75rem;
            margin: 0.25rem 0 1rem;
        }}
        .ll-tile {{
            background: linear-gradient(180deg, #1d1d1c, #161615);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 14px;
            padding: 0.8rem 1rem 0.7rem;
        }}
        .ll-tile .ll-label {{
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: {INK_MUTED};
            font-weight: 600;
            margin-bottom: 0.2rem;
        }}
        .ll-tile .ll-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: {INK};
            font-variant-numeric: tabular-nums;
            line-height: 1.15;
        }}
        .ll-tile .ll-value span {{
            font-size: 0.8rem;
            color: {INK_MUTED};
            font-weight: 500;
            margin-left: 0.15rem;
        }}
        .ll-tile .ll-sub {{ font-size: 0.74rem; color: {INK_MUTED}; margin-top: 0.2rem; }}

        .ll-login-head {{ text-align: center; margin: 2.5rem 0 1rem; }}
        .ll-login-head .ll-logo {{ font-size: 2.4rem; }}
        .ll-login-head h1 {{ font-size: 1.9rem; margin: 0.2rem 0 0.3rem; }}
        .ll-login-head p {{ color: {INK_MUTED}; margin: 0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="ll-header"><span class="ll-eyebrow">Load Log</span>'
        f"<h1>{title}</h1><p>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )


def stat_tiles(tiles: list[tuple[str, str, str]]) -> None:
    """Render a row of stat tiles from (label, value_html, sub) triples."""
    cells = "".join(
        f'<div class="ll-tile"><div class="ll-label">{label}</div>'
        f'<div class="ll-value">{value}</div><div class="ll-sub">{sub}</div></div>'
        for label, value, sub in tiles
    )
    st.markdown(f'<div class="ll-tiles">{cells}</div>', unsafe_allow_html=True)


_inject_css()


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

    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown(
            '<div class="ll-login-head"><div class="ll-logo">🏋</div>'
            "<h1>Load Log</h1><p>Habits, workouts, and progressive overload.</p></div>",
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
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
# 1RM #


def epley_1rm(weight_lbs: float, reps: int) -> float:
    """Estimated one-rep max via the Epley formula: weight × (1 + reps/30).

    A single rep IS the 1RM; the estimate gets rougher as reps climb past ~12,
    which the UI notes next to the chart.
    """
    if reps <= 1:
        return weight_lbs
    return weight_lbs * (1.0 + reps / 30.0)


# %%
# Heatmap #


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
        lambda r: (
            GH_DONE if r["completed"] else (GH_FUTURE if r["future"] else GH_EMPTY)
        ),
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
        .mark_rect(stroke=BG, strokeWidth=1, cornerRadius=2)
        .encode(
            x=alt.X("week:O", title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y("dow:O", sort=dow_order, title=None),
            color=alt.Color("color:N", scale=None, legend=None),
            stroke=alt.condition(
                "datum.is_today", alt.value(TODAY_RING), alt.value(BG)
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
        .mark_text(align="left", baseline="bottom", fontSize=11, color=INK_MUTED)
        .encode(x=alt.X("week:O", axis=None), text="month_label:N")
        .properties(height=14)
    )

    return alt.vconcat(month_labels, rects).resolve_scale(x="shared")


# %%
# Habits Page #


def page_habits():
    page_header(
        "Daily Habits", "Keep the streaks alive — click any cell to toggle a day."
    )
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
                width="stretch",
                theme=None,
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
            toggle_label = (
                f"Uncheck {picked:%b %-d}" if is_done else f"Mark {picked:%b %-d}"
            )
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
        .mark_rect(stroke=BG, strokeWidth=1, cornerRadius=2)
        .encode(
            x=alt.X("week:O", title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y("dow:O", sort=dow_order, title=None),
            color=alt.Color(
                "volume_or_null:Q",
                title="Volume (lbs)",
                scale=alt.Scale(
                    range=[GH_EMPTY] + GH_RAMP,
                    type="threshold",
                    domain=_volume_thresholds(volumes),
                ),
                legend=alt.Legend(orient="bottom", format=",.0f"),
            ),
            stroke=alt.condition(
                "datum.is_today", alt.value(TODAY_RING), alt.value(BG)
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
        .mark_text(align="left", baseline="bottom", fontSize=11, color=INK_MUTED)
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
# History Charts #


def build_volume_chart(daily: pd.DataFrame) -> alt.LayerChart:
    """Total volume (sum of reps × weight) per workout day, as an area+line trend."""
    x = alt.X(
        "workout_date:T",
        title=None,
        axis=alt.Axis(format="%b %-d", grid=False, labelAngle=0),
    )
    y = alt.Y("volume_lbs:Q", title="Total volume (lbs)")
    tooltip = [
        alt.Tooltip("workout_date:T", title="Date", format="%a %b %-d, %Y"),
        alt.Tooltip("volume_lbs:Q", title="Volume (lbs)", format=",.0f"),
        alt.Tooltip("sets:Q", title="Sets"),
        alt.Tooltip("top_weight:Q", title="Top weight (lbs)", format=",.1f"),
    ]

    base = alt.Chart(daily).encode(x=x)
    area = base.mark_area(
        line=False,
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="#3987e500", offset=0),
                alt.GradientStop(color="#3987e566", offset=1),
            ],
            x1=1,
            x2=1,
            y1=1,
            y2=0,
        ),
    ).encode(y=y)
    line = base.mark_line(color=ACCENT, strokeWidth=2).encode(y=y)
    points = base.mark_circle(color=ACCENT, size=70).encode(y=y, tooltip=tooltip)
    return (area + line + points).properties(height=300)


def build_e1rm_chart(sets_df: pd.DataFrame, daily: pd.DataFrame) -> alt.LayerChart:
    """Estimated 1RM over time: every set as a soft point, daily best as a line."""
    sets_df = sets_df.assign(series="Each set")
    daily = daily.assign(series="Daily best")

    x = alt.X(
        "workout_date:T",
        title=None,
        axis=alt.Axis(format="%b %-d", grid=False, labelAngle=0),
    )
    y_scale = alt.Scale(zero=False)
    color = alt.Color(
        "series:N",
        title=None,
        scale=alt.Scale(domain=["Each set", "Daily best"], range=[SERIES_AQUA, ACCENT]),
        legend=alt.Legend(orient="top", direction="horizontal"),
    )

    points = (
        alt.Chart(sets_df)
        .mark_circle(size=55, opacity=0.45)
        .encode(
            x=x,
            y=alt.Y("e1rm_lbs:Q", title="Estimated 1RM (lbs)", scale=y_scale),
            color=color,
            tooltip=[
                alt.Tooltip("workout_date:T", title="Date", format="%a %b %-d, %Y"),
                alt.Tooltip("set_number:Q", title="Set"),
                alt.Tooltip("reps:Q", title="Reps"),
                alt.Tooltip("weight_lbs:Q", title="Weight (lbs)", format=",.1f"),
                alt.Tooltip("e1rm_lbs:Q", title="Est. 1RM (lbs)", format=",.1f"),
            ],
        )
    )
    line = (
        alt.Chart(daily)
        .mark_line(strokeWidth=2.5, point=alt.OverlayMarkDef(size=60, filled=True))
        .encode(
            x=x,
            y=alt.Y("best_e1rm:Q", title="Estimated 1RM (lbs)", scale=y_scale),
            color=color,
            tooltip=[
                alt.Tooltip("workout_date:T", title="Date", format="%a %b %-d, %Y"),
                alt.Tooltip("best_e1rm:Q", title="Best est. 1RM (lbs)", format=",.1f"),
            ],
        )
    )
    return (points + line).properties(height=300)


# %%
# Workouts Page #


def page_workouts():
    page_header(
        "Workouts",
        "Log sets, watch total volume accumulate, and track strength via estimated 1RM.",
    )
    token = _token()

    today = browser_today()
    volumes = api_client.get_volume_by_date(token, days=400)

    event = st.altair_chart(
        build_volume_heatmap(volumes, today),
        width="stretch",
        theme=None,
        on_select="rerun",
        key="workout_heatmap",
    )
    picked = _selected_date_from_event(event) or st.session_state.get(
        "workout_picked_date", today
    )
    if isinstance(picked, str):
        picked = date.fromisoformat(picked)
    st.session_state["workout_picked_date"] = picked.isoformat()

    sets = api_client.get_sets_for_date(token, picked)
    _day_stat_tiles(picked, sets, volumes)
    st.caption(
        f"Selected: **{picked.strftime('%a %b %-d, %Y')}** — click another heatmap cell to jump"
    )

    _render_day(picked, sets)
    st.divider()
    _render_history_section()


def _day_stat_tiles(picked: date, sets: list[dict], volumes: dict[date, float]) -> None:
    day_volume = volumes.get(picked, 0.0)
    week_volume = sum(volumes.get(picked - timedelta(days=i), 0.0) for i in range(7))
    n_exercises = len({s["exercise_id"] for s in sets})
    best_e1rm = max(
        (epley_1rm(float(s["weight_lbs"]), int(s["reps"])) for s in sets),
        default=0.0,
    )
    stat_tiles(
        [
            (
                "Day volume",
                f"{day_volume:,.0f} <span>lbs</span>",
                f"{picked:%a %b %-d}",
            ),
            (
                "Sets logged",
                f"{len(sets)}",
                f"{n_exercises} exercise{'s' if n_exercises != 1 else ''}",
            ),
            (
                "Best est. 1RM",
                f"{best_e1rm:,.0f} <span>lbs</span>" if best_e1rm else "—",
                "Epley, best set of the day",
            ),
            (
                "7-day volume",
                f"{week_volume:,.0f} <span>lbs</span>",
                "ending on selected day",
            ),
        ]
    )


def _render_day(picked: date, sets: list[dict]) -> None:
    token = _token()

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

    with st.form(
        key=f"set_form_{picked.isoformat()}_{ex['id']}", clear_on_submit=False
    ):
        c1, c2 = st.columns([1, 1])
        reps = c1.number_input(
            "Reps", min_value=1, max_value=100, value=int(default_reps), step=1
        )
        weight = c2.number_input(
            "Weight (lbs)",
            min_value=0.0,
            max_value=2000.0,
            value=float(default_weight),
            step=2.5,
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
                st.write(
                    f"• {s['exercise_name']}: next session try **{suggestion:g} lbs**"
                )


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

    df = pd.DataFrame(sets)[["id", "exercise_name", "set_number", "reps", "weight_lbs"]]
    edited = st.data_editor(
        df,
        column_config={
            "id": None,
            "exercise_name": st.column_config.TextColumn("Exercise", disabled=True),
            "set_number": st.column_config.NumberColumn("Set", disabled=True),
            "reps": st.column_config.NumberColumn(
                "Reps",
                required=True,
                min_value=1,
                max_value=100,
                step=1,
                format="%d",
            ),
            "weight_lbs": st.column_config.NumberColumn(
                "Weight (lbs)",
                required=True,
                min_value=0.0,
                max_value=2000.0,
                step=2.5,
            ),
        },
        num_rows="dynamic",
        width="stretch",
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
        if int(orig_map[sid]["reps"]) != int(new_map[sid]["reps"]) or float(
            orig_map[sid]["weight_lbs"]
        ) != float(new_map[sid]["weight_lbs"]):
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

    df["volume_lbs"] = df["reps"] * df["weight_lbs"]
    df["e1rm_lbs"] = [
        epley_1rm(float(w), int(r)) for w, r in zip(df["weight_lbs"], df["reps"])
    ]
    daily = df.groupby("workout_date", as_index=False).agg(
        volume_lbs=("volume_lbs", "sum"),
        best_e1rm=("e1rm_lbs", "max"),
        sets=("set_number", "count"),
        top_weight=("weight_lbs", "max"),
    )

    best_row = daily.loc[daily["best_e1rm"].idxmax()]
    latest = daily.iloc[-1]
    best_vol = daily.loc[daily["volume_lbs"].idxmax()]
    stat_tiles(
        [
            (
                "Best est. 1RM",
                f"{best_row['best_e1rm']:,.0f} <span>lbs</span>",
                f"{best_row['workout_date']:%b %-d, %Y}",
            ),
            (
                "Latest est. 1RM",
                f"{latest['best_e1rm']:,.0f} <span>lbs</span>",
                f"{latest['workout_date']:%b %-d, %Y}",
            ),
            (
                "Best day volume",
                f"{best_vol['volume_lbs']:,.0f} <span>lbs</span>",
                f"{best_vol['workout_date']:%b %-d, %Y}",
            ),
            ("Sessions", f"{len(daily)}", f"{len(df)} sets in the last year"),
        ]
    )

    tab_volume, tab_e1rm = st.tabs(["Total volume", "Estimated 1RM"])
    with tab_volume:
        st.altair_chart(build_volume_chart(daily), width="stretch", theme=None)
        st.caption("Total volume = Σ reps × weight across every set that day.")
    with tab_e1rm:
        st.altair_chart(build_e1rm_chart(df, daily), width="stretch", theme=None)
        st.caption(
            "Estimated 1RM (Epley): weight × (1 + reps ÷ 30) per set; the line tracks "
            "each day's best set. Estimates get rough above ~12 reps."
        )

    with st.expander("All sets (last year)"):
        table = pd.DataFrame(
            {
                "Date": df["workout_date"].dt.date,
                "Set": df["set_number"],
                "Reps": df["reps"],
                "Weight (lbs)": df["weight_lbs"],
                "Volume (lbs)": df["volume_lbs"],
                "Est. 1RM (lbs)": df["e1rm_lbs"].round(1),
            }
        )
        st.dataframe(table, width="stretch", hide_index=True)


# %%
# Router #

PAGES = {
    "Habits": page_habits,
    "Workouts": page_workouts,
}

if require_login():
    with st.sidebar:
        st.markdown(
            '<div class="ll-brand">🏋&nbsp; Load <span>Log</span></div>',
            unsafe_allow_html=True,
        )
        choice = st.sidebar.radio(
            "Page", list(PAGES.keys()), label_visibility="collapsed"
        )
        st.divider()
    PAGES[choice]()
    with st.sidebar:
        st.divider()
        if st.button("Log out", key="logout_btn", width="stretch"):
            st.session_state.pop("jwt", None)
            st.rerun()
