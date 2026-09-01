"""shrink recipes.embedding to 1024 dims

Revision ID: 2586f1c1d796
Revises: 8e1ad5807d15
Create Date: 2026-08-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import pgvector


# revision identifiers, used by Alembic.
revision: str = '2586f1c1d796'
down_revision: Union[str, Sequence[str], None] = '8e1ad5807d15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    1536-dim vectors (OpenAI text-embedding-3-small) cannot be reinterpreted
    as 1024-dim vectors, so existing embeddings are discarded via `USING
    NULL` rather than cast. Re-populate them afterwards with
    `python manage_db.py --reembed`.
    """
    op.alter_column(
        'recipes',
        'embedding',
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=1024),
        postgresql_using='NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'recipes',
        'embedding',
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
        postgresql_using='NULL',
    )
