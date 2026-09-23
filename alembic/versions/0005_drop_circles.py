"""drop circles, moved to acute-core

Revision ID: cd14b76bce02
Revises: 0004
Create Date: 2026-09-23 22:20:44.982227

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the circles tables.

    Circles moved to acute-core, which owns the product domain. acute-auth is
    identity only: users, tokens, sessions, profile, onboarding and places.

    Destructive. Any circle data here must be copied to acute-core first.
    """
    op.drop_table("circle_invites")
    op.drop_table("circle_members")
    op.drop_table("circles")


def downgrade() -> None:
    """Deliberately not reversible.

    Recreating empty tables would suggest the data came back. To go back past
    this point, restore from a backup taken before it ran.
    """
    raise NotImplementedError(
        "Circles moved to acute-core; restore from a backup to go back."
    )
