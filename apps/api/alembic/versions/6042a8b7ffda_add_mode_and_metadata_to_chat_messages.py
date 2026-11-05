"""add_mode_and_metadata_to_chat_messages

Revision ID: 6042a8b7ffda
Revises: aaf92165f231
Create Date: 2026-11-05 20:36:21.993313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6042a8b7ffda'
down_revision: Union[str, Sequence[str], None] = 'aaf92165f231'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'chat_messages',
        sa.Column('mode', sa.String(length=50), server_default=sa.text("'standard'"), nullable=False),
    )
    op.add_column(
        'chat_messages',
        sa.Column(
            'mode_metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_messages', 'mode_metadata')
    op.drop_column('chat_messages', 'mode')
