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


class MatchedOpenWindowRead(OpenSeminarWindowRead):
    fit_type: str
    distance_days: int
    within_scoring_window: bool
    travel_fit_score: int = 0
    travel_fit_label: str | None = None
    travel_fit_summary: str | None = None
    travel_fit_severity: str = "review"
    planning_warnings: list[str] = Field(default_factory=list)
    travel_fit: dict[str, Any] = Field(default_factory=dict)


class CostShareEstimateRead(BaseModel):
    baseline_round_trip_chf: int
    multi_city_incremental_chf: int
    estimated_savings_chf: int
    roi_percent: int
    nearest_itinerary_city: str
    nearest_distance_km: int
    recommended_mode: str
    recommendation: str
    assumption_notes: list[str]
    slot_starts_at: str | None = None


class OpportunityDraftBlockerRead(BaseModel):
    code: str
    fact_type: str | None = None
    label: str
    message: str
    action_label: str
    action_href: str
    pending_candidate_id: str | None = None


class OpportunityAutonomyActionRead(BaseModel):
    label: str
    consequence: str
    href: str | None = None
    action_key: str | None = None
    disabled_reason: str | None = None


class OpportunityAutonomySignalRead(BaseModel):
    label: str
    status: str
    confidence: int
    detail: str
    evidence: list[str] = Field(default_factory=list)


class OpportunityAutonomyAssessmentRead(BaseModel):
    level: str
    score: int
    summary: str
    can_prepare_draft: bool
    can_build_tour_leg: bool
    can_search_evidence: bool
    can_refresh_prices: bool = False
    requires_human_approval: bool
    signals: list[OpportunityAutonomySignalRead] = Field(default_factory=list)
    next_action: OpportunityAutonomyActionRead
    moonshot_actions: list[OpportunityAutonomyActionRead] = Field(default_factory=list)


class OpportunityCardRead(BaseModel):
    cluster: TripClusterRead
    researcher: ResearcherRead
    best_window: MatchedOpenWindowRead | None = None
    cost_share: CostShareEstimateRead | None = None
    itinerary_cities: list[str]
    draft_ready: bool
    draft_blockers: list[str]
    draft_blocker_details: list[OpportunityDraftBlockerRead] = Field(default_factory=list)
    draft_count: int = 0
    latest_draft_id: str | None = None
    latest_draft_template: str | None = None
    tour_leg_count: int = 0
    latest_tour_leg_id: str | None = None
    route_review_required: bool = False
    route_review_resolved: bool = False
    route_review_action: dict[str, Any] | None = None
    automation_assessment: OpportunityAutonomyAssessmentRead | None = None


class OpportunityWorkbenchResponse(BaseModel):
    opportunities: list[OpportunityCardRead]
    host_events: list[HostCalendarEventRead]
    open_windows: list[OpenSeminarWindowRead]


class SourceHealthRead(BaseModel):
    source_name: str
    source_type: str
    status: str
    page_count: int
    event_count: int
    samples: list[str]
    error: str | None = None
    official_url: str | None = None
    parser_strategy: str | None = None
    needs_adapter: bool = False
    action_label: str | None = None
    action_href: str | None = None
    consequence: str | None = None
    disabled_reason: str | None = None
    checked_at: datetime


class SourceHealthHistoryRead(SourceHealthRead):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class SourceReliabilityRead(BaseModel):
    source_name: str
    source_type: str
    latest_status: str
    latest_event_count: int
    last_event_count: int
    previous_event_count: int | None = None
    checks_recorded: int
    success_rate: float
    average_event_count: float
    trend: str
    needs_attention: bool
    attention_reason: str | None = None
    latest_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    latest_error: str | None = None
    official_url: str | None = None
    parser_strategy: str | None = None
    needs_adapter: bool = False
    action_label: str | None = None
    action_href: str | None = None
    consequence: str | None = None
    disabled_reason: str | None = None


class RunbookStepRead(BaseModel):
    key: str
    title: str
    status: str
    detail: str
    href: str
    cta_label: str
    count: int


class OperatorRunbookResponse(BaseModel):
    source_attention_count: int
    pending_fact_count: int
    draft_ready_opportunity_count: int
    open_window_count: int
    host_event_count: int
    draft_counts_by_status: dict[str, int]
    recommended_steps: list[RunbookStepRead]


class OperatorActionRead(BaseModel):
    label: str
    href: str | None = None
    method: str = "GET"
    action_key: str | None = None
    disabled_reason: str | None = None


class OperatorPrimaryFlowRead(OperatorActionRead):
    consequence: str


class OperatorSetupBlockerRead(BaseModel):
    id: str
    title: str
    explanation: str
    action: OperatorPrimaryFlowRead
    count: int = 0


class OperatorTaskRead(BaseModel):
    id: str
    group: str
    severity: str
    status: str
    title: str
    explanation: str
    primary_action: OperatorActionRead
    secondary_actions: list[OperatorActionRead] = Field(default_factory=list)
    entity_type: str | None = None
    entity_id: str | None = None
    count: int = 1
    disabled_reason: str | None = None
    last_updated_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OperatorTaskGroupRead(BaseModel):
    key: str
    title: str
    purpose: str
    tasks: list[OperatorTaskRead]


class OperatorCockpitResponse(BaseModel):
    generated_at: datetime
    posture: str
    posture_detail: str
    data_state: str
    setup_blockers: list[OperatorSetupBlockerRead] = Field(default_factory=list)
    primary_flow: OperatorPrimaryFlowRead
    summary_metrics: dict[str, int]
    next_best_action: OperatorTaskRead | None = None
    groups: list[OperatorTaskGroupRead]
    recent_changes: list[dict[str, Any]] = Field(default_factory=list)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)


class MorningSweepStepRead(BaseModel):
    key: str
    title: str
    status: str
    detail: str
    processed_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class MorningSweepResponse(BaseModel):
    started_at: datetime
    finished_at: datetime
    status: str
    steps: list[MorningSweepStepRead]
    summary_metrics: dict[str, int]


class InstitutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    city: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    metadata_json: dict[str, Any]


class SpeakerProfileUpdate(BaseModel):
    topics: list[str] = Field(default_factory=list)
    fee_floor_chf: int | None = Field(default=None, ge=0)
    notice_period_days: int | None = Field(default=None, ge=0)
    travel_preferences: dict[str, Any] = Field(default_factory=dict)
    rider: dict[str, Any] = Field(default_factory=dict)
    availability_notes: str | None = None
    communication_preferences: dict[str, Any] = Field(default_factory=dict)
    consent_status: str = "pre_consent"
    verification_status: str = "shadow"


class SpeakerProfileRead(SpeakerProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    created_at: datetime
    updated_at: datetime


class InstitutionProfileUpdate(BaseModel):
    wishlist_topics: list[str] = Field(default_factory=list)
    procurement_notes: str | None = None
    po_threshold_chf: int | None = Field(default=None, ge=0)
    grant_code_support: bool = False
    coordinator_contacts: list[dict[str, Any]] = Field(default_factory=list)
    av_notes: str | None = None
    hospitality_notes: str | None = None
    host_quality_score: float | None = Field(default=None, ge=0, le=100)


class InstitutionProfileRead(InstitutionProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    institution_id: str
    created_at: datetime
    updated_at: datetime


class WishlistEntryCreate(BaseModel):
    institution_id: str
    researcher_id: str | None = None
    speaker_name: str | None = None
    topic: str | None = None
    priority: int = Field(default=50, ge=0, le=100)
    status: str = "active"
    notes: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WishlistEntryRead(WishlistEntryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class WishlistAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    wishlist_entry_id: str
    researcher_id: str | None = None
    trip_cluster_id: str | None = None
    status: str
    match_reason: str
    score: int
    metadata_json: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None = None
    researcher_name: str | None = None
    institution_name: str | None = None


class WishlistAlertStatusUpdate(BaseModel):
    status: str
    note: str | None = None


class WishlistMatchParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    match_group_id: str
    masked_label: str
    distance_km: float | None = None
    distance_band: str
    role: str
    status: str
    budget_status: str
    slot_status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WishlistMatchGroupRead(BaseModel):
    id: str
    researcher_id: str | None = None
    normalized_speaker_name: str
    display_speaker_name: str
    status: str
    radius_km: int
    score: int
    anonymity_mode: str
    rationale: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    participant_count: int
    participants: list[WishlistMatchParticipantRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WishlistMatchStatusUpdate(BaseModel):
    status: str
    note: str | None = None


class TourLegProposalRequest(BaseModel):
    trip_cluster_id: str
    fee_per_stop_chf: int | None = Field(default=None, ge=0)


class TravelPriceCheckCreate(BaseModel):
    origin_city: str = Field(min_length=1, max_length=120)
    destination_city: str = Field(min_length=1, max_length=120)
    departure_at: datetime | None = None
    tour_leg_id: str | None = None
    force_refresh: bool = False
    travel_class: str = "first"
    fare_policy: str = "full_fare"


class TravelPriceCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tour_leg_id: str | None = None
    cache_key: str
    origin_city: str
    destination_city: str
    departure_at: datetime | None = None
    travel_class: str
    fare_policy: str
    provider: str
    status: str
    amount: float | None = None
    currency: str
    amount_chf: int
    confidence: float
    source_url: str | None = None
    action_href: str | None = None
    raw_summary: dict[str, Any]
    error: str | None = None
    fetched_at: datetime
    expires_at: datetime
    created_at: datetime


class TourStopRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tour_leg_id: str
    institution_id: str | None = None
    open_window_id: str | None = None
    sequence: int
    city: str
    country: str | None = None
    starts_at: datetime | None = None
    format: str
    fee_chf: int
    travel_share_chf: int
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime


class TourLegRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    trip_cluster_id: str | None = None
    title: str
    status: str
    start_date: date
    end_date: date
    estimated_fee_total_chf: int
    estimated_travel_total_chf: int
    cost_split_json: dict[str, Any]
    rationale: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    stops: list[TourStopRead] = Field(default_factory=list)


class TourAssemblyProposalRequest(BaseModel):
    match_group_id: str


class TourAssemblyProposalRead(BaseModel):
    id: str
    match_group_id: str
    researcher_id: str | None = None
    tour_leg_id: str | None = None
    speaker_draft_id: str | None = None
    title: str
    status: str
    term_sheet_json: dict[str, Any]
    budget_summary_json: dict[str, Any]
    blockers: list[dict[str, Any]]
    masked_summary_json: dict[str, Any]
    match_group: WishlistMatchGroupRead | None = None
    created_at: datetime
    updated_at: datetime


class RelationshipBriefUpdate(BaseModel):
    summary: str = ""
    communication_preferences: dict[str, Any] = Field(default_factory=dict)
    decision_patterns: dict[str, Any] = Field(default_factory=dict)
    relationship_history: list[dict[str, Any]] = Field(default_factory=list)
    operational_memory: dict[str, Any] = Field(default_factory=dict)
    forward_signals: dict[str, Any] = Field(default_factory=dict)


class RelationshipBriefRead(RelationshipBriefUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    institution_id: str
    created_at: datetime
    updated_at: datetime


class FeedbackSignalCreate(BaseModel):
    researcher_id: str
    institution_id: str
    tour_leg_id: str | None = None
    party: str
    signal_type: str
    value: str
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    notes: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FeedbackSignalRead(FeedbackSignalCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    actor_type: str
    actor_id: str | None = None
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    created_at: datetime


class BusinessCaseResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    researcher_id: str | None = None
    case_key: str
    display_name: str
    target_name: str
    verdict: str
    score: int
    data_found: bool
    kof_fit_status: str
    route_status: str
    evidence_status: str
    draft_status: str
    price_status: str
    evidence_summary_json: dict[str, Any]
    fit_summary_json: dict[str, Any]
    route_summary_json: dict[str, Any]
    price_summary_json: dict[str, Any]
    draft_gate_json: dict[str, Any]
    blockers: list[dict[str, Any]]
    source_links_json: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    created_at: datetime


class BusinessCaseRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    summary_json: dict[str, Any]
    error: str | None = None
    created_at: datetime
    results: list[BusinessCaseResultRead] = Field(default_factory=list)


class EnrichRequest(BaseModel):
    cv_text: str | None = None
    source_url: str | None = None
    evidence_snippet: str | None = None
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
    template_key: str = "kof_invitation"


class DraftStatusUpdate(BaseModel):
    status: str
    note: str | None = None
    checklist_confirmations: list[str] = Field(default_factory=list)
    send_confirmed: bool = False


class DraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    researcher_id: str
    trip_cluster_id: str
    subject: str
    body: str
    status: str
    blocked_reason: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DraftListRead(DraftRead):
    researcher_name: str
    researcher_home_institution: str | None = None
    cluster_start_date: date
    cluster_end_date: date
    cluster_score: int
    template_label: str | None = None


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
