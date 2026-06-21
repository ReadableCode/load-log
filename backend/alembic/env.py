# %%
# Imports #

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# %%
# Config #

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up loggers from the ini file (only when a config file is present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Build the SQLAlchemy URL from the same POSTGRES_* env vars db.py / config.py
# use. We never hardcode the URL or read it from a .env secret here — the
# container gets these from docker-compose `environment:`.
POSTGRES_USER = os.environ.get("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_URL = os.environ.get("POSTGRES_URL", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "apps")

db_url = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_URL}:{POSTGRES_PORT}/{POSTGRES_DB}"
)
config.set_main_option("sqlalchemy.url", db_url)

# No ORM models — migrations are hand-written op.execute() SQL, so there is no
# autogenerate target metadata.
target_metadata = None

# The alembic_version bookkeeping table lives in the load_log schema (the app's
# dedicated schema), NOT public. include_schemas lets alembic reflect across
# non-default schemas if a future migration ever needs it.
VERSION_TABLE_SCHEMA = "load_log"


# %%
# Offline #


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (`alembic upgrade --sql`)."""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=VERSION_TABLE_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# %%
# Online #


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=VERSION_TABLE_SCHEMA,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


# %%
# Main #


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
