# %%
# Imports #

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

import workouts as workouts_mod

# %%
# Screen #


class WorkoutsScreen(Screen):
    current_session_id: int | None = None
    current_exercise_id: int | None = None
    current_exercise_name: str = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("Workouts — press [h] habits, [w] workouts, [q] quit", id="title")

        with Vertical(classes="panel"):
            with Horizontal(classes="row"):
                yield Button("New Session", id="new-session", variant="success")
                yield Static("", id="session-label")

        with Vertical(classes="panel"):
            yield Static("Exercise:")
            with Horizontal(classes="row"):
                yield Input(placeholder="e.g. bench press", id="exercise-name")
                yield Button("Select", id="select-exercise", variant="primary")
            yield Static("", id="last-session")

        with Vertical(classes="panel"):
            yield Static("Log a set:")
            with Horizontal(classes="row"):
                yield Input(placeholder="reps", id="reps-input")
                yield Input(placeholder="weight (lbs)", id="weight-input")
                yield Button("Log", id="log-set", variant="success")

        yield Static("This session:", classes="row")
        yield VerticalScroll(id="set-list", classes="panel")

        with Vertical(classes="panel"):
            with Horizontal(classes="row"):
                yield Input(placeholder="session notes", id="notes-input")
                yield Button("Save notes", id="save-notes")
                yield Button("Finish & suggest", id="finish-session", variant="warning")

        yield Footer()

    def on_mount(self) -> None:
        recent = workouts_mod.get_recent_sessions(limit=1)
        if recent:
            self._activate_session(recent[0]["id"])

    # %%
    # Helpers #

    def _activate_session(self, session_id: int) -> None:
        self.current_session_id = session_id
        sessions = {s["id"]: s for s in workouts_mod.get_recent_sessions(limit=50)}
        s = sessions.get(session_id)
        label = f"Session #{session_id} ({s['session_date']})" if s else f"Session #{session_id}"
        self.query_one("#session-label", Static).update(label)
        self.query_one("#notes-input", Input).value = s["notes"] if s else ""
        self.refresh_sets()

    def refresh_sets(self) -> None:
        container = self.query_one("#set-list", VerticalScroll)
        container.remove_children()
        if self.current_session_id is None:
            return
        sets = workouts_mod.get_session_sets(self.current_session_id)
        for s in sets:
            container.mount(
                Static(
                    f"  {s['exercise_name']}  set {s['set_number']}: "
                    f"{s['reps']} reps @ {s['weight_lbs']:g} lbs"
                )
            )

    def _show_last_session(self) -> None:
        target = self.query_one("#last-session", Static)
        if self.current_exercise_id is None or self.current_session_id is None:
            target.update("")
            return
        last = workouts_mod.get_last_session_for_exercise(
            self.current_exercise_id, before_session_id=self.current_session_id
        )
        if not last:
            target.update(f"  {self.current_exercise_name}: no prior history.")
            return
        summary = ", ".join(f"{s['reps']}×{s['weight_lbs']:g}" for s in last)
        target.update(
            f"  {self.current_exercise_name} — last ({last[0]['session_date']}): {summary}"
        )

    # %%
    # Events #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "new-session":
            session = workouts_mod.create_session()
            self._activate_session(session["id"])
        elif button_id == "select-exercise":
            name = self.query_one("#exercise-name", Input).value.strip()
            if not name:
                return
            ex = workouts_mod.get_or_create_exercise(name)
            self.current_exercise_id = ex["id"]
            self.current_exercise_name = ex["name"]
            self._show_last_session()
        elif button_id == "log-set":
            self._log_set()
        elif button_id == "save-notes":
            if self.current_session_id is not None:
                notes = self.query_one("#notes-input", Input).value
                workouts_mod.update_session_notes(self.current_session_id, notes)
        elif button_id == "finish-session":
            self._finish_session()

    def _log_set(self) -> None:
        if self.current_session_id is None or self.current_exercise_id is None:
            return
        reps_input = self.query_one("#reps-input", Input)
        weight_input = self.query_one("#weight-input", Input)
        try:
            reps = int(reps_input.value)
            weight = float(weight_input.value)
        except ValueError:
            return

        existing = [
            s for s in workouts_mod.get_session_sets(self.current_session_id)
            if s["exercise_id"] == self.current_exercise_id
        ]
        next_num = max((s["set_number"] for s in existing), default=0) + 1
        workouts_mod.add_set(
            self.current_session_id,
            self.current_exercise_id,
            next_num,
            reps,
            weight,
        )
        reps_input.value = ""
        weight_input.value = ""
        self.refresh_sets()

    def _finish_session(self) -> None:
        if self.current_session_id is None:
            return
        container = self.query_one("#set-list", VerticalScroll)
        container.mount(Static("— Suggestions for next time —"))
        sets = workouts_mod.get_session_sets(self.current_session_id)
        seen: set[int] = set()
        for s in sets:
            if s["exercise_id"] in seen:
                continue
            seen.add(s["exercise_id"])
            suggestion = workouts_mod.suggest_next_weight(
                s["exercise_id"], self.current_session_id
            )
            if suggestion is None:
                container.mount(Static(f"  {s['exercise_name']}: build a baseline"))
            else:
                container.mount(
                    Static(f"  {s['exercise_name']}: try {suggestion:g} lbs")
                )
