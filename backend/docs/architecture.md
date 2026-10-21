# Architecture

## Goal

Fast, lightweight, easy to read, and reachable from anywhere. Two clients over
the same data — a Textual **TUI** for quick terminal input and a Streamlit **web
app** for visualization. Neither touches Postgres for its data: both log in
in-process through the postgrest-auth library (it reads `load_log.users` over the
superuser connection and signs a JWT), then read/write through **PostgREST**
over HTTPS. This makes the app multi-device and accessible outside the house,
and establishes a reusable pattern for future apps.

The schema converges from the app's startup bootstrap (`src/bootstrap.py`); the
cluster-wide PostgREST roles come from the `postgres-cluster-roles` service in
the Docker repo (`Docker/postgres/cluster_roles.sql`).

## Project Structure

```text
load-log/
├── backend/
│   ├── src/
│   │   ├── config.py          # env vars; walks up dirs to find .env, loads it
│   │   ├── api_client.py      # login + shared PostgREST HTTP client (web AND tui)
│   │   ├── main.py            # CLI entry point (stub)
│   │   ├── tui/
│   │   │   ├── app.py         # Textual root; logs in from env, threads JWT to screens
│   │   │   ├── habits.py      # HabitsScreen (ListView) + HabitDetailScreen (heatmap)
│   │   │   └── workouts.py    # WorkoutsScreen (volume heatmap + stacked form)
│   │   ├── web/
│   │   │   └── app.py         # Streamlit; login gate + habits/workouts pages
│   │   └── utils/             # display helpers
│   │   └── bootstrap.py       # app-owned schema convergence, run at startup
│   ├── docker-entrypoint.sh   # deliberately inert: `exec "$@"`, no migrations
│   ├── scripts/
│   │   ├── create_user.py     # seed load_log.users (argon2id) — admin tool
│   │   └── backup_to_files.py # read-only dump of all tables to CSV/Parquet
│   ├── docs/                  # this directory: architecture / schema / features
│   ├── pyproject.toml
│   └── Dockerfile
├── docker-compose.yml         # portable web container → shared PostgREST
├── docker-compose.dev.yml     # self-contained local stack (own PG+PostgREST)
├── deploy/                    # 02_schema.sql + 03_secure_users.sql (applied at
│                              #   startup), dev_init.sql, historic/ (already run)
├── data/                      # personal goal markdown + data backups
├── CLAUDE.md
├── .env.example
└── .env                       # NOT committed
```

Login comes from the postgrest-auth library (separate repo, `../postgrest-auth/`),
a git dependency pinned to a tag in `pyproject.toml`. Nothing runs beside the
app for login; PostgREST is the only shared server infrastructure.

## Tech Stack

| Layer          | Library            | Reason                                         |
|----------------|--------------------|------------------------------------------------|
| API layer      | PostgREST          | auto-generates the REST API from the schema    |
| Auth           | postgrest-auth     | in-process login library, app-agnostic         |
| HTTP client    | requests           | `api_client` talks to PostgREST                |
| TUI            | textual            | modern, composable, keyboard-driven            |
| Web UI         | streamlit          | fast to build, good charting, no JS needed     |
| Schema         | deploy/*.sql       | idempotent, applied by `bootstrap.py` at start  |
| DB driver      | psycopg2-binary    | login, bootstrap, `scripts/` (not data paths)  |
| Runner         | uv                 | already in use                                 |

## Data Flow

```text
                 api_client.login(username, password)
 tui/app.py ───▶  postgrest-auth  ───▶ JWT (role=load_log_user, user_id)
 web/app.py       (library, in-process;  │
       │           superuser reads       │
       │           load_log.users)       ▼
       └────────▶ api_client.py ──Bearer JWT──▶ PostgREST ──▶ Postgres
                  (requests; returns                (SET ROLE   (load_log schema;
                   dict/list[dict]/DataFrame)        load_log_user) GRANTs enforce)
```

`api_client.py` is the single source of truth for all data access. The two
interfaces only call its functions — they contain no SQL and no DB driver.
Login's one read of `load_log.users` happens inside the library, over the
superuser connection (`bootstrap.superuser_dsn()`).

## Database

- Shared database `apps`; load-log's tables live in the `load_log` **schema**
  (`habits`, `habit_completions`, `exercises`, `workout_sets`) plus
  `load_log.users` (credentials, never exposed via PostgREST).
- Roles: `postgrest_authenticator` (login role PostgREST uses), `web_anon`
  (anonymous, no grants), `load_log_user` (the app role; the JWT `role` claim).
- Schema changes go in `deploy/02_schema.sql` (and further numbered files),
  applied by `src/bootstrap.py` from the app's own startup — the Streamlit script
  and the TUI's `main()`, never the docker entrypoint. Version-gated on
  `load_log.deploy_meta`, additive and idempotent only.
- `ALTER DATABASE apps SET search_path = load_log, public` keeps direct-DB
  tooling (bootstrap, scripts) pointed at the right tables. This is set on the
  whole shared `apps` database, which is a fleet-level wart — see
  `backlog/shared-apps-search-path.md`.

## Running Locally

```bash
# Streamlit web UI (login form)
cd backend && PYTHONPATH=src uv run streamlit run src/web/app.py

# TUI (reads LOAD_LOG_USERNAME / LOAD_LOG_PASSWORD from .env to log in)
cd backend && PYTHONPATH=src uv run python -m tui.app

# Fully self-contained local stack (own Postgres + PostgREST):
docker compose -f docker-compose.dev.yml up --build
```

Both clients default `POSTGREST_URL` to the tinkernet deployment; override it
(and `POSTGRES_*`, `POSTGREST_JWT_SECRET`) in `.env` to point at the local dev
stack.

## Configuration (.env at repo root)

```env
APP_ENV=development

# Direct DB: login (web + TUI), startup bootstrap, scripts:
POSTGRES_URL=<shared-postgres-host>
POSTGRES_PORT=5432
POSTGRES_DB=apps
POSTGRES_USER=...
POSTGRES_PASSWORD=...

# Clients (web + TUI):
POSTGREST_URL=https://pgrest.tinkernet.me
POSTGREST_JWT_SECRET=...   # PostgREST's secret; login signs with it (JWT_SECRET also read)
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
   container, pointed at the shared PostgREST (defaults to tinkernet) and Postgres.
2. **EliteDesk deployment** — the shared `postgrest` service and the
   `load-log-streamlit` service in `docker_compose_projects.yaml`.

### Port assignments

| Service             | Host port | Container port |
|---------------------|-----------|----------------|
| postgrest           | 3001      | 3000           |
| load-log-streamlit  | 8505      | 8505           |

There is no hand-run deploy SQL. The app applies `deploy/02_schema.sql` and
`deploy/03_secure_users.sql` itself at startup (`src/bootstrap.py`), and the
cluster-wide PostgREST roles come from the `postgres-cluster-roles` service in
the Docker repo (`Docker/postgres/cluster_roles.sql`). Deploy commands live in
`~/GitHub/Docker/README.md`.

## Code Style Rules

- `# %%` section markers throughout every file (Jupyter-compatible cells)
- Data access is HTTP-only via `api_client` — no SQL or DB driver in data paths
- `api_client` functions return `dict`, `list[dict]`, or `pd.DataFrame`
- Max line length: 120 (matches flake8 config in pyproject.toml)
```
