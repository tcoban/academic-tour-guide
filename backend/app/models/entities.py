from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Time
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


class Researcher(Base):
    __tablename__ = "researchers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    home_institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repec_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    birth_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    facts: Mapped[list["ResearcherFact"]] = relationship(back_populates="researcher", cascade="all, delete-orphan")
    talk_events: Mapped[list["TalkEvent"]] = relationship(back_populates="researcher")
    trip_clusters: Mapped[list["TripCluster"]] = relationship(back_populates="researcher")
    outreach_drafts: Mapped[list["OutreachDraft"]] = relationship(back_populates="researcher")


class ResearcherFact(Base):
    __tablename__ = "researcher_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    researcher_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    fact_type: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="facts")


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
    rationale: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="trip_clusters")
    drafts: Mapped[list["OutreachDraft"]] = relationship(back_populates="trip_cluster")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    researcher: Mapped["Researcher"] = relationship(back_populates="outreach_drafts")
    trip_cluster: Mapped["TripCluster"] = relationship(back_populates="drafts")
