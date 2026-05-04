"""Introduce Roadshow tenant and session tables.

Revision ID: 20260504_0001
Revises: 20260428_0004
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260504_0001"
down_revision = "20260428_0004"
branch_labels = None
depends_on = None


TENANT_SCOPED_TABLES = [
    "audit_events",
    "business_case_runs",
    "feedback_signals",
    "host_calendar_events",
    "open_seminar_windows",
    "outreach_drafts",
    "relationship_briefs",
    "researcher_facts",
    "seminar_slot_overrides",
    "seminar_slot_templates",
    "tour_assembly_proposals",
    "tour_legs",
    "travel_price_checks",
    "wishlist_alerts",
    "wishlist_entries",
    "wishlist_match_participants",
]


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("host_institution_id", sa.String(length=36), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("anonymous_matching_opt_in", sa.Boolean(), nullable=False),
        sa.Column("branding_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)
    op.create_index("ix_tenants_status", "tenants", ["status"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_tenant_membership_user_tenant"),
    )
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])

    op.create_table(
        "tenant_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("research_focuses", sa.JSON(), nullable=False),
        sa.Column("hospitality_policy_json", sa.JSON(), nullable=False),
        sa.Column("rail_policy_json", sa.JSON(), nullable=False),
        sa.Column("outreach_defaults_json", sa.JSON(), nullable=False),
        sa.Column("source_subscriptions_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_settings_tenant_id", "tenant_settings", ["tenant_id"], unique=True)

    op.create_table(
        "tenant_source_subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_name", name="uq_tenant_source_subscription"),
    )
    op.create_index("ix_tenant_source_subscriptions_tenant_id", "tenant_source_subscriptions", ["tenant_id"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active_tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)

    op.create_table(
        "tenant_opportunities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("trip_cluster_id", sa.String(length=36), sa.ForeignKey("trip_clusters.id"), nullable=False),
        sa.Column("opportunity_score", sa.Integer(), nullable=False),
        sa.Column("best_open_window_id", sa.String(length=36), sa.ForeignKey("open_seminar_windows.id"), nullable=True),
        sa.Column("draft_ready", sa.Boolean(), nullable=False),
        sa.Column("uses_unreviewed_evidence", sa.Boolean(), nullable=False),
        sa.Column("fit_rationale", sa.JSON(), nullable=False),
        sa.Column("draft_blockers", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "trip_cluster_id", name="uq_tenant_opportunity_cluster"),
    )

    for table_name in TENANT_SCOPED_TABLES:
        op.add_column(table_name, sa.Column("tenant_id", sa.String(length=36), nullable=True))
        op.create_index(f"ix_{table_name}_tenant_id", table_name, ["tenant_id"])


def downgrade() -> None:
    for table_name in reversed(TENANT_SCOPED_TABLES):
        op.drop_index(f"ix_{table_name}_tenant_id", table_name=table_name)
        op.drop_column(table_name, "tenant_id")
    op.drop_table("tenant_opportunities")
    op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_tenant_source_subscriptions_tenant_id", table_name="tenant_source_subscriptions")
    op.drop_table("tenant_source_subscriptions")
    op.drop_index("ix_tenant_settings_tenant_id", table_name="tenant_settings")
    op.drop_table("tenant_settings")
    op.drop_index("ix_tenant_memberships_tenant_id", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_user_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_tenants_status", table_name="tenants")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
