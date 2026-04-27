"""Initial Academic Tour Guide schema.

Revision ID: 20260427_0001
Revises:
Create Date: 2026-04-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260427_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_institutions_name", "institutions", ["name"])

    op.create_table(
        "researchers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("home_institution", sa.String(length=255), nullable=True),
        sa.Column("home_institution_id", sa.String(length=36), nullable=True),
        sa.Column("repec_rank", sa.Float(), nullable=True),
        sa.Column("birth_month", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["home_institution_id"], ["institutions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_researchers_home_institution_id", "researchers", ["home_institution_id"])
    op.create_index("ix_researchers_name", "researchers", ["name"])
    op.create_index("ix_researchers_normalized_name", "researchers", ["normalized_name"])

    op.create_table(
        "researcher_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("researcher_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=False),
        sa.Column("ranking_percentile", sa.Float(), nullable=True),
        sa.Column("ranking_label", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_researcher_identity_provider_external"),
    )
    op.create_index("ix_researcher_identities_external_id", "researcher_identities", ["external_id"])
    op.create_index("ix_researcher_identities_provider", "researcher_identities", ["provider"])
    op.create_index("ix_researcher_identities_researcher_id", "researcher_identities", ["researcher_id"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("researcher_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("discovered_from_url", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("fetch_status", sa.String(length=32), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_documents_fetch_status", "source_documents", ["fetch_status"])
    op.create_index("ix_source_documents_researcher_id", "source_documents", ["researcher_id"])
    op.create_index("ix_source_documents_url", "source_documents", ["url"])

    op.create_table(
        "fact_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("researcher_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=True),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_snippet", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("origin", sa.String(length=64), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
        sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_candidates_fact_type", "fact_candidates", ["fact_type"])
    op.create_index("ix_fact_candidates_institution_id", "fact_candidates", ["institution_id"])
    op.create_index("ix_fact_candidates_researcher_id", "fact_candidates", ["researcher_id"])
    op.create_index("ix_fact_candidates_source_document_id", "fact_candidates", ["source_document_id"])
    op.create_index("ix_fact_candidates_status", "fact_candidates", ["status"])

    op.create_table(
        "researcher_facts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("researcher_id", sa.String(length=36), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("source_document_id", sa.String(length=36), nullable=True),
        sa.Column("approved_via_candidate_id", sa.String(length=36), nullable=True),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("evidence_snippet", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("approval_origin", sa.String(length=64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_via_candidate_id"], ["fact_candidates.id"]),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
        sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_researcher_facts_approved_via_candidate_id", "researcher_facts", ["approved_via_candidate_id"])
    op.create_index("ix_researcher_facts_fact_type", "researcher_facts", ["fact_type"])
    op.create_index("ix_researcher_facts_institution_id", "researcher_facts", ["institution_id"])
    op.create_index("ix_researcher_facts_researcher_id", "researcher_facts", ["researcher_id"])
    op.create_index("ix_researcher_facts_source_document_id", "researcher_facts", ["source_document_id"])

    op.create_table(
        "talk_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("researcher_id", sa.String(length=36), nullable=True),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("speaker_name", sa.String(length=255), nullable=False),
        sa.Column("speaker_affiliation", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash"),
    )
    op.create_index("ix_talk_events_researcher_id", "talk_events", ["researcher_id"])
    op.create_index("ix_talk_events_source_hash", "talk_events", ["source_hash"])
    op.create_index("ix_talk_events_source_name", "talk_events", ["source_name"])
    op.create_index("ix_talk_events_speaker_name", "talk_events", ["speaker_name"])
    op.create_index("ix_talk_events_starts_at", "talk_events", ["starts_at"])

    op.create_table(
        "trip_clusters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("researcher_id", sa.String(length=36), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("itinerary", sa.JSON(), nullable=False),
        sa.Column("opportunity_score", sa.Integer(), nullable=False),
        sa.Column("uses_unreviewed_evidence", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_clusters_researcher_id", "trip_clusters", ["researcher_id"])

    op.create_table(
        "host_calendar_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash"),
    )
    op.create_index("ix_host_calendar_events_source_hash", "host_calendar_events", ["source_hash"])
    op.create_index("ix_host_calendar_events_starts_at", "host_calendar_events", ["starts_at"])

    op.create_table(
        "seminar_slot_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seminar_slot_templates_weekday", "seminar_slot_templates", ["weekday"])

    op.create_table(
        "seminar_slot_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seminar_slot_overrides_start_at", "seminar_slot_overrides", ["start_at"])
    op.create_index("ix_seminar_slot_overrides_status", "seminar_slot_overrides", ["status"])

    op.create_table(
        "open_seminar_windows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("derived_from_template_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["derived_from_template_id"], ["seminar_slot_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_open_seminar_windows_starts_at", "open_seminar_windows", ["starts_at"])

    op.create_table(
        "outreach_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("researcher_id", sa.String(length=36), nullable=False),
        sa.Column("trip_cluster_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocked_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["researcher_id"], ["researchers.id"]),
        sa.ForeignKeyConstraint(["trip_cluster_id"], ["trip_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outreach_drafts_researcher_id", "outreach_drafts", ["researcher_id"])
    op.create_index("ix_outreach_drafts_trip_cluster_id", "outreach_drafts", ["trip_cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_outreach_drafts_trip_cluster_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_researcher_id", table_name="outreach_drafts")
    op.drop_table("outreach_drafts")
    op.drop_index("ix_open_seminar_windows_starts_at", table_name="open_seminar_windows")
    op.drop_table("open_seminar_windows")
    op.drop_index("ix_seminar_slot_overrides_status", table_name="seminar_slot_overrides")
    op.drop_index("ix_seminar_slot_overrides_start_at", table_name="seminar_slot_overrides")
    op.drop_table("seminar_slot_overrides")
    op.drop_index("ix_seminar_slot_templates_weekday", table_name="seminar_slot_templates")
    op.drop_table("seminar_slot_templates")
    op.drop_index("ix_host_calendar_events_starts_at", table_name="host_calendar_events")
    op.drop_index("ix_host_calendar_events_source_hash", table_name="host_calendar_events")
    op.drop_table("host_calendar_events")
    op.drop_index("ix_trip_clusters_researcher_id", table_name="trip_clusters")
    op.drop_table("trip_clusters")
    op.drop_index("ix_talk_events_starts_at", table_name="talk_events")
    op.drop_index("ix_talk_events_speaker_name", table_name="talk_events")
    op.drop_index("ix_talk_events_source_name", table_name="talk_events")
    op.drop_index("ix_talk_events_source_hash", table_name="talk_events")
    op.drop_index("ix_talk_events_researcher_id", table_name="talk_events")
    op.drop_table("talk_events")
    op.drop_index("ix_researcher_facts_source_document_id", table_name="researcher_facts")
    op.drop_index("ix_researcher_facts_researcher_id", table_name="researcher_facts")
    op.drop_index("ix_researcher_facts_institution_id", table_name="researcher_facts")
    op.drop_index("ix_researcher_facts_fact_type", table_name="researcher_facts")
    op.drop_index("ix_researcher_facts_approved_via_candidate_id", table_name="researcher_facts")
    op.drop_table("researcher_facts")
    op.drop_index("ix_fact_candidates_status", table_name="fact_candidates")
    op.drop_index("ix_fact_candidates_source_document_id", table_name="fact_candidates")
    op.drop_index("ix_fact_candidates_researcher_id", table_name="fact_candidates")
    op.drop_index("ix_fact_candidates_institution_id", table_name="fact_candidates")
    op.drop_index("ix_fact_candidates_fact_type", table_name="fact_candidates")
    op.drop_table("fact_candidates")
    op.drop_index("ix_source_documents_url", table_name="source_documents")
    op.drop_index("ix_source_documents_researcher_id", table_name="source_documents")
    op.drop_index("ix_source_documents_fetch_status", table_name="source_documents")
    op.drop_table("source_documents")
    op.drop_index("ix_researcher_identities_researcher_id", table_name="researcher_identities")
    op.drop_index("ix_researcher_identities_provider", table_name="researcher_identities")
    op.drop_index("ix_researcher_identities_external_id", table_name="researcher_identities")
    op.drop_table("researcher_identities")
    op.drop_index("ix_researchers_normalized_name", table_name="researchers")
    op.drop_index("ix_researchers_name", table_name="researchers")
    op.drop_index("ix_researchers_home_institution_id", table_name="researchers")
    op.drop_table("researchers")
    op.drop_index("ix_institutions_name", table_name="institutions")
    op.drop_table("institutions")
