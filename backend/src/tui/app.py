# %%
# Imports #

import os
import sys

# Ensure src/ on path when launched via `python -m tui.app`
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from textual.app import App  # noqa: E402

from db import bootstrap  # noqa: E402
from tui.habits import HabitsScreen  # noqa: E402
from tui.workouts import WorkoutsScreen  # noqa: E402

# %%
# App #


class LoadLogApp(App):
    CSS = """
    Screen { background: $surface; }
    #title { padding: 1 2; color: $text; text-style: bold; }
    .row { height: 3; padding: 0 1; }
    .panel { padding: 1 2; border: round $primary; }
    Button { margin: 0 1; }

    /* Habit detail heatmap */
    #streak { padding: 0 2; color: $text-muted; }
    #month-row { height: 1; padding: 0 2; color: $text-muted; }
    #heatmap-wrap { height: auto; }
    #heatmap-grid { height: 7; }
    .dow-col { width: 4; }
    .dow-label { width: 4; height: 1; color: $text-muted; }
    .week-col { width: 3; }
    #selected-info { padding: 1 2; color: $accent; text-style: bold; }
    """

    BINDINGS = [
        ("h", "show_habits", "Habits"),
        ("w", "show_workouts", "Workouts"),
        ("q", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        bootstrap()
        self.push_screen(HabitsScreen())

    def action_show_habits(self) -> None:
        self.pop_screen() if len(self.screen_stack) > 1 else None
        self.push_screen(HabitsScreen())

    def action_show_workouts(self) -> None:
        self.pop_screen() if len(self.screen_stack) > 1 else None
        self.push_screen(WorkoutsScreen())


def main() -> None:
    LoadLogApp().run()


if __name__ == "__main__":
    main()
