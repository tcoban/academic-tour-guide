from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.entities import HostCalendarEvent, OpenSeminarWindow, OutreachDraft, Researcher, TourLeg, TripCluster
from app.services.enrichment import best_fact, best_fact_candidate
from app.services.logistics import CostSharingCalculator
from app.services.autonomy import AutonomyEngine
from app.services.scoring import ensure_timezone
from app.services.travel_planning import TravelPlanner


@dataclass(slots=True)
class SlotMatch:
    window: OpenSeminarWindow
    fit_type: str
    distance_days: int
    within_scoring_window: bool
    travel_fit_score: int
    travel_fit_label: str
    travel_fit_summary: str
    travel_fit_severity: str
    planning_warnings: list[str]
    travel_fit: dict


class OpportunityWorkbench:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cost_sharing = CostSharingCalculator()
        self.travel_planner = TravelPlanner()

    def build(self, limit: int = 25) -> dict:
        windows = self.session.scalars(select(OpenSeminarWindow).order_by(OpenSeminarWindow.starts_at)).all()
        host_events = self.session.scalars(select(HostCalendarEvent).order_by(HostCalendarEvent.starts_at)).all()
        today = date.today()
        horizon = today + timedelta(days=settings.opportunity_horizon_days)
        clusters = self.session.scalars(
            select(TripCluster)
            .where(TripCluster.end_date >= today, TripCluster.start_date <= horizon)
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
        blocker_details = self._draft_blockers(researcher)
        existing_drafts = self.session.scalars(
            select(OutreachDraft).where(OutreachDraft.trip_cluster_id == cluster.id).order_by(desc(OutreachDraft.created_at))
        ).all()
        existing_tour_legs = self.session.scalars(
            select(TourLeg).where(TourLeg.trip_cluster_id == cluster.id).order_by(desc(TourLeg.created_at))
        ).all()
        route_review_required = bool(match and match.travel_fit_severity in {"review", "risky"})
        route_review_resolved = bool(route_review_required and existing_tour_legs)
        return {
            "cluster": cluster,
            "researcher": researcher,
            "best_window": self._match_payload(match) if match else None,
            "cost_share": self.cost_sharing.estimate(cluster, researcher, match.window if match else None),
            "itinerary_cities": [item["city"] for item in cluster.itinerary],
            "draft_ready": len(blocker_details) == 0,
            "draft_blockers": [blocker["message"] for blocker in blocker_details],
            "draft_blocker_details": blocker_details,
            "draft_count": len(existing_drafts),
            "latest_draft_id": existing_drafts[0].id if existing_drafts else None,
            "latest_draft_template": (existing_drafts[0].metadata_json or {}).get("template_label") if existing_drafts else None,
            "tour_leg_count": len(existing_tour_legs),
            "latest_tour_leg_id": existing_tour_legs[0].id if existing_tour_legs else None,
            "route_review_required": route_review_required,
            "route_review_resolved": route_review_resolved,
            "route_review_action": self._route_review_action(cluster, match, existing_tour_legs),
            "automation_assessment": AutonomyEngine(self.session).assess_opportunity(
                cluster,
                researcher,
                match,
                blocker_details,
                existing_tour_legs,
            ),
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
                -match.travel_fit_score,
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
            fit_type = "overlap"
            distance_days = 0
            within_scoring_window = True
        elif window_start > cluster_end:
            distance_days = (window_start.date() - cluster.end_date).days
            fit_type = "after_trip"
            within_scoring_window = distance_days <= settings.slot_match_buffer_days
        else:
            distance_days = (cluster.start_date - window_end.date()).days
            fit_type = "before_trip"
            within_scoring_window = distance_days <= settings.slot_match_buffer_days

        if fit_type != "overlap" and distance_days <= settings.slot_match_buffer_days:
            fit_type = "nearby"

        researcher = cluster.researcher or self.session.get(Researcher, cluster.researcher_id)
        travel_fit = (
            self.travel_planner.assess_slot(cluster, researcher, window)
            if researcher
            else None
        )
        return SlotMatch(
            window=window,
            fit_type=fit_type,
            distance_days=distance_days,
            within_scoring_window=within_scoring_window,
            travel_fit_score=travel_fit.score if travel_fit else 0,
            travel_fit_label=travel_fit.label if travel_fit else "Route review advised",
            travel_fit_summary=travel_fit.summary if travel_fit else "No researcher profile is attached for route planning.",
            travel_fit_severity=travel_fit.severity if travel_fit else "review",
            planning_warnings=travel_fit.warnings if travel_fit else ["Missing researcher route context"],
            travel_fit=travel_fit.to_dict() if travel_fit else {},
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
            "travel_fit_score": match.travel_fit_score,
            "travel_fit_label": match.travel_fit_label,
            "travel_fit_summary": match.travel_fit_summary,
            "travel_fit_severity": match.travel_fit_severity,
            "planning_warnings": match.planning_warnings,
            "travel_fit": match.travel_fit,
        }

    def _route_review_action(self, cluster: TripCluster, match: SlotMatch | None, tour_legs: list[TourLeg]) -> dict | None:
        if not match or match.travel_fit_severity not in {"review", "risky"}:
            return None
        if tour_legs:
            return {
                "label": "Open route review",
                "href": f"/tour-legs/{tour_legs[0].id}",
                "action_key": "open_tour_leg",
                "explanation": "A route and cost-split review already exists for this opportunity.",
                "disabled_reason": None,
            }
        return {
            "label": "Review route and cost split",
            "href": None,
            "action_key": "propose_tour_leg",
            "trip_cluster_id": cluster.id,
            "explanation": "Builds a tour-leg review with ordered stops, route sanity, and deterministic logistics.",
            "disabled_reason": None,
        }

    def _draft_blockers(self, researcher: Researcher) -> list[dict]:
        blockers: list[dict] = []
        for fact_type, label in [("phd_institution", "PhD institution"), ("nationality", "nationality")]:
            fact = best_fact(researcher, fact_type)
            if fact and fact.confidence >= settings.evidence_confidence_threshold:
                continue
            pending = best_fact_candidate(researcher, fact_type, statuses=("pending",))
            if pending:
                blockers.append(
                    {
                        "code": "pending_fact_review",
                        "fact_type": fact_type,
                        "label": label,
                        "message": f"Approve pending {label}: {pending.value}",
                        "action_label": f"Approve {label} evidence",
                        "action_href": f"/review?status=pending&fact_type={fact_type}&researcher_id={researcher.id}",
                        "pending_candidate_id": pending.id,
                    }
                )
            else:
                blockers.append(
                    {
                        "code": "missing_approved_fact",
                        "fact_type": fact_type,
                        "label": label,
                        "message": f"Add approved {label}",
                        "action_label": f"Add approved {label}",
                        "action_href": f"/researchers/{researcher.id}?missing_fact={fact_type}#manual-facts",
                        "pending_candidate_id": None,
                    }
                )
        return blockers
