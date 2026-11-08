"""add_roadmap_exam_and_remediation_fields

Revision ID: b1e83c49d20a
Revises: 6042a8b7ffda
Create Date: 2026-11-08 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1e83c49d20a"
down_revision: Union[str, Sequence[str], None] = "6042a8b7ffda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Idempotently upgrade schema for Roadmap Final Assessment, Adaptive Remediation & User Avatar."""
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT NULL;"
    )
    op.execute(
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS exam_status VARCHAR(20) NOT NULL DEFAULT 'locked';"
    )
    op.execute(
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS latest_exam_score DOUBLE PRECISION NULL;"
    )
    op.execute(
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS iteration INTEGER NOT NULL DEFAULT 1;"
    )
    op.execute(
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS parent_roadmap_id UUID NULL REFERENCES roadmaps(id) ON DELETE SET NULL;"
    )
    op.execute(
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS weak_topics JSONB NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute("ALTER TABLE quizzes ALTER COLUMN document_id DROP NOT NULL;")
    op.execute(
        "ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS roadmap_id UUID NULL REFERENCES roadmaps(id) ON DELETE CASCADE;"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_quizzes_roadmap_id ON quizzes (roadmap_id);")
    op.execute(
        "ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS source_document_id UUID NULL;"
    )
    op.execute(
        "ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS source_document_title VARCHAR(255) NULL;"
    )


def downgrade() -> None:
    """Idempotently downgrade schema."""
    op.execute("ALTER TABLE quiz_questions DROP COLUMN IF EXISTS source_document_title;")
    op.execute("ALTER TABLE quiz_questions DROP COLUMN IF EXISTS source_document_id;")
    op.execute("DROP INDEX IF EXISTS ix_quizzes_roadmap_id;")
    op.execute("ALTER TABLE quizzes DROP COLUMN IF EXISTS roadmap_id;")
    op.execute("ALTER TABLE roadmaps DROP COLUMN IF EXISTS weak_topics;")
    op.execute("ALTER TABLE roadmaps DROP COLUMN IF EXISTS parent_roadmap_id;")
    op.execute("ALTER TABLE roadmaps DROP COLUMN IF EXISTS iteration;")
    op.execute("ALTER TABLE roadmaps DROP COLUMN IF EXISTS latest_exam_score;")
    op.execute("ALTER TABLE roadmaps DROP COLUMN IF EXISTS exam_status;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS avatar_url;")
