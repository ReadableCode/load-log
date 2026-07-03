# Dev fixtures

Tools for previewing the app locally without touching the real auth service,
PostgREST, or Postgres. Nothing in this directory is imported by production
code — it sits outside `src/` so that can't happen by accident.

## Browser preview with fake data

`stub/api_client.py` is a drop-in fake of `src/api_client.py`: any
username/password logs in, and every read returns deterministic synthetic
data (three exercises, ~180 days of Mon/Wed/Fri sessions with progressive
overload). It shadows the real client via `PYTHONPATH` ordering — the stub
directory is listed first, so `import api_client` resolves here instead.

From `backend/`:

```bash
PYTHONPATH="dev/stub:src" uv run streamlit run src/web/app.py --server.port 8601
```

Then open <http://localhost:8601> and log in with anything (e.g. `demo` /
`demo`). The port is pinned to 8601 to stay clear of a deployed instance on
Streamlit's default 8501; pass any other free port if 8601 is taken —
Streamlit fails loudly on a busy port rather than hijacking it.

To preview a branch without disturbing your main checkout:

```bash
git worktree add ../load-log-preview <branch>
cd ../load-log-preview/backend && uv sync
PYTHONPATH="dev/stub:src" uv run streamlit run src/web/app.py --server.port 8601
```

Writes (logging sets, toggling habits, edits/deletes) are accepted but
discarded — the fake data is regenerated fresh on each app start, so there is
nothing to clean up.
