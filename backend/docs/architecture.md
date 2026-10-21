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
├── compose.yaml               # self-contained stack (own PG+PostgREST+web app)
├── compose.external.yaml      # web container alone → existing PG+PostgREST
├── deploy/                    # 02_schema.sql + 03_secure_users.sql (applied at
│                              #   startup), compose.elitedesk.yaml (the server's
│                              #   service fragment), historic/ (already run)
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
  (first page load), the TUI's `main()` and `scripts/create_user.py`, never the
  docker entrypoint. Version-gated on
  `load_log.deploy_meta`, additive and idempotent only.
- Nothing sets a `search_path`: the SQL in `deploy/` and `scripts/` qualifies
  every object (`load_log.habits`), and PostgREST requests pin the schema with
  `Accept-Profile` / `Content-Profile`.

## Running Locally

```bash
# Streamlit web UI (login form)
cd backend && PYTHONPATH=src uv run streamlit run src/web/app.py

# TUI (reads LOAD_LOG_USERNAME / LOAD_LOG_PASSWORD from .env to log in)
cd backend && PYTHONPATH=src uv run python -m tui.app

# Fully self-contained stack (own Postgres + PostgREST + web app), from the
# repo root with three secrets in .env (README "Run it with Docker"):
docker compose up --build
```

Both clients default `POSTGREST_URL` to the tinkernet deployment; override it
(and `POSTGRES_*`, `POSTGREST_JWT_SECRET`) in `.env` to point at your own
Postgres and PostgREST. `compose.yaml` publishes only the web app's port, so it
is not a backend for the bare-metal clients.

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

Three compose setups. In production load-log never hosts its own DB: the
EliteDesk deployment is backed by the shared Postgres on the EliteDesk host
(`Docker/docker_compose_projects.yaml`).

1. **Self-contained** (`compose.yaml` at the repo root): `postgres:17` (data in
   the `postgres_data` volume), `postgrest/postgrest:v16.5` and the
   `load-log-streamlit` web container, with only the web port published
   (`LOAD_LOG_PORT`, default 8505). `.env` supplies three secrets:
   `POSTGRES_PASSWORD`, `POSTGREST_DB_PASSWORD`, `POSTGREST_JWT_SECRET`. On
   first start an inline init script creates only the two cluster roles
   (`postgrest_authenticator`, `web_anon`); the app's bootstrap creates the
   schema, `load_log_user`, the tables and the grants.
2. **External** (`compose.external.yaml`): just the Streamlit container,
   pointed at an existing PostgREST and Postgres from `POSTGREST_URL` /
   `POSTGRES_*` in `.env`, with `POSTGREST_JWT_SECRET` for login. There is no
   default URL; every required setting must be set.
3. **EliteDesk deployment**: the shared `postgrest` service and the
   `load-log-streamlit` service in `docker_compose_projects.yaml` (the service
   fragment is `deploy/compose.elitedesk.yaml`).

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
