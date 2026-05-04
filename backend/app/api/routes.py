from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import session_dep
from app.core.config import settings
from app.models.entities import (
    AuditEvent,
    BusinessCaseRun,
    FactCandidate,
    FeedbackSignal,
    HostCalendarEvent,
    Institution,
    OpenSeminarWindow,
    OutreachDraft,
    RelationshipBrief,
    Researcher,
    SeminarSlotOverride,
    SeminarSlotTemplate,
    SourceHealthCheck,
    SourceDocument,
    TalkEvent,
    Tenant,
    TenantMembership,
    TenantSettings,
    TenantSourceSubscription,
    TourAssemblyProposal,
    TourLeg,
    TravelPriceCheck,
    TripCluster,
    User,
    WishlistAlert,
    WishlistEntry,
    WishlistMatchGroup,
    WishlistMatchParticipant,
)
from app.schemas.api import (
    AuditEventRead,
    AuthResponse,
    BusinessCaseRunRead,
    CalendarOverlayResponse,
    DailyCatchResponse,
    DraftCreate,
    DraftListRead,
    DraftRead,
    DraftStatusUpdate,
    EnrichRequest,
    FactCandidateRead,
    FeedbackSignalCreate,
    FeedbackSignalRead,
    IngestResponse,
    InstitutionRead,
    InstitutionProfileRead,
    InstitutionProfileUpdate,
    JobRunResponse,
    LoginRequest,
    MeRead,
    MorningSweepResponse,
    OperatorCockpitResponse,
    OperatorRunbookResponse,
    OpportunityWorkbenchResponse,
    RelationshipBriefRead,
    RelationshipBriefUpdate,
    RegisterRequest,
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
    SpeakerProfileRead,
    SpeakerProfileUpdate,
    TenantRead,
    TenantSettingsRead,
    TenantSettingsUpdate,
    TenantSourceSubscriptionCreate,
    TenantSourceSubscriptionRead,
    TenantSourceSubscriptionUpdate,
    TenantSwitchRequest,
    TenantUpdate,
    TourAssemblyProposalRead,
    TourAssemblyProposalRequest,
    TourLegProposalRequest,
    TourLegRead,
    TravelPriceCheckCreate,
    TravelPriceCheckRead,
    TripClusterRead,
    WishlistAlertRead,
    WishlistAlertStatusUpdate,
    WishlistEntryCreate,
    WishlistEntryRead,
    WishlistMatchGroupRead,
    WishlistMatchParticipantRead,
    WishlistMatchStatusUpdate,
)
from app.services.audit import SourceAuditor, SourceReliabilityService
from app.services.availability import AvailabilityBuilder
from app.services.business_cases import BusinessCaseService
from app.services.enrichment import Biographer, BiographerPipeline
from app.services.ingestion import IngestionService
from app.services.operator import MorningSweepRunner, OperatorCockpit
from app.services.outreach import DraftGenerator, ReviewRequiredError
from app.services.opportunities import OpportunityWorkbench
from app.services.plausibility import PlausibilityService
from app.services.review import FactReviewService
from app.services.roadshow import RoadshowService
from app.services.scoring import Scorer
from app.services.seed import seed_demo_data
from app.services.tenancy import (
    SESSION_COOKIE_NAME,
    authenticate_user,
    ensure_tenant_settings,
    get_session_tenant,
    register_user,
    resolve_auth_session,
    revoke_auth_session,
    switch_active_tenant,
    tenant_scope,
)
from app.services.tour_assembly import TourAssemblyService
from app.services.travel_prices import PriceQuoteRequest, TravelPriceChecker

router = APIRouter()
ALLOWED_DRAFT_STATUSES = {"draft", "reviewed", "sent_manually", "archived"}
ALLOWED_WISHLIST_ALERT_STATUSES = {"new", "reviewed", "dismissed", "converted"}
ALLOWED_WISHLIST_MATCH_STATUSES = {"new", "reviewed", "dismissed", "converted", "stale"}


def _count(session: Session, statement) -> int:
    return int(session.scalar(statement) or 0)


def _tenant_read(tenant: Tenant) -> TenantRead:
    return TenantRead.model_validate(tenant)


def _auth_response(response: Response, auth_session) -> AuthResponse:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=auth_session.token,
        httponly=True,
        samesite="lax",
        secure=False,
        expires=auth_session.expires_at,
    )
    return AuthResponse(
        user_id=auth_session.user.id,
        email=auth_session.user.email,
        name=auth_session.user.name,
        active_tenant=_tenant_read(auth_session.tenant),
        expires_at=auth_session.expires_at,
    )


def _draft_counts_by_status(session: Session) -> dict[str, int]:
    tenant = get_session_tenant(session)
    rows = session.execute(
        select(OutreachDraft.status, func.count())
        .where(OutreachDraft.tenant_id == tenant.id)
        .group_by(OutreachDraft.status)
    ).all()
    counts = {status_name: 0 for status_name in sorted(ALLOWED_DRAFT_STATUSES)}
    for status_name, count in rows:
        counts[status_name] = int(count)
    return counts


def _needs_review_checklist_labels(draft: OutreachDraft) -> list[str]:
    checklist = (draft.metadata_json or {}).get("checklist") or []
    return [str(item.get("label")) for item in checklist if item.get("status") == "needs_review" and item.get("label")]


def _validate_draft_status_transition(draft: OutreachDraft, payload: DraftStatusUpdate) -> None:
    if payload.status == "reviewed":
        required_labels = set(_needs_review_checklist_labels(draft))
        confirmed_labels = set(payload.checklist_confirmations)
        missing = sorted(required_labels - confirmed_labels)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Checklist confirmation required before review: {', '.join(missing)}",
            )
    if payload.status == "sent_manually":
        if draft.status != "reviewed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draft must be reviewed before it can be marked sent.",
            )
        if not payload.send_confirmed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Manual send confirmation is required before marking the draft sent.",
            )


def _wishlist_alert_read(alert: WishlistAlert) -> WishlistAlertRead:
    return WishlistAlertRead.model_validate(
        {
            **WishlistAlertRead.model_validate(alert).model_dump(),
            "researcher_name": alert.researcher.name if alert.researcher else None,
            "institution_name": alert.wishlist_entry.institution.name if alert.wishlist_entry and alert.wishlist_entry.institution else None,
        }
    )


def _wishlist_match_read(group: WishlistMatchGroup) -> WishlistMatchGroupRead:
    participants = [
        WishlistMatchParticipantRead.model_validate(participant).model_dump()
        for participant in sorted(group.participants, key=lambda item: item.masked_label)
    ]
    return WishlistMatchGroupRead.model_validate(
        {
            "id": group.id,
            "researcher_id": group.researcher_id,
            "normalized_speaker_name": group.normalized_speaker_name,
            "display_speaker_name": group.display_speaker_name,
            "status": group.status,
            "radius_km": group.radius_km,
            "score": group.score,
            "anonymity_mode": group.anonymity_mode,
            "rationale": group.rationale,
            "metadata_json": group.metadata_json,
            "participant_count": len(group.participants),
            "participants": participants,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        }
    )


def _tour_assembly_read(proposal: TourAssemblyProposal) -> TourAssemblyProposalRead:
    return TourAssemblyProposalRead.model_validate(
        {
            "id": proposal.id,
            "match_group_id": proposal.match_group_id,
            "researcher_id": proposal.researcher_id,
            "tour_leg_id": proposal.tour_leg_id,
            "speaker_draft_id": proposal.speaker_draft_id,
            "title": proposal.title,
            "status": proposal.status,
            "term_sheet_json": proposal.term_sheet_json,
            "budget_summary_json": proposal.budget_summary_json,
            "blockers": proposal.blockers,
            "masked_summary_json": proposal.masked_summary_json,
            "match_group": _wishlist_match_read(proposal.match_group) if proposal.match_group else None,
            "created_at": proposal.created_at,
            "updated_at": proposal.updated_at,
        }
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest, response: Response, session: Session = Depends(session_dep)) -> AuthResponse:
    try:
        auth_session = register_user(
            session,
            email=payload.email,
            name=payload.name,
            password=payload.password,
            institution_name=payload.institution_name,
            city=payload.city,
            country=payload.country,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    return _auth_response(response, auth_session)


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, session: Session = Depends(session_dep)) -> AuthResponse:
    try:
        auth_session = authenticate_user(session, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    session.commit()
    return _auth_response(response, auth_session)


@router.post("/auth/logout")
def logout(request: Request, response: Response, session: Session = Depends(session_dep)) -> dict[str, str]:
    token = request.headers.get("x-roadshow-session") or request.cookies.get(SESSION_COOKIE_NAME)
    revoked = revoke_auth_session(session, token)
    session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "logged_out", "session": "revoked" if revoked else "cleared"}


@router.get("/me", response_model=MeRead)
def me(session: Session = Depends(session_dep)) -> MeRead:
    tenant = get_session_tenant(session)
    user_id = session.info.get("user_id")
    if not user_id:
        return MeRead(authenticated=False, active_tenant=_tenant_read(tenant), memberships=[])
    user = session.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.memberships).selectinload(TenantMembership.tenant))
    )
    if not user:
        return MeRead(authenticated=False, active_tenant=_tenant_read(tenant), memberships=[])
    memberships = [
        {"tenant": _tenant_read(membership.tenant), "role": membership.role, "status": membership.status}
        for membership in user.memberships
        if membership.status == "active"
    ]
    return MeRead(
        authenticated=True,
        user_id=user.id,
        email=user.email,
        name=user.name,
        active_tenant=_tenant_read(tenant),
        memberships=memberships,
    )


@router.get("/tenants/current", response_model=TenantRead)
def get_current_tenant(session: Session = Depends(session_dep)) -> Tenant:
    return get_session_tenant(session)


@router.patch("/tenants/current", response_model=TenantRead)
def update_current_tenant(payload: TenantUpdate, session: Session = Depends(session_dep)) -> Tenant:
    tenant = get_session_tenant(session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    tenant.updated_at = datetime.now(UTC)
    session.add(tenant)
    session.commit()
    return tenant


@router.get("/tenants/current/settings", response_model=TenantSettingsRead)
def get_current_tenant_settings(session: Session = Depends(session_dep)) -> TenantSettings:
    return ensure_tenant_settings(session, get_session_tenant(session))


@router.patch("/tenants/current/settings", response_model=TenantSettingsRead)
def update_current_tenant_settings(payload: TenantSettingsUpdate, session: Session = Depends(session_dep)) -> TenantSettings:
    settings_row = ensure_tenant_settings(session, get_session_tenant(session))
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings_row, field, value)
    settings_row.updated_at = datetime.now(UTC)
    session.add(settings_row)
    session.commit()
    return settings_row


@router.post("/tenants/switch", response_model=MeRead)
def switch_tenant(payload: TenantSwitchRequest, request: Request, session: Session = Depends(session_dep)) -> MeRead:
    user_id = session.info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Roadshow login required.")
    membership = session.scalar(
        select(TenantMembership)
        .where(TenantMembership.user_id == user_id, TenantMembership.tenant_id == payload.tenant_id, TenantMembership.status == "active")
        .options(selectinload(TenantMembership.tenant))
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The active user is not a member of that tenant.")
    token = request.cookies.get(SESSION_COOKIE_NAME) or request.headers.get("x-roadshow-session")
    auth_session = resolve_auth_session(session, token)
    if auth_session:
        switch_active_tenant(session, auth_session, membership.tenant_id)
    session.info["tenant_id"] = membership.tenant_id
    session.commit()
    return me(session)


@router.get("/tenant/source-subscriptions", response_model=list[TenantSourceSubscriptionRead])
def list_source_subscriptions(session: Session = Depends(session_dep)) -> list[TenantSourceSubscription]:
    tenant = get_session_tenant(session)
    return session.scalars(
        select(TenantSourceSubscription)
        .where(TenantSourceSubscription.tenant_id == tenant.id)
        .order_by(TenantSourceSubscription.source_name)
    ).all()


@router.post("/tenant/source-subscriptions", response_model=TenantSourceSubscriptionRead)
def create_source_subscription(
    payload: TenantSourceSubscriptionCreate,
    session: Session = Depends(session_dep),
) -> TenantSourceSubscription:
    tenant = get_session_tenant(session)
    existing = session.scalar(
        select(TenantSourceSubscription).where(
            TenantSourceSubscription.tenant_id == tenant.id,
            TenantSourceSubscription.source_name == payload.source_name,
        )
    )
    if existing:
        existing.status = payload.status
        existing.notes = payload.notes
        existing.updated_at = datetime.now(UTC)
        session.commit()
        return existing
    subscription = TenantSourceSubscription(tenant_id=tenant.id, **payload.model_dump())
    session.add(subscription)
    session.commit()
    return subscription


@router.patch("/tenant/source-subscriptions/{subscription_id}", response_model=TenantSourceSubscriptionRead)
def update_source_subscription(
    subscription_id: str,
    payload: TenantSourceSubscriptionUpdate,
    session: Session = Depends(session_dep),
) -> TenantSourceSubscription:
    tenant = get_session_tenant(session)
    subscription = session.scalar(
        select(TenantSourceSubscription).where(
            TenantSourceSubscription.id == subscription_id,
            TenantSourceSubscription.tenant_id == tenant.id,
        )
    )
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source subscription not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(subscription, field, value)
    subscription.updated_at = datetime.now(UTC)
    session.commit()
    return subscription


@router.delete("/tenant/source-subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source_subscription(subscription_id: str, session: Session = Depends(session_dep)) -> None:
    tenant = get_session_tenant(session)
    subscription = session.scalar(
        select(TenantSourceSubscription).where(
            TenantSourceSubscription.id == subscription_id,
            TenantSourceSubscription.tenant_id == tenant.id,
        )
    )
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source subscription not found.")
    session.delete(subscription)
    session.commit()


@router.get("/tenant/opportunities", response_model=OpportunityWorkbenchResponse)
def tenant_opportunities(limit: int = Query(default=25, ge=1, le=100), session: Session = Depends(session_dep)) -> dict:
    return OpportunityWorkbench(session).build(limit=limit)


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
    tenant = get_session_tenant(session)
    reliability = SourceReliabilityService().summarize(session)
    source_attention_count = sum(1 for source in reliability if source.needs_attention)
    pending_fact_count = _count(session, select(func.count()).select_from(FactCandidate).where(FactCandidate.status == "pending"))
    open_window_count = _count(session, select(func.count()).select_from(OpenSeminarWindow).where(OpenSeminarWindow.tenant_id == tenant.id))
    host_event_count = _count(session, select(func.count()).select_from(HostCalendarEvent).where(HostCalendarEvent.tenant_id == tenant.id))
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
                cta_label="Inspect data sources",
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
                cta_label="Approve evidence for outreach",
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
                cta_label="Review draft-ready opportunities",
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
                cta_label="Review draft lifecycle",
                count=draft_followup_count,
            ),
        ],
    )


@router.get("/operator/cockpit", response_model=OperatorCockpitResponse)
def operator_cockpit(session: Session = Depends(session_dep)) -> dict:
    RoadshowService(session).refresh_wishlist_alerts()
    TourAssemblyService(session).refresh_wishlist_matches()
    session.commit()
    return OperatorCockpit(session).build()


@router.post("/operator/morning-sweep", response_model=MorningSweepResponse)
def operator_morning_sweep(session: Session = Depends(session_dep)) -> dict:
    result = MorningSweepRunner(session).run()
    session.commit()
    return result


@router.post("/operator/real-sync", response_model=MorningSweepResponse)
def operator_real_sync(session: Session = Depends(session_dep)) -> dict:
    result = MorningSweepRunner(session).run()
    session.commit()
    return result


@router.post("/business-cases/run", response_model=BusinessCaseRunRead)
def run_business_case_shadow_audit(session: Session = Depends(session_dep)) -> BusinessCaseRun:
    run = BusinessCaseService(session).run_shadow_audit()
    session.commit()
    run = session.scalar(
        select(BusinessCaseRun)
        .where(BusinessCaseRun.id == run.id)
        .options(selectinload(BusinessCaseRun.results))
    )
    return run


@router.get("/business-cases/runs", response_model=list[BusinessCaseRunRead])
def list_business_case_runs(
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(session_dep),
) -> list[BusinessCaseRun]:
    tenant = get_session_tenant(session)
    return session.scalars(
        select(BusinessCaseRun)
        .where(BusinessCaseRun.tenant_id == tenant.id)
        .options(selectinload(BusinessCaseRun.results))
        .order_by(desc(BusinessCaseRun.started_at))
        .limit(limit)
    ).all()


@router.get("/business-cases/runs/{run_id}", response_model=BusinessCaseRunRead)
def get_business_case_run(run_id: str, session: Session = Depends(session_dep)) -> BusinessCaseRun:
    tenant = get_session_tenant(session)
    run = session.scalar(
        select(BusinessCaseRun)
        .where(BusinessCaseRun.id == run_id, BusinessCaseRun.tenant_id == tenant.id)
        .options(selectinload(BusinessCaseRun.results))
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business-case run not found")
    return run


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


@router.post("/jobs/repec-top-authors", response_model=JobRunResponse)
def sync_repec_top_authors(limit: int = 200, session: Session = Depends(session_dep)) -> JobRunResponse:
    summary = BiographerPipeline(session).sync_top_authors(limit=max(1, min(limit, 500)))
    Scorer(session).score_all_clusters()
    session.commit()
    return JobRunResponse(**asdict(summary))


@router.post("/jobs/biographer-refresh", response_model=JobRunResponse)
def biographer_refresh(
    payload: ResearcherJobRequest | None = None,
    session: Session = Depends(session_dep),
) -> JobRunResponse:
    summary = BiographerPipeline(session).search_trusted_evidence(payload.researcher_id if payload else None)
    PlausibilityService(session).run()
    Scorer(session).score_all_clusters()
    session.commit()
    return JobRunResponse(**asdict(summary))


@router.post("/jobs/evidence-search", response_model=JobRunResponse)
def evidence_search(
    payload: ResearcherJobRequest | None = None,
    session: Session = Depends(session_dep),
) -> JobRunResponse:
    researcher_id = payload.researcher_id if payload else None
    summary = BiographerPipeline(session).search_trusted_evidence(researcher_id)
    PlausibilityService(session).run()
    Scorer(session).score_all_clusters()
    RoadshowService(session).record_event(
        event_type="jobs.evidence_search",
        entity_type="researcher" if researcher_id else "evidence",
        entity_id=researcher_id or "all",
        payload=asdict(summary),
    )
    session.commit()
    return JobRunResponse(**asdict(summary))


@router.post("/jobs/plausibility-check", response_model=JobRunResponse)
def plausibility_check(session: Session = Depends(session_dep)) -> JobRunResponse:
    summary = PlausibilityService(session).run()
    Scorer(session).score_all_clusters()
    RoadshowService(session).record_event(
        event_type="jobs.plausibility_check",
        entity_type="evidence",
        entity_id="plausibility",
        payload=asdict(summary),
    )
    session.commit()
    return JobRunResponse(
        processed_count=summary.processed_count,
        created_count=summary.created_count,
        updated_count=summary.updated_count,
    )


@router.post("/jobs/seed-demo", response_model=JobRunResponse)
def seed_demo(session: Session = Depends(session_dep)) -> JobRunResponse:
    if not settings.demo_tools_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo tooling is not enabled.")
    summary = seed_demo_data(session)
    RoadshowService(session).record_event(
        event_type="jobs.seed_demo",
        entity_type="demo",
        entity_id="local_seed",
        payload=asdict(summary),
    )
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


@router.post("/researchers/{researcher_id}/evidence-search", response_model=JobRunResponse)
def researcher_evidence_search(researcher_id: str, session: Session = Depends(session_dep)) -> JobRunResponse:
    if not session.get(Researcher, researcher_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    summary = BiographerPipeline(session).search_trusted_evidence(researcher_id)
    PlausibilityService(session).run()
    Scorer(session).score_all_clusters()
    RoadshowService(session).record_event(
        event_type="researcher.evidence_search",
        entity_type="researcher",
        entity_id=researcher_id,
        payload=asdict(summary),
    )
    session.commit()
    return JobRunResponse(**asdict(summary))


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


@router.get("/institutions", response_model=list[InstitutionRead])
def list_institutions(session: Session = Depends(session_dep)) -> list[Institution]:
    RoadshowService(session).ensure_kof_institution()
    session.commit()
    return session.scalars(select(Institution).order_by(Institution.name)).all()


@router.get("/speakers/{researcher_id}/profile", response_model=SpeakerProfileRead)
def get_speaker_profile(researcher_id: str, session: Session = Depends(session_dep)):
    researcher = session.scalar(
        select(Researcher).where(Researcher.id == researcher_id).options(selectinload(Researcher.speaker_profile))
    )
    if not researcher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    profile = RoadshowService(session).ensure_speaker_profile(researcher)
    session.commit()
    return profile


@router.patch("/speakers/{researcher_id}/profile", response_model=SpeakerProfileRead)
def update_speaker_profile(
    researcher_id: str,
    payload: SpeakerProfileUpdate,
    session: Session = Depends(session_dep),
):
    researcher = session.scalar(
        select(Researcher).where(Researcher.id == researcher_id).options(selectinload(Researcher.speaker_profile))
    )
    if not researcher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    profile = RoadshowService(session).update_speaker_profile(researcher, payload.model_dump())
    session.commit()
    session.refresh(profile)
    return profile


@router.get("/institutions/{institution_id}/profile", response_model=InstitutionProfileRead)
def get_institution_profile(institution_id: str, session: Session = Depends(session_dep)):
    institution = session.scalar(
        select(Institution).where(Institution.id == institution_id).options(selectinload(Institution.roadshow_profile))
    )
    if not institution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    profile = RoadshowService(session).ensure_institution_profile(institution)
    session.commit()
    return profile


@router.patch("/institutions/{institution_id}/profile", response_model=InstitutionProfileRead)
def update_institution_profile(
    institution_id: str,
    payload: InstitutionProfileUpdate,
    session: Session = Depends(session_dep),
):
    institution = session.scalar(
        select(Institution).where(Institution.id == institution_id).options(selectinload(Institution.roadshow_profile))
    )
    if not institution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    profile = RoadshowService(session).update_institution_profile(institution, payload.model_dump())
    session.commit()
    session.refresh(profile)
    return profile


@router.get("/wishlist", response_model=list[WishlistEntryRead])
def list_wishlist(session: Session = Depends(session_dep)) -> list[WishlistEntry]:
    tenant = get_session_tenant(session)
    RoadshowService(session).ensure_kof_institution()
    session.commit()
    return session.scalars(
        select(WishlistEntry)
        .where(WishlistEntry.tenant_id == tenant.id)
        .order_by(WishlistEntry.priority.desc(), WishlistEntry.created_at.desc())
    ).all()


@router.post("/wishlist", response_model=WishlistEntryRead)
def create_wishlist_entry(payload: WishlistEntryCreate, session: Session = Depends(session_dep)) -> WishlistEntry:
    if not session.get(Institution, payload.institution_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    if payload.researcher_id and not session.get(Researcher, payload.researcher_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    entry = RoadshowService(session).create_wishlist_entry(payload.model_dump())
    TourAssemblyService(session).refresh_wishlist_matches()
    session.commit()
    session.refresh(entry)
    return entry


@router.patch("/wishlist/{entry_id}", response_model=WishlistEntryRead)
def update_wishlist_entry(
    entry_id: str,
    payload: WishlistEntryCreate,
    session: Session = Depends(session_dep),
) -> WishlistEntry:
    tenant = get_session_tenant(session)
    entry = session.scalar(select(WishlistEntry).where(WishlistEntry.id == entry_id, WishlistEntry.tenant_id == tenant.id))
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist entry not found")
    if not session.get(Institution, payload.institution_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    if payload.researcher_id and not session.get(Researcher, payload.researcher_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    RoadshowService(session).update_wishlist_entry(entry, payload.model_dump())
    TourAssemblyService(session).refresh_wishlist_matches()
    session.commit()
    session.refresh(entry)
    return entry


@router.delete("/wishlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wishlist_entry(entry_id: str, session: Session = Depends(session_dep)) -> None:
    tenant = get_session_tenant(session)
    entry = session.scalar(select(WishlistEntry).where(WishlistEntry.id == entry_id, WishlistEntry.tenant_id == tenant.id))
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist entry not found")
    RoadshowService(session).delete_wishlist_entry(entry)
    session.flush()
    TourAssemblyService(session).refresh_wishlist_matches()
    session.commit()


@router.get("/wishlist-alerts", response_model=list[WishlistAlertRead])
def list_wishlist_alerts(session: Session = Depends(session_dep)) -> list[WishlistAlertRead]:
    tenant = get_session_tenant(session)
    RoadshowService(session).refresh_wishlist_alerts()
    session.commit()
    alerts = session.scalars(
        select(WishlistAlert)
        .options(
            selectinload(WishlistAlert.researcher),
            selectinload(WishlistAlert.wishlist_entry).selectinload(WishlistEntry.institution),
        )
        .where(WishlistAlert.tenant_id == tenant.id)
        .order_by(WishlistAlert.status, desc(WishlistAlert.score), WishlistAlert.created_at.desc())
    ).all()
    return [_wishlist_alert_read(alert) for alert in alerts]


@router.patch("/wishlist-alerts/{alert_id}", response_model=WishlistAlertRead)
def update_wishlist_alert_status(
    alert_id: str,
    payload: WishlistAlertStatusUpdate,
    session: Session = Depends(session_dep),
) -> WishlistAlertRead:
    if payload.status not in ALLOWED_WISHLIST_ALERT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported wishlist alert status")
    tenant = get_session_tenant(session)
    alert = session.scalar(
        select(WishlistAlert)
        .where(WishlistAlert.id == alert_id, WishlistAlert.tenant_id == tenant.id)
        .options(
            selectinload(WishlistAlert.researcher),
            selectinload(WishlistAlert.wishlist_entry).selectinload(WishlistEntry.institution),
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist alert not found")

    old_status = alert.status
    alert.status = payload.status
    alert.resolved_at = None if payload.status == "new" else datetime.now(UTC)
    metadata = dict(alert.metadata_json or {})
    if payload.note:
        metadata["status_note"] = payload.note
    alert.metadata_json = metadata
    session.add(alert)
    RoadshowService(session).record_event(
        event_type="wishlist_alert.status_updated",
        entity_type="wishlist_alert",
        entity_id=alert.id,
        payload={"from": old_status, "to": payload.status, "note": payload.note},
    )
    session.commit()
    session.refresh(alert)
    return _wishlist_alert_read(alert)


@router.post("/wishlist-matches/refresh", response_model=list[WishlistMatchGroupRead])
def refresh_wishlist_matches(session: Session = Depends(session_dep)) -> list[WishlistMatchGroupRead]:
    tenant = get_session_tenant(session)
    groups = TourAssemblyService(session).refresh_wishlist_matches()
    session.commit()
    groups = session.scalars(
        select(WishlistMatchGroup)
        .where(WishlistMatchGroup.id.in_([group.id for group in groups]))
        .where(WishlistMatchGroup.participants.any(WishlistMatchParticipant.tenant_id == tenant.id))
        .options(selectinload(WishlistMatchGroup.participants))
        .order_by(desc(WishlistMatchGroup.score), WishlistMatchGroup.created_at.desc())
    ).all()
    return [_wishlist_match_read(group) for group in groups]


@router.get("/wishlist-matches", response_model=list[WishlistMatchGroupRead])
def list_wishlist_matches(session: Session = Depends(session_dep)) -> list[WishlistMatchGroupRead]:
    tenant = get_session_tenant(session)
    groups = session.scalars(
        select(WishlistMatchGroup)
        .options(selectinload(WishlistMatchGroup.participants))
        .where(
            WishlistMatchGroup.status != "stale",
            WishlistMatchGroup.participants.any(WishlistMatchParticipant.tenant_id == tenant.id),
        )
        .order_by(desc(WishlistMatchGroup.score), WishlistMatchGroup.created_at.desc())
    ).all()
    return [_wishlist_match_read(group) for group in groups]


@router.get("/wishlist-matches/{match_id}", response_model=WishlistMatchGroupRead)
def get_wishlist_match(match_id: str, session: Session = Depends(session_dep)) -> WishlistMatchGroupRead:
    tenant = get_session_tenant(session)
    group = session.scalar(
        select(WishlistMatchGroup)
        .where(
            WishlistMatchGroup.id == match_id,
            WishlistMatchGroup.participants.any(WishlistMatchParticipant.tenant_id == tenant.id),
        )
        .options(selectinload(WishlistMatchGroup.participants))
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist match not found")
    return _wishlist_match_read(group)


@router.patch("/wishlist-matches/{match_id}/status", response_model=WishlistMatchGroupRead)
def update_wishlist_match_status(
    match_id: str,
    payload: WishlistMatchStatusUpdate,
    session: Session = Depends(session_dep),
) -> WishlistMatchGroupRead:
    if payload.status not in ALLOWED_WISHLIST_MATCH_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported wishlist match status")
    tenant = get_session_tenant(session)
    group = session.scalar(
        select(WishlistMatchGroup)
        .where(
            WishlistMatchGroup.id == match_id,
            WishlistMatchGroup.participants.any(WishlistMatchParticipant.tenant_id == tenant.id),
        )
        .options(selectinload(WishlistMatchGroup.participants))
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist match not found")
    TourAssemblyService(session).update_match_status(group, payload.status, note=payload.note)
    session.commit()
    session.refresh(group)
    return _wishlist_match_read(group)


@router.post("/tour-legs/propose", response_model=TourLegRead)
def propose_tour_leg(payload: TourLegProposalRequest, session: Session = Depends(session_dep)) -> TourLeg:
    cluster = session.scalar(
        select(TripCluster)
        .where(TripCluster.id == payload.trip_cluster_id)
        .options(selectinload(TripCluster.researcher).selectinload(Researcher.speaker_profile))
    )
    if not cluster:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip cluster not found")
    try:
        tour_leg = RoadshowService(session).propose_tour_leg(cluster, fee_per_stop_chf=payload.fee_per_stop_chf)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    session.commit()
    return session.scalar(select(TourLeg).where(TourLeg.id == tour_leg.id).options(selectinload(TourLeg.stops)))


@router.post("/travel-price-checks", response_model=TravelPriceCheckRead)
def create_travel_price_check(payload: TravelPriceCheckCreate, session: Session = Depends(session_dep)) -> TravelPriceCheck:
    tenant = get_session_tenant(session)
    if payload.tour_leg_id:
        tour_leg = session.scalar(select(TourLeg).where(TourLeg.id == payload.tour_leg_id, TourLeg.tenant_id == tenant.id))
        if not tour_leg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tour leg not found")
    check = TravelPriceChecker(session).quote(
        PriceQuoteRequest(
            origin_city=payload.origin_city,
            destination_city=payload.destination_city,
            departure_at=payload.departure_at,
            travel_class=payload.travel_class,
            fare_policy=payload.fare_policy,
            tour_leg_id=payload.tour_leg_id,
            force_refresh=payload.force_refresh,
        )
    )
    session.commit()
    session.refresh(check)
    return check


@router.get("/travel-price-checks", response_model=list[TravelPriceCheckRead])
def list_travel_price_checks(
    tour_leg_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(session_dep),
) -> list[TravelPriceCheck]:
    tenant = get_session_tenant(session)
    query = (
        select(TravelPriceCheck)
        .where(TravelPriceCheck.tenant_id == tenant.id)
        .order_by(TravelPriceCheck.fetched_at.desc())
        .limit(limit)
    )
    if tour_leg_id:
        query = (
            select(TravelPriceCheck)
            .where(TravelPriceCheck.tenant_id == tenant.id, TravelPriceCheck.tour_leg_id == tour_leg_id)
            .order_by(TravelPriceCheck.fetched_at.desc())
            .limit(limit)
        )
    return session.scalars(query).all()


@router.get("/tour-legs", response_model=list[TourLegRead])
def list_tour_legs(session: Session = Depends(session_dep)) -> list[TourLeg]:
    tenant = get_session_tenant(session)
    return session.scalars(
        select(TourLeg)
        .where(TourLeg.tenant_id == tenant.id)
        .options(selectinload(TourLeg.stops))
        .order_by(TourLeg.created_at.desc())
    ).all()


@router.post("/tour-legs/{tour_leg_id}/refresh-prices", response_model=TourLegRead)
def refresh_tour_leg_prices(tour_leg_id: str, session: Session = Depends(session_dep)) -> TourLeg:
    tenant = get_session_tenant(session)
    tour_leg = session.scalar(
        select(TourLeg).where(TourLeg.id == tour_leg_id, TourLeg.tenant_id == tenant.id).options(selectinload(TourLeg.stops))
    )
    if not tour_leg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tour leg not found")
    TravelPriceChecker(session).refresh_tour_leg(tour_leg, force=True)
    RoadshowService(session).record_event(
        event_type="travel_prices.refreshed",
        entity_type="tour_leg",
        entity_id=tour_leg.id,
        payload={
            "component_count": len((tour_leg.cost_split_json or {}).get("components") or []),
            "estimated_travel_total_chf": tour_leg.estimated_travel_total_chf,
        },
    )
    session.commit()
    return session.scalar(
        select(TourLeg).where(TourLeg.id == tour_leg.id, TourLeg.tenant_id == tenant.id).options(selectinload(TourLeg.stops))
    )


@router.get("/tour-legs/{tour_leg_id}", response_model=TourLegRead)
def get_tour_leg(tour_leg_id: str, session: Session = Depends(session_dep)) -> TourLeg:
    tenant = get_session_tenant(session)
    tour_leg = session.scalar(
        select(TourLeg).where(TourLeg.id == tour_leg_id, TourLeg.tenant_id == tenant.id).options(selectinload(TourLeg.stops))
    )
    if not tour_leg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tour leg not found")
    return tour_leg


@router.post("/tour-assemblies/propose", response_model=TourAssemblyProposalRead)
def propose_tour_assembly(
    payload: TourAssemblyProposalRequest,
    session: Session = Depends(session_dep),
) -> TourAssemblyProposalRead:
    tenant = get_session_tenant(session)
    group = session.scalar(
        select(WishlistMatchGroup).where(
            WishlistMatchGroup.id == payload.match_group_id,
            WishlistMatchGroup.participants.any(WishlistMatchParticipant.tenant_id == tenant.id),
        )
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist match not found")
    try:
        proposal = TourAssemblyService(session).propose_assembly(group)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    session.commit()
    proposal = session.scalar(
        select(TourAssemblyProposal)
        .where(TourAssemblyProposal.id == proposal.id)
        .options(
            selectinload(TourAssemblyProposal.match_group).selectinload(WishlistMatchGroup.participants),
        )
    )
    return _tour_assembly_read(proposal)


@router.get("/tour-assemblies", response_model=list[TourAssemblyProposalRead])
def list_tour_assemblies(session: Session = Depends(session_dep)) -> list[TourAssemblyProposalRead]:
    tenant = get_session_tenant(session)
    proposals = session.scalars(
        select(TourAssemblyProposal)
        .where(TourAssemblyProposal.tenant_id == tenant.id)
        .options(selectinload(TourAssemblyProposal.match_group).selectinload(WishlistMatchGroup.participants))
        .order_by(TourAssemblyProposal.status, TourAssemblyProposal.created_at.desc())
    ).all()
    return [_tour_assembly_read(proposal) for proposal in proposals]


@router.get("/tour-assemblies/{proposal_id}", response_model=TourAssemblyProposalRead)
def get_tour_assembly(proposal_id: str, session: Session = Depends(session_dep)) -> TourAssemblyProposalRead:
    tenant = get_session_tenant(session)
    proposal = session.scalar(
        select(TourAssemblyProposal)
        .where(TourAssemblyProposal.id == proposal_id, TourAssemblyProposal.tenant_id == tenant.id)
        .options(selectinload(TourAssemblyProposal.match_group).selectinload(WishlistMatchGroup.participants))
    )
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tour assembly proposal not found")
    return _tour_assembly_read(proposal)


@router.post("/tour-assemblies/{proposal_id}/speaker-draft", response_model=DraftRead)
def create_tour_assembly_speaker_draft(proposal_id: str, session: Session = Depends(session_dep)) -> OutreachDraft:
    tenant = get_session_tenant(session)
    proposal = session.scalar(select(TourAssemblyProposal).where(TourAssemblyProposal.id == proposal_id, TourAssemblyProposal.tenant_id == tenant.id))
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tour assembly proposal not found")
    try:
        draft = TourAssemblyService(session).create_speaker_draft(proposal)
    except ReviewRequiredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    session.commit()
    session.refresh(draft)
    return draft


@router.get("/relationship-briefs/{speaker_id}/{institution_id}", response_model=RelationshipBriefRead)
def get_relationship_brief(speaker_id: str, institution_id: str, session: Session = Depends(session_dep)) -> RelationshipBrief:
    if not session.get(Researcher, speaker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    if not session.get(Institution, institution_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    brief = RoadshowService(session).ensure_relationship_brief(speaker_id, institution_id)
    session.commit()
    return brief


@router.patch("/relationship-briefs/{speaker_id}/{institution_id}", response_model=RelationshipBriefRead)
def update_relationship_brief(
    speaker_id: str,
    institution_id: str,
    payload: RelationshipBriefUpdate,
    session: Session = Depends(session_dep),
) -> RelationshipBrief:
    if not session.get(Researcher, speaker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    if not session.get(Institution, institution_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    service = RoadshowService(session)
    brief = service.ensure_relationship_brief(speaker_id, institution_id)
    service.update_relationship_brief(brief, payload.model_dump())
    session.commit()
    session.refresh(brief)
    return brief


@router.post("/feedback-signals", response_model=FeedbackSignalRead)
def create_feedback_signal(payload: FeedbackSignalCreate, session: Session = Depends(session_dep)) -> FeedbackSignal:
    tenant = get_session_tenant(session)
    if not session.get(Researcher, payload.researcher_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found")
    if not session.get(Institution, payload.institution_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    if payload.tour_leg_id:
        tour_leg = session.scalar(select(TourLeg).where(TourLeg.id == payload.tour_leg_id, TourLeg.tenant_id == tenant.id))
        if not tour_leg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tour leg not found")
    signal = RoadshowService(session).create_feedback_signal(payload.model_dump())
    session.commit()
    session.refresh(signal)
    return signal


@router.get("/audit-events", response_model=list[AuditEventRead])
def list_audit_events(
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(session_dep),
) -> list[AuditEvent]:
    tenant = get_session_tenant(session)
    query = select(AuditEvent).where(AuditEvent.tenant_id == tenant.id).order_by(AuditEvent.created_at.desc()).limit(limit)
    if entity_type:
        query = (
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant.id, AuditEvent.entity_type == entity_type)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
    return session.scalars(query).all()


@router.get("/trip-clusters", response_model=list[TripClusterRead])
def list_trip_clusters(session: Session = Depends(session_dep)) -> list[TripCluster]:
    return session.scalars(select(TripCluster).order_by(TripCluster.opportunity_score.desc())).all()


@router.get("/calendar/overlay", response_model=CalendarOverlayResponse)
def calendar_overlay(
    rebuild: bool = Query(default=False),
    session: Session = Depends(session_dep),
) -> CalendarOverlayResponse:
    tenant = get_session_tenant(session)
    if rebuild:
        AvailabilityBuilder(session).rebuild_persisted()
        Scorer(session).score_all_clusters()
        session.commit()
    host_events = session.scalars(
        select(HostCalendarEvent).where(tenant_scope(HostCalendarEvent, tenant)).order_by(HostCalendarEvent.starts_at)
    ).all()
    open_windows = session.scalars(
        select(OpenSeminarWindow).where(tenant_scope(OpenSeminarWindow, tenant)).order_by(OpenSeminarWindow.starts_at)
    ).all()
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
    fact_type: str | None = Query(default=None),
    researcher_id: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    source_contains: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(session_dep),
) -> list[ReviewFactRead]:
    if status_filter not in {"pending", "approved", "rejected", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported review status filter")
    query = select(FactCandidate).options(selectinload(FactCandidate.researcher))
    if status_filter != "all":
        query = query.where(FactCandidate.status == status_filter)
    if fact_type:
        query = query.where(FactCandidate.fact_type == fact_type)
    if researcher_id:
        query = query.where(FactCandidate.researcher_id == researcher_id)
    if min_confidence is not None:
        query = query.where(FactCandidate.confidence >= min_confidence)
    if source_contains:
        query = query.where(FactCandidate.source_url.ilike(f"%{source_contains}%"))

    candidates = session.scalars(
        query.order_by(FactCandidate.status, FactCandidate.confidence.desc(), FactCandidate.created_at.desc()).limit(limit)
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
    tenant = get_session_tenant(session)
    return session.scalars(
        select(SeminarSlotTemplate)
        .where(SeminarSlotTemplate.tenant_id == tenant.id)
        .order_by(SeminarSlotTemplate.weekday, SeminarSlotTemplate.start_time)
    ).all()


@router.post("/seminar/templates", response_model=SeminarSlotTemplateRead)
def create_slot_template(payload: SeminarSlotTemplateCreate, session: Session = Depends(session_dep)) -> SeminarSlotTemplate:
    tenant = get_session_tenant(session)
    template = SeminarSlotTemplate(tenant_id=tenant.id, **payload.model_dump())
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
    tenant = get_session_tenant(session)
    template = session.scalar(select(SeminarSlotTemplate).where(SeminarSlotTemplate.id == template_id, SeminarSlotTemplate.tenant_id == tenant.id))
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    for field, value in payload.model_dump().items():
        setattr(template, field, value)
    session.add(template)
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()
    return template


@router.delete("/seminar/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slot_template(template_id: str, session: Session = Depends(session_dep)) -> None:
    tenant = get_session_tenant(session)
    template = session.scalar(select(SeminarSlotTemplate).where(SeminarSlotTemplate.id == template_id, SeminarSlotTemplate.tenant_id == tenant.id))
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    session.execute(delete(OpenSeminarWindow).where(OpenSeminarWindow.tenant_id == tenant.id, OpenSeminarWindow.derived_from_template_id == template.id))
    session.delete(template)
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()


@router.get("/seminar/overrides", response_model=list[SeminarSlotOverrideRead])
def list_slot_overrides(session: Session = Depends(session_dep)) -> list[SeminarSlotOverride]:
    tenant = get_session_tenant(session)
    return session.scalars(
        select(SeminarSlotOverride).where(SeminarSlotOverride.tenant_id == tenant.id).order_by(SeminarSlotOverride.start_at)
    ).all()


@router.post("/seminar/overrides", response_model=SeminarSlotOverrideRead)
def create_slot_override(payload: SeminarSlotOverrideCreate, session: Session = Depends(session_dep)) -> SeminarSlotOverride:
    tenant = get_session_tenant(session)
    override = SeminarSlotOverride(tenant_id=tenant.id, **payload.model_dump())
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
    tenant = get_session_tenant(session)
    override = session.scalar(select(SeminarSlotOverride).where(SeminarSlotOverride.id == override_id, SeminarSlotOverride.tenant_id == tenant.id))
    if not override:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    for field, value in payload.model_dump().items():
        setattr(override, field, value)
    session.add(override)
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()
    return override


@router.delete("/seminar/overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slot_override(override_id: str, session: Session = Depends(session_dep)) -> None:
    tenant = get_session_tenant(session)
    override = session.scalar(select(SeminarSlotOverride).where(SeminarSlotOverride.id == override_id, SeminarSlotOverride.tenant_id == tenant.id))
    if not override:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    session.delete(override)
    AvailabilityBuilder(session).rebuild_persisted()
    Scorer(session).score_all_clusters()
    session.commit()


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
    tenant = get_session_tenant(session)
    query = (
        select(OutreachDraft)
        .where(OutreachDraft.tenant_id == tenant.id)
        .options(selectinload(OutreachDraft.researcher), selectinload(OutreachDraft.trip_cluster))
        .order_by(OutreachDraft.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        if status_filter not in ALLOWED_DRAFT_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported draft status filter")
        query = (
            select(OutreachDraft)
            .where(OutreachDraft.tenant_id == tenant.id, OutreachDraft.status == status_filter)
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
        if draft.researcher and draft.trip_cluster
    ]


@router.patch("/outreach-drafts/{draft_id}/status", response_model=DraftRead)
def update_draft_status(
    draft_id: str,
    payload: DraftStatusUpdate,
    session: Session = Depends(session_dep),
) -> OutreachDraft:
    if payload.status not in ALLOWED_DRAFT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported draft status")
    tenant = get_session_tenant(session)
    draft = session.scalar(select(OutreachDraft).where(OutreachDraft.id == draft_id, OutreachDraft.tenant_id == tenant.id))
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    _validate_draft_status_transition(draft, payload)

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
    if payload.status == "reviewed":
        confirmations = list(metadata.get("checklist_confirmations") or [])
        confirmations.extend(
            {
                "label": label,
                "confirmed_at": datetime.now(UTC).isoformat(),
            }
            for label in payload.checklist_confirmations
        )
        metadata["checklist_confirmations"] = confirmations
    if payload.status == "sent_manually":
        metadata["manual_send_confirmed_at"] = datetime.now(UTC).isoformat()
    draft.status = payload.status
    draft.metadata_json = metadata
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


@router.get("/outreach-drafts/{draft_id}", response_model=DraftRead)
def get_draft(draft_id: str, session: Session = Depends(session_dep)) -> OutreachDraft:
    tenant = get_session_tenant(session)
    draft = session.scalar(select(OutreachDraft).where(OutreachDraft.id == draft_id, OutreachDraft.tenant_id == tenant.id))
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft
