"""Add persisted source health checks.

Revision ID: 20260428_0002
Revises: 20260427_0001
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260428_0002"
down_revision: str | None = "20260427_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "source_health_checks" in inspector.get_table_names():
        return

    op.create_table(
        "source_health_checks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("samples", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_health_checks_checked_at", "source_health_checks", ["checked_at"])
    op.create_index("ix_source_health_checks_source_name", "source_health_checks", ["source_name"])
    op.create_index("ix_source_health_checks_source_type", "source_health_checks", ["source_type"])
    op.create_index("ix_source_health_checks_status", "source_health_checks", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "source_health_checks" not in inspector.get_table_names():
        return

    op.drop_index("ix_source_health_checks_status", table_name="source_health_checks")
    op.drop_index("ix_source_health_checks_source_type", table_name="source_health_checks")
    op.drop_index("ix_source_health_checks_source_name", table_name="source_health_checks")
    op.drop_index("ix_source_health_checks_checked_at", table_name="source_health_checks")
    op.drop_table("source_health_checks")
