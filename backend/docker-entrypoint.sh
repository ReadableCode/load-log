#!/bin/sh
# Run database migrations before starting whatever command was passed (CMD or a
# docker-compose `command:` override). Setting this as the ENTRYPOINT means the
# streamlit service still gets migrations first even though compose overrides the
# command.
#
# Idempotent: `alembic upgrade head` is a no-op when the DB is already current.
# If the load_log schema does not yet have an alembic_version row (fresh stamp
# pending) the user runs `alembic stamp 0001` manually first per the migration
# plan — this script does not stamp, only upgrades.
set -e

echo "[entrypoint] running alembic upgrade head..."
uv run alembic upgrade head

echo "[entrypoint] migrations complete; starting: $*"
exec "$@"
