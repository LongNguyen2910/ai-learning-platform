"""widen_quiz_option_fields

Revision ID: c2f94e77a10b
Revises: b1e83c49d20a
Create Date: 2026-11-15 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2f94e77a10b"
down_revision: Union[str, Sequence[str], None] = "b1e83c49d20a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE quiz_attempt_answers ALTER COLUMN selected_option TYPE VARCHAR(20);"
    )
    op.execute(
        "ALTER TABLE quiz_questions ALTER COLUMN correct_option TYPE VARCHAR(20);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE quiz_attempt_answers ALTER COLUMN selected_option TYPE VARCHAR(5);"
    )
    op.execute(
        "ALTER TABLE quiz_questions ALTER COLUMN correct_option TYPE VARCHAR(5);"
    )
