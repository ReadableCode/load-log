"""initial_schema (idempotent baseline)

Revision ID: 0001
Revises:
Create Date: 2026-06-20

Baseline for Alembic's history. Creates the load-log tables —

    habits, habit_completions, exercises, workout_sets

— in the `load_log` schema, but ONLY with CREATE ... IF NOT EXISTS, so it is:

  * a harmless no-op on the production DB, where the tables already exist
    (created by db.ensure_tables() and moved into the load_log schema during the
    manual Phase 2 migration); and
  * the thing that actually builds the schema on a fresh database — the local
    dev stack (docker-compose.dev.yml) and any cloner — so `alembic upgrade head`
    works from zero without a manual stamp.

This mirrors the DDL in backend/docs/schema.md exactly. It is intentionally
non-destructive (no DROP / no ALTER COLUMN), per the project's DB safety rules.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS load_log")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS load_log.habits (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            created_at  DATE NOT NULL DEFAULT CURRENT_DATE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS load_log.habit_completions (
            id              SERIAL PRIMARY KEY,
            habit_id        INTEGER NOT NULL REFERENCES load_log.habits(id) ON DELETE CASCADE,
            completed_date  DATE NOT NULL,
            UNIQUE (habit_id, completed_date)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS load_log.exercises (
            id    SERIAL PRIMARY KEY,
            name  TEXT NOT NULL UNIQUE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS load_log.workout_sets (
            id            SERIAL PRIMARY KEY,
            workout_date  DATE NOT NULL DEFAULT CURRENT_DATE,
            exercise_id   INTEGER NOT NULL REFERENCES load_log.exercises(id),
            set_number    INTEGER NOT NULL,
            reps          INTEGER NOT NULL,
            weight_lbs    REAL NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS workout_sets_date_idx "
        "ON load_log.workout_sets (workout_date)"
    )


def downgrade() -> None:
    # Non-destructive baseline: we deliberately do NOT drop the data tables here.
    pass
