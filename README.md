# load-log

Personal health tracker with two UIs over a shared **PostgREST** API:

- **TUI** (Textual) — terminal, keyboard-driven, opens instantly.
- **Web** (Streamlit) — browser, GitHub-style heatmaps + inline editing.

Two features today: a daily **habit tracker** (click any day on the heatmap to
toggle it) and a **workout tracker** (volume heatmap, log sets with
progressive-overload guidance, edit/delete inline).

## Architecture

Neither UI talks to Postgres directly. Both log in through a shared, app-agnostic
auth service to get a JWT, then read/write through PostgREST over HTTP:

```
 TUI / Web ──POST /token {schema,username,password}──▶ auth  ──▶ JWT (role=load_log_user, user_id)
     │                                                              │
     └────────── api_client.py ──Authorization: Bearer <jwt>──▶ PostgREST ──▶ Postgres
                 (requests; returns dict/list[dict]/DataFrame)        (apps DB · load_log schema)
```

- Data lives in the **`load_log` schema** of the shared **`apps`** database. The
  app's data is reached only via PostgREST; Postgres enforces access through the
  `load_log_user` role.
- PostgREST and the auth service are shared server infrastructure (added once,
  serve every app). The auth service lives in the sibling
  [`postgrest-auth`](https://github.com/ReadableCode/postgrest-auth) repo.
- Direct Postgres connections remain only in the startup schema bootstrap and
  the `scripts/` helpers.

For full design + schema details see [`backend/docs/`](backend/docs/),
[`CLAUDE.md`](CLAUDE.md), and the server runbook in [`deploy/`](deploy/).

## Prerequisites

- Python 3.13 (pinned in `backend/.python-version`)
- [uv](https://docs.astral.sh/uv/) — `brew install uv` (macOS) or
  `curl -LsSf https://astral.sh/uv/install.sh | sh` (Linux)
- A login user in `load_log.users` (create one with
  `scripts/create_user.py`, below)

## One-time setup

```bash
git clone <load-log remote> ~/GitHub/load-log
cd ~/GitHub/load-log

cp .env.example .env
$EDITOR .env                # see keys below
cd backend && uv sync
```

`.env` keys:

```env
# Clients (web + TUI) — default to the tinkernet deployment; override to point
# at a local dev stack.
POSTGREST_URL=https://pgrest.tinkernet.me
AUTH_URL=https://auth.tinkernet.me

# The TUI is non-interactive: it logs in with these at startup.
LOAD_LOG_USERNAME=<your-username>
LOAD_LOG_PASSWORD=<your-password>

# Direct-DB only: the startup schema bootstrap and scripts/. Not the data path.
POSTGRES_URL=<host or LAN IP of the shared Postgres>
POSTGRES_PORT=5432
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<password>
POSTGRES_DB=apps
```

Create your login user (writes `load_log.users` with a bcrypt hash):

```bash
cd backend && uv run python scripts/create_user.py --username you --password 'your-password'
```

## Run locally (bare-metal)

From `backend/`:

```bash
# Web (Streamlit) — http://localhost:8501 — shows a login form
PYTHONPATH=src uv run streamlit run src/web/app.py

# TUI — logs in using LOAD_LOG_USERNAME / LOAD_LOG_PASSWORD from .env
PYTHONPATH=src uv run python -m tui.app
```

Both default to the tinkernet PostgREST/auth; set `POSTGREST_URL` / `AUTH_URL` in
`.env` to point them at a local dev stack instead.

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
keyboard shortcuts available right now — and each Footer entry is clickable.

## Run locally in Docker

Two options:

- **`docker-compose.yml`** (repo root) — just the Streamlit container, pointed at
  the shared PostgREST/auth (defaults to tinkernet). Bring it up with
  `docker-compose up -d --build` → web on `http://localhost:8505`.
- **`docker-compose.dev.yml`** — a fully self-contained stack (its own throwaway
  Postgres + PostgREST + the shared auth service + Streamlit), so you can develop
  without touching the server:

  ```bash
  docker compose -f docker-compose.dev.yml up --build
  # App http://localhost:8505 · PostgREST http://localhost:3000 · Auth http://localhost:8000
  ```

  First boot converges the schema: the app's own startup bootstrap applies
  `deploy/02_schema.sql` and `deploy/03_secure_users.sql`, creating the tables.
  Bootstrap ends with `NOTIFY pgrst` so PostgREST reloads its cache; if it still
  404s a table right after, `docker compose -f docker-compose.dev.yml restart
  postgrest`.

On macOS, Docker runs through [colima](https://github.com/abiosoft/colima) — start
it once per session: `colima start` (or `colima start --cpu 4 --memory 6`).

## DB schema (app-owned bootstrap)

Schema changes go in the idempotent SQL files under [`deploy/`](deploy/), applied
by [`backend/src/bootstrap.py`](backend/src/bootstrap.py) from the app's own
startup — the Streamlit script and the TUI's `main()`, never the docker
entrypoint. Starting load-log any way at all converges the schema, so the code
and the database cannot disagree because of how you launched it.

Convergence is gated on an integer `SCHEMA_VERSION` stamped into
`load_log.deploy_meta`, so it is a no-op on every boot after the first. The SQL
is additive and idempotent only: `CREATE ... IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`, never `DROP`, `TRUNCATE`, or `ALTER COLUMN`. A
destructive change is a new numbered file plus a reviewed `SCHEMA_VERSION` bump —
not something a boot can do by surprise.

To add a column: edit `deploy/02_schema.sql` (or add `deploy/04_*.sql` and put it
in `SCHEMA_FILES`), bump `SCHEMA_VERSION`, restart. Run it by hand if needed:

```bash
cd backend && uv run python src/bootstrap.py
```

This replaced Alembic in 2026-08. The four revisions that built the schema up to
this point are in git history; `deploy/historic/` holds the one-shot SQL that has
already run and must not run again.

Take a read-only CSV/Parquet backup before any risky change:

```bash
cd backend && uv run --with pyarrow python scripts/backup_to_files.py   # writes data/backup_<ts>/
```

## Lint / format / type-check

```bash
cd backend
uv run flake8 src/
uv run black src/ && uv run isort src/
uv run mypy src/
```

## Production deployment (EliteDesk)

The shared `postgrest` + `auth` services and the `load-log-streamlit` service live
in `~/GitHub/Docker/docker_compose_projects.yaml`, reverse-proxied by SWAG at
`pgrest.tinkernet.me`, `auth.tinkernet.me`, and `loadlog.tinkernet.me`. The
ordered server runbook (roles, schema move, rebuild, verification) is in
[`deploy/`](deploy/); deploy commands and the systemd unit are in
`~/GitHub/Docker/README.md`.
