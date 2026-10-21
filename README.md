# load-log

A personal health tracker for daily habits and strength training. It has two
interfaces over the same data:

- **Web** (Streamlit): browser UI with GitHub-style heatmaps, charts and inline
  editing.
- **TUI** (Textual): terminal UI, keyboard-driven, opens instantly.

It exists to make logging a habit or a lifting set take a few keystrokes, from
any device, and to show at a glance whether streaks and training volume are
holding up.

![Web habits page](docs/screenshots/web_habits.png)

## What it does

- **Habit tracker.** Define daily habits (for example "10,000 steps"). Each one
  gets a 52-week heatmap and a current streak. Click any day on the heatmap to
  select it, then mark or unmark it. Habits can be added, reordered and deleted.
- **Workout tracker.** Log sets (exercise, reps, weight) for any date. A volume
  heatmap (reps x weight per day) picks the date, the form shows what you did
  last time for that exercise, pre-fills the next set, and suggests the next
  weight for progressive overload. Logged sets can be edited or deleted inline;
  per-exercise history shows total volume and estimated 1RM (Epley) over time.

![Web workouts page](docs/screenshots/web_workouts.png)

![TUI habit heatmap](docs/screenshots/tui_habit_detail.png)

Screenshots use synthetic data from a local stub client, not a real account.

## How it works

Neither UI talks to Postgres directly. Both log in through a shared,
app-agnostic auth service to get a JWT, then read and write through PostgREST
over HTTP:

```
 TUI / Web ──POST /token {schema,username,password}──▶ auth  ──▶ JWT (role=load_log_user, user_id)
     │                                                              │
     └────────── api_client.py ──Authorization: Bearer <jwt>──▶ PostgREST ──▶ Postgres
                 (requests; returns dict/list[dict]/DataFrame)        (apps DB · load_log schema)
```

- Data lives in the **`load_log` schema** of a shared **`apps`** database. The
  app's data is reached only via PostgREST; Postgres enforces access through the
  `load_log_user` role.
- All data access is in [`backend/src/api_client.py`](backend/src/api_client.py),
  shared by the web app and the TUI. The UIs contain no SQL.
- PostgREST and the auth service are shared server infrastructure (added once,
  serve every app). The auth service lives in the sibling
  [`postgrest-auth`](https://github.com/ReadableCode/postgrest-auth) repo.
- Direct Postgres connections remain only in the startup schema bootstrap and
  the `scripts/` helpers.

For full design and schema details see [`backend/docs/`](backend/docs/) and
[`CLAUDE.md`](CLAUDE.md).

## Prerequisites

- Python 3.13 (pinned in `backend/.python-version`)
- [uv](https://docs.astral.sh/uv/): `brew install uv` (macOS) or
  `curl -LsSf https://astral.sh/uv/install.sh | sh` (Linux)
- A reachable PostgREST and auth service (your own, or the self-contained dev
  stack below)
- A login user in `load_log.users` (create one with `scripts/create_user.py`,
  below)

## One-time setup

```bash
git clone https://github.com/ReadableCode/load-log.git
cd load-log

cp .env.example .env
$EDITOR .env                # see keys below
cd backend && uv sync
```

`.env` keys:

```env
# Clients (web + TUI). Without these set, the code falls back to the author's
# own deployment (defaults in backend/src/api_client.py); set them to point at
# your server or a local dev stack.
POSTGREST_URL=https://pgrest.example.com
AUTH_URL=https://auth.example.com

# The TUI is non-interactive: it logs in with these at startup.
LOAD_LOG_USERNAME=<your-username>
LOAD_LOG_PASSWORD=<your-password>

# Direct-DB only: the startup schema bootstrap and scripts/. Not the data path.
POSTGRES_URL=<host of the shared Postgres>
POSTGRES_PORT=5432
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<password>
POSTGRES_DB=apps
```

Create your login user (writes one row to `load_log.users` with an argon2id
hash; refuses to overwrite an existing username):

```bash
cd backend && uv run python scripts/create_user.py --username you --password 'your-password'
```

## Run locally (bare-metal)

From `backend/`:

```bash
# Web (Streamlit), http://localhost:8501, shows a login form
PYTHONPATH=src uv run streamlit run src/web/app.py

# TUI, logs in using LOAD_LOG_USERNAME / LOAD_LOG_PASSWORD from .env
PYTHONPATH=src uv run python -m tui.app
```

Both use `POSTGREST_URL` / `AUTH_URL` from `.env`; point them at a local dev
stack to develop without a server. [`backend/dev/`](backend/dev/README.md) has a
stub `api_client` with synthetic data for previewing the web UI with no network.

### TUI cheatsheet

Anywhere:

- `h` / `w` / `q`: habits screen / workouts screen / quit

Habits list:

- `↑` / `↓`: move highlight between habits
- `enter`: open the heatmap detail view for the highlighted habit
- `space`: toggle today on the highlighted habit
- `delete`: delete the highlighted habit
- `a`: focus the "new habit" input

Habit detail and workouts heatmap:

- click any cell: select that date
- `t` / `T`: toggle the selected day / jump back to today

Workouts log-a-set form:

- `enter` in reps: jump to weight (or submit if weight is already filled)
- `enter` in weight: submit the set
- weight accepts decimals (e.g. `47.5`)
- `Edit` / `Delete` button on each logged set: inline edit or remove

The Footer at the bottom of every screen is the source of truth for the
keyboard shortcuts available right now, and each Footer entry is clickable.

## Run locally in Docker

Two options:

- **`docker-compose.yml`** (repo root): just the Streamlit container, pointed at
  the shared PostgREST and auth service from `POSTGREST_URL` / `AUTH_URL`. Bring
  it up with `docker-compose up -d --build`; web on `http://localhost:8505`.
- **`docker-compose.dev.yml`**: a fully self-contained stack (its own throwaway
  Postgres + PostgREST + the shared auth service + Streamlit), so you can develop
  without touching a server:

  ```bash
  docker compose -f docker-compose.dev.yml up --build
  # App http://localhost:8505 · PostgREST http://localhost:3000 · Auth http://localhost:8000
  ```

  First boot converges the schema: the app's own startup bootstrap applies
  `deploy/02_schema.sql` and `deploy/03_secure_users.sql`, creating the tables.
  Bootstrap ends with `NOTIFY pgrst` so PostgREST reloads its cache; if it still
  404s a table right after, `docker compose -f docker-compose.dev.yml restart
  postgrest`.

On macOS, Docker runs through [colima](https://github.com/abiosoft/colima). Start
it once per session: `colima start` (or `colima start --cpu 4 --memory 6`).

## DB schema (app-owned bootstrap)

Schema changes go in the idempotent SQL files under [`deploy/`](deploy/), applied
by [`backend/src/bootstrap.py`](backend/src/bootstrap.py) from the app's own
startup: the Streamlit script and the TUI's `main()`, never the docker
entrypoint. Starting load-log any way at all converges the schema, so the code
and the database cannot disagree because of how you launched it. A failed
bootstrap is logged and the app serves anyway; the next boot retries.

Convergence is gated on an integer `SCHEMA_VERSION` stamped into
`load_log.deploy_meta`, so it is a no-op on every boot after the first. The SQL
is additive and idempotent only: `CREATE ... IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`, never `DROP`, `TRUNCATE`, or `ALTER COLUMN`. A
destructive change is a new numbered file plus a reviewed `SCHEMA_VERSION` bump,
not something a boot can do by surprise.

To add a column: edit `deploy/02_schema.sql` (or add `deploy/04_*.sql` and put it
in `SCHEMA_FILES`), bump `SCHEMA_VERSION`, restart. Run it by hand if needed:

```bash
cd backend && uv run python src/bootstrap.py
```

The bootstrap expects the cluster-wide PostgREST roles (`postgrest_authenticator`,
`web_anon`) to exist already; it stops with an error naming them if they do not.

This replaced Alembic in 2026-08. The four revisions that built the schema up to
this point are in git history; `deploy/historic/` holds the one-shot SQL that has
already run and must not run again.

Take a read-only CSV/Parquet backup before any risky change:

```bash
cd backend && uv run --with pyarrow python scripts/backup_to_files.py   # writes data/backup_<ts>/
```

## Lint / format / type-check / test

```bash
cd backend
uv run flake8 src/
uv run black src/ && uv run isort src/
uv run mypy src/
uv run pytest tests/
```

The tests are read-only conformance checks against the real Postgres and
PostgREST configured in `.env` (schema, grants, login, that `load_log.users` is
not reachable over HTTP). There is no skip path: an unreachable dependency is a
failing test.

## Production deployment

In production the shared `postgrest` and `auth` services and the
`load-log-streamlit` service (its compose fragment is under
[`deploy/`](deploy/)) run from a
separate Docker compose repo on a home server, behind a SWAG reverse proxy. The
app applies its own schema from [`deploy/`](deploy/) at startup; the
cluster-wide PostgREST roles come from a `postgres-cluster-roles` service in the
same compose setup. Deploy commands and the systemd unit live in that Docker
repo.
