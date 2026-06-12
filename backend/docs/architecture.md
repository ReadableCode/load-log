# Architecture

## Goal

Fast, lightweight, easy to read. Three ways to use the same data — TUI for quick terminal input, Streamlit for visualization, FastAPI for any future automation or external access. All three import the same DB module directly; no HTTP overhead between the interfaces and the data layer.

## Project Structure

```text
load-log/
├── backend/
│   ├── src/
│   │   ├── config.py          # env vars; walks up dirs to find .env
│   │   ├── db.py              # pool, ensure_database_exists (+ collation refresh),
│   │   │                      # ensure_tables (never drops; raises on drift)
│   │   ├── habits.py          # all SQL for habit tracker
│   │   ├── workouts.py        # all SQL for workout tracker (date-keyed sets)
│   │   ├── api.py             # FastAPI routes (thin wrappers)
│   │   ├── main.py            # CLI entry point
│   │   ├── tui/
│   │   │   ├── app.py         # Textual app root, BINDINGS h/w/q
│   │   │   ├── habits.py      # HabitsScreen (ListView) + HabitDetailScreen (heatmap)
│   │   │   └── workouts.py    # WorkoutsScreen (volume heatmap + stacked form)
│   │   └── web/
│   │       └── app.py         # Streamlit; habits + workouts pages
│   ├── tests/
│   │   ├── conftest.py        # forces POSTGRES_DB=load_log_test
│   │   ├── test_habits.py
│   │   └── test_workouts.py
│   ├── scripts/               # explicit DB migrations
│   │   └── migrate_drop_sessions.py   # legacy session-schema → date-only sets
│   ├── docs/                  # this directory: architecture / schema / features
│   ├── pyproject.toml
│   └── Dockerfile
├── docker-compose.yml         # portable dev stack (talks to shared Postgres)
├── data/                      # personal goal markdown files
├── CLAUDE.md
├── .env.example
└── .env                       # NOT committed
```

## Tech Stack

| Layer      | Library         | Reason                                      |
|------------|-----------------|---------------------------------------------|
| DB driver  | psycopg2-binary | matches existing postgres_tools.py pattern  |
| API        | FastAPI         | already wired up                            |
| TUI        | textual         | modern, composable, keyboard-driven         |
| Web UI     | streamlit       | fast to build, good charting, no JS needed  |
| Runner     | uv              | already in use                              |

## Data Flow

```text
PostgreSQL
    ↑
 db.py  (pool, ensure_database_exists, ensure_tables)
    ↑
habits.py / workouts.py  (all SQL functions, return dicts or DataFrames)
    ↑           ↑              ↑
api.py       tui/app.py    web/app.py
(FastAPI)    (Textual)     (Streamlit)
```

`habits.py` and `workouts.py` are the single source of truth for all queries and mutations. The three interfaces only call those functions — they contain no SQL.

## Database

- Database name: `load_log` (created via `ensure_database_exists("load_log")` on startup)
- `db.py` exposes a module-level pool and three helpers:
  - `get_conn()` → connection from pool
  - `release_conn(conn)` → return to pool
  - `ensure_tables()` → idempotent CREATE TABLE IF NOT EXISTS for all tables

## Running Each Interface (local dev)

```bash
# API server
cd backend && PYTHONPATH=src uv run uvicorn api:app --reload --port 8000

# TUI
cd backend && PYTHONPATH=src uv run python -m tui.app

# Streamlit web UI
cd backend && PYTHONPATH=src uv run streamlit run src/web/app.py
```

## New Dependencies to Add to pyproject.toml

```toml
psycopg2-binary>=2.9
textual>=0.80
streamlit>=1.40
altair>=5.0        # used by streamlit for the completion heatmap
```

## Configuration (.env at repo root)

```env
APP_ENV=development
POSTGRES_URL=localhost
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_PORT=5432
```

`config.py` already resolves the `.env` path by walking up from `__file__` to find `pyproject.toml`, so no changes needed there. `db.py` will import from `config.py`.

## Docker Compose Deployment

Load Log ships with two compose setups, **both of which connect to the same
shared Postgres** running on the home server (defined in
`/Users/jason/GitHub/Docker/docker_compose_projects.yaml`). We never host our
own Postgres — there is one source of truth for the data.

1. **Portable dev stack** — `docker-compose.yml` at the repo root. Runs the API
   and Streamlit containers on any machine that has the repo checked out and an
   `.env` pointing at the shared Postgres. Host ports: API `8004`, Web `8505`.
2. **Server deployment** — service blocks added to the central compose file at
   `/Users/jason/GitHub/Docker/docker_compose_projects.yaml`, where the shared
   `postgres` service already lives.

### Local: `docker-compose.yml` (repo root)

The Mac host runs Docker through **colima** (Homebrew install). It is **not**
configured as a brew background service, so it has to be started manually
each session before any `docker` / `docker-compose` command will work:

```bash
# Start the Docker VM (default profile: 2 CPU / 2 GiB RAM / 100 GiB disk).
colima start

# Optional: bump resources — Postgres + 2 Python services on 2 GiB is tight.
colima start --cpu 4 --memory 6

# Verify it's up.
colima status
docker info | head -5

# Stop the VM when done (containers persist, restart with `colima start`).
colima stop
```

Once colima is running, bring up the stack:

```bash
# from /Users/jason/GitHub/load-log
docker-compose up -d --build         # bring up postgres + api + web
docker-compose logs -f api           # tail api logs
docker-compose down                  # stop everything (data persists in named volume)
docker-compose down -v               # stop and wipe DB
```

Use `docker-compose` (Homebrew formula) on this machine — the v2 `docker compose`
plugin isn't installed.

The local compose:

- Does **not** include a Postgres service. Both containers read
  `POSTGRES_URL` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD`
  from `.env` via variable substitution and connect out to the shared DB.
- That means whatever machine you run `docker-compose up` from will write to
  the **same** Postgres as the server deployment — no schema drift, no test
  data living in a parallel local DB.
- Requirement: the shared Postgres host (whatever `POSTGRES_URL` points at)
  must be reachable from inside Docker's network on this machine. On a Mac
  with colima this works automatically for LAN IPs since the colima VM
  bridges to the host network.

Use `localhost:5433` from the host (`psql`, host-side pytest) to reach the
bundled DB.

### Production deployment

#### Port assignments

| Service        | Host port | Container port |
|----------------|-----------|----------------|
| load-log-api   | 8004      | 8000           |
| load-log-web   | 8505      | 8505           |

Port 8000 is already taken by `duck_db_api`; 8505 is the next free Streamlit slot after `crowncentral` (8503).

#### Services to add to docker_compose_projects.yaml

```yaml
  load-log-fastapi:
    image: load_log_fastapi_image
    build:
      context: ../load-log/backend
      dockerfile: Dockerfile
    container_name: load_log_fastapi
    environment:
      POSTGRES_URL: postgres
      POSTGRES_PORT: "5432"
      POSTGRES_DB: load_log
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    depends_on:
      - postgres
    ports:
      - "8004:8000"
    restart: unless-stopped

  load-log-streamlit:
    image: load_log_streamlit_image
    build:
      context: ../load-log/backend
      dockerfile: Dockerfile
    container_name: load_log_streamlit
    command: ["uv", "run", "streamlit", "run", "src/web/app.py",
              "--server.port=8505", "--server.address=0.0.0.0",
              "--server.headless=true"]
    environment:
      POSTGRES_URL: postgres
      POSTGRES_PORT: "5432"
      POSTGRES_DB: load_log
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    depends_on:
      - postgres
    ports:
      - "8505:8505"
    restart: unless-stopped
```

Both services share the same `backend/Dockerfile`; the web service overrides `CMD` via `command`.
The `POSTGRES_URL` value in `.env` must be `postgres` (the Docker service name) when running in compose,
vs `localhost` for local dev. Use `APP_ENV` to switch if needed.

Service names are deliberately `load-log-fastapi` / `load-log-streamlit` (not
`load-log-api` / `load-log-web`) because the shared prod compose file has many
"api" and "web" services — naming by framework makes them unambiguous at a glance.

These two services connect to the in-file `postgres` service via service name,
just like the portable dev stack connects to it via its LAN address.

#### Deploy steps (when ready)

1. Add the two service blocks above to `docker_compose_projects.yaml`
2. Ensure `POSTGRES_USER` / `POSTGRES_PASSWORD` are set in the prod-host `.env`
   (the postgres service in that file already reads them)
3. `docker compose -f docker_compose_projects.yaml up -d --build load-log-fastapi load-log-streamlit`

## Code Style Rules

- `# %%` section markers throughout every file (Jupyter-compatible cells)
- One function per SQL operation — no inline SQL outside `habits.py` / `workouts.py`
- Functions return `dict`, `list[dict]`, or `pd.DataFrame` — never raw cursor rows
- No ORM — raw psycopg2 with `%s` parameter binding
- Max line length: 120 (matches .flake8)
