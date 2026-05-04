from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Researcher, TourLeg, TripCluster
from app.services.enrichment import best_fact, best_fact_candidate
from app.services.tenancy import get_session_tenant


@dataclass(slots=True)
class AutonomySignal:
    label: str
    status: str
    confidence: int
    detail: str
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AutonomyAction:
    label: str
    consequence: str
    href: str | None = None
    action_key: str | None = None
    disabled_reason: str | None = None


@dataclass(slots=True)
class AutonomyAssessment:
    level: str
    score: int
    summary: str
    can_prepare_draft: bool
    can_build_tour_leg: bool
    can_search_evidence: bool
    can_refresh_prices: bool
    requires_human_approval: bool
    signals: list[AutonomySignal]
    next_action: AutonomyAction
    moonshot_actions: list[AutonomyAction]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "score": self.score,
            "summary": self.summary,
            "can_prepare_draft": self.can_prepare_draft,
            "can_build_tour_leg": self.can_build_tour_leg,
            "can_search_evidence": self.can_search_evidence,
            "can_refresh_prices": self.can_refresh_prices,
            "requires_human_approval": self.requires_human_approval,
            "signals": [asdict(signal) for signal in self.signals],
            "next_action": asdict(self.next_action),
            "moonshot_actions": [asdict(action) for action in self.moonshot_actions],
        }


class AutonomyEngine:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tenant = get_session_tenant(session)

    def assess_opportunity(
        self,
        cluster: TripCluster,
        researcher: Researcher,
        match: Any | None,
        blocker_details: list[dict[str, Any]],
        existing_tour_legs: list[TourLeg],
    ) -> dict[str, Any]:
        signals: list[AutonomySignal] = []
        signals.append(self._evidence_signal(researcher, blocker_details))
        signals.append(self._slot_signal(match))
        signals.append(self._route_signal(match, existing_tour_legs))
        signals.append(self._research_fit_signal(cluster))
        signals.append(self._prestige_signal(cluster, researcher))
        signals.append(self._price_signal(existing_tour_legs))

        score = round(sum(signal.confidence for signal in signals) / max(1, len(signals)))
        has_human_gate = any(signal.status in {"approval_required", "blocked", "review"} for signal in signals)
        can_refresh_prices = self._price_refresh_needed(existing_tour_legs)
        can_prepare_draft = (
            not blocker_details
            and bool(match)
            and self._route_allows_draft(match, existing_tour_legs)
            and not can_refresh_prices
        )
        can_build_tour_leg = bool(match) and not existing_tour_legs
        can_search_evidence = any(blocker.get("code") == "missing_approved_fact" for blocker in blocker_details)

        if can_search_evidence:
            level = "ai_research_needed"
            summary = "Roadshow should run trusted-source evidence discovery before outreach is safe."
            next_action = AutonomyAction(
                label="Search trusted evidence",
                consequence="Search RePEc Genealogy, ORCID, CEPR, institution profiles, and CV links; return fact candidates for review.",
                action_key="evidence_search",
            )
        elif can_build_tour_leg:
            level = "assisted_autopilot"
            summary = "Roadshow can build the route and price review automatically, then decide whether the draft can be prepared."
            next_action = AutonomyAction(
                label="Build route and cost review",
                consequence="Create an ordered tour leg with route sanity, rest-day logic, first-class fare checks, and internal logistics estimates.",
                action_key="propose_tour_leg",
            )
        elif can_refresh_prices:
            level = "assisted_autopilot"
            summary = "Roadshow has a route review, but older or incomplete fare evidence should be refreshed before drafting."
            next_action = AutonomyAction(
                label="Check first-class fares",
                consequence="Refresh authorized fare providers and conservative fallback estimates for the existing tour leg.",
                action_key="refresh_prices",
            )
        elif can_prepare_draft:
            level = "autopilot_ready" if score >= 82 else "assisted_autopilot"
            summary = "Roadshow can prepare the KOF invitation draft; human review still signs off before manual sending."
            next_action = AutonomyAction(
                label="Create KOF invitation draft",
                consequence="Generate one professional KOF invitation with approved facts and the selected slot; keep all logistics internal.",
                action_key="create_draft",
            )
        else:
            level = "human_gate"
            summary = "Roadshow has useful signals, but at least one approval, slot, route, or price gate still needs an operator decision."
            next_action = self._human_gate_action(researcher, blocker_details, match, existing_tour_legs)

        assessment = AutonomyAssessment(
            level=level,
            score=score,
            summary=summary,
            can_prepare_draft=can_prepare_draft,
            can_build_tour_leg=can_build_tour_leg,
            can_search_evidence=can_search_evidence,
            can_refresh_prices=can_refresh_prices,
            requires_human_approval=has_human_gate or can_prepare_draft,
            signals=signals,
            next_action=next_action,
            moonshot_actions=self._moonshot_actions(researcher, cluster, match, blocker_details, existing_tour_legs),
        )
        return assessment.to_dict()

    def _evidence_signal(self, researcher: Researcher, blocker_details: list[dict[str, Any]]) -> AutonomySignal:
        approved = []
        pending = []
        missing = []
        for fact_type in ("phd_institution", "nationality"):
            fact = best_fact(researcher, fact_type, tenant_id=self.tenant.id)
            candidate = best_fact_candidate(researcher, fact_type, statuses=("pending",))
            if fact and fact.confidence >= settings.evidence_confidence_threshold:
                approved.append(f"{fact_type}: {fact.value}")
            elif candidate:
                pending.append(f"{fact_type}: {candidate.value}")
            else:
                missing.append(fact_type)
        if not blocker_details:
            return AutonomySignal("Approved evidence", "ready", 95, "Required biographic hooks are approved.", approved)
        if pending and not missing:
            return AutonomySignal("Evidence candidates", "approval_required", 68, "AI can rank candidates, but outreach needs approval.", pending)
        return AutonomySignal("Evidence discovery", "blocked", 35, "Trusted-source evidence is missing before outreach.", missing)

    def _slot_signal(self, match: Any | None) -> AutonomySignal:
        if not match:
            return AutonomySignal("KOF slot fit", "blocked", 15, "No open KOF slot is available.")
        if match.within_scoring_window:
            return AutonomySignal("KOF slot fit", "ready", 90, f"{match.fit_type} slot selected within the planning window.")
        return AutonomySignal("KOF slot fit", "review", 55, "A slot exists, but it is outside the scoring window.")

    def _route_signal(self, match: Any | None, existing_tour_legs: list[TourLeg]) -> AutonomySignal:
        if not match:
            return AutonomySignal("Route logic", "blocked", 20, "Route quality cannot be assessed without a candidate slot.")
        if match.travel_fit_severity in {"strong", "good"}:
            return AutonomySignal("Route logic", "ready", 88, match.travel_fit_summary or "Route looks plausible.")
        if existing_tour_legs:
            return AutonomySignal("Route logic", "reviewed", 76, "A route review exists for this warning.")
        return AutonomySignal("Route logic", "review", 48, match.travel_fit_summary or "Planner flagged a route issue.")

    def _research_fit_signal(self, cluster: TripCluster) -> AutonomySignal:
        fit = next((item for item in cluster.rationale or [] if item.get("label") == "KOF Research Fit"), None)
        if fit:
            return AutonomySignal("KOF research fit", "ready", 82, str(fit.get("detail") or "KOF topic match found."))
        return AutonomySignal("KOF research fit", "weak_signal", 45, "No deterministic KOF research-topic match is attached yet.")

    def _prestige_signal(self, cluster: TripCluster, researcher: Researcher) -> AutonomySignal:
        superstar = next((item for item in cluster.rationale or [] if item.get("label") == "Superstar Priority"), None)
        if superstar:
            return AutonomySignal("Academic priority", "ready", 90, str(superstar.get("detail") or "Top economist signal found."))
        if researcher.repec_rank is not None:
            return AutonomySignal("Academic priority", "ready", 70, f"RePEc percentile signal: {researcher.repec_rank}.")
        return AutonomySignal("Academic priority", "unknown", 45, "No RePEc/top-economist signal is attached yet.")

    def _price_signal(self, existing_tour_legs: list[TourLeg]) -> AutonomySignal:
        if not existing_tour_legs:
            return AutonomySignal("Fare and cost confidence", "review", 50, "No tour-leg price review exists yet.")
        components = self._rail_components(existing_tour_legs)
        if self._price_refresh_needed(existing_tour_legs):
            return AutonomySignal("Fare and cost confidence", "review", 48, "A tour leg exists, but rail fare evidence has not been checked yet.")
        statuses = {str(component.get("price_status") or "") for component in components}
        if statuses and statuses <= {"live", "cached"}:
            return AutonomySignal("Fare and cost confidence", "ready", 85, "Rail components have live or cached fare evidence.")
        if "estimate_requires_review" in statuses:
            return AutonomySignal("Fare and cost confidence", "reviewed_estimate", 72, "First-class fare checks were attempted; at least one leg still uses a conservative review estimate.")
        return AutonomySignal("Fare and cost confidence", "reviewed_estimate", 68, "Cost split exists with internal fare provenance, but no live provider returned a final fare.")

    def _rail_components(self, existing_tour_legs: list[TourLeg]) -> list[dict[str, Any]]:
        if not existing_tour_legs:
            return []
        components = list((existing_tour_legs[0].cost_split_json or {}).get("components") or [])
        return [
            dict(component)
            for component in components
            if component.get("category") != "zurich_hospitality"
            and str(component.get("mode") or "").lower() in {"rail", "train", "public_transport"}
        ]

    def _price_refresh_needed(self, existing_tour_legs: list[TourLeg]) -> bool:
        components = self._rail_components(existing_tour_legs)
        if not components:
            return False
        unchecked_statuses = {"", "failed", "not_rail_priced", "pending", "manual_review"}
        for component in components:
            status = str(component.get("price_status") or "")
            if status in unchecked_statuses:
                return True
            if not component.get("last_checked_at") and not component.get("price_check_id"):
                return True
        return False

    def _route_allows_draft(self, match: Any | None, existing_tour_legs: list[TourLeg]) -> bool:
        if not match:
            return False
        return bool(existing_tour_legs)

    def _human_gate_action(
        self,
        researcher: Researcher,
        blocker_details: list[dict[str, Any]],
        match: Any | None,
        existing_tour_legs: list[TourLeg],
    ) -> AutonomyAction:
        if blocker_details:
            first = blocker_details[0]
            return AutonomyAction(
                label=str(first.get("action_label") or "Resolve evidence"),
                consequence=str(first.get("message") or "Resolve the evidence blocker before outreach."),
                href=str(first.get("action_href") or f"/researchers/{researcher.id}"),
            )
        if match and not existing_tour_legs and match.travel_fit_severity in {"review", "risky"}:
            return AutonomyAction(
                label="Review route and cost split",
                consequence="Build the route review before deciding whether the slot is humane enough for outreach.",
                action_key="propose_tour_leg",
            )
        if self._price_refresh_needed(existing_tour_legs):
            return AutonomyAction(
                label="Check first-class fares",
                consequence="Refresh fare evidence for the existing route review before drafting.",
                action_key="refresh_prices",
            )
        return AutonomyAction(
            label="Inspect opportunity",
            consequence="Open the opportunity card and resolve the remaining human gate.",
            href="/opportunities",
        )

    def _moonshot_actions(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        match: Any | None,
        blocker_details: list[dict[str, Any]],
        existing_tour_legs: list[TourLeg],
    ) -> list[AutonomyAction]:
        actions: list[AutonomyAction] = []
        if any(blocker.get("code") == "missing_approved_fact" for blocker in blocker_details):
            actions.append(
                AutonomyAction(
                    label="AI-search trusted bios",
                    consequence="Try institution profiles, RePEc Genealogy, ORCID, CEPR, and CV links; return evidence candidates, not final facts.",
                    action_key="evidence_search",
                )
            )
        if match and not existing_tour_legs:
            actions.append(
                AutonomyAction(
                    label="AI-plan humane route",
                    consequence="Generate a Zurich insertion with rest-day, order-of-stops, and first-class fare checks before drafting.",
                    action_key="propose_tour_leg",
                )
            )
        if self._price_refresh_needed(existing_tour_legs):
            actions.append(
                AutonomyAction(
                    label="Refresh first-class fares",
                    consequence="Re-check authorized fare providers and update internal price provenance for the tour leg.",
                    action_key="refresh_prices",
                )
            )
        if cluster.opportunity_score >= 100:
            actions.append(
                AutonomyAction(
                    label="Escalate superstar opportunity",
                    consequence="Treat this as a high-investment target and allow broader slot search plus stronger manual follow-up.",
                    href="/opportunities",
                )
            )
        actions.append(
            AutonomyAction(
                label="Learn from outcome",
                consequence="After the seminar decision, feed acceptance/decline and feedback signals back into future ranking.",
                href="/tour-legs" if existing_tour_legs else "/opportunities",
            )
        )
        return actions
