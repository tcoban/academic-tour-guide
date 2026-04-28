from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.entities import HostCalendarEvent, OpenSeminarWindow, OutreachDraft, Researcher, TripCluster
from app.services.enrichment import best_fact, best_fact_candidate
from app.services.logistics import CostSharingCalculator
from app.services.scoring import ensure_timezone


@dataclass(slots=True)
class SlotMatch:
    window: OpenSeminarWindow
    fit_type: str
    distance_days: int
    within_scoring_window: bool


class OpportunityWorkbench:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cost_sharing = CostSharingCalculator()

    def build(self, limit: int = 25) -> dict:
        windows = self.session.scalars(select(OpenSeminarWindow).order_by(OpenSeminarWindow.starts_at)).all()
        host_events = self.session.scalars(select(HostCalendarEvent).order_by(HostCalendarEvent.starts_at)).all()
        clusters = self.session.scalars(
            select(TripCluster)
            .options(
                selectinload(TripCluster.researcher).selectinload(Researcher.facts),
                selectinload(TripCluster.researcher).selectinload(Researcher.fact_candidates),
            )
            .order_by(desc(TripCluster.opportunity_score), TripCluster.start_date)
            .limit(limit)
        ).all()

        return {
            "opportunities": [self._opportunity_card(cluster, windows) for cluster in clusters if cluster.researcher],
            "open_windows": windows,
            "host_events": host_events,
        }

    def _opportunity_card(self, cluster: TripCluster, windows: list[OpenSeminarWindow]) -> dict:
        researcher = cluster.researcher
        match = self.best_window_for_cluster(cluster, windows)
        blockers = self._draft_blockers(researcher)
        existing_drafts = self.session.scalars(
            select(OutreachDraft).where(OutreachDraft.trip_cluster_id == cluster.id).order_by(desc(OutreachDraft.created_at))
        ).all()
        return {
            "cluster": cluster,
            "researcher": researcher,
            "best_window": self._match_payload(match) if match else None,
            "cost_share": self.cost_sharing.estimate(cluster, researcher, match.window if match else None),
            "itinerary_cities": [item["city"] for item in cluster.itinerary],
            "draft_ready": len(blockers) == 0,
            "draft_blockers": blockers,
            "draft_count": len(existing_drafts),
            "latest_draft_id": existing_drafts[0].id if existing_drafts else None,
            "latest_draft_template": (existing_drafts[0].metadata_json or {}).get("template_label") if existing_drafts else None,
        }

    def best_window_for_cluster(self, cluster: TripCluster, windows: list[OpenSeminarWindow] | None = None) -> SlotMatch | None:
        windows = windows if windows is not None else self.session.scalars(select(OpenSeminarWindow)).all()
        if not windows:
            return None

        matches = [self._slot_match(cluster, window) for window in windows]
        return min(
            matches,
            key=lambda match: (
                not match.within_scoring_window,
                match.distance_days,
                ensure_timezone(match.window.starts_at),
            ),
        )

    def _slot_match(self, cluster: TripCluster, window: OpenSeminarWindow) -> SlotMatch:
        tz = ZoneInfo(settings.default_timezone)
        cluster_start = datetime.combine(cluster.start_date, datetime.min.time(), tzinfo=tz)
        cluster_end = datetime.combine(cluster.end_date, datetime.max.time(), tzinfo=tz)
        window_start = ensure_timezone(window.starts_at)
        window_end = ensure_timezone(window.ends_at)

        if window_start <= cluster_end and window_end >= cluster_start:
            return SlotMatch(window=window, fit_type="overlap", distance_days=0, within_scoring_window=True)

        if window_start > cluster_end:
            distance_days = (window_start.date() - cluster.end_date).days
            fit_type = "after_trip"
        else:
            distance_days = (cluster.start_date - window_end.date()).days
            fit_type = "before_trip"

        return SlotMatch(
            window=window,
            fit_type=fit_type if distance_days > settings.slot_match_buffer_days else "nearby",
            distance_days=distance_days,
            within_scoring_window=distance_days <= settings.slot_match_buffer_days,
        )

    def _match_payload(self, match: SlotMatch) -> dict:
        return {
            "id": match.window.id,
            "starts_at": match.window.starts_at,
            "ends_at": match.window.ends_at,
            "source": match.window.source,
            "metadata_json": match.window.metadata_json,
            "fit_type": match.fit_type,
            "distance_days": match.distance_days,
            "within_scoring_window": match.within_scoring_window,
        }

    def _draft_blockers(self, researcher: Researcher) -> list[str]:
        blockers: list[str] = []
        for fact_type, label in [("phd_institution", "PhD institution"), ("nationality", "nationality")]:
            fact = best_fact(researcher, fact_type)
            if fact and fact.confidence >= settings.evidence_confidence_threshold:
                continue
            pending = best_fact_candidate(researcher, fact_type, statuses=("pending",))
            if pending:
                blockers.append(f"Approve pending {label}: {pending.value}")
            else:
                blockers.append(f"Add approved {label}")
        return blockers
