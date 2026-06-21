# Architecture

## Goal

Fast, lightweight, easy to read, and reachable from anywhere. Two clients over
the same data — a Textual **TUI** for quick terminal input and a Streamlit **web
app** for visualization. Neither touches Postgres directly: both log in through a
shared auth service to get a JWT, then read/write through **PostgREST** over
HTTPS. This makes the app multi-device and accessible outside the house, and
establishes a reusable pattern for future apps.

See `../../migration_plan.md` for the full design and `../../deploy/DEPLOY.md`
for the server runbook.

## Project Structure

```text
load-log/
├── backend/
│   ├── src/
│   │   ├── config.py          # env vars; walks up dirs to find .env, loads it
│   │   ├── api_client.py      # shared PostgREST + auth HTTP client (web AND tui)
│   │   ├── main.py            # CLI entry point (stub)
│   │   ├── tui/
│   │   │   ├── app.py         # Textual root; logs in from env, threads JWT to screens
│   │   │   ├── habits.py      # HabitsScreen (ListView) + HabitDetailScreen (heatmap)
│   │   │   └── workouts.py    # WorkoutsScreen (volume heatmap + stacked form)
│   │   ├── web/
│   │   │   └── app.py         # Streamlit; login gate + habits/workouts pages
│   │   └── utils/             # display helpers
│   ├── alembic/               # migrations (versions/), env.py targets load_log schema
│   ├── alembic.ini
│   ├── docker-entrypoint.sh   # runs `alembic upgrade head`, then the app
│   ├── scripts/
│   │   ├── create_user.py     # seed load_log.users (bcrypt) — admin tool
│   │   └── backup_to_files.py # read-only dump of all tables to CSV/Parquet
│   ├── docs/                  # this directory: architecture / schema / features
│   ├── pyproject.toml
│   └── Dockerfile
├── docker-compose.yml         # portable web container → shared PostgREST
├── docker-compose.dev.yml     # self-contained local stack (own PG+PostgREST+auth)
├── deploy/                    # server SQL + DEPLOY.md runbook + dev_init.sql
├── data/                      # personal goal markdown + data backups
├── CLAUDE.md
├── .env.example
└── .env                       # NOT committed
```

The shared auth service lives in a **separate repo** (`../postgrest-auth/`) — it
is server infrastructure, like PostgREST, not part of load-log.

## Tech Stack

| Layer          | Library            | Reason                                         |
|----------------|--------------------|------------------------------------------------|
| API layer      | PostgREST          | auto-generates the REST API from the schema    |
| Auth           | FastAPI (shared)   | tiny `/token` service, app-agnostic            |
| HTTP client    | requests           | `api_client` talks to PostgREST + auth         |
| TUI            | textual            | modern, composable, keyboard-driven            |
| Web UI         | streamlit          | fast to build, good charting, no JS needed     |
| Migrations     | alembic            | versioned schema changes, run on startup       |
| DB driver      | psycopg2-binary    | Alembic + `scripts/` only (never in app paths) |
| Runner         | uv                 | already in use                                 |

## Data Flow

```text
                 POST /token {schema,username,password}
 tui/app.py ───▶  auth service  ───▶ JWT (role=load_log_user, user_id)
 web/app.py        (shared)            │
       │                               ▼
       └────────▶ api_client.py ──Bearer JWT──▶ PostgREST ──▶ Postgres
                  (requests; returns                (SET ROLE   (load_log schema;
                   dict/list[dict]/DataFrame)        load_log_user) GRANTs enforce)
```

`api_client.py` is the single source of truth for all data access. The two
interfaces only call its functions — they contain no SQL and no DB driver.

## Database

- Database `load_log`; app tables live in the `load_log` **schema**
  (`habits`, `habit_completions`, `exercises`, `workout_sets`) plus
  `load_log.users` (credentials, never exposed via PostgREST).
- Roles: `postgrest_authenticator` (login role PostgREST uses), `web_anon`
  (anonymous, no grants), `load_log_user` (the app role; the JWT `role` claim).
- Schema changes go through Alembic (`alembic/versions/`), applied on container
  startup by `docker-entrypoint.sh`. Baseline `0001` is idempotent
  (`CREATE ... IF NOT EXISTS`); `0002` adds the users table.
- `ALTER DATABASE load_log SET search_path = load_log, public` keeps any
  direct-DB tooling (Alembic, scripts) pointed at the right tables.

## Running Locally

```bash
# Streamlit web UI (login form)
cd backend && PYTHONPATH=src uv run streamlit run src/web/app.py

# TUI (reads LOAD_LOG_USERNAME / LOAD_LOG_PASSWORD from .env to log in)
cd backend && PYTHONPATH=src uv run python -m tui.app

# Fully self-contained local stack (own Postgres + PostgREST + auth):
docker compose -f docker-compose.dev.yml up --build
```

Both clients default `POSTGREST_URL`/`AUTH_URL` to the tinkernet deployment;
override them in `.env` to point at the local dev stack.

## Configuration (.env at repo root)

```env
APP_ENV=development

# Alembic + scripts (direct DB) only:
POSTGRES_URL=<shared-postgres-host>
POSTGRES_PORT=5432
POSTGRES_DB=load_log
POSTGRES_USER=...
POSTGRES_PASSWORD=...

# Clients (web + TUI):
POSTGREST_URL=https://pgrest.tinkernet.me
AUTH_URL=https://auth.tinkernet.me
LOAD_LOG_USERNAME=...   # the non-interactive TUI logs in with these
LOAD_LOG_PASSWORD=...
```

`config.py` resolves `.env` by walking up from `__file__` and loads it into the
environment.

## Docker Compose Deployment

Two compose setups, both ultimately backed by the shared Postgres on the
EliteDesk host (`Docker/docker_compose_projects.yaml`) — load-log never hosts its
own DB in production:

1. **Portable** — `docker-compose.yml` at the repo root: just the Streamlit
   container, pointed at the shared PostgREST/auth (defaults to tinkernet).
2. **EliteDesk deployment** — the shared `postgrest` + `auth` services and the
   `load-log-streamlit` service in `docker_compose_projects.yaml`.

### Port assignments

| Service             | Host port | Container port |
|---------------------|-----------|----------------|
| postgrest           | 3001      | 3000           |
| auth (shared)       | 8006      | 8000           |
| load-log-streamlit  | 8505      | 8505           |

The full, ordered deploy + verification steps live in **`../../deploy/DEPLOY.md`**
(secrets, role/schema SQL, proxy confs, rebuild commands, user seeding, checks).
Do not duplicate that runbook here.

## Code Style Rules

- `# %%` section markers throughout every file (Jupyter-compatible cells)
- Data access is HTTP-only via `api_client` — no SQL or DB driver in app paths
- `api_client` functions return `dict`, `list[dict]`, or `pd.DataFrame`
- Max line length: 120 (matches flake8 config in pyproject.toml)
```
