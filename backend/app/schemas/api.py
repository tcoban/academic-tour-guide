from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResearcherFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    fact_type: str
    value: str
    confidence: float
    source_url: str | None = None
    evidence_snippet: str | None = None
    verified: bool


class ResearcherRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    normalized_name: str
    home_institution: str | None = None
    repec_rank: float | None = None
    birth_month: int | None = None
    facts: list[ResearcherFactRead] = Field(default_factory=list)


class TalkEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_name: str
    title: str
    speaker_name: str
    speaker_affiliation: str | None = None
    city: str
    country: str
    starts_at: datetime
    ends_at: datetime | None = None
    url: str


class TripClusterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    start_date: date
    end_date: date
    itinerary: list[dict[str, Any]]
    opportunity_score: int
    rationale: list[dict[str, Any]]


class HostCalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    location: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    url: str
    metadata_json: dict[str, Any]


class OpenSeminarWindowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    starts_at: datetime
    ends_at: datetime
    source: str
    metadata_json: dict[str, Any]


class SeminarSlotTemplateCreate(BaseModel):
    label: str
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    timezone: str = "Europe/Zurich"
    active: bool = True


class SeminarSlotTemplateRead(SeminarSlotTemplateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str


class SeminarSlotOverrideCreate(BaseModel):
    start_at: datetime
    end_at: datetime
    status: str
    reason: str | None = None


class SeminarSlotOverrideRead(SeminarSlotOverrideCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str


class DailyCatchResponse(BaseModel):
    recent_events: list[TalkEventRead]
    top_clusters: list[TripClusterRead]


class CalendarOverlayResponse(BaseModel):
    host_events: list[HostCalendarEventRead]
    open_windows: list[OpenSeminarWindowRead]


class EnrichRequest(BaseModel):
    cv_text: str | None = None
    source_url: str | None = None
    repec_rank: float | None = None
    phd_institution: str | None = None
    nationality: str | None = None
    home_institution: str | None = None
    birth_month: int | None = Field(default=None, ge=1, le=12)


class DraftCreate(BaseModel):
    researcher_id: str
    trip_cluster_id: str


class DraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    trip_cluster_id: str
    subject: str
    body: str
    status: str
    blocked_reason: str | None = None
    created_at: datetime


class ResearcherDetailRead(ResearcherRead):
    talk_events: list[TalkEventRead] = Field(default_factory=list)
    trip_clusters: list[TripClusterRead] = Field(default_factory=list)


class IngestResponse(BaseModel):
    source_counts: dict[str, int]
    created_count: int
    updated_count: int
