# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Load Log is a personal health tracking app with two interfaces over the same
data, both reached through **PostgREST** (never Postgres directly):

- **TUI** (Textual) — terminal, keyboard-driven data entry
- **Web** (Streamlit) — browser, charts and visualizations

Features: daily habit tracker with GitHub-style heatmap, workout tracker with
progressive overload guidance.

Architecture: each client logs in through the shared auth service
(`https://auth.tinkernet.me`) to get a JWT, then talks to PostgREST
(`https://pgrest.tinkernet.me`) with `Authorization: Bearer <jwt>`. Postgres
enforces access via the `load_log_user` role. See `migration_plan.md` for the
full design and `deploy/DEPLOY.md` for the server runbook.

## Source Layout

```text
backend/
├── src/
│   ├── config.py      # env vars, walks up to find .env (loads it into os.environ)
│   ├── api_client.py  # shared PostgREST + auth HTTP client (used by web AND tui)
│   ├── main.py        # CLI entry point (stub)
│   ├── tui/           # Textual TUI (app.py, habits.py, workouts.py)
│   ├── web/           # Streamlit app (app.py)
│   └── utils/         # display helpers
├── alembic/           # migrations (versions/), env.py targets the load_log schema
├── alembic.ini
├── docker-entrypoint.sh  # runs `alembic upgrade head` before the app starts
├── scripts/           # one-off ops scripts (create_user.py, backup_to_files.py)
└── docs/              # architecture / schema / features
```

The shared auth service is a **separate repo** (`../postgrest-auth/`), not part
of load-log — it is server infrastructure, like PostgREST.

## Commands

```bash
# Install / sync deps
cd backend && uv sync

# Run Streamlit web UI (logs in via a form)
cd backend && PYTHONPATH=src uv run streamlit run src/web/app.py

# Run TUI (reads LOAD_LOG_USERNAME / LOAD_LOG_PASSWORD from .env to log in)
cd backend && PYTHONPATH=src uv run python -m tui.app

# Lint
cd backend && uv run flake8 src/

# Type check
cd backend && uv run mypy src/

# Format
cd backend && uv run black src/ && uv run isort src/

# Apply migrations manually (normally the container entrypoint does this)
cd backend && uv run alembic upgrade head
```

## Data Access

- All data access goes through `src/api_client.py`, which calls PostgREST over
  HTTP with a Bearer JWT. There is **no** psycopg2/SQLAlchemy in the app paths.
- Auth: `api_client.login(username, password)` POSTs to the auth service and
  returns a JWT. The web app stores it in `st.session_state`; the TUI threads it
  into each screen. Every PostgREST call carries `Authorization: Bearer <jwt>`.
- Tables are exposed at the schema root (e.g. `/workout_sets`) — paths are NOT
  prefixed with `/load_log`. Every PostgREST request pins the schema with
  `Accept-Profile`/`Content-Profile: load_log` headers (set in
  `api_client._headers`); the app must not rely on schema-list order in the
  server's `PGRST_DB_SCHEMAS`, and future sibling apps should pin their own
  schema the same way.
- Schema lives in the `load_log` schema of the shared `apps` database. See
  `backend/docs/schema.md`. Schema changes go through **Alembic** migrations
  (`backend/alembic/versions/`), applied on container startup by
  `docker-entrypoint.sh`.
- Direct Postgres connections remain only in ops tooling: Alembic, and the
  `scripts/` helpers (`create_user.py` seeds `load_log.users`;
  `backup_to_files.py` dumps tables to CSV/Parquet). These read `POSTGRES_*`
  from `.env`.

Required `.env` keys for clients: `POSTGREST_URL`, `AUTH_URL` (both default to
the tinkernet deployment), plus `LOAD_LOG_USERNAME` / `LOAD_LOG_PASSWORD` for the
non-interactive TUI. `POSTGRES_*` keys are needed only for Alembic + scripts.

## Code Conventions

- `# %%` section markers in every file (Jupyter cell compatibility)
- Data access is HTTP-only via `api_client`; interfaces contain no SQL
- `api_client` functions return `dict`, `list[dict]`, or `pd.DataFrame`
- Flake8: max line length 120, max complexity 15

## Safety Rules (Database)

- Schema changes go through Alembic migrations under
  `backend/alembic/versions/`. Migrations must be **non-destructive** by default:
  no `DROP`, `TRUNCATE`, `ALTER COLUMN`, or unfiltered `DELETE` in an upgrade
  path without an explicit, reviewed reason. The baseline (`0001`) uses
  `CREATE ... IF NOT EXISTS` so it is a no-op on the populated prod DB and builds
  a fresh dev DB.
- A verified CSV/Parquet backup exists under `data/backup_*/`; re-run
  `scripts/backup_to_files.py` (read-only) before any risky schema work.
- `load_log.users` (password hashes) must never be granted to `load_log_user` /
  `web_anon`, so PostgREST cannot serve it. Only the auth service reads it, as
  the superuser.
- Confirm with the user before running any ad-hoc command that mutates rows in
  the shared Postgres.

## TUI Design Rules (Textual)

- Two header lines per screen: bold `#title` (screen name only) and muted
  `#subtitle` (one explanatory sentence).
- Footer is the **only** place that lists keyboard shortcuts. Do not put
  `[a]dd · [w]orkouts · [q]uit` style hints in titles, panels, or anywhere
  else — the bracketed notation reads as missing characters and is not
  clickable in VSCode terminal, which mismatches the Footer's clickable
  hot-spots.
- Avoid `border: tall …` on single-row cells: it overflows into adjacent
  rows. Use glyph swaps (e.g., `◉` for today vs `■` for any other day) and
  `text-style: bold` instead.

## Environment

- Python 3.13 (`backend/.python-version`)
- Package manager: `uv`
- Docker: `backend/Dockerfile` builds the web/TUI image; the entrypoint runs
  Alembic, then the (compose-overridable) command.
