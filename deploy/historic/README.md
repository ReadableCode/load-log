# deploy/historic

One-shot SQL that has already run against the live database and must never run
again. Nothing in this directory is loaded by `backend/src/bootstrap.py` —
`SCHEMA_FILES` there names the files it applies explicitly, and these are not in
it.

Kept because they explain how the live schema got its present shape, which the
idempotent files in `deploy/` no longer show.

| File | Ran | What it did |
|------|-----|-------------|
| `02_migrate_schema.sql` | 2026-06-21 | Moved the four data tables out of `public` into the `load_log` schema with `ALTER TABLE ... SET SCHEMA`, and granted `load_log_user` on them. |

`02_migrate_schema.sql` also ran
`ALTER DATABASE apps SET search_path = load_log, public`, which is still in
effect and now applies to every app sharing the `apps` database. See
`backlog/shared-apps-search-path.md`.
