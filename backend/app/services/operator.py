from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    AuditEvent,
    FactCandidate,
    HostCalendarEvent,
    OpenSeminarWindow,
    OutreachDraft,
    Researcher,
    ResearcherFact,
    SeminarSlotTemplate,
    SourceHealthCheck,
    SourceDocument,
    TalkEvent,
    TourAssemblyProposal,
    TourLeg,
    WishlistAlert,
    WishlistMatchGroup,
    WishlistMatchParticipant,
)
from app.services.audit import SourceAuditor, SourceReliabilityService
from app.services.availability import AvailabilityBuilder
from app.services.enrichment import BiographerPipeline
from app.services.ingestion import IngestionService
from app.services.opportunities import OpportunityWorkbench
from app.services.plausibility import PlausibilityService
from app.services.roadshow import RoadshowService
from app.services.scoring import Scorer
from app.services.tenancy import get_session_tenant
from app.services.tour_assembly import TourAssemblyService


GROUPS: dict[str, tuple[str, str]] = {
    "freshness": ("Freshness", "Keep Scout and the KOF calendar current before making invitation decisions."),
    "evidence": ("Evidence", "Approve the biographic facts required for safe outreach."),
    "calendar": ("Calendar", "Maintain KOF seminar supply and remove blocked dates."),
    "wishlist": ("Wishlist", "Triage KOF-demand matches as soon as Scout finds them."),
    "opportunity": ("Opportunities", "Convert the best European trip windows into Zurich decisions."),
    "draft": ("Drafts", "Move generated drafts through review and manual send tracking."),
    "tour_leg": ("Tour Legs", "Review deterministic KOF-stop proposals and their cost split."),
    "feedback": ("Feedback", "Capture post-event signals so relationship memory improves over time."),
}
GROUP_ORDER = list(GROUPS)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


@dataclass(slots=True)
class OperatorAction:
    label: str
    href: str | None = None
    method: str = "GET"
    action_key: str | None = None
    disabled_reason: str | None = None


@dataclass(slots=True)
class OperatorPrimaryFlow:
    label: str
    consequence: str
    href: str | None = None
    method: str = "GET"
    action_key: str | None = None
    disabled_reason: str | None = None


@dataclass(slots=True)
class OperatorSetupBlocker:
    id: str
    title: str
    explanation: str
    action: OperatorPrimaryFlow
    count: int = 0


@dataclass(slots=True)
class OperatorTask:
    id: str
    group: str
    severity: str
    status: str
    title: str
    explanation: str
    primary_action: OperatorAction
    secondary_actions: list[OperatorAction] = field(default_factory=list)
    entity_type: str | None = None
    entity_id: str | None = None
    count: int = 1
    disabled_reason: str | None = None
    last_updated_at: datetime | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MorningSweepStep:
    key: str
    title: str
    status: str
    detail: str
    processed_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)
    error: str | None = None


class OperatorCockpit:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tenant = get_session_tenant(session)

    def build(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        tasks = self._build_tasks()
        ordered_tasks = sorted(tasks, key=lambda item: (SEVERITY_ORDER.get(item.severity, 9), GROUP_ORDER.index(item.group), item.title))
        next_best_action = ordered_tasks[0] if ordered_tasks else None
        posture = self._posture(ordered_tasks)
        recent_changes = self._recent_changes()
        summary_metrics = self._summary_metrics(tasks)
        data_state = self._data_state()
        setup_blockers = self._setup_blockers(summary_metrics, data_state)
        primary_flow = self._primary_flow(ordered_tasks, setup_blockers, summary_metrics, data_state)
        source_snapshot = self._source_snapshot()

        return {
            "generated_at": now,
            "posture": posture[0],
            "posture_detail": posture[1],
            "data_state": data_state,
            "setup_blockers": [asdict(blocker) for blocker in setup_blockers],
            "primary_flow": asdict(primary_flow),
            "summary_metrics": summary_metrics,
            "next_best_action": self._task_payload(next_best_action) if next_best_action else None,
            "source_snapshot": source_snapshot,
            "groups": [
                {
                    "key": key,
                    "title": GROUPS[key][0],
                    "purpose": GROUPS[key][1],
                    "tasks": [self._task_payload(task) for task in ordered_tasks if task.group == key],
                }
                for key in GROUP_ORDER
            ],
            "recent_changes": recent_changes,
            "ai_next_action_explanation": None,
        }

    def _data_state(self) -> str:
        source_health_count = int(self.session.scalar(select(func.count()).select_from(SourceHealthCheck)) or 0)
        researcher_count = int(self.session.scalar(select(func.count()).select_from(Researcher)) or 0)
        talk_payloads = list(self.session.scalars(select(TalkEvent.raw_payload)).all())
        document_metadata = list(self.session.scalars(select(SourceDocument.metadata_json)).all())
        fact_origins = list(self.session.scalars(select(ResearcherFact.approval_origin)).all())
        host_metadata = list(
            self.session.scalars(select(HostCalendarEvent.metadata_json).where(HostCalendarEvent.tenant_id == self.tenant.id)).all()
        )
        template_count = int(
            self.session.scalar(select(func.count()).select_from(SeminarSlotTemplate).where(SeminarSlotTemplate.tenant_id == self.tenant.id)) or 0
        )
        open_window_count = int(
            self.session.scalar(select(func.count()).select_from(OpenSeminarWindow).where(OpenSeminarWindow.tenant_id == self.tenant.id)) or 0
        )
        draft_count = int(
            self.session.scalar(select(func.count()).select_from(OutreachDraft).where(OutreachDraft.tenant_id == self.tenant.id)) or 0
        )
        tour_leg_count = int(
            self.session.scalar(select(func.count()).select_from(TourLeg).where(TourLeg.tenant_id == self.tenant.id)) or 0
        )

        def is_demo_metadata(value: Any) -> bool:
            return isinstance(value, dict) and str(value.get("source", "")).startswith("demo")

        demo_marker = (
            any(is_demo_metadata(payload) for payload in talk_payloads)
            or any(is_demo_metadata(metadata) for metadata in document_metadata)
            or any(is_demo_metadata(metadata) for metadata in host_metadata)
            or any(origin == "demo_seed" for origin in fact_origins)
        )
        real_talk_marker = any(not is_demo_metadata(payload) for payload in talk_payloads)
        real_document_marker = any(not is_demo_metadata(metadata) for metadata in document_metadata)
        if (
            researcher_count
            + len(talk_payloads)
            + len(document_metadata)
            + template_count
            + open_window_count
            + draft_count
            + tour_leg_count
            + source_health_count
            == 0
        ):
            return "empty"
        reliability = SourceReliabilityService().summarize(self.session)
        if reliability and any(source.needs_attention for source in reliability):
            return "stale"
        if demo_marker and not real_talk_marker and not real_document_marker and source_health_count == 0:
            return "demo"
        return "real"

    def _setup_blockers(self, summary_metrics: dict[str, int], data_state: str) -> list[OperatorSetupBlocker]:
        template_count = int(
            self.session.scalar(
                select(func.count()).select_from(SeminarSlotTemplate).where(
                    SeminarSlotTemplate.tenant_id == self.tenant.id,
                    SeminarSlotTemplate.active.is_(True),
                )
            )
            or 0
        )
        talk_count = int(self.session.scalar(select(func.count()).select_from(TalkEvent)) or 0)
        blockers: list[OperatorSetupBlocker] = []
        if data_state == "empty":
            blockers.append(
                OperatorSetupBlocker(
                    id="run-real-source-sync",
                    title="No seminar data is loaded yet",
                    explanation="Roadshow needs a real source sync before it can show speaker visits, source status, and seminar opportunities.",
                    action=OperatorPrimaryFlow(
                        label="Run real source sync",
                        consequence="Checks watched sources, syncs KOF, refreshes evidence, rebuilds windows, updates scores, and records data-source status.",
                        method="POST",
                        action_key="real_sync",
                    ),
                )
            )
        if template_count == 0:
            blockers.append(
                OperatorSetupBlocker(
                    id="set-weekly-kof-slot",
                    title="No weekly KOF seminar slot is defined",
                    explanation="Speaker visits cannot be matched to Zurich invitations until Roadshow knows KOF's recurring seminar capacity.",
                    action=OperatorPrimaryFlow(
                        label="Set weekly KOF slot",
                        consequence="Opens the seminar settings page so you can define the recurring KOF seminar pattern.",
                        href="/seminar-admin",
                    ),
                    count=template_count,
                )
            )
        if talk_count == 0 and data_state != "empty":
            blockers.append(
                OperatorSetupBlocker(
                    id="find-speaker-visits",
                    title="No speaker visits have been found",
                    explanation="The KOF calendar may be configured, but there are no external speaker appearances to match against it yet.",
                    action=OperatorPrimaryFlow(
                        label="Run real source sync",
                        consequence="Checks watched sources, syncs KOF, refreshes evidence, rebuilds windows, and updates scores.",
                        method="POST",
                        action_key="real_sync",
                    ),
                    count=talk_count,
                )
            )
        if template_count > 0 and summary_metrics["open_windows"] == 0:
            blockers.append(
                OperatorSetupBlocker(
                    id="no-open-kof-windows",
                    title="KOF has no open invitation windows",
                    explanation="Templates exist, but all derived windows are blocked or not generated, so opportunities cannot get a slot fit.",
                    action=OperatorPrimaryFlow(
                        label="Review blocked KOF slots",
                        consequence="Shows occupied KOF events and derived windows so you can decide whether an override is needed.",
                        href="/calendar",
                    ),
                    count=summary_metrics["open_windows"],
                )
            )
        if summary_metrics["pending_evidence"]:
            blockers.append(
                OperatorSetupBlocker(
                    id="approve-evidence",
                    title="Evidence approval is blocking outreach",
                    explanation="Drafts require approved biographic hooks; pending candidates can influence scoring but cannot be used in outreach.",
                    action=OperatorPrimaryFlow(
                        label="Approve evidence",
                        consequence="Opens the evidence queue so you can approve or reject extracted PhD and nationality facts.",
                        href="/review?status=pending",
                    ),
                    count=summary_metrics["pending_evidence"],
                )
            )
        if data_state == "stale":
            blockers.append(
                OperatorSetupBlocker(
                    id="refresh-stale-sources",
                    title="Some watched sources need attention",
                    explanation="At least one source is failing, empty, or degrading, so the current opportunity picture may be stale.",
                    action=OperatorPrimaryFlow(
                        label="Run real source sync",
                        consequence="Refreshes the source picture and records which steps still need attention.",
                        method="POST",
                        action_key="real_sync",
                    ),
                )
            )
        return blockers

    def _primary_flow(
        self,
        ordered_tasks: list[OperatorTask],
        setup_blockers: list[OperatorSetupBlocker],
        summary_metrics: dict[str, int],
        data_state: str,
    ) -> OperatorPrimaryFlow:
        if data_state == "empty":
            return setup_blockers[0].action
        if setup_blockers:
            return setup_blockers[0].action

        anonymous_match = next((task for task in ordered_tasks if task.status == "anonymous_match"), None)
        if anonymous_match:
            return OperatorPrimaryFlow(
                label="Build anonymous tour proposal",
                consequence="Opens the wishlist match so Roadshow can assemble a masked multi-host request with deterministic budget checks.",
                href="/wishlist",
            )
        assembly_ready = next((task for task in ordered_tasks if task.status == "ready_for_speaker_draft"), None)
        if assembly_ready:
            return OperatorPrimaryFlow(
                label="Create speaker tour draft",
                consequence="Opens the tour assembly proposal so the review-gated multi-host speaker request can be generated.",
                href=assembly_ready.primary_action.href,
            )
        ready_opportunity = next((task for task in ordered_tasks if task.group == "opportunity" and task.status == "ready_for_decision"), None)
        if ready_opportunity:
            return OperatorPrimaryFlow(
                label="Create KOF invitation draft",
                consequence="Opens the opportunity workbench where the approved hook, best KOF slot, and internal logistics notes are shown before draft creation.",
                href="/opportunities",
            )
        if summary_metrics["drafts_waiting"]:
            return OperatorPrimaryFlow(
                label="Mark sent",
                consequence="Opens reviewed drafts so you can track the manual off-platform send step.",
                href="/drafts?status=reviewed",
            )
        return OperatorPrimaryFlow(
            label="Run real source sync",
            consequence="Checks watched sources, KOF calendar, evidence, open slots, scores, and wishlist alerts.",
            method="POST",
            action_key="real_sync",
        )

    def _build_tasks(self) -> list[OperatorTask]:
        tasks: list[OperatorTask] = []
        reliability = SourceReliabilityService().summarize(self.session)
        workbench = OpportunityWorkbench(self.session).build(limit=100)
        alerts = self.session.scalars(
            select(WishlistAlert)
            .options(selectinload(WishlistAlert.researcher), selectinload(WishlistAlert.trip_cluster))
            .where(WishlistAlert.tenant_id == self.tenant.id, WishlistAlert.status == "new")
            .order_by(desc(WishlistAlert.score), WishlistAlert.created_at.desc())
        ).all()
        match_groups = self.session.scalars(
            select(WishlistMatchGroup)
            .options(selectinload(WishlistMatchGroup.participants))
            .where(
                WishlistMatchGroup.status == "new",
                WishlistMatchGroup.participants.any(WishlistMatchParticipant.tenant_id == self.tenant.id),
            )
            .order_by(desc(WishlistMatchGroup.score), WishlistMatchGroup.created_at.desc())
            .limit(5)
        ).all()
        assemblies = self.session.scalars(
            select(TourAssemblyProposal).where(
                TourAssemblyProposal.tenant_id == self.tenant.id,
                TourAssemblyProposal.status.in_(("blocked", "ready_for_review")),
            ).order_by(
                TourAssemblyProposal.status,
                TourAssemblyProposal.created_at.desc(),
            )
        ).all()

        tasks.extend(self._freshness_tasks(reliability))
        tasks.extend(self._evidence_tasks())
        tasks.extend(self._calendar_tasks())
        tasks.extend(self._wishlist_tasks(alerts))
        tasks.extend(self._anonymous_assembly_tasks(match_groups, assemblies))
        tasks.extend(self._opportunity_tasks(workbench["opportunities"]))
        tasks.extend(self._draft_tasks())
        tasks.extend(self._tour_leg_tasks())
        tasks.extend(self._feedback_tasks())
        return tasks

    def _anonymous_assembly_tasks(
        self,
        match_groups: list[WishlistMatchGroup],
        assemblies: list[TourAssemblyProposal],
    ) -> list[OperatorTask]:
        tasks: list[OperatorTask] = []
        for group in match_groups:
            tasks.append(
                OperatorTask(
                    id=f"anonymous-match-{group.id}",
                    group="wishlist",
                    severity="high" if group.score >= 85 else "medium",
                    status="anonymous_match",
                    title=f"Build a masked Roadshow for {group.display_speaker_name}",
                    explanation=(
                        f"{len(group.participants)} nearby institutions wishlist this speaker. "
                        "Roadshow can assemble a private multi-host proposal without exposing co-host identities."
                    ),
                    primary_action=OperatorAction(label="Build anonymous tour proposal", href="/wishlist"),
                    secondary_actions=[OperatorAction(label="Review co-host match", href="/wishlist")],
                    entity_type="wishlist_match_group",
                    entity_id=group.id,
                    count=len(group.participants),
                    last_updated_at=group.updated_at,
                    metadata_json={"score": group.score, "radius_km": group.radius_km},
                )
            )
        for proposal in assemblies[:5]:
            if proposal.status == "blocked":
                tasks.append(
                    OperatorTask(
                        id=f"assembly-blocked-{proposal.id}",
                        group="tour_leg",
                        severity="high",
                        status="assembly_blocked",
                        title=f"Clear tour assembly blockers for {proposal.title}",
                        explanation="The anonymous tour exists, but budget, identity, or trip-window blockers must be resolved before speaker outreach.",
                        primary_action=OperatorAction(label="Review assembly blockers", href=f"/tour-assemblies/{proposal.id}"),
                        entity_type="tour_assembly_proposal",
                        entity_id=proposal.id,
                        count=len(proposal.blockers),
                        last_updated_at=proposal.updated_at,
                        metadata_json={"blockers": proposal.blockers},
                    )
                )
            elif proposal.status == "ready_for_review":
                tasks.append(
                    OperatorTask(
                        id=f"assembly-draft-ready-{proposal.id}",
                        group="tour_leg",
                        severity="medium",
                        status="ready_for_speaker_draft",
                        title=f"Create speaker tour draft for {proposal.title}",
                        explanation="The anonymous multi-host terms are compatible; generate the review-gated speaker request when evidence is approved.",
                        primary_action=OperatorAction(label="Create speaker tour draft", href=f"/tour-assemblies/{proposal.id}"),
                        entity_type="tour_assembly_proposal",
                        entity_id=proposal.id,
                        last_updated_at=proposal.updated_at,
                    )
                )
        return tasks

    def _freshness_tasks(self, reliability) -> list[OperatorTask]:
        latest_check = self.session.scalar(select(SourceHealthCheck).order_by(desc(SourceHealthCheck.checked_at)).limit(1))
        if not reliability:
            return [
                OperatorTask(
                    id="freshness-first-real-sync",
                    group="freshness",
                    severity="high",
                    status="needs_setup",
                    title="Run the first Roadshow source sync",
                    explanation="No source audit history exists yet, so the cockpit cannot tell whether Scout is hearing the seminar circuit.",
                    primary_action=OperatorAction(label="Run real source sync", method="POST", action_key="real_sync"),
                    secondary_actions=[OperatorAction(label="Open data sources", href="/source-health")],
                    count=1,
                )
            ]

        tasks: list[OperatorTask] = []
        stale_sources = [source for source in reliability if source.needs_attention]
        if stale_sources:
            tasks.append(
                OperatorTask(
                    id="freshness-source-attention",
                    group="freshness",
                    severity="high",
                    status="needs_attention",
                    title=f"Inspect {len(stale_sources)} Scout source signal{'s' if len(stale_sources) != 1 else ''}",
                    explanation="One or more watched sources are failing, empty, or degrading compared with the last recorded checks.",
                    primary_action=OperatorAction(label="Inspect data sources", href="/source-health"),
                    secondary_actions=[OperatorAction(label="Run real source sync", method="POST", action_key="real_sync")],
                    count=len(stale_sources),
                    last_updated_at=latest_check.checked_at if latest_check else None,
                    metadata_json={"sources": [source.source_name for source in stale_sources]},
                )
            )
        else:
            tasks.append(
                OperatorTask(
                    id="freshness-real-sync",
                    group="freshness",
                    severity="low",
                    status="ready",
                    title="Refresh Roadshow before decisions",
                    explanation="Run the deterministic sweep when you want the cockpit to re-check sources, KOF slots, evidence, scores, and alerts.",
                    primary_action=OperatorAction(label="Run real source sync", method="POST", action_key="real_sync"),
                    count=len(reliability),
                    last_updated_at=latest_check.checked_at if latest_check else None,
                )
            )
        return tasks

    def _evidence_tasks(self) -> list[OperatorTask]:
        pending_count = int(
            self.session.scalar(select(func.count()).select_from(FactCandidate).where(FactCandidate.status == "pending")) or 0
        )
        if pending_count == 0:
            return []
        latest = self.session.scalar(
            select(FactCandidate).where(FactCandidate.status == "pending").order_by(desc(FactCandidate.created_at)).limit(1)
        )
        return [
            OperatorTask(
                id="evidence-pending-facts",
                group="evidence",
                severity="high",
                status="blocks_outreach",
                title=f"Approve {pending_count} evidence candidate{'s' if pending_count != 1 else ''}",
                explanation="Outreach drafts stay blocked until required PhD and nationality hooks are approved, not merely detected.",
                primary_action=OperatorAction(label="Approve evidence for outreach", href="/review?status=pending"),
                count=pending_count,
                last_updated_at=latest.created_at if latest else None,
            )
        ]

    def _calendar_tasks(self) -> list[OperatorTask]:
        template_count = int(
            self.session.scalar(
                select(func.count()).select_from(SeminarSlotTemplate).where(
                    SeminarSlotTemplate.tenant_id == self.tenant.id,
                    SeminarSlotTemplate.active.is_(True),
                )
            )
            or 0
        )
        open_window_count = int(
            self.session.scalar(select(func.count()).select_from(OpenSeminarWindow).where(OpenSeminarWindow.tenant_id == self.tenant.id)) or 0
        )
        host_event_count = int(
            self.session.scalar(select(func.count()).select_from(HostCalendarEvent).where(HostCalendarEvent.tenant_id == self.tenant.id)) or 0
        )
        if template_count == 0:
            return [
                OperatorTask(
                    id="calendar-create-template",
                    group="calendar",
                    severity="high",
                    status="blocks_slot_fit",
                    title="Create KOF seminar slot templates",
                    explanation="Roadshow cannot find invitation windows until recurring KOF seminar capacity is defined by an admin.",
                    primary_action=OperatorAction(label="Create seminar template", href="/seminar-admin"),
                    count=0,
                )
            ]
        if open_window_count == 0:
            return [
                OperatorTask(
                    id="calendar-no-open-windows",
                    group="calendar",
                    severity="high",
                    status="blocks_slot_fit",
                    title="Re-open or adjust KOF seminar capacity",
                    explanation="Templates exist, but all derived windows are currently blocked by host events or manual overrides.",
                    primary_action=OperatorAction(label="Review calendar blocks", href="/calendar"),
                    secondary_actions=[OperatorAction(label="Manage slot overrides", href="/seminar-admin")],
                    count=host_event_count,
                )
            ]
        return []

    def _wishlist_tasks(self, alerts: list[WishlistAlert]) -> list[OperatorTask]:
        tasks: list[OperatorTask] = []
        for alert in alerts[:5]:
            researcher_name = alert.researcher.name if alert.researcher else "Matched speaker"
            tasks.append(
                OperatorTask(
                    id=f"wishlist-alert-{alert.id}",
                    group="wishlist",
                    severity="medium" if alert.score < 90 else "high",
                    status="new_match",
                    title=f"Wishlist match: {researcher_name}",
                    explanation=alert.match_reason,
                    primary_action=OperatorAction(label="Review wishlist match", href="/wishlist"),
                    secondary_actions=[
                        OperatorAction(label="Review speaker dossier", href=f"/researchers/{alert.researcher_id}") if alert.researcher_id else OperatorAction(label="Review wishlist", href="/wishlist"),
                        OperatorAction(label="Open opportunity workbench", href="/opportunities"),
                    ],
                    entity_type="wishlist_alert",
                    entity_id=alert.id,
                    count=1,
                    last_updated_at=alert.created_at,
                    metadata_json={"score": alert.score, "trip_cluster_id": alert.trip_cluster_id},
                )
            )
        if len(alerts) > 5:
            tasks.append(
                OperatorTask(
                    id="wishlist-more-alerts",
                    group="wishlist",
                    severity="medium",
                    status="new_match",
                    title=f"Triage {len(alerts) - 5} additional wishlist matches",
                    explanation="The cockpit shows the top five matches here; open the wishlist page to clear the rest.",
                    primary_action=OperatorAction(label="Triage all wishlist alerts", href="/wishlist"),
                    count=len(alerts) - 5,
                )
            )
        return tasks

    def _opportunity_tasks(self, opportunities: list[dict[str, Any]]) -> list[OperatorTask]:
        tasks: list[OperatorTask] = []
        ready = [item for item in opportunities if item["draft_ready"] and item["best_window"]]
        blocked = [item for item in opportunities if not item["draft_ready"]]
        for item in ready[:3]:
            researcher = item["researcher"]
            cluster = item["cluster"]
            best_window = item["best_window"]
            tasks.append(
                OperatorTask(
                    id=f"opportunity-ready-{cluster.id}",
                    group="opportunity",
                    severity="high" if cluster.opportunity_score >= 85 else "medium",
                    status="ready_for_decision",
                    title=f"Decide on {researcher.name}'s KOF stop",
                    explanation="This opportunity has approved hook facts, a matched KOF slot, and internal logistics notes ready for review.",
                    primary_action=OperatorAction(label="Create KOF invitation draft", href="/opportunities"),
                    secondary_actions=[
                        OperatorAction(label="Add KOF as a tour stop", href="/opportunities"),
                        OperatorAction(label="Review speaker dossier", href=f"/researchers/{researcher.id}"),
                    ],
                    entity_type="trip_cluster",
                    entity_id=cluster.id,
                    count=1,
                    metadata_json={
                        "score": cluster.opportunity_score,
                        "slot_starts_at": best_window["starts_at"].isoformat() if hasattr(best_window["starts_at"], "isoformat") else str(best_window["starts_at"]),
                        "cost_share": item["cost_share"],
                    },
                )
            )
        if blocked and not ready:
            item = blocked[0]
            researcher = item["researcher"]
            cluster = item["cluster"]
            tasks.append(
                OperatorTask(
                    id=f"opportunity-blocked-{cluster.id}",
                    group="opportunity",
                    severity="medium",
                    status="blocked",
                    title=f"Unblock {researcher.name}'s opportunity",
                    explanation="The trip is visible in Scout, but outreach cannot be generated until the blockers are cleared.",
                    primary_action=OperatorAction(label="Clear opportunity blockers", href="/opportunities"),
                    secondary_actions=[OperatorAction(label="Approve evidence for outreach", href="/review?status=pending")],
                    entity_type="trip_cluster",
                    entity_id=cluster.id,
                    disabled_reason="; ".join(item["draft_blockers"]),
                    metadata_json={"score": cluster.opportunity_score, "draft_blockers": item["draft_blockers"]},
                )
            )
        return tasks

    def _draft_tasks(self) -> list[OperatorTask]:
        draft_count = int(
            self.session.scalar(
                select(func.count()).select_from(OutreachDraft).where(
                    OutreachDraft.tenant_id == self.tenant.id,
                    OutreachDraft.status == "draft",
                )
            )
            or 0
        )
        reviewed_count = int(
            self.session.scalar(
                select(func.count()).select_from(OutreachDraft).where(
                    OutreachDraft.tenant_id == self.tenant.id,
                    OutreachDraft.status == "reviewed",
                )
            )
            or 0
        )
        tasks: list[OperatorTask] = []
        if draft_count:
            latest = self.session.scalar(
                select(OutreachDraft)
                .where(OutreachDraft.tenant_id == self.tenant.id, OutreachDraft.status == "draft")
                .order_by(desc(OutreachDraft.created_at))
                .limit(1)
            )
            tasks.append(
                OperatorTask(
                    id="draft-review-generated",
                    group="draft",
                    severity="medium",
                    status="needs_review",
                    title=f"Review {draft_count} generated draft{'s' if draft_count != 1 else ''}",
                    explanation="Generated copy still needs a human check before it can be marked reviewed or sent manually.",
                    primary_action=OperatorAction(label="Review generated drafts", href="/drafts?status=draft"),
                    count=draft_count,
                    last_updated_at=latest.created_at if latest else None,
                )
            )
        if reviewed_count:
            tasks.append(
                OperatorTask(
                    id="draft-mark-sent",
                    group="draft",
                    severity="low",
                    status="ready_to_send",
                    title=f"Track {reviewed_count} reviewed draft{'s' if reviewed_count != 1 else ''}",
                    explanation="Reviewed drafts are ready for the off-platform send step and should be marked sent manually afterward.",
                    primary_action=OperatorAction(label="Mark reviewed drafts as sent", href="/drafts?status=reviewed"),
                    count=reviewed_count,
                )
            )
        return tasks

    def _tour_leg_tasks(self) -> list[OperatorTask]:
        proposed_count = int(
            self.session.scalar(
                select(func.count()).select_from(TourLeg).where(TourLeg.tenant_id == self.tenant.id, TourLeg.status == "proposed")
            )
            or 0
        )
        if not proposed_count:
            return []
        return [
            OperatorTask(
                id="tour-leg-review-proposals",
                group="tour_leg",
                severity="low",
                status="needs_review",
                title=f"Review {proposed_count} proposed tour leg{'s' if proposed_count != 1 else ''}",
                explanation="Tour legs are deterministic logistics proposals; review the KOF stop, assumptions, and cost split before outreach.",
                primary_action=OperatorAction(label="Review tour-leg proposals", href="/tour-legs"),
                count=proposed_count,
            )
        ]

    def _feedback_tasks(self) -> list[OperatorTask]:
        today = datetime.now(UTC).date()
        past_legs = self.session.scalars(
            select(TourLeg)
            .where(TourLeg.tenant_id == self.tenant.id, TourLeg.end_date < today)
            .options(selectinload(TourLeg.feedback_signals), selectinload(TourLeg.researcher))
            .order_by(desc(TourLeg.end_date))
            .limit(5)
        ).all()
        missing_feedback = [leg for leg in past_legs if not leg.feedback_signals]
        if not missing_feedback:
            return []
        leg = missing_feedback[0]
        return [
            OperatorTask(
                id=f"feedback-missing-{leg.id}",
                group="feedback",
                severity="low",
                status="needs_memory",
                title=f"Capture feedback for {leg.researcher.name if leg.researcher else 'past Roadshow leg'}",
                explanation="No post-event feedback signal is attached yet, so relationship memory will not improve from this visit.",
                primary_action=OperatorAction(label="Capture post-event feedback", href=f"/tour-legs/{leg.id}"),
                entity_type="tour_leg",
                entity_id=leg.id,
                count=len(missing_feedback),
            )
        ]

    def _summary_metrics(self, tasks: list[OperatorTask]) -> dict[str, int]:
        return {
            "urgent_tasks": sum(1 for task in tasks if task.severity == "high"),
            "pending_tasks": len(tasks),
            "open_windows": int(
                self.session.scalar(select(func.count()).select_from(OpenSeminarWindow).where(OpenSeminarWindow.tenant_id == self.tenant.id)) or 0
            ),
            "active_kof_slots": int(
                self.session.scalar(
                    select(func.count()).select_from(SeminarSlotTemplate).where(
                        SeminarSlotTemplate.tenant_id == self.tenant.id,
                        SeminarSlotTemplate.active.is_(True),
                    )
                )
                or 0
            ),
            "speaker_visits": int(self.session.scalar(select(func.count()).select_from(TalkEvent)) or 0),
            "pending_evidence": int(self.session.scalar(select(func.count()).select_from(FactCandidate).where(FactCandidate.status == "pending")) or 0),
            "new_wishlist_alerts": int(
                self.session.scalar(
                    select(func.count()).select_from(WishlistAlert).where(WishlistAlert.tenant_id == self.tenant.id, WishlistAlert.status == "new")
                )
                or 0
            ),
            "anonymous_matches": int(
                self.session.scalar(
                    select(func.count())
                    .select_from(WishlistMatchGroup)
                    .where(
                        WishlistMatchGroup.status == "new",
                        WishlistMatchGroup.participants.any(WishlistMatchParticipant.tenant_id == self.tenant.id),
                    )
                )
                or 0
            ),
            "tour_assemblies_blocked": int(
                self.session.scalar(
                    select(func.count()).select_from(TourAssemblyProposal).where(
                        TourAssemblyProposal.tenant_id == self.tenant.id,
                        TourAssemblyProposal.status == "blocked",
                    )
                )
                or 0
            ),
            "drafts_waiting": int(
                self.session.scalar(
                    select(func.count()).select_from(OutreachDraft).where(
                        OutreachDraft.tenant_id == self.tenant.id,
                        OutreachDraft.status.in_(("draft", "reviewed")),
                    )
                )
                or 0
            ),
        }

    def _source_snapshot(self) -> dict[str, Any]:
        reliability = SourceReliabilityService().summarize(self.session)
        checked = [source for source in reliability if source.latest_checked_at]
        latest_checked_at = max((source.latest_checked_at for source in checked if source.latest_checked_at), default=None)
        latest_issues = [
            {
                "source_name": source.source_name,
                "status": source.latest_status,
                "reason": source.attention_reason or source.latest_error,
                "official_url": source.official_url,
            }
            for source in reliability
            if source.needs_attention
        ][:6]
        return {
            "last_sync_at": latest_checked_at,
            "sources_tracked": len(reliability),
            "sources_checked": len(checked),
            "sources_with_events": sum(1 for source in reliability if source.last_event_count > 0),
            "sources_needing_attention": sum(1 for source in reliability if source.needs_attention),
            "needs_adapter": sum(1 for source in reliability if source.needs_adapter),
            "total_events_last_check": sum(source.last_event_count for source in reliability),
            "latest_issues": latest_issues,
        }

    def _posture(self, tasks: list[OperatorTask]) -> tuple[str, str]:
        if any(task.severity == "high" for task in tasks):
            return "needs_attention", "Roadshow has high-priority blockers or high-value matches that deserve a quick admin decision."
        if tasks:
            return "ready_with_queue", "Roadshow is operational; work the queue when you have a few minutes."
        return "clear", "No operator tasks are currently waiting. The desk is clear."

    def _recent_changes(self) -> list[dict[str, Any]]:
        events = self.session.scalars(
            select(AuditEvent).where(AuditEvent.tenant_id == self.tenant.id).order_by(desc(AuditEvent.created_at)).limit(8)
        ).all()
        return [
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "payload": event.payload,
                "created_at": event.created_at,
            }
            for event in events
        ]

    def _task_payload(self, task: OperatorTask | None) -> dict[str, Any] | None:
        if task is None:
            return None
        payload = asdict(task)
        payload["primary_action"] = asdict(task.primary_action)
        payload["secondary_actions"] = [asdict(action) for action in task.secondary_actions]
        return payload


class MorningSweepRunner:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tenant = get_session_tenant(session)

    def run(self) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        steps = [
            self._run_step("source_audit", "Record data-source status", lambda: SourceAuditor().record(self.session)),
            self._run_step("kof_calendar", "Sync KOF occupied calendar", lambda: IngestionService(self.session).sync_host_calendar()),
            self._run_step("speaker_visits", "Find new speaker visits", lambda: IngestionService(self.session).ingest_sources()),
            self._run_step("repec_top_authors", "Sync RePEc top economists", lambda: BiographerPipeline(self.session).sync_top_authors(200)),
            self._run_step("repec_sync", "Sync RePEc identities", lambda: BiographerPipeline(self.session).sync_repec(None)),
            self._run_step("evidence_search", "Search trusted evidence", lambda: BiographerPipeline(self.session).search_trusted_evidence(None)),
            self._run_step("plausibility", "Check evidence plausibility", lambda: PlausibilityService(self.session).run()),
            self._run_step("availability", "Rebuild open KOF windows", lambda: AvailabilityBuilder(self.session).rebuild_persisted()),
            self._run_step("scoring", "Rescore Roadshow opportunities", lambda: Scorer(self.session).score_all_clusters()),
            self._run_step("wishlist_alerts", "Refresh KOF wishlist alerts", lambda: RoadshowService(self.session).refresh_wishlist_alerts()),
            self._run_step("wishlist_matches", "Refresh anonymous wishlist matches", lambda: TourAssemblyService(self.session).refresh_wishlist_matches()),
        ]
        status = "ok" if all(step.status == "ok" for step in steps) else "partial"
        RoadshowService(self.session).record_event(
            event_type="operator.real_sync",
            entity_type="operator",
            entity_id="real_sync",
            payload={"status": status, "steps": [asdict(step) for step in steps]},
        )
        finished_at = datetime.now(UTC)
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "steps": [asdict(step) for step in steps],
            "summary_metrics": {
                "processed_count": sum(step.processed_count for step in steps),
                "created_count": sum(step.created_count for step in steps),
                "updated_count": sum(step.updated_count for step in steps),
                "failed_steps": sum(1 for step in steps if step.status != "ok"),
            },
        }

    def _run_step(self, key: str, title: str, callback: Callable[[], Any]) -> MorningSweepStep:
        try:
            result = callback()
            self.session.flush()
            return self._success_step(key, title, result)
        except Exception as exc:  # pragma: no cover - live network/adapter failures are environment-specific
            return MorningSweepStep(
                key=key,
                title=title,
                status="error",
                detail=f"{title} failed. Continue with the remaining safe checks.",
                error=f"{type(exc).__name__}: {str(exc)[:400]}",
            )

    def _success_step(self, key: str, title: str, result: Any) -> MorningSweepStep:
        if hasattr(result, "source_counts"):
            source_counts = dict(result.source_counts)
            return MorningSweepStep(
                key=key,
                title=title,
                status="ok",
                detail=self._source_count_detail(source_counts),
                processed_count=sum(source_counts.values()),
                created_count=int(result.created_count),
                updated_count=int(result.updated_count),
                source_counts=source_counts,
            )
        if hasattr(result, "processed_count"):
            return MorningSweepStep(
                key=key,
                title=title,
                status="ok",
                detail=f"Processed {int(result.processed_count)} researcher record{'s' if int(result.processed_count) != 1 else ''}.",
                processed_count=int(result.processed_count),
                created_count=int(result.created_count),
                updated_count=int(result.updated_count),
            )
        if isinstance(result, list):
            return MorningSweepStep(
                key=key,
                title=title,
                status="ok",
                detail=f"Updated {len(result)} item{'s' if len(result) != 1 else ''}.",
                processed_count=len(result),
                created_count=len(result),
            )
        return MorningSweepStep(key=key, title=title, status="ok", detail="Step completed.")

    def _source_count_detail(self, counts: dict[str, int]) -> str:
        if not counts:
            return "No source counts were returned."
        return ", ".join(f"{source}: {count}" for source, count in counts.items())
