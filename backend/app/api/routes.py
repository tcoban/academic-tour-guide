from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import session_dep
from app.models.entities import (
    HostCalendarEvent,
    OpenSeminarWindow,
    OutreachDraft,
    Researcher,
    SeminarSlotOverride,
    SeminarSlotTemplate,
    TalkEvent,
    TripCluster,
)
from app.schemas.api import (
    CalendarOverlayResponse,
    DailyCatchResponse,
    DraftCreate,
    DraftRead,
    EnrichRequest,
    IngestResponse,
    ResearcherDetailRead,
    ResearcherRead,
    SeminarSlotOverrideCreate,
    SeminarSlotOverrideRead,
    SeminarSlotTemplateCreate,
    SeminarSlotTemplateRead,
    TripClusterRead,
)
from app.services.availability import AvailabilityBuilder
from app.services.enrichment import Biographer
from app.services.ingestion import IngestionService
from app.services.outreach import DraftGenerator
from app.services.scoring import Scorer

router = APIRouter()


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


@router.post("/jobs/ingest", response_model=IngestResponse)
def ingest(session: Session = Depends(session_dep)) -> IngestResponse:
    summary = IngestionService(session).ingest_sources()
    session.commit()
    return IngestResponse(**summary.__dict__)


@router.post("/jobs/sync-kof-calendar", response_model=IngestResponse)
def sync_kof_calendar(session: Session = Depends(session_dep)) -> IngestResponse:
    summary = IngestionService(session).sync_host_calendar()
    session.commit()
    return IngestResponse(**summary.__dict__)


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
            selectinload(Researcher.talk_events),
            selectinload(Researcher.trip_clusters),
        )
    )
    if not researcher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    return researcher


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
    draft = DraftGenerator(session).generate(researcher, cluster)
    session.commit()
    return draft


@router.get("/outreach-drafts/{draft_id}", response_model=DraftRead)
def get_draft(draft_id: str, session: Session = Depends(session_dep)) -> OutreachDraft:
    draft = session.get(OutreachDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft
