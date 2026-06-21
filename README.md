# load-log

Personal health tracker with three UIs over one shared PostgreSQL:

- **TUI** (Textual) — terminal, keyboard-driven, opens instantly.
- **Web** (Streamlit) — browser, GitHub-style heatmaps + inline editing.
- **API** (FastAPI) — HTTP, for automation.

Two features today: a daily **habit tracker** (click any day on the heatmap to
toggle it) and a **workout tracker** (volume heatmap, log sets with
progressive-overload guidance, edit/delete inline).

All three UIs import the same `habits.py` / `workouts.py` modules and talk
to Postgres directly via psycopg2 — there is no app-internal HTTP.

For full design + schema details see [`backend/docs/`](backend/docs/) and
[`CLAUDE.md`](CLAUDE.md).

## Prerequisites

- Python 3.13 (pinned in `backend/.python-version`)
- [uv](https://docs.astral.sh/uv/) — `brew install uv` (macOS) or
  `curl -LsSf https://astral.sh/uv/install.sh | sh` (Linux)
- TCP reachability to the shared Postgres on port `5432` (LAN or VPN)

## One-time setup

```bash
git clone <load-log remote> ~/GitHub/load-log
cd ~/GitHub/load-log

# Create .env at the repo root pointing at the shared Postgres
cp .env.example .env
$EDITOR .env                # fill in POSTGRES_URL / USER / PASSWORD

# Install Python deps
cd backend && uv sync
```

`.env` keys (database optional, defaults to the shared `apps` database):

```env
POSTGRES_URL=<host or LAN IP of the shared Postgres>
POSTGRES_PORT=5432
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<password>
POSTGRES_DB=apps
```

The first run of any UI bootstraps the `load_log` database and creates the
five tables idempotently — no manual SQL.

## Run locally (bare-metal)

All commands below are run from `backend/`.

```bash
# TUI
PYTHONPATH=src uv run python -m tui.app

# Web (Streamlit) — http://localhost:8501
PYTHONPATH=src uv run streamlit run src/web/app.py

# API (FastAPI) — http://localhost:8000  · /docs for Swagger
PYTHONPATH=src uv run uvicorn api:app --reload --port 8000
```

Each UI is independent. You can run all three at the same time against the
same Postgres — they only see each other's writes after a refresh
(Streamlit: any interaction; TUI: re-render via the action that triggered
the change).

### TUI cheatsheet

Anywhere:

- `h` / `w` / `q` — habits screen / workouts screen / quit

Habits list:

- `↑` / `↓` — move highlight between habits
- `enter` — open the heatmap detail view for the highlighted habit
- `space` — toggle today on the highlighted habit
- `delete` — delete the highlighted habit
- `a` — focus the "new habit" input

Habit detail and workouts heatmap:

- click any cell — select that date
- `t` / `T` — toggle the selected day / jump back to today

Workouts log-a-set form:

- `enter` in reps — jump to weight (or submit if weight is already filled)
- `enter` in weight — submit the set
- weight accepts decimals (e.g. `47.5`)
- `Edit` / `Delete` button on each logged set — inline edit or remove

The Footer at the bottom of every screen is the source of truth for the
keyboard shortcuts available right now — and each Footer entry is
clickable.

## Run locally in Docker

`docker-compose.yml` at the repo root brings up the API and Streamlit
containers, both connecting **out** to the shared Postgres (no local DB).

```bash
docker-compose up -d --build
# API: http://localhost:8004
# Web: http://localhost:8505
docker-compose logs -f api
docker-compose down
```

On macOS, Docker runs through [colima](https://github.com/abiosoft/colima).
It is not a brew service, so start it once per session before any
`docker` / `docker-compose` command:

```bash
colima start                         # default 2 CPU / 2 GiB
colima start --cpu 4 --memory 6      # if you want more headroom
colima status
```

## Tests

```bash
cd backend
PYTHONPATH=src uv run pytest -q
```

Tests run against an isolated `load_log_test` database (forced by
`tests/conftest.py` overriding `POSTGRES_DB`). They cannot mutate the
production `load_log` data.

To run a single file:

```bash
PYTHONPATH=src uv run pytest -q tests/test_workouts.py
```

## Lint / format / type-check

```bash
uv run flake8 src/ tests/
uv run black src/ tests/ && uv run isort src/ tests/
uv run mypy src/
```

## DB migrations

`db.ensure_tables()` only ever runs `CREATE TABLE IF NOT EXISTS`. If it
detects a legacy schema, it **raises and refuses to start** — it never
drops or mutates user data. Explicit migrations live in
[`backend/scripts/`](backend/scripts/) (e.g. `migrate_drop_sessions.py`),
back up the affected tables to timestamped copies before mutating, and
have to be run by hand:

```bash
cd backend
PYTHONPATH=src uv run python scripts/migrate_drop_sessions.py
```

## Production deployment (EliteDesk)

The two services `load-log-fastapi` and `load-log-streamlit` are appended
to `~/GitHub/Docker/docker_compose_projects.yaml`. Deploy commands and the
systemd unit live in `~/GitHub/Docker/README.md`. See
[`backend/docs/architecture.md`](backend/docs/architecture.md) for the
load-log-specific port assignments and rebuild shortcuts.
