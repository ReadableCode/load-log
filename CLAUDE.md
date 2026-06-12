# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Load Log is a personal health tracking app with three interfaces over the same PostgreSQL database:

- **TUI** (Textual) — terminal, keyboard-driven data entry
- **Web** (Streamlit) — browser, charts and visualizations
- **API** (FastAPI) — HTTP, for automation

Features: daily habit tracker with GitHub-style heatmap, workout tracker with progressive overload guidance.

See `backend/docs/architecture.md`, `backend/docs/schema.md`, and `backend/docs/features.md` for the full plan.

## Source Layout

```text
backend/src/
├── config.py       # env vars, path resolution
├── db.py           # psycopg2 pool, ensure_database_exists, ensure_tables
├── habits.py       # all SQL for habit tracker
├── workouts.py     # all SQL for workout tracker
├── api.py          # FastAPI routes (thin wrappers)
├── main.py         # CLI entry point
├── tui/            # Textual TUI screens
└── web/            # Streamlit app
```

## Commands

```bash
# Install / sync deps
cd backend && uv sync

# Run API server
cd backend && PYTHONPATH=src uv run uvicorn api:app --reload --port 8000

# Run Streamlit web UI
cd backend && PYTHONPATH=src uv run streamlit run src/web/app.py

# Run TUI
cd backend && PYTHONPATH=src uv run python -m tui.app

# Run all tests
cd backend && PYTHONPATH=src uv run pytest

# Run a single test file
cd backend && PYTHONPATH=src uv run pytest tests/test_habits.py

# Lint
cd backend && uv run flake8 src/ tests/

# Type check
cd backend && uv run mypy src/

# Format
cd backend && uv run black src/ tests/ && uv run isort src/ tests/
```

## Database

- Production DB: `load_log` — created on first startup via `ensure_database_exists`
- Test DB: `load_log_test` — `tests/conftest.py` overrides `POSTGRES_DB` before
  `config.py` reads it, so `pytest` can NEVER touch the production DB
- `db.py::ensure_tables()` only ever runs `CREATE TABLE IF NOT EXISTS`. If it
  detects an old schema, it raises and refuses to start. Explicit migrations
  live under `backend/scripts/` (e.g. `migrate_drop_sessions.py`) and write
  backups before changing anything
- Schema: see `backend/docs/schema.md`
- Connection pattern: psycopg2 connection pool (matches `postgres_tools.py` in dotfiles)
- `.env` at repo root; `config.py` walks up directories until it finds a `.env`

Required `.env` keys: `POSTGRES_URL` (host), `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`

## Docker Compose

Both compose setups connect to the **same shared Postgres** (defined in
`/Users/jason/GitHub/Docker/docker_compose_projects.yaml`). We never host our
own DB — single source of truth.

- **Portable dev stack** — `docker-compose.yml` at repo root. Runs API + web
  containers anywhere; the `.env` tells them how to reach the shared DB.
  Start with `docker-compose up -d --build`.
- **Server deployment** — service blocks in `backend/docs/architecture.md`
  appended to `docker_compose_projects.yaml` (named `load-log-fastapi` /
  `load-log-streamlit`).

In both setups API maps to host port `8004`, Streamlit to `8505`.

## Code Conventions

- `# %%` section markers in every file (Jupyter cell compatibility)
- All SQL lives in `habits.py` / `workouts.py` only — interfaces contain no SQL
- DB functions return `dict`, `list[dict]`, or `pd.DataFrame`, never raw cursor rows
- No ORM — raw psycopg2 with `%s` parameter binding
- Flake8: max line length 120, max complexity 15

## Environment

- Python 3.13 (`backend/.python-version`)
- Package manager: `uv`
- Docker: same `backend/Dockerfile` for both API and web services; web overrides CMD
