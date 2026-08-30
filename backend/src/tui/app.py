# %%
# Imports #

import os
import sys

# Ensure src/ on path when launched via `python -m tui.app`
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from textual.app import App  # noqa: E402

import api_client  # noqa: E402
import bootstrap  # noqa: E402
import config  # noqa: E402,F401  side effect: loads the repo .env into os.environ
from tui.habits import HabitsScreen  # noqa: E402
from tui.workouts import WorkoutsScreen  # noqa: E402

# %%
# App #


class LoadLogApp(App):
    TITLE = "Load Log"

    CSS = """
    Screen { background: $surface; }

    /* Single bold screen heading. No bracketed key hints — the Footer at the
       bottom is the source of truth for shortcuts and it's clickable. */
    #title {
        height: 1;
        padding: 0 2;
        color: $accent;
        text-style: bold;
    }
    #subtitle {
        height: 1;
        padding: 0 2;
        color: $text-muted;
    }

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

    /* Set-logging form */
    .form-label { width: 16; padding: 1 0; color: $text-muted; }

    /* Set-row in the "logged this day" list */
    .set-row { height: 3; padding: 0 1; }
    .set-row > .set-text { width: 1fr; padding: 1 0; }
    """

    BINDINGS = [
        ("h", "show_habits", "Habits"),
        ("w", "show_workouts", "Workouts"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, token: str) -> None:
        super().__init__()
        # JWT from the auth service; threaded into every screen, which sends it
        # as a Bearer token on each PostgREST request via api_client.
        self.token = token

    def on_mount(self) -> None:
        self.push_screen(HabitsScreen(self.token))

    def action_show_habits(self) -> None:
        self.pop_screen() if len(self.screen_stack) > 1 else None
        self.push_screen(HabitsScreen(self.token))

    def action_show_workouts(self) -> None:
        self.pop_screen() if len(self.screen_stack) > 1 else None
        self.push_screen(WorkoutsScreen(self.token))


def main() -> None:
    # Converge the schema before logging in, for the same reason the web app
    # does it (I6): the TUI is a first-class entry point, so starting it must not
    # depend on a container having started first. Best-effort — a schema problem
    # is logged, not a reason the TUI refuses to open.
    bootstrap.bootstrap_best_effort()

    # The TUI is just another PostgREST client: get a JWT from the auth service
    # with credentials from the environment (.env), then run. Non-interactive so
    # it works headless / scripted, identically to any other client.
    username = os.environ.get("LOAD_LOG_USERNAME")
    password = os.environ.get("LOAD_LOG_PASSWORD")
    if not username or not password:
        sys.exit(
            "Set LOAD_LOG_USERNAME and LOAD_LOG_PASSWORD (in your .env) to run the TUI."
        )
    try:
        token = api_client.login(username, password)
    except Exception as exc:  # noqa: BLE001 — surface any login/network failure cleanly
        sys.exit(f"Login failed: {exc}")
    LoadLogApp(token).run()


if __name__ == "__main__":
    main()
