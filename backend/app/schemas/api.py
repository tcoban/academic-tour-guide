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
    approval_origin: str


class FactCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    source_document_id: str | None = None
    fact_type: str
    value: str
    confidence: float
    evidence_snippet: str | None = None
    source_url: str | None = None
    status: str
    origin: str
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ReviewFactRead(FactCandidateRead):
    researcher_name: str


class ResearcherIdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    external_id: str
    canonical_name: str
    profile_url: str | None = None
    match_confidence: float
    ranking_percentile: float | None = None
    ranking_label: str | None = None
    metadata_json: dict[str, Any]
    synced_at: datetime


class SourceDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    url: str
    discovered_from_url: str | None = None
    content_type: str | None = None
    checksum: str | None = None
    fetch_status: str
    http_status: int | None = None
    title: str | None = None
    metadata_json: dict[str, Any]
    fetched_at: datetime | None = None
    created_at: datetime


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
    uses_unreviewed_evidence: bool
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


class ResearcherJobRequest(BaseModel):
    researcher_id: str | None = None


class ReviewDecisionRequest(BaseModel):
    merged_value: str | None = None
    note: str | None = None


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
    identities: list[ResearcherIdentityRead] = Field(default_factory=list)
    documents: list[SourceDocumentRead] = Field(default_factory=list)
    fact_candidates: list[FactCandidateRead] = Field(default_factory=list)


class IngestResponse(BaseModel):
    source_counts: dict[str, int]
    created_count: int
    updated_count: int


class JobRunResponse(BaseModel):
    processed_count: int
    created_count: int
    updated_count: int
