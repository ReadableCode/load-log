# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Load Log is a personal health tracking app with two interfaces over the same
data, both reached through **PostgREST** (never Postgres directly; only login
reads `load_log.users` over the superuser connection):

- **TUI** (Textual) — terminal, keyboard-driven data entry
- **Web** (Streamlit) — browser, charts and visualizations

Features: daily habit tracker with GitHub-style heatmap, workout tracker with
progressive overload guidance.

Architecture: each client logs in in-process through the postgrest-auth
library (verifies the password against `load_log.users` over the superuser
connection, signs a JWT with PostgREST's secret), then talks to PostgREST
(`https://pgrest.tinkernet.me`) with `Authorization: Bearer <jwt>`. Postgres
enforces access via the `load_log_user` role. The schema converges from the
app's startup bootstrap (`backend/src/bootstrap.py`); the cluster-wide roles
come from the `postgres-cluster-roles` service in the Docker repo
(`Docker/postgres/cluster_roles.sql`).

## Source Layout

```text
backend/
├── src/
│   ├── config.py      # env vars, walks up to find .env (loads it into os.environ)
│   ├── api_client.py  # login + shared PostgREST HTTP client (used by web AND tui)
│   ├── main.py        # CLI entry point (stub)
│   ├── bootstrap.py   # app-owned schema convergence, run from app startup
│   ├── tui/           # Textual TUI (app.py, habits.py, workouts.py)
│   ├── web/           # Streamlit app (app.py)
│   └── utils/         # display helpers
├── conftest.py        # puts src/ on the path for the test suite
├── tests/             # real-DB + real-PostgREST conformance tests
├── docker-entrypoint.sh  # deliberately inert (`exec "$@"`) — no migrations here
├── scripts/           # one-off ops scripts (create_user.py, backup_to_files.py)
└── docs/              # architecture / schema / features

deploy/                # applied by src/bootstrap.py at startup:
├── 02_schema.sql      #   tables, columns, grants
└── 03_secure_users.sql#   I4 revokes on load_log.users
                       # not applied by bootstrap:
├── dev_init.sql       #   dev stack's initdb mount
└── historic/          #   one-shot SQL that already ran; must not run again
```

Login comes from the postgrest-auth library (separate repo, `../postgrest-auth/`),
a git dependency pinned to a tag in `backend/pyproject.toml`. Nothing runs
beside the app for login; PostgREST is the only shared server infrastructure.

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

# Converge the schema manually (normally the app does this at startup)
cd backend && uv run python src/bootstrap.py

# Real-dependency tests (hit the actual DB + PostgREST; no skips by design)
cd backend && uv run pytest tests/
```

## Data Access

- All data access goes through `src/api_client.py`, which calls PostgREST over
  HTTP with a Bearer JWT. There is **no** psycopg2/SQLAlchemy in the data paths.
- Auth: `api_client.login(username, password)` calls `postgrest_auth.login`
  in-process over the superuser connection (`bootstrap.superuser_dsn()`) and
  returns a JWT signed with `config.JWT_SECRET`. It raises
  `postgrest_auth.InvalidCredentials`, `postgrest_auth.LoginLocked`, or
  `api_client.LoginUnavailable` (POSTGRES_* or the secret unset, database
  unreachable). The web app stores the JWT in `st.session_state`; the TUI threads
  it into each screen. Every PostgREST call carries `Authorization: Bearer <jwt>`.
  There is no app-side session validation.
- Tables are exposed at the schema root (e.g. `/workout_sets`) — paths are NOT
  prefixed with `/load_log`. Every PostgREST request pins the schema with
  `Accept-Profile`/`Content-Profile: load_log` headers (set in
  `api_client._headers`); the app must not rely on schema-list order in the
  server's `PGRST_DB_SCHEMAS`, and future sibling apps should pin their own
  schema the same way.
- Schema lives in the `load_log` schema of the shared `apps` database. See
  `backend/docs/schema.md`. Schema changes go in the idempotent SQL under
  `deploy/`, applied by `src/bootstrap.py` from the app's **own startup path**
  (the Streamlit script and the TUI's `main()`) — never the docker entrypoint.
- Direct Postgres connections remain only in login (`api_client.login` reads
  `load_log.users`) and ops tooling: the startup bootstrap, and the
  `scripts/` helpers (`create_user.py` seeds `load_log.users`;
  `backup_to_files.py` dumps tables to CSV/Parquet). These read `POSTGRES_*`
  from `.env`.

Required `.env` keys for clients (web and TUI): `POSTGREST_URL` (defaults to the
tinkernet deployment), `POSTGRES_*` and `POSTGREST_JWT_SECRET` (`JWT_SECRET` is
accepted as a fallback name) for login, plus `LOAD_LOG_USERNAME` /
`LOAD_LOG_PASSWORD` for the non-interactive TUI. `POSTGRES_*` also serves the
startup schema bootstrap and the `scripts/` helpers.

## Code Conventions

- `# %%` section markers in every file (Jupyter cell compatibility)
- Data access is HTTP-only via `api_client`; interfaces contain no SQL (login's
  one users-table read is inside the postgrest-auth library)
- `api_client` functions return `dict`, `list[dict]`, or `pd.DataFrame`
- Flake8: max line length 120, max complexity 15

## Safety Rules (Database)

- Schema changes go in `deploy/02_schema.sql` (or a new numbered file added to
  `SCHEMA_FILES` in `src/bootstrap.py`), with a `SCHEMA_VERSION` bump. The SQL
  must be **additive and idempotent**: `CREATE ... IF NOT EXISTS`,
  `ADD COLUMN IF NOT EXISTS`. No `DROP`, `TRUNCATE`, `ALTER COLUMN`, or
  unfiltered `DELETE` without an explicit, reviewed reason — a boot must not be
  able to do a destructive change by surprise.
- **Do not reintroduce a second migration mechanism.** Alembic was removed in
  2026-08 precisely because a migration that only runs in the docker entrypoint
  does not run for a bare `streamlit run`, the TUI, or a test — so the code and
  the schema could disagree depending on how the app was launched. Every app on
  this Postgres instance now converges the same way.
- A verified CSV/Parquet backup exists under `data/backup_*/`; re-run
  `scripts/backup_to_files.py` (read-only) before any risky schema work.
- `load_log.users` (password hashes) must never be granted to `load_log_user` /
  `web_anon`, so PostgREST cannot serve it. Only login (the postgrest-auth
  library, in-process) reads it, as the superuser.
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
- Docker: `backend/Dockerfile` builds the web/TUI image. Its build context is the
  **repo root**, not `backend/`, because the image needs `deploy/*.sql` too — so
  every `COPY` source is prefixed with `backend/`. The entrypoint is inert; the
  app converges its own schema at startup.

## Working rules for this repo

- The shared Postgres on the home server is production for several apps.
  Never a destructive operation without confirmation. The tests run against
  the Postgres and PostgREST configured in `.env` and are read-only by design;
  keep any new test read-only too.
- Preferences: fast, lightweight, easy to read. Plain SQL over ORMs, `# %%`
  section markers, functions returning `dict`, `list[dict]` or a DataFrame,
  `uv` for packages. Pull only the keys a container needs from the shared
  `.env`, never `env_file:` the whole thing.
- TUI screens have exactly two header lines: a bold one-word title and a
  muted one-sentence subtitle. The Footer is the single source of truth for
  keyboard shortcuts; never repeat them as `[a]dd` text at the top (it reads
  as broken titles in the VS Code terminal and is not clickable).
- Docker on the Mac is colima (`colima start`, not a brew service) with the
  v1 `docker-compose` binary; the VM bridges to the LAN so containers reach
  the shared Postgres directly.
