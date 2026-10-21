# %%
# Imports #

from datetime import date, timedelta

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

import api_client

# %%
# Constants #

HEATMAP_WEEKS = 18  # ~4 months fits comfortably in a standard terminal


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
        color: white;
    }
    DayCell.empty { background: #ebedf0; color: #999; }
    DayCell.done  { background: #216e39; color: white; }
    DayCell.future { background: #f6f8fa; color: #ccc; }
    DayCell.today { text-style: bold; color: #ff8c00; }
    DayCell.today.done { color: #ffcc00; }
    DayCell.selected { background: #ffcc00; color: black; text-style: bold; }
    """

    GLYPH_DEFAULT = "■"
    GLYPH_TODAY = "◉"

    def __init__(
        self, day_date: date, completed: bool, is_today: bool, is_future: bool
    ):
        super().__init__(self.GLYPH_TODAY if is_today else self.GLYPH_DEFAULT)
        self.day_date = day_date
        self.completed = completed
        self.is_today = is_today
        self.is_future = is_future
        self.set_status_class()

    def set_status_class(self) -> None:
        self.remove_class("empty", "done", "future", "today", "selected")
        if self.completed:
            self.add_class("done")
        elif self.is_future:
            self.add_class("future")
        else:
            self.add_class("empty")
        if self.is_today:
            self.add_class("today")

    def on_click(self) -> None:
        self.post_message(DaySelected(self.day_date))


# %%
# Habit list item #


class HabitItem(ListItem):
    def __init__(self, habit: dict, done_today: bool, streak: int):
        check = "✓" if done_today else "✗"
        name = habit["name"]
        text = f" {check}  {name:<28}  streak: {streak:>3}d"
        super().__init__(Label(text))
        self.habit = habit


# %%
# Habits list screen #


class HabitsScreen(Screen):
    BINDINGS = [
        ("a", "focus_add", "Add"),
        ("enter", "view_selected", "View"),
        ("space", "toggle_today_selected", "Toggle today"),
        ("delete", "delete_selected", "Delete"),
    ]

    def __init__(self, token: str):
        super().__init__()
        # JWT from api_client.login — sent as a Bearer token on every PostgREST
        # call via api_client. Threaded in from the app.
        self.token = token

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("Habits", id="title")
        yield Static(
            "Daily tracker — pick a habit and view its heatmap.",
            id="subtitle",
        )
        with Vertical(classes="panel"):
            with Horizontal(classes="row"):
                yield Input(placeholder="new habit name…", id="new-habit")
                yield Button("Add", id="add-habit", variant="success")
        yield ListView(id="habit-list")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        lv = self.query_one("#habit-list", ListView)
        keep_index = lv.index or 0
        lv.clear()
        today = date.today()
        for h in api_client.get_all_habits(self.token):
            completions = set(api_client.get_completions(self.token, h["id"], days=30))
            lv.append(
                HabitItem(
                    habit=h,
                    done_today=today in completions,
                    streak=api_client.get_current_streak(self.token, h["id"]),
                )
            )
        if len(lv):
            lv.index = min(keep_index, len(lv) - 1)

    # %%
    # Actions #

    def action_focus_add(self) -> None:
        self.query_one("#new-habit", Input).focus()

    def _selected(self) -> HabitItem | None:
        lv = self.query_one("#habit-list", ListView)
        item = lv.highlighted_child
        return item if isinstance(item, HabitItem) else None

    def action_view_selected(self) -> None:
        item = self._selected()
        if item is not None:
            self.app.push_screen(HabitDetailScreen(item.habit, self.token))

    def action_toggle_today_selected(self) -> None:
        item = self._selected()
        if item is not None:
            api_client.toggle_completion(self.token, item.habit["id"], date.today())
            self.refresh_list()

    def action_delete_selected(self) -> None:
        item = self._selected()
        if item is not None:
            api_client.delete_habit(self.token, item.habit["id"])
            self.refresh_list()

    # %%
    # Events #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-habit":
            inp = self.query_one("#new-habit", Input)
            name = inp.value.strip()
            if name:
                api_client.add_habit(self.token, name)
                inp.value = ""
                self.refresh_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "new-habit":
            name = event.value.strip()
            if name:
                api_client.add_habit(self.token, name)
                event.input.value = ""
                self.refresh_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, HabitItem):
            self.app.push_screen(HabitDetailScreen(event.item.habit, self.token))


# %%
# Detail screen with heatmap #


class HabitDetailScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("t", "toggle_selected", "Toggle selected"),
        ("T", "toggle_today", "Toggle today"),
    ]

    def __init__(self, habit: dict, token: str):
        super().__init__()
        self.habit = habit
        self.token = token
        self.selected_date: date = date.today()
        self._cell_index: dict[date, DayCell] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(self.habit["name"], id="title")
        yield Static("Click a day in the heatmap to select it.", id="subtitle")
        yield Static("", id="streak")
        yield Static("", id="month-row")
        with VerticalScroll(id="heatmap-wrap", classes="panel"):
            yield Horizontal(id="heatmap-grid")
        yield Static("", id="selected-info")
        with Horizontal(classes="row"):
            yield Button("Toggle selected (t)", id="toggle-selected", variant="primary")
            yield Button("Toggle today (T)", id="toggle-today")
            yield Button("Back (esc)", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        today = date.today()
        completions = set(
            api_client.get_completions(self.token, self.habit["id"], days=365)
        )
        streak = api_client.get_current_streak(self.token, self.habit["id"])

        self.query_one("#streak", Static).update(
            f"Current streak: {streak} day{'s' if streak != 1 else ''}"
        )

        start = (
            today - timedelta(days=today.weekday()) - timedelta(weeks=HEATMAP_WEEKS - 1)
        )

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
                    completed=day in completions,
                    is_today=day == today,
                    is_future=day > today,
                )
                col.mount(cell)
                self._cell_index[day] = cell

        # Month label row, aligned to columns (each col = 3 chars).
        labels: list[str] = ["    "]  # 4-char spacer over the dow column
        last_month = ""
        for w in range(HEATMAP_WEEKS):
            week_start = start + timedelta(weeks=w)
            month = week_start.strftime("%b")
            labels.append(f"{month:<3}" if month != last_month else "   ")
            last_month = month
        self.query_one("#month-row", Static).update("".join(labels))

        self._refresh_selection()

    def _refresh_selection(self) -> None:
        completions = set(
            api_client.get_completions(self.token, self.habit["id"], days=365)
        )
        for day, cell in self._cell_index.items():
            cell.completed = day in completions
            cell.set_status_class()
        selected = self._cell_index.get(self.selected_date)
        if selected is not None:
            selected.add_class("selected")

        is_done = self.selected_date in completions
        status = "✓ completed" if is_done else "✗ not done"
        self.query_one("#selected-info", Static).update(
            f"Selected: {self.selected_date.strftime('%a %b %d, %Y')} — {status}"
        )

    # %%
    # Events #

    def on_day_selected(self, message: DaySelected) -> None:
        self.selected_date = message.day_date
        self._refresh_selection()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "toggle-selected":
            self.action_toggle_selected()
        elif button_id == "toggle-today":
            self.action_toggle_today()
        elif button_id == "back":
            self.action_back()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_toggle_selected(self) -> None:
        api_client.toggle_completion(self.token, self.habit["id"], self.selected_date)
        self._refresh_selection()

    def action_toggle_today(self) -> None:
        self.selected_date = date.today()
        api_client.toggle_completion(self.token, self.habit["id"], date.today())
        self._refresh_selection()
