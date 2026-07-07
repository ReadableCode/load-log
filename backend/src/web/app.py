# %%
# Imports #

import json
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
# The look mirrors the readablecode portfolio site: navy terminal surfaces,
# monospace type, green prompt accent, amber highlights, `// section` headers.
BG = "#0d1420"  # page plane (navy)
SURFACE = "#121b2a"  # cards / sidebar / forms
SURFACE_2 = "#182333"  # terminal title bar
BORDER = "rgba(148, 163, 184, 0.16)"
INK = "#dbe4f0"
INK_SECONDARY = "#9fb0c3"
INK_MUTED = "#7d8b9e"
GRID = "#1c2739"
AXIS = "#2a3850"
ACCENT = "#2ea043"  # primary chart/widget green
ACCENT_BRIGHT = "#56d364"  # text green: prompt glyph, // slashes, brand
AMBER = "#b8860b"  # second chart series (validated CVD-safe next to ACCENT)
AMBER_BRIGHT = "#e3b341"  # amber text highlights + today ring
TODAY_RING = AMBER_BRIGHT
SELECTED_RING = INK  # selected-day outline; CVD-safe next to TODAY_RING

FONT = 'ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace'

# GitHub-dark activity ramp for the heatmaps
GH_EMPTY = "#161b22"
GH_FUTURE = "#10151d"
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
    """Global CSS: terminal-style headers, stat pills, and card-styled widgets."""
    st.markdown(
        f"""
        <style>
        .stApp {{ background: {BG}; }}
        [data-testid="stHeader"] {{ background: transparent; }}
        h1, h2, h3 {{ letter-spacing: -0.01em; }}

        [data-testid="stSidebar"] {{
            background: {SURFACE};
            border-right: 1px solid {BORDER};
        }}
        [data-testid="stExpander"] {{
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}
        [data-testid="stForm"] {{
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}

        .ll-brand {{
            font-size: 1.02rem;
            font-weight: 700;
            color: {INK};
            padding: 0.25rem 0 0.5rem;
        }}
        .ll-brand .ll-prompt {{ color: {ACCENT_BRIGHT}; margin-right: 0.4rem; }}

        .ll-header {{
            margin: 0 0 1rem;
            padding-bottom: 0.6rem;
            border-bottom: 1px solid {BORDER};
        }}
        .ll-header h1 {{ font-size: 1.55rem; margin: 0 0 0.25rem; font-weight: 700; }}
        .ll-header h1 .ll-sl,
        .ll-section h3 .ll-sl {{ color: {ACCENT_BRIGHT}; }}
        .ll-header p {{ color: {INK_MUTED}; margin: 0; font-size: 0.88rem; }}

        .ll-section {{
            margin: 0.4rem 0 0.9rem;
            padding-bottom: 0.45rem;
            border-bottom: 1px solid {BORDER};
        }}
        .ll-section h3 {{ font-size: 1.15rem; margin: 0; font-weight: 700; }}

        .ll-tiles {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
            gap: 0.7rem;
            margin: 0.25rem 0 1rem;
        }}
        .ll-tile {{
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 0.7rem 0.9rem 0.6rem;
        }}
        .ll-tile .ll-label {{
            font-size: 0.74rem;
            color: {INK_MUTED};
            margin-bottom: 0.25rem;
            display: flex;
            align-items: center;
            gap: 0.45rem;
        }}
        .ll-tile .ll-label::before {{
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: {ACCENT_BRIGHT};
            box-shadow: 0 0 6px rgba(86, 211, 100, 0.65);
            flex: none;
        }}
        .ll-tile .ll-value {{
            font-size: 1.35rem;
            font-weight: 700;
            color: {INK};
            font-variant-numeric: tabular-nums;
            line-height: 1.2;
        }}
        .ll-tile .ll-value span {{
            font-size: 0.78rem;
            color: {INK_MUTED};
            font-weight: 500;
            margin-left: 0.15rem;
        }}
        .ll-tile .ll-sub {{ font-size: 0.72rem; color: {INK_MUTED}; margin-top: 0.2rem; }}

        .ll-term {{
            border: 1px solid {BORDER};
            border-radius: 10px;
            overflow: hidden;
            margin: 2.2rem 0 1rem;
        }}
        .ll-term-bar {{
            background: {SURFACE_2};
            padding: 0.55rem 0.9rem;
            display: flex;
            align-items: center;
            gap: 0.45rem;
        }}
        .ll-term-bar .d {{ width: 11px; height: 11px; border-radius: 50%; }}
        .ll-term-bar .d.r {{ background: #f87171; }}
        .ll-term-bar .d.y {{ background: #fbbf24; }}
        .ll-term-bar .d.g {{ background: #34d399; }}
        .ll-term-title {{ color: {INK_MUTED}; font-size: 0.8rem; margin-left: 0.4rem; }}
        .ll-term-body {{
            background: {SURFACE};
            padding: 1rem 1.1rem 1.3rem;
            font-size: 0.9rem;
            color: {INK_SECONDARY};
            line-height: 1.8;
        }}
        .ll-term-body .ll-prompt {{ color: {ACCENT_BRIGHT}; }}
        .ll-term-body .hl {{ color: {AMBER_BRIGHT}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="ll-header"><h1><span class="ll-sl">//</span> {title}</h1>'
        f"<p>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )


def section_header(title: str) -> None:
    st.markdown(
        f'<div class="ll-section"><h3><span class="ll-sl">//</span> {title}</h3></div>',
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

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown(
            '<div class="ll-term">'
            '<div class="ll-term-bar"><span class="d r"></span><span class="d y"></span>'
            '<span class="d g"></span>'
            '<span class="ll-term-title">user@load-log: ~</span></div>'
            '<div class="ll-term-body">'
            'load-log <span class="ll-prompt">//</span> personal health terminal<br>'
            "habits · workouts · progressive overload<br>"
            '<span class="ll-prompt">❯</span> <span class="hl">log in</span> to continue'
            "</div></div>",
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


def _selection_ring(
    df: pd.DataFrame, select_day: alt.Parameter, dow_order: list[str]
) -> alt.Chart:
    """Bright outline layered over the clicked cell, so the selected day stands
    out from its neighbors regardless of the cell's fill shade."""
    return (
        alt.Chart(df)
        .mark_rect(fillOpacity=0, stroke=SELECTED_RING, strokeWidth=2, cornerRadius=2)
        .encode(
            # No explicit axis: an `axis=None` here would win the layer merge
            # and hide the month labels the base layer puts on the shared axis.
            x=alt.X("week:O", title=None),
            y=alt.Y("dow:O", sort=dow_order, title=None),
        )
        .transform_filter(select_day)
    )


def _month_axis(week_starts: pd.DataFrame) -> alt.Axis:
    """Top x-axis that names the first week of each month, GitHub style.

    The labels ride the axis (via labelExpr) rather than a vconcat'd text
    chart: Vega-Lite can only autosize single/layered views to the container,
    so a concat chart ignores Streamlit's stretch width and its cells overflow
    the card it sits in.
    """
    labels = {
        str(int(w)): m
        for w, m in zip(week_starts["week"], week_starts["month_label"])
        if m
    }
    return alt.Axis(
        orient="top",
        ticks=False,
        domain=False,
        labelAngle=0,
        labelAlign="left",
        labelPadding=6,
        labelExpr=f"{json.dumps(labels)}[datum.value] || ''",
    )


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
            x=alt.X("week:O", title=None, axis=_month_axis(week_starts)),
            y=alt.Y("dow:O", sort=dow_order, title=None),
            color=alt.Color("color:N", scale=None, legend=None),
            stroke=alt.condition(
                "datum.is_today", alt.value(TODAY_RING), alt.value(BG)
            ),
            strokeWidth=alt.condition("datum.is_today", alt.value(2), alt.value(1)),
            tooltip=[
                alt.Tooltip("date_pretty:N", title="Date"),
                alt.Tooltip("status:N", title="Status"),
            ],
        )
        .add_params(select_day)
        .properties(height=150)
    )
    ring = _selection_ring(df, select_day, dow_order)
    return rects + ring


# %%
# Habits Page #


def page_habits():
    page_header(
        "daily habits", "keep the streaks alive — click any cell to toggle a day"
    )
    token = _token()

    with st.sidebar:
        st.subheader("add habit")
        new_name = st.text_input("Name", key="new_habit_name")
        if st.button("Add", key="add_habit_btn") and new_name.strip():
            api_client.add_habit(token, new_name.strip())
            st.rerun()

        st.divider()
        st.subheader("your habits")
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
                "(click a cell to pick another day — white outline = selected, "
                "amber = today)"
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
            x=alt.X("week:O", title=None, axis=_month_axis(week_starts)),
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
            tooltip=[
                alt.Tooltip("date_pretty:N", title="Date"),
                alt.Tooltip("volume:Q", title="Volume (lbs)", format=",.0f"),
            ],
        )
        .add_params(select_day)
        .properties(height=160)
    )
    ring = _selection_ring(df, select_day, dow_order)
    return rects + ring


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
                alt.GradientStop(color="#2ea04300", offset=0),
                alt.GradientStop(color="#2ea04355", offset=1),
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
        scale=alt.Scale(domain=["Each set", "Daily best"], range=[AMBER, ACCENT]),
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
        "workouts",
        "log sets, watch total volume accumulate, track strength via estimated 1RM",
    )
    token = _token()

    today = browser_today()
    if "workout_date_input" not in st.session_state:
        st.session_state["workout_date_input"] = today
    volumes = api_client.get_volume_by_date(token, days=400)

    event = st.altair_chart(
        build_volume_heatmap(volumes, today),
        width="stretch",
        theme=None,
        on_select="rerun",
        key="workout_heatmap",
    )
    # The heatmap selection persists across reruns, so only a *new* click moves
    # the date — otherwise the picker below stays in charge.
    clicked = _selected_date_from_event(event)
    if (
        clicked
        and clicked <= today
        and clicked.isoformat() != st.session_state.get("workout_heatmap_click")
    ):
        st.session_state["workout_heatmap_click"] = clicked.isoformat()
        st.session_state["workout_date_input"] = clicked

    st.caption(
        "Click a cell to jump to that day — white outline = selected, amber = today"
    )

    # The date widget renders further down (inside the log-sets section), but its
    # value already lives in session_state, so the day summary can use it here.
    picked = st.session_state["workout_date_input"]
    sets = api_client.get_sets_for_date(token, picked)
    _day_stat_tiles(picked, sets, volumes)

    section_header("log sets")
    date_col, _ = st.columns([1, 2])
    picked = date_col.date_input(
        "Workout date",
        key="workout_date_input",
        max_value=today,
        help="Defaults to today — pick any past day to add or fix sets.",
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
                "day volume",
                f"{day_volume:,.0f} <span>lbs</span>",
                f"{picked:%a %b %-d}",
            ),
            (
                "sets logged",
                f"{len(sets)}",
                f"{n_exercises} exercise{'s' if n_exercises != 1 else ''}",
            ),
            (
                "best est. 1RM",
                f"{best_e1rm:,.0f} <span>lbs</span>" if best_e1rm else "—",
                "epley, best set of the day",
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
    section_header("exercise history")
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
                "best est. 1RM",
                f"{best_row['best_e1rm']:,.0f} <span>lbs</span>",
                f"{best_row['workout_date']:%b %-d, %Y}",
            ),
            (
                "latest est. 1RM",
                f"{latest['best_e1rm']:,.0f} <span>lbs</span>",
                f"{latest['workout_date']:%b %-d, %Y}",
            ),
            (
                "best day volume",
                f"{best_vol['volume_lbs']:,.0f} <span>lbs</span>",
                f"{best_vol['workout_date']:%b %-d, %Y}",
            ),
            ("sessions", f"{len(daily)}", f"{len(df)} sets in the last year"),
        ]
    )

    tab_volume, tab_e1rm = st.tabs(["total volume", "estimated 1RM"])
    with tab_volume:
        st.altair_chart(build_volume_chart(daily), width="stretch", theme=None)
        st.caption("Total volume = Σ reps × weight across every set that day.")
    with tab_e1rm:
        st.altair_chart(build_e1rm_chart(df, daily), width="stretch", theme=None)
        st.caption(
            "Estimated 1RM (Epley): weight × (1 + reps ÷ 30) per set; the line tracks "
            "each day's best set. Estimates get rough above ~12 reps."
        )

    with st.expander("all sets (last year)"):
        _history_set_editor(df, ex_id)


def _history_set_editor(df: pd.DataFrame, ex_id: int) -> None:
    """Editable per-set history table. Edits to reps/weight persist on commit
    (tab-out or Enter) via update_set; volume and est. 1RM refresh on rerun."""
    st.caption("Click a Reps or Weight cell to edit — changes save immediately.")
    table = pd.DataFrame(
        {
            "id": df["id"],
            "Date": df["workout_date"].dt.date,
            "Set": df["set_number"],
            "Reps": df["reps"],
            "Weight (lbs)": df["weight_lbs"],
            "Volume (lbs)": df["volume_lbs"],
            "Est. 1RM (lbs)": df["e1rm_lbs"].round(1),
        }
    )
    edited = st.data_editor(
        table,
        column_config={
            "id": None,
            "Date": st.column_config.DateColumn("Date", disabled=True),
            "Set": st.column_config.NumberColumn("Set", disabled=True),
            "Reps": st.column_config.NumberColumn(
                "Reps",
                required=True,
                min_value=1,
                max_value=100,
                step=1,
                format="%d",
            ),
            "Weight (lbs)": st.column_config.NumberColumn(
                "Weight (lbs)",
                required=True,
                min_value=0.0,
                max_value=2000.0,
                step=2.5,
            ),
            "Volume (lbs)": st.column_config.NumberColumn(
                "Volume (lbs)", disabled=True
            ),
            "Est. 1RM (lbs)": st.column_config.NumberColumn(
                "Est. 1RM (lbs)", disabled=True
            ),
        },
        width="stretch",
        hide_index=True,
        key=f"history_editor_{ex_id}",
    )

    token = _token()
    orig_map = {int(r["id"]): r for _, r in table.iterrows()}
    changed = False
    for _, row in edited.iterrows():
        sid = int(row["id"])
        orig = orig_map[sid]
        if int(row["Reps"]) != int(orig["Reps"]) or float(row["Weight (lbs)"]) != float(
            orig["Weight (lbs)"]
        ):
            api_client.update_set(
                token, sid, int(row["Reps"]), float(row["Weight (lbs)"])
            )
            changed = True
    if changed:
        st.rerun()


# %%
# Router #

PAGES = {
    "habits": page_habits,
    "workouts": page_workouts,
}

if require_login():
    with st.sidebar:
        st.markdown(
            '<div class="ll-brand"><span class="ll-prompt">❯</span>load-log</div>',
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
