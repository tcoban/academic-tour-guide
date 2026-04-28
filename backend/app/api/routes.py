from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import session_dep
from app.models.entities import (
    FactCandidate,
    HostCalendarEvent,
    OpenSeminarWindow,
    OutreachDraft,
    Researcher,
    SeminarSlotOverride,
    SeminarSlotTemplate,
    SourceHealthCheck,
    SourceDocument,
    TalkEvent,
    TripCluster,
)
from app.schemas.api import (
    CalendarOverlayResponse,
    DailyCatchResponse,
    DraftCreate,
    DraftListRead,
    DraftRead,
    DraftStatusUpdate,
    EnrichRequest,
    FactCandidateRead,
    IngestResponse,
    JobRunResponse,
    OperatorRunbookResponse,
    OpportunityWorkbenchResponse,
    ResearcherDetailRead,
    ResearcherJobRequest,
    ResearcherRead,
    ReviewDecisionRequest,
    ReviewFactRead,
    RunbookStepRead,
    SeminarSlotOverrideCreate,
    SeminarSlotOverrideRead,
    SeminarSlotTemplateCreate,
    SeminarSlotTemplateRead,
    SourceHealthHistoryRead,
    SourceHealthRead,
    SourceReliabilityRead,
    SourceDocumentRead,
    TripClusterRead,
)
from app.services.audit import SourceAuditor, SourceReliabilityService
from app.services.availability import AvailabilityBuilder
from app.services.enrichment import Biographer, BiographerPipeline
from app.services.ingestion import IngestionService
from app.services.outreach import DraftGenerator, ReviewRequiredError
from app.services.opportunities import OpportunityWorkbench
from app.services.review import FactReviewService
from app.services.scoring import Scorer
from app.services.seed import seed_demo_data

router = APIRouter()
ALLOWED_DRAFT_STATUSES = {"draft", "reviewed", "sent_manually", "archived"}


def _count(session: Session, statement) -> int:
    return int(session.scalar(statement) or 0)


def _draft_counts_by_status(session: Session) -> dict[str, int]:
    rows = session.execute(select(OutreachDraft.status, func.count()).group_by(OutreachDraft.status)).all()
    counts = {status_name: 0 for status_name in sorted(ALLOWED_DRAFT_STATUSES)}
    for status_name, count in rows:
        counts[status_name] = int(count)
    return counts


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/dashboard/daily-catch", response_model=DailyCatchResponse)
def daily_catch(session: Session = Depends(session_dep)) -> DailyCatchResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    recent = session.scalars(
        select(TalkEvent).where(TalkEvent.created_at >= cutoff).order_by(TalkEvent.starts_at.desc()).limit(20)
    ).all()
    clusters = session.scalars(select(TripCluster).order_by(TripCluster.opportunity_score.desc()).limit(10)).all()
    return DailyCatchResponse(recent_events=recent, top_clusters=clusters)


@router.get("/operator/runbook", response_model=OperatorRunbookResponse)
def operator_runbook(session: Session = Depends(session_dep)) -> OperatorRunbookResponse:
    reliability = SourceReliabilityService().summarize(session)
    source_attention_count = sum(1 for source in reliability if source.needs_attention)
    pending_fact_count = _count(session, select(func.count()).select_from(FactCandidate).where(FactCandidate.status == "pending"))
    open_window_count = _count(session, select(func.count()).select_from(OpenSeminarWindow))
    host_event_count = _count(session, select(func.count()).select_from(HostCalendarEvent))
    draft_counts_by_status = _draft_counts_by_status(session)
    workbench = OpportunityWorkbench(session).build(limit=100)
    draft_ready_opportunity_count = sum(1 for opportunity in workbench["opportunities"] if opportunity["draft_ready"])

    source_status = "needs_attention" if source_attention_count or not reliability else "ready"
    source_detail = (
        f"{source_attention_count} source reliability signal needs attention."
        if source_attention_count
        else "No recorded source audit history yet."
        if not reliability
        else "Source reliability looks stable from recorded audits."
    )
    pending_draft_count = draft_counts_by_status.get("draft", 0)
    reviewed_draft_count = draft_counts_by_status.get("reviewed", 0)
    draft_followup_count = pending_draft_count + reviewed_draft_count

    return OperatorRunbookResponse(
        source_attention_count=source_attention_count,
        pending_fact_count=pending_fact_count,
        draft_ready_opportunity_count=draft_ready_opportunity_count,
        open_window_count=open_window_count,
        host_event_count=host_event_count,
        draft_counts_by_status=draft_counts_by_status,
        recommended_steps=[
            RunbookStepRead(
                key="source-audit",
                title="Refresh source signal",
                status=source_status,
                detail=source_detail,
                href="/source-health",
                cta_label="Open Source Health",
                count=source_attention_count,
            ),
            RunbookStepRead(
                key="fact-review",
                title="Clear evidence review",
                status="needs_attention" if pending_fact_count else "ready",
                detail=(
                    f"{pending_fact_count} extracted fact candidate needs admin review."
                    if pending_fact_count == 1
                    else f"{pending_fact_count} extracted fact candidates need admin review."
                    if pending_fact_count
                    else "No pending biographic facts are blocking the queue."
                ),
                href="/review",
                cta_label="Review Facts",
                count=pending_fact_count,
            ),
            RunbookStepRead(
                key="opportunities",
                title="Pick draft-ready opportunities",
                status="ready" if draft_ready_opportunity_count else "blocked",
                detail=(
                    f"{draft_ready_opportunity_count} opportunity dossier is ready for draft generation."
                    if draft_ready_opportunity_count == 1
                    else f"{draft_ready_opportunity_count} opportunity dossiers are ready for draft generation."
                    if draft_ready_opportunity_count
                    else "No opportunity has all required approved facts and slot context yet."
                ),
                href="/opportunities",
                cta_label="Open Workbench",
                count=draft_ready_opportunity_count,
            ),
            RunbookStepRead(
                key="draft-library",
                title="Move drafts through the desk",
                status="needs_attention" if draft_followup_count else "ready",
                detail=(
                    f"{pending_draft_count} draft and {reviewed_draft_count} reviewed draft need lifecycle follow-up."
                    if draft_followup_count
                    else "No generated drafts are waiting for review or manual send status."
                ),
                href="/drafts",
                cta_label="Open Drafts",
                count=draft_followup_count,
            ),
        ],
    )


@router.post("/jobs/ingest", response_model=IngestResponse)
def ingest(session: Session = Depends(session_dep)) -> IngestResponse:
    summary = IngestionService(session).ingest_sources()
    session.commit()
    return IngestResponse(**asdict(summary))


@router.post("/jobs/sync-kof-calendar", response_model=IngestResponse)
def sync_kof_calendar(session: Session = Depends(session_dep)) -> IngestResponse:
    summary = IngestionService(session).sync_host_calendar()
    session.commit()
    return IngestResponse(**asdict(summary))


@router.post("/jobs/audit-sources", response_model=list[SourceHealthHistoryRead])
def audit_sources(session: Session = Depends(session_dep)) -> list[SourceHealthCheck]:
    records = SourceAuditor().record(session)
    session.commit()
    return records


@router.post("/jobs/repec-sync", response_model=JobRunResponse)
def sync_repec(
    payload: ResearcherJobRequest | None = None,
    session: Session = Depends(session_dep),
) -> JobRunResponse:
    summary = BiographerPipeline(session).sync_repec(payload.researcher_id if payload else None)
    Scorer(session).score_all_clusters()
    session.commit()
    return JobRunResponse(**asdict(summary))


@router.post("/jobs/biographer-refresh", response_model=JobRunResponse)
def biographer_refresh(
    payload: ResearcherJobRequest | None = None,
    session: Session = Depends(session_dep),
) -> JobRunResponse:
    summary = BiographerPipeline(session).refresh(payload.researcher_id if payload else None)
    Scorer(session).score_all_clusters()
    session.commit()
    return JobRunResponse(**asdict(summary))


@router.post("/jobs/seed-demo", response_model=JobRunResponse)
def seed_demo(session: Session = Depends(session_dep)) -> JobRunResponse:
    summary = seed_demo_data(session)
    session.commit()
    return JobRunResponse(**asdict(summary))


@router.get("/researchers", response_model=list[ResearcherRead])
def list_researchers(session: Session = Depends(session_dep)) -> list[Researcher]:
    return session.scalars(select(Researcher).options(selectinload(Researcher.facts)).order_by(Researcher.name)).all()


@router.get("/researchers/{researcher_id}", response_model=ResearcherDetailRead)
def get_researcher(researcher_id: str, session: Session = Depends(session_dep)) -> Researcher:
    researcher = session.scalar(
        select(Researcher)
        .where(Researcher.id == researcher_id)
        .options(
            selectinload(Researcher.facts),
            selectinload(Researcher.fact_candidates),
            selectinload(Researcher.identities),
            selectinload(Researcher.documents),
            selectinload(Researcher.talk_events),
            selectinload(Researcher.trip_clusters),
        )
    )
    if not researcher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    return researcher


@router.get("/researchers/{researcher_id}/documents", response_model=list[SourceDocumentRead])
def get_researcher_documents(researcher_id: str, session: Session = Depends(session_dep)) -> list[SourceDocument]:
    researcher = session.get(Researcher, researcher_id)
    if not researcher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    return session.scalars(
        select(SourceDocument).where(SourceDocument.researcher_id == researcher_id).order_by(SourceDocument.created_at.desc())
    ).all()


@router.post("/researchers/{researcher_id}/enrich", response_model=ResearcherRead)
def enrich_researcher(researcher_id: str, payload: EnrichRequest, session: Session = Depends(session_dep)) -> Researcher:
    researcher = session.get(Researcher, researcher_id)
    if not researcher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    enriched = Biographer(session).enrich(researcher, payload)
    Scorer(session).score_all_clusters()
    session.commit()
    session.refresh(enriched)
    return enriched


@router.get("/trip-clusters", response_model=list[TripClusterRead])
def list_trip_clusters(session: Session = Depends(session_dep)) -> list[TripCluster]:
    return session.scalars(select(TripCluster).order_by(TripCluster.opportunity_score.desc())).all()


@router.get("/calendar/overlay", response_model=CalendarOverlayResponse)
def calendar_overlay(
    rebuild: bool = Query(default=True),
    session: Session = Depends(session_dep),
) -> CalendarOverlayResponse:
    if rebuild:
        AvailabilityBuilder(session).rebuild_persisted()
        Scorer(session).score_all_clusters()
        session.commit()
    host_events = session.scalars(select(HostCalendarEvent).order_by(HostCalendarEvent.starts_at)).all()
    open_windows = session.scalars(select(OpenSeminarWindow).order_by(OpenSeminarWindow.starts_at)).all()
    return CalendarOverlayResponse(host_events=host_events, open_windows=open_windows)


@router.get("/opportunities/workbench", response_model=OpportunityWorkbenchResponse)
def opportunity_workbench(
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(session_dep),
) -> dict:
    return OpportunityWorkbench(session).build(limit=limit)


@router.get("/source-health", response_model=list[SourceHealthRead])
def source_health() -> list[dict]:
    return [asdict(result) for result in SourceAuditor().audit()]


@router.get("/source-health/history", response_model=list[SourceHealthHistoryRead])
def source_health_history(
    source_name: str | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=500),
    session: Session = Depends(session_dep),
) -> list[SourceHealthCheck]:
    query = select(SourceHealthCheck).order_by(SourceHealthCheck.checked_at.desc()).limit(limit)
    if source_name:
        query = (
            select(SourceHealthCheck)
            .where(SourceHealthCheck.source_name == source_name)
            .order_by(SourceHealthCheck.checked_at.desc())
            .limit(limit)
        )
    return session.scalars(query).all()


@router.get("/source-health/reliability", response_model=list[SourceReliabilityRead])
def source_health_reliability(
    per_source_limit: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(session_dep),
) -> list[dict]:
    return [asdict(result) for result in SourceReliabilityService().summarize(session, per_source_limit=per_source_limit)]


@router.get("/review/facts", response_model=list[ReviewFactRead])
def list_review_facts(
    status_filter: str = Query(default="pending", alias="status"),
    session: Session = Depends(session_dep),
) -> list[ReviewFactRead]:
    candidates = session.scalars(
        select(FactCandidate)
        .options(selectinload(FactCandidate.researcher))
        .where(FactCandidate.status == status_filter)
        .order_by(FactCandidate.confidence.desc(), FactCandidate.created_at.desc())
    ).all()
    return [
        ReviewFactRead.model_validate(
            {
                **FactCandidateRead.model_validate(candidate).model_dump(),
                "researcher_name": candidate.researcher.name,
            }
        )
        for candidate in candidates
    ]


@router.post("/review/facts/{candidate_id}/approve", response_model=FactCandidateRead)
def approve_fact_candidate(
    candidate_id: str,
    payload: ReviewDecisionRequest,
    session: Session = Depends(session_dep),
) -> FactCandidate:
    candidate = session.get(FactCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact candidate not found")
    FactReviewService(session).approve(candidate, merged_value=payload.merged_value, note=payload.note)
    Scorer(session).score_all_clusters()
    session.commit()
    session.refresh(candidate)
    return candidate


@router.post("/review/facts/{candidate_id}/reject", response_model=FactCandidateRead)
def reject_fact_candidate(
    candidate_id: str,
    payload: ReviewDecisionRequest,
    session: Session = Depends(session_dep),
) -> FactCandidate:
    candidate = session.get(FactCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact candidate not found")
    FactReviewService(session).reject(candidate, note=payload.note)
    Scorer(session).score_all_clusters()
    session.commit()
    session.refresh(candidate)
    return candidate


@router.get("/seminar/templates", response_model=list[SeminarSlotTemplateRead])
def list_slot_templates(session: Session = Depends(session_dep)) -> list[SeminarSlotTemplate]:
    return session.scalars(select(SeminarSlotTemplate).order_by(SeminarSlotTemplate.weekday, SeminarSlotTemplate.start_time)).all()


@router.post("/seminar/templates", response_model=SeminarSlotTemplateRead)
def create_slot_template(payload: SeminarSlotTemplateCreate, session: Session = Depends(session_dep)) -> SeminarSlotTemplate:
    template = SeminarSlotTemplate(**payload.model_dump())
    session.add(template)
    session.flush()
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()
    return template


@router.patch("/seminar/templates/{template_id}", response_model=SeminarSlotTemplateRead)
def update_slot_template(
    template_id: str,
    payload: SeminarSlotTemplateCreate,
    session: Session = Depends(session_dep),
) -> SeminarSlotTemplate:
    template = session.get(SeminarSlotTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    for field, value in payload.model_dump().items():
        setattr(template, field, value)
    session.add(template)
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()
    return template


@router.get("/seminar/overrides", response_model=list[SeminarSlotOverrideRead])
def list_slot_overrides(session: Session = Depends(session_dep)) -> list[SeminarSlotOverride]:
    return session.scalars(select(SeminarSlotOverride).order_by(SeminarSlotOverride.start_at)).all()


@router.post("/seminar/overrides", response_model=SeminarSlotOverrideRead)
def create_slot_override(payload: SeminarSlotOverrideCreate, session: Session = Depends(session_dep)) -> SeminarSlotOverride:
    override = SeminarSlotOverride(**payload.model_dump())
    session.add(override)
    session.flush()
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()
    return override


@router.patch("/seminar/overrides/{override_id}", response_model=SeminarSlotOverrideRead)
def update_slot_override(
    override_id: str,
    payload: SeminarSlotOverrideCreate,
    session: Session = Depends(session_dep),
) -> SeminarSlotOverride:
    override = session.get(SeminarSlotOverride, override_id)
    if not override:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    for field, value in payload.model_dump().items():
        setattr(override, field, value)
    session.add(override)
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()
    return override


@router.post("/outreach-drafts", response_model=DraftRead)
def create_draft(payload: DraftCreate, session: Session = Depends(session_dep)) -> OutreachDraft:
    researcher = session.get(Researcher, payload.researcher_id)
    cluster = session.get(TripCluster, payload.trip_cluster_id)
    if not researcher or not cluster:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher or cluster not found")
    try:
        draft = DraftGenerator(session).generate(researcher, cluster, template_key=payload.template_key)
    except ReviewRequiredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    session.commit()
    return draft


@router.get("/outreach-drafts", response_model=list[DraftListRead])
def list_drafts(
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    session: Session = Depends(session_dep),
) -> list[DraftListRead]:
    query = (
        select(OutreachDraft)
        .options(selectinload(OutreachDraft.researcher), selectinload(OutreachDraft.trip_cluster))
        .order_by(OutreachDraft.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        if status_filter not in ALLOWED_DRAFT_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported draft status filter")
        query = (
            select(OutreachDraft)
            .where(OutreachDraft.status == status_filter)
            .options(selectinload(OutreachDraft.researcher), selectinload(OutreachDraft.trip_cluster))
            .order_by(OutreachDraft.created_at.desc())
            .limit(limit)
        )
    drafts = session.scalars(query).all()
    return [
        DraftListRead.model_validate(
            {
                **DraftRead.model_validate(draft).model_dump(),
                "researcher_name": draft.researcher.name,
                "researcher_home_institution": draft.researcher.home_institution,
                "cluster_start_date": draft.trip_cluster.start_date,
                "cluster_end_date": draft.trip_cluster.end_date,
                "cluster_score": draft.trip_cluster.opportunity_score,
                "template_label": (draft.metadata_json or {}).get("template_label"),
            }
        )
        for draft in drafts
    ]


@router.patch("/outreach-drafts/{draft_id}/status", response_model=DraftRead)
def update_draft_status(
    draft_id: str,
    payload: DraftStatusUpdate,
    session: Session = Depends(session_dep),
) -> OutreachDraft:
    if payload.status not in ALLOWED_DRAFT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported draft status")
    draft = session.get(OutreachDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    metadata = dict(draft.metadata_json or {})
    history = list(metadata.get("status_history") or [])
    history.append(
        {
            "from": draft.status,
            "to": payload.status,
            "note": payload.note,
            "changed_at": datetime.now(UTC).isoformat(),
        }
    )
    metadata["status_history"] = history
    draft.status = payload.status
    draft.metadata_json = metadata
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


@router.get("/outreach-drafts/{draft_id}", response_model=DraftRead)
def get_draft(draft_id: str, session: Session = Depends(session_dep)) -> OutreachDraft:
    draft = session.get(OutreachDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft
