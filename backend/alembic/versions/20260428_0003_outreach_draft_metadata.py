"""Add outreach draft metadata.

Revision ID: 20260428_0003
Revises: 20260428_0002
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260428_0003"
down_revision: str | None = "20260428_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("outreach_drafts")}
    if "metadata_json" not in columns:
        op.add_column("outreach_drafts", sa.Column("metadata_json", sa.JSON(), nullable=True))
        op.execute(sa.text("UPDATE outreach_drafts SET metadata_json = '{}' WHERE metadata_json IS NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("outreach_drafts")}
    if "metadata_json" in columns:
        op.drop_column("outreach_drafts", "metadata_json")
