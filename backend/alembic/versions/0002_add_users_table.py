"""add_users_table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-20

Creates load_log.users — the credential store the auth service reads to issue
JWTs. Passwords are stored as bcrypt hashes (see scripts/create_user.py).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS load_log.users (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            username      text UNIQUE NOT NULL,
            password_hash text NOT NULL,
            created_at    timestamptz DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS load_log.users;")
