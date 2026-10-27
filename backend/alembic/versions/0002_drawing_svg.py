"""vector (SVG) export of the final drawing

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_results") as batch:
        batch.add_column(sa.Column("drawing_svg_path", sa.String(512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_results") as batch:
        batch.drop_column("drawing_svg_path")
