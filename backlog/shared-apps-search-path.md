# load-log set search_path on the whole shared apps database

    found:  2026-08-28
    status: open
    verify: docker exec -i postgres psql -U postgres -d postgres -c "select datname, setconfig from pg_db_role_setting s join pg_database d on d.oid = s.setdatabase"

`deploy/historic/02_migrate_schema.sql` ran this in 2026-06, when load-log was
the only app on the instance:

```sql
ALTER DATABASE apps SET search_path = load_log, public;
```

It is still in effect, and `apps` is no longer load-log's alone. As of
2026-08-28 the database holds six schemas:

    book_bot
    cash_flow_commander
    load_log
    public
    solitaire
    syncplex

So every session opened against `apps` by any app, by the shared postgrest-auth
service, or by a human at `psql`, resolves unqualified table names to
`load_log` first. One app's historic migration is setting a default for the
whole shared database, which is the sort of cross-schema reach into other apps'
territory that I1 exists to prevent.

## Why it has not bitten anything

Everything that would notice is already schema-qualified:

- `deploy/02_schema.sql` and `03_secure_users.sql` qualify every object
  (`load_log.habits`, not `habits`).
- `scripts/create_user.py` and `backup_to_files.py` qualify their SQL.
- Application data never uses this connection at all — it goes through
  PostgREST, which pins the schema per request with `Accept-Profile`
  (I9), not with `search_path`.
- The other apps' bootstraps qualify their objects the same way.

The hazard is a future unqualified statement, from any app or any person, that
silently lands on a `load_log` table because it happens to share a name. The
collision is not hypothetical: `users` exists in four of the six schemas
(`book_bot`, `load_log`, `solitaire`, `syncplex`), and a session opened against
`apps` on 2026-08-28 reported `search_path = load_log, public`,
`current_schema() = load_log`, and resolved a bare `users` to `load_log.users`.
So `SELECT * FROM users` at a `psql` prompt returns load-log's credentials
table today.

## fix

Drop the database-wide default:

```sql
ALTER DATABASE apps RESET search_path;
```

Do this from the Docker repo's runbook rather than from load-log's bootstrap:
the setting belongs to the shared database, so no single app should assert or
reset it at startup. Resetting it from load-log's boot path would be the same
mistake in the other direction.

blast radius: sessions that today rely on the implicit `load_log` default would
start resolving to `public`. Grep each app for unqualified DDL/DML before
running it — `load-log` is clean (checked 2026-08-28); `Cash_Flow_Commander`
uses SQLAlchemy direct-to-Postgres and is the most likely to depend on a
default, so check it first. PostgREST is unaffected either way: it reads
`PGRST_DB_SCHEMAS` and the per-request profile header, not the database
default.

not doing yet: out of scope for the Postgres conformance work, which was about
load-log's own migration mechanism. This needs a look at every app that
connects to `apps`, not just this one, so it wants its own change window.
