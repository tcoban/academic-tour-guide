from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def new_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    roadshow_profile: Mapped["InstitutionProfile | None"] = relationship(
        back_populates="institution",
        cascade="all, delete-orphan",
    )
    wishlist_entries: Mapped[list["WishlistEntry"]] = relationship(back_populates="institution")


class Researcher(Base):
    __tablename__ = "researchers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    home_institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"), nullable=True, index=True)
    repec_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    birth_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    home_institution_ref: Mapped[Institution | None] = relationship(foreign_keys=[home_institution_id])
    facts: Mapped[list["ResearcherFact"]] = relationship(back_populates="researcher", cascade="all, delete-orphan")
    fact_candidates: Mapped[list["FactCandidate"]] = relationship(
        back_populates="researcher",
        cascade="all, delete-orphan",
    )
    identities: Mapped[list["ResearcherIdentity"]] = relationship(
        back_populates="researcher",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="researcher",
        cascade="all, delete-orphan",
    )
    talk_events: Mapped[list["TalkEvent"]] = relationship(back_populates="researcher")
    trip_clusters: Mapped[list["TripCluster"]] = relationship(back_populates="researcher")
    outreach_drafts: Mapped[list["OutreachDraft"]] = relationship(back_populates="researcher")
    speaker_profile: Mapped["SpeakerProfile | None"] = relationship(
        back_populates="researcher",
        cascade="all, delete-orphan",
    )
    wishlist_entries: Mapped[list["WishlistEntry"]] = relationship(back_populates="researcher")
    tour_legs: Mapped[list["TourLeg"]] = relationship(back_populates="researcher")
    relationship_briefs: Mapped[list["RelationshipBrief"]] = relationship(back_populates="researcher")
    feedback_signals: Mapped[list["FeedbackSignal"]] = relationship(back_populates="researcher")


class SpeakerProfile(Base):
    __tablename__ = "speaker_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), unique=True, index=True)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    fee_floor_chf: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    travel_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rider: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    availability_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    communication_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    consent_status: Mapped[str] = mapped_column(String(64), default="pre_consent", index=True)
    verification_status: Mapped[str] = mapped_column(String(64), default="shadow", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="speaker_profile")


class InstitutionProfile(Base):
    __tablename__ = "institution_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), unique=True, index=True)
    wishlist_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    procurement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    po_threshold_chf: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grant_code_support: Mapped[bool] = mapped_column(Boolean, default=False)
    coordinator_contacts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    av_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    hospitality_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    host_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    institution: Mapped["Institution"] = relationship(back_populates="roadshow_profile")


class WishlistEntry(Base):
    __tablename__ = "wishlist_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    researcher_id: Mapped[str | None] = mapped_column(ForeignKey("researchers.id"), nullable=True, index=True)
    speaker_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    institution: Mapped["Institution"] = relationship(back_populates="wishlist_entries")
    researcher: Mapped["Researcher | None"] = relationship(back_populates="wishlist_entries")
    alerts: Mapped[list["WishlistAlert"]] = relationship(back_populates="wishlist_entry", cascade="all, delete-orphan")


class WishlistAlert(Base):
    __tablename__ = "wishlist_alerts"
    __table_args__ = (UniqueConstraint("wishlist_entry_id", "trip_cluster_id", name="uq_wishlist_alert_entry_cluster"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    wishlist_entry_id: Mapped[str] = mapped_column(ForeignKey("wishlist_entries.id"), index=True)
    researcher_id: Mapped[str | None] = mapped_column(ForeignKey("researchers.id"), nullable=True, index=True)
    trip_cluster_id: Mapped[str | None] = mapped_column(ForeignKey("trip_clusters.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    match_reason: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    wishlist_entry: Mapped["WishlistEntry"] = relationship(back_populates="alerts")
    researcher: Mapped["Researcher | None"] = relationship()
    trip_cluster: Mapped["TripCluster | None"] = relationship()


class ResearcherIdentity(Base):
    __tablename__ = "researcher_identities"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_researcher_identity_provider_external"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    canonical_name: Mapped[str] = mapped_column(String(255))
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    match_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ranking_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    ranking_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="identities")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    url: Mapped[str] = mapped_column(String(500), index=True)
    discovered_from_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetch_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="documents")
    fact_candidates: Mapped[list["FactCandidate"]] = relationship(back_populates="source_document")
    approved_facts: Mapped[list["ResearcherFact"]] = relationship(back_populates="source_document")


class SourceHealthCheck(Base):
    __tablename__ = "source_health_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_name: Mapped[str] = mapped_column(String(120), index=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    samples: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ResearcherFact(Base):
    __tablename__ = "researcher_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"), nullable=True, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True, index=True)
    approved_via_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("fact_candidates.id"), nullable=True, index=True)
    fact_type: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_origin: Mapped[str] = mapped_column(String(64), default="manual")
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="facts")
    institution: Mapped[Institution | None] = relationship()
    source_document: Mapped[SourceDocument | None] = relationship(back_populates="approved_facts")
    approved_via_candidate: Mapped["FactCandidate | None"] = relationship(
        back_populates="approved_fact",
        foreign_keys=[approved_via_candidate_id],
    )


class FactCandidate(Base):
    __tablename__ = "fact_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True, index=True)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"), nullable=True, index=True)
    fact_type: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    origin: Mapped[str] = mapped_column(String(64), default="extracted")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="fact_candidates")
    source_document: Mapped[SourceDocument | None] = relationship(back_populates="fact_candidates")
    institution: Mapped[Institution | None] = relationship()
    approved_fact: Mapped[ResearcherFact | None] = relationship(
        back_populates="approved_via_candidate",
        foreign_keys="ResearcherFact.approved_via_candidate_id",
    )


class TalkEvent(Base):
    __tablename__ = "talk_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str | None] = mapped_column(ForeignKey("researchers.id"), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(500))
    speaker_name: Mapped[str] = mapped_column(String(255), index=True)
    speaker_affiliation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(120))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(String(500))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped[Researcher | None] = relationship(back_populates="talk_events")


class TripCluster(Base):
    __tablename__ = "trip_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    itinerary: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    opportunity_score: Mapped[int] = mapped_column(Integer, default=0)
    uses_unreviewed_evidence: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="trip_clusters")
    drafts: Mapped[list["OutreachDraft"]] = relationship(back_populates="trip_cluster")
    tour_legs: Mapped[list["TourLeg"]] = relationship(back_populates="trip_cluster")


class TourLeg(Base):
    __tablename__ = "tour_legs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    trip_cluster_id: Mapped[str | None] = mapped_column(ForeignKey("trip_clusters.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    estimated_fee_total_chf: Mapped[int] = mapped_column(Integer, default=0)
    estimated_travel_total_chf: Mapped[int] = mapped_column(Integer, default=0)
    cost_split_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rationale: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="tour_legs")
    trip_cluster: Mapped["TripCluster | None"] = relationship(back_populates="tour_legs")
    stops: Mapped[list["TourStop"]] = relationship(
        back_populates="tour_leg",
        cascade="all, delete-orphan",
        order_by="TourStop.sequence",
    )
    feedback_signals: Mapped[list["FeedbackSignal"]] = relationship(back_populates="tour_leg")


class TourStop(Base):
    __tablename__ = "tour_stops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tour_leg_id: Mapped[str] = mapped_column(ForeignKey("tour_legs.id"), index=True)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"), nullable=True, index=True)
    open_window_id: Mapped[str | None] = mapped_column(ForeignKey("open_seminar_windows.id"), nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    format: Mapped[str] = mapped_column(String(64), default="seminar")
    fee_chf: Mapped[int] = mapped_column(Integer, default=0)
    travel_share_chf: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tour_leg: Mapped["TourLeg"] = relationship(back_populates="stops")
    institution: Mapped["Institution | None"] = relationship()
    open_window: Mapped["OpenSeminarWindow | None"] = relationship()


class RelationshipBrief(Base):
    __tablename__ = "relationship_briefs"
    __table_args__ = (UniqueConstraint("researcher_id", "institution_id", name="uq_relationship_brief_researcher_institution"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    communication_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decision_patterns: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    relationship_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    operational_memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    forward_signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="relationship_briefs")
    institution: Mapped["Institution"] = relationship()


class FeedbackSignal(Base):
    __tablename__ = "feedback_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    tour_leg_id: Mapped[str | None] = mapped_column(ForeignKey("tour_legs.id"), nullable=True, index=True)
    party: Mapped[str] = mapped_column(String(64), index=True)
    signal_type: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[str] = mapped_column(String(255))
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="feedback_signals")
    institution: Mapped["Institution"] = relationship()
    tour_leg: Mapped["TourLeg | None"] = relationship(back_populates="feedback_signals")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    actor_type: Mapped[str] = mapped_column(String(64), default="system", index=True)
    actor_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class HostCalendarEvent(Base):
    __tablename__ = "host_calendar_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(String(500))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SeminarSlotTemplate(Base):
    __tablename__ = "seminar_slot_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    label: Mapped[str] = mapped_column(String(255))
    weekday: Mapped[int] = mapped_column(Integer, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Zurich")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SeminarSlotOverride(Base):
    __tablename__ = "seminar_slot_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OpenSeminarWindow(Base):
    __tablename__ = "open_seminar_windows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    derived_from_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("seminar_slot_templates.id"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(64), default="derived")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    trip_cluster_id: Mapped[str] = mapped_column(ForeignKey("trip_clusters.id"), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    blocked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="outreach_drafts")
    trip_cluster: Mapped["TripCluster"] = relationship(back_populates="drafts")
