"""Add Roadshow touring OS models.

Revision ID: 20260428_0004
Revises: 20260428_0003
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260428_0004"
down_revision: str | None = "20260428_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "speaker_profiles" not in tables:
        op.create_table(
            "speaker_profiles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("researcher_id", sa.String(length=36), nullable=False),
            sa.Column("topics", sa.JSON(), nullable=False),
            sa.Column("fee_floor_chf", sa.Integer(), nullable=True),
            sa.Column("notice_period_days", sa.Integer(), nullable=True),
            sa.Column("travel_preferences", sa.JSON(), nullable=False),
            sa.Column("rider", sa.JSON(), nullable=False),
            sa.Column("availability_notes", sa.Text(), nullable=True),
            sa.Column("communication_preferences", sa.JSON(), nullable=False),
            sa.Column("consent_status", sa.String(length=64), nullable=False),
            sa.Column("verification_status", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("researcher_id"),
        )
        op.create_index("ix_speaker_profiles_consent_status", "speaker_profiles", ["consent_status"])
        op.create_index("ix_speaker_profiles_researcher_id", "speaker_profiles", ["researcher_id"])
        op.create_index("ix_speaker_profiles_verification_status", "speaker_profiles", ["verification_status"])

    if "institution_profiles" not in tables:
        op.create_table(
            "institution_profiles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("institution_id", sa.String(length=36), nullable=False),
            sa.Column("wishlist_topics", sa.JSON(), nullable=False),
            sa.Column("procurement_notes", sa.Text(), nullable=True),
            sa.Column("po_threshold_chf", sa.Integer(), nullable=True),
            sa.Column("grant_code_support", sa.Boolean(), nullable=False),
            sa.Column("coordinator_contacts", sa.JSON(), nullable=False),
            sa.Column("av_notes", sa.Text(), nullable=True),
            sa.Column("hospitality_notes", sa.Text(), nullable=True),
            sa.Column("host_quality_score", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("institution_id"),
        )
        op.create_index("ix_institution_profiles_institution_id", "institution_profiles", ["institution_id"])

    if "wishlist_entries" not in tables:
        op.create_table(
            "wishlist_entries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("institution_id", sa.String(length=36), nullable=False),
            sa.Column("researcher_id", sa.String(length=36), nullable=True),
            sa.Column("speaker_name", sa.String(length=255), nullable=True),
            sa.Column("topic", sa.String(length=255), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
            sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_wishlist_entries_institution_id", "wishlist_entries", ["institution_id"])
        op.create_index("ix_wishlist_entries_researcher_id", "wishlist_entries", ["researcher_id"])
        op.create_index("ix_wishlist_entries_speaker_name", "wishlist_entries", ["speaker_name"])
        op.create_index("ix_wishlist_entries_status", "wishlist_entries", ["status"])
        op.create_index("ix_wishlist_entries_topic", "wishlist_entries", ["topic"])

    if "tour_legs" not in tables:
        op.create_table(
            "tour_legs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("researcher_id", sa.String(length=36), nullable=False),
            sa.Column("trip_cluster_id", sa.String(length=36), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("estimated_fee_total_chf", sa.Integer(), nullable=False),
            sa.Column("estimated_travel_total_chf", sa.Integer(), nullable=False),
            sa.Column("cost_split_json", sa.JSON(), nullable=False),
            sa.Column("rationale", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
            sa.ForeignKeyConstraint(["trip_cluster_id"], ["trip_clusters.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tour_legs_researcher_id", "tour_legs", ["researcher_id"])
        op.create_index("ix_tour_legs_status", "tour_legs", ["status"])
        op.create_index("ix_tour_legs_trip_cluster_id", "tour_legs", ["trip_cluster_id"])

    if "relationship_briefs" not in tables:
        op.create_table(
            "relationship_briefs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("researcher_id", sa.String(length=36), nullable=False),
            sa.Column("institution_id", sa.String(length=36), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("communication_preferences", sa.JSON(), nullable=False),
            sa.Column("decision_patterns", sa.JSON(), nullable=False),
            sa.Column("relationship_history", sa.JSON(), nullable=False),
            sa.Column("operational_memory", sa.JSON(), nullable=False),
            sa.Column("forward_signals", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
            sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("researcher_id", "institution_id", name="uq_relationship_brief_researcher_institution"),
        )
        op.create_index("ix_relationship_briefs_institution_id", "relationship_briefs", ["institution_id"])
        op.create_index("ix_relationship_briefs_researcher_id", "relationship_briefs", ["researcher_id"])

    if "audit_events" not in tables:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("actor_type", sa.String(length=64), nullable=False),
            sa.Column("actor_id", sa.String(length=120), nullable=True),
            sa.Column("entity_type", sa.String(length=120), nullable=False),
            sa.Column("entity_id", sa.String(length=120), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_audit_events_actor_type", "audit_events", ["actor_type"])
        op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
        op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
        op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
        op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])

    if "wishlist_alerts" not in tables:
        op.create_table(
            "wishlist_alerts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("wishlist_entry_id", sa.String(length=36), nullable=False),
            sa.Column("researcher_id", sa.String(length=36), nullable=True),
            sa.Column("trip_cluster_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("match_reason", sa.Text(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
            sa.ForeignKeyConstraint(["trip_cluster_id"], ["trip_clusters.id"]),
            sa.ForeignKeyConstraint(["wishlist_entry_id"], ["wishlist_entries.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("wishlist_entry_id", "trip_cluster_id", name="uq_wishlist_alert_entry_cluster"),
        )
        op.create_index("ix_wishlist_alerts_researcher_id", "wishlist_alerts", ["researcher_id"])
        op.create_index("ix_wishlist_alerts_status", "wishlist_alerts", ["status"])
        op.create_index("ix_wishlist_alerts_trip_cluster_id", "wishlist_alerts", ["trip_cluster_id"])
        op.create_index("ix_wishlist_alerts_wishlist_entry_id", "wishlist_alerts", ["wishlist_entry_id"])

    if "tour_stops" not in tables:
        op.create_table(
            "tour_stops",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tour_leg_id", sa.String(length=36), nullable=False),
            sa.Column("institution_id", sa.String(length=36), nullable=True),
            sa.Column("open_window_id", sa.String(length=36), nullable=True),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("city", sa.String(length=120), nullable=False),
            sa.Column("country", sa.String(length=120), nullable=True),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("format", sa.String(length=64), nullable=False),
            sa.Column("fee_chf", sa.Integer(), nullable=False),
            sa.Column("travel_share_chf", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
            sa.ForeignKeyConstraint(["open_window_id"], ["open_seminar_windows.id"]),
            sa.ForeignKeyConstraint(["tour_leg_id"], ["tour_legs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tour_stops_institution_id", "tour_stops", ["institution_id"])
        op.create_index("ix_tour_stops_open_window_id", "tour_stops", ["open_window_id"])
        op.create_index("ix_tour_stops_status", "tour_stops", ["status"])
        op.create_index("ix_tour_stops_tour_leg_id", "tour_stops", ["tour_leg_id"])

    if "feedback_signals" not in tables:
        op.create_table(
            "feedback_signals",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("researcher_id", sa.String(length=36), nullable=False),
            sa.Column("institution_id", sa.String(length=36), nullable=False),
            sa.Column("tour_leg_id", sa.String(length=36), nullable=True),
            sa.Column("party", sa.String(length=64), nullable=False),
            sa.Column("signal_type", sa.String(length=120), nullable=False),
            sa.Column("value", sa.String(length=255), nullable=False),
            sa.Column("sentiment_score", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
            sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
            sa.ForeignKeyConstraint(["tour_leg_id"], ["tour_legs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_feedback_signals_institution_id", "feedback_signals", ["institution_id"])
        op.create_index("ix_feedback_signals_party", "feedback_signals", ["party"])
        op.create_index("ix_feedback_signals_researcher_id", "feedback_signals", ["researcher_id"])
        op.create_index("ix_feedback_signals_signal_type", "feedback_signals", ["signal_type"])
        op.create_index("ix_feedback_signals_tour_leg_id", "feedback_signals", ["tour_leg_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for index_name, table_name in [
        ("ix_feedback_signals_tour_leg_id", "feedback_signals"),
        ("ix_feedback_signals_signal_type", "feedback_signals"),
        ("ix_feedback_signals_researcher_id", "feedback_signals"),
        ("ix_feedback_signals_party", "feedback_signals"),
        ("ix_feedback_signals_institution_id", "feedback_signals"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "feedback_signals" in tables:
        op.drop_table("feedback_signals")

    for index_name, table_name in [
        ("ix_tour_stops_tour_leg_id", "tour_stops"),
        ("ix_tour_stops_status", "tour_stops"),
        ("ix_tour_stops_open_window_id", "tour_stops"),
        ("ix_tour_stops_institution_id", "tour_stops"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "tour_stops" in tables:
        op.drop_table("tour_stops")

    for index_name, table_name in [
        ("ix_wishlist_alerts_wishlist_entry_id", "wishlist_alerts"),
        ("ix_wishlist_alerts_trip_cluster_id", "wishlist_alerts"),
        ("ix_wishlist_alerts_status", "wishlist_alerts"),
        ("ix_wishlist_alerts_researcher_id", "wishlist_alerts"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "wishlist_alerts" in tables:
        op.drop_table("wishlist_alerts")

    for index_name, table_name in [
        ("ix_audit_events_event_type", "audit_events"),
        ("ix_audit_events_entity_type", "audit_events"),
        ("ix_audit_events_entity_id", "audit_events"),
        ("ix_audit_events_created_at", "audit_events"),
        ("ix_audit_events_actor_type", "audit_events"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "audit_events" in tables:
        op.drop_table("audit_events")

    for index_name, table_name in [
        ("ix_relationship_briefs_researcher_id", "relationship_briefs"),
        ("ix_relationship_briefs_institution_id", "relationship_briefs"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "relationship_briefs" in tables:
        op.drop_table("relationship_briefs")

    for index_name, table_name in [
        ("ix_tour_legs_trip_cluster_id", "tour_legs"),
        ("ix_tour_legs_status", "tour_legs"),
        ("ix_tour_legs_researcher_id", "tour_legs"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "tour_legs" in tables:
        op.drop_table("tour_legs")

    for index_name, table_name in [
        ("ix_wishlist_entries_topic", "wishlist_entries"),
        ("ix_wishlist_entries_status", "wishlist_entries"),
        ("ix_wishlist_entries_speaker_name", "wishlist_entries"),
        ("ix_wishlist_entries_researcher_id", "wishlist_entries"),
        ("ix_wishlist_entries_institution_id", "wishlist_entries"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "wishlist_entries" in tables:
        op.drop_table("wishlist_entries")

    if "institution_profiles" in tables:
        op.drop_index("ix_institution_profiles_institution_id", table_name="institution_profiles")
        op.drop_table("institution_profiles")

    for index_name, table_name in [
        ("ix_speaker_profiles_verification_status", "speaker_profiles"),
        ("ix_speaker_profiles_researcher_id", "speaker_profiles"),
        ("ix_speaker_profiles_consent_status", "speaker_profiles"),
    ]:
        if table_name in tables:
            op.drop_index(index_name, table_name=table_name)
    if "speaker_profiles" in tables:
        op.drop_table("speaker_profiles")
