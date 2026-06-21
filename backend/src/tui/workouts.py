# %%
# Imports #

from datetime import date, timedelta

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

import api_client

# %%
# Constants #

HEATMAP_WEEKS = 18
VOLUME_SHADES = [
    "#ebedf0",  # 0 — no volume
    "#9be9a8",
    "#40c463",
    "#30a14e",
    "#216e39",
]


# %%
# Heatmap cell #


class DaySelected(Message):
    def __init__(self, day_date: date) -> None:
        super().__init__()
        self.day_date = day_date


class DayCell(Static):
    DEFAULT_CSS = """
    DayCell {
        width: 3;
        height: 1;
        content-align: center middle;
    }
    DayCell.v0 { background: #ebedf0; color: #999; }
    DayCell.v1 { background: #9be9a8; color: #1a4a23; }
    DayCell.v2 { background: #40c463; color: white; }
    DayCell.v3 { background: #30a14e; color: white; }
    DayCell.v4 { background: #216e39; color: white; }
    DayCell.future { background: #f6f8fa; color: #ccc; }
    DayCell.today { text-style: bold; color: #ff8c00; }
    DayCell.selected { background: #ffcc00; color: black; text-style: bold; }
    """

    GLYPH_DEFAULT = "■"
    GLYPH_TODAY = "◉"

    def __init__(
        self,
        day_date: date,
        volume: float,
        max_volume: float,
        is_today: bool,
        is_future: bool,
    ):
        super().__init__(self.GLYPH_TODAY if is_today else self.GLYPH_DEFAULT)
        self.day_date = day_date
        self.volume = volume
        self.max_volume = max_volume
        self.is_today = is_today
        self.is_future = is_future
        self.set_status_class()

    def _shade(self) -> str:
        if self.is_future or self.volume <= 0 or self.max_volume <= 0:
            return "v0"
        frac = self.volume / self.max_volume
        if frac < 0.25:
            return "v1"
        if frac < 0.5:
            return "v2"
        if frac < 0.75:
            return "v3"
        return "v4"

    def set_status_class(self) -> None:
        self.remove_class(
            "v0", "v1", "v2", "v3", "v4", "future", "today", "selected"
        )
        if self.is_future:
            self.add_class("future")
        else:
            self.add_class(self._shade())
        if self.is_today:
            self.add_class("today")

    def on_click(self) -> None:
        self.post_message(DaySelected(self.day_date))


# %%
# Screen #


class WorkoutsScreen(Screen):
    BINDINGS = [
        ("t", "select_today", "Today"),
    ]

    def __init__(self, token: str) -> None:
        super().__init__()
        # JWT from the auth service — sent as a Bearer token on every PostgREST
        # call via api_client. Threaded in from the app.
        self.token = token
        self.selected_date: date = date.today()
        self.current_exercise_id: int | None = None
        self.current_exercise_name: str = ""
        self._cell_index: dict[date, DayCell] = {}
        # When editing an existing set, this holds the row id; None = adding.
        self._editing_set_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("Workouts", id="title")
        yield Static(
            "Click a day on the heatmap to pick it · enter on either field logs the set.",
            id="subtitle",
        )
        yield Static("", id="month-row")
        with VerticalScroll(id="heatmap-wrap", classes="panel"):
            yield Horizontal(id="heatmap-grid")
        yield Static("", id="selected-info")

        with Vertical(classes="panel"):
            yield Static("Exercise (enter or pick to start logging):")
            with Horizontal(classes="row"):
                yield Input(placeholder="e.g. bench press", id="exercise-name")
                yield Button("Select", id="select-exercise", variant="primary")
            yield Static("", id="last-workout")

        with Vertical(classes="panel", id="form-panel"):
            yield Static("Log a set — enter in either field submits:", id="form-title")
            with Horizontal(classes="row"):
                yield Static("Reps:", classes="form-label")
                yield Input(
                    placeholder="e.g. 8",
                    id="reps-input",
                    restrict=r"[0-9]*",
                )
            with Horizontal(classes="row"):
                yield Static("Weight (lbs):", classes="form-label")
                yield Input(
                    placeholder="e.g. 135 or 47.5",
                    id="weight-input",
                    restrict=r"[0-9]*\.?[0-9]*",
                )
            with Horizontal(classes="row"):
                yield Button("Log set", id="log-set", variant="success")
                yield Button("Cancel edit", id="cancel-edit", variant="warning")

        yield Static("Sets logged on selected date:", classes="row")
        yield VerticalScroll(id="set-list", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()

    # %%
    # Rendering #

    def refresh_view(self) -> None:
        today = date.today()
        volumes = api_client.get_volume_by_date(self.token, days=HEATMAP_WEEKS * 7 + 14)
        max_volume = max(volumes.values()) if volumes else 0.0

        start = today - timedelta(days=today.weekday()) - timedelta(weeks=HEATMAP_WEEKS - 1)

        grid = self.query_one("#heatmap-grid", Horizontal)
        grid.remove_children()
        self._cell_index.clear()

        dow_col = Vertical(classes="dow-col")
        grid.mount(dow_col)
        for label in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            dow_col.mount(Static(label, classes="dow-label"))

        for w in range(HEATMAP_WEEKS):
            col = Vertical(classes="week-col")
            grid.mount(col)
            week_start = start + timedelta(weeks=w)
            for d in range(7):
                day = week_start + timedelta(days=d)
                cell = DayCell(
                    day_date=day,
                    volume=volumes.get(day, 0.0),
                    max_volume=max_volume,
                    is_today=day == today,
                    is_future=day > today,
                )
                col.mount(cell)
                self._cell_index[day] = cell

        labels: list[str] = ["    "]
        last_month = ""
        for w in range(HEATMAP_WEEKS):
            week_start = start + timedelta(weeks=w)
            month = week_start.strftime("%b")
            labels.append(f"{month:<3}" if month != last_month else "   ")
            last_month = month
        self.query_one("#month-row", Static).update("".join(labels))

        self._refresh_selection()
        self._refresh_set_list()
        self._refresh_last_workout()

    def _refresh_selection(self) -> None:
        for day, cell in self._cell_index.items():
            cell.set_status_class()
        cell = self._cell_index.get(self.selected_date)
        if cell is not None:
            cell.add_class("selected")

        volume = api_client.get_volume_by_date(self.token, days=400).get(self.selected_date, 0.0)
        self.query_one("#selected-info", Static).update(
            f"Selected: {self.selected_date.strftime('%a %b %d, %Y')}  •  "
            f"volume: {volume:,.0f} lbs"
        )

    def _refresh_set_list(self) -> None:
        container = self.query_one("#set-list", VerticalScroll)
        container.remove_children()
        sets = api_client.get_sets_for_date(self.token, self.selected_date)
        if not sets:
            container.mount(Static("  (no sets logged)"))
            self._update_form_mode_label()
            return
        for s in sets:
            row = Horizontal(classes="set-row")
            container.mount(row)
            row.mount(
                Static(
                    f" {s['exercise_name']:<20} #{s['set_number']:>2}  "
                    f"{s['reps']:>3} reps @ {s['weight_lbs']:>6g} lbs",
                    classes="set-text",
                )
            )
            row.mount(Button("Edit", id=f"edit-set-{s['id']}", variant="primary"))
            row.mount(Button("Delete", id=f"del-set-{s['id']}", variant="error"))
        self._update_form_mode_label()

    def _update_form_mode_label(self) -> None:
        title = self.query_one("#form-title", Static)
        cancel = self.query_one("#cancel-edit", Button)
        log_btn = self.query_one("#log-set", Button)
        if self._editing_set_id is None:
            title.update("Log a set — enter in either field submits:")
            log_btn.label = "Log set"
            cancel.display = False
        else:
            title.update(
                f"Editing set #{self._editing_set_id} — change reps/weight, "
                "enter saves:"
            )
            log_btn.label = "Save changes"
            cancel.display = True

    def _refresh_last_workout(self) -> None:
        target = self.query_one("#last-workout", Static)
        if self.current_exercise_id is None:
            target.update("")
            return
        last = api_client.get_last_workout_for_exercise(
            self.token, self.current_exercise_id, before_date=self.selected_date
        )
        if not last:
            target.update(f"  {self.current_exercise_name}: no prior history.")
            return
        summary = ", ".join(f"{s['reps']}×{s['weight_lbs']:g}" for s in last)
        target.update(
            f"  {self.current_exercise_name} — last ({last[0]['workout_date']}): {summary}"
        )

    # %%
    # Events #

    def on_day_selected(self, message: DaySelected) -> None:
        self.selected_date = message.day_date
        self._refresh_selection()
        self._refresh_set_list()
        self._refresh_last_workout()

    def action_select_today(self) -> None:
        self.selected_date = date.today()
        self._refresh_selection()
        self._refresh_set_list()
        self._refresh_last_workout()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "select-exercise":
            self._select_exercise_from_input()
        elif button_id == "log-set":
            self._submit_set()
        elif button_id == "cancel-edit":
            self._cancel_edit()
        elif button_id.startswith("edit-set-"):
            self._start_editing(int(button_id.removeprefix("edit-set-")))
        elif button_id.startswith("del-set-"):
            api_client.delete_set(self.token, int(button_id.removeprefix("del-set-")))
            # If we were editing this row, drop back to add mode.
            if self._editing_set_id == int(button_id.removeprefix("del-set-")):
                self._cancel_edit()
            self._refresh_set_list()
            self._refresh_selection()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "exercise-name":
            self._select_exercise_from_input()
        elif event.input.id == "reps-input":
            # Move to the weight field if it's still empty; otherwise log.
            weight = self.query_one("#weight-input", Input)
            if weight.value.strip():
                self._submit_set()
            else:
                weight.focus()
        elif event.input.id == "weight-input":
            self._submit_set()

    # %%
    # Actions #

    def _select_exercise_from_input(self) -> None:
        name = self.query_one("#exercise-name", Input).value.strip()
        if not name:
            return
        ex = api_client.get_or_create_exercise(self.token, name)
        self.current_exercise_id = ex["id"]
        self.current_exercise_name = ex["name"]
        self._refresh_last_workout()
        self._prefill_inputs()
        self.query_one("#reps-input", Input).focus()

    def _prefill_inputs(self) -> None:
        """Reps/weight come from today's last logged set if we've started this
        exercise on the selected day, otherwise from the last workout's last set.
        """
        if self.current_exercise_id is None:
            return
        today_sets = [
            s for s in api_client.get_sets_for_date(self.token, self.selected_date)
            if s["exercise_id"] == self.current_exercise_id
        ]
        source = None
        if today_sets:
            source = today_sets[-1]
        else:
            last = api_client.get_last_workout_for_exercise(
                self.token, self.current_exercise_id, before_date=self.selected_date
            )
            if last:
                source = last[-1]
        if source is not None:
            self.query_one("#reps-input", Input).value = f"{source['reps']}"
            self.query_one("#weight-input", Input).value = f"{source['weight_lbs']:g}"

    def _submit_set(self) -> None:
        reps_input = self.query_one("#reps-input", Input)
        weight_input = self.query_one("#weight-input", Input)
        try:
            reps = int(reps_input.value)
            weight = float(weight_input.value)
        except ValueError:
            return
        if reps <= 0:
            return

        if self._editing_set_id is not None:
            # Save edit, then drop back to add mode.
            api_client.update_set(self.token, self._editing_set_id, reps, weight)
            self._editing_set_id = None
            reps_input.value = ""
            weight_input.value = ""
            self._refresh_set_list()
            self._refresh_selection()
            self._prefill_inputs()
            reps_input.focus()
            return

        if self.current_exercise_id is None:
            return

        # Commit immediately — survives a crash mid-workout.
        api_client.add_set(
            self.token,
            workout_date=self.selected_date,
            exercise_id=self.current_exercise_id,
            reps=reps,
            weight_lbs=weight,
        )

        self._refresh_set_list()
        self._refresh_selection()  # update volume tally on the heatmap
        self._prefill_inputs()      # set 2/3/... reuses just-logged values
        reps_input.focus()

    def _start_editing(self, set_id: int) -> None:
        target = next(
            (s for s in api_client.get_sets_for_date(self.token, self.selected_date)
             if s["id"] == set_id),
            None,
        )
        if target is None:
            return
        self._editing_set_id = set_id
        # Adopt the row's exercise so the "last workout" reference is right.
        self.current_exercise_id = target["exercise_id"]
        self.current_exercise_name = target["exercise_name"]
        self.query_one("#exercise-name", Input).value = target["exercise_name"]
        self.query_one("#reps-input", Input).value = str(target["reps"])
        self.query_one("#weight-input", Input).value = f"{target['weight_lbs']:g}"
        self._refresh_last_workout()
        self._update_form_mode_label()
        self.query_one("#reps-input", Input).focus()

    def _cancel_edit(self) -> None:
        self._editing_set_id = None
        self.query_one("#reps-input", Input).value = ""
        self.query_one("#weight-input", Input).value = ""
        self._update_form_mode_label()
        self._prefill_inputs()
