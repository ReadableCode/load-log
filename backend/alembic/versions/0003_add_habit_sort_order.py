"""add_habit_sort_order

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-17

Adds load_log.habits.sort_order so users can reorder habits in the UI.
Backfills existing rows from id (which matches the previous created_at/id
display order), so the visible order does not change on deploy. The column
stays nullable — clients order with nullslast and assign positions on
insert/reorder, so a NULL only ever means "not yet reordered, sort last".
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE load_log.habits ADD COLUMN IF NOT EXISTS sort_order INTEGER"
    )
    op.execute("UPDATE load_log.habits SET sort_order = id WHERE sort_order IS NULL")


def downgrade() -> None:
    # Non-destructive: keep the column (and any user-arranged order) on downgrade.
    pass
