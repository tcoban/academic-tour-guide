from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import asc, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.entities import (
    AuditEvent,
    BusinessCaseResult,
    BusinessCaseRun,
    OpenSeminarWindow,
    Researcher,
    ResearcherIdentity,
    TalkEvent,
    TourLeg,
    TripCluster,
)
from app.services.enrichment import Biographer, BiographerPipeline, best_fact, best_fact_candidate, normalize_name
from app.services.opportunities import OpportunityWorkbench
from app.services.outreach import DraftGenerator, ReviewRequiredError
from app.services.plausibility import PlausibilityService, speaker_name_quality_flags
from app.services.roadshow import RoadshowService
from app.services.scoring import Scorer


@dataclass(slots=True)
class BusinessCaseSpec:
    key: str
    display_name: str
    target_name: str
    home_institution_hint: str | None = None
    route_scenario: str | None = None
    expected_superstar: bool = False
    negative_control: bool = False


CASE_SPECS = [
    BusinessCaseSpec(
        key="mirko_wiederholt",
        display_name="Mirko Wiederholt",
        target_name="Mirko Wiederholt",
        home_institution_hint="Ludwig-Maximilians University of Munich",
        route_scenario="munich_zurich_milan",
    ),
    BusinessCaseSpec(
        key="rahul_deb",
        display_name="Rahul Deb",
        target_name="Rahul Deb",
        home_institution_hint="Boston University",
        route_scenario="bonn_zurich_milan",
    ),
    BusinessCaseSpec(
        key="daron_acemoglu",
        display_name="Daron Acemoglu",
        target_name="Daron Acemoglu",
        home_institution_hint="MIT",
        expected_superstar=True,
    ),
    BusinessCaseSpec(
        key="negative_control:auto_selected_from_real_sources",
        display_name="Negative control from real sources",
        target_name="auto-selected",
        negative_control=True,
    ),
]

MONEY_TERMS = ("CHF", "cost", "fare", "savings", "cost-sharing")
EUROPE_VISIT_TERMS = ("scheduled to be in Europe", "your European visit", "your European trip")


class BusinessCaseService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run_shadow_audit(self) -> BusinessCaseRun:
        run = BusinessCaseRun(mode="shadow", status="running", started_at=datetime.now(UTC), summary_json={})
        self.session.add(run)
        self.session.flush()

        results: list[BusinessCaseResult] = []
        try:
            for spec in CASE_SPECS:
                payload = self._evaluate_case_in_shadow(spec)
                result = BusinessCaseResult(run_id=run.id, **payload)
                self.session.add(result)
                results.append(result)

            summary = self._summarize(results)
            run.status = "completed" if not summary["failing_cases"] else "completed_with_blockers"
            run.summary_json = summary
        except Exception as error:  # pragma: no cover - preserves an audit record for unexpected provider issues
            run.status = "failed"
            run.error = str(error)
            run.summary_json = {"error": str(error)}
        finally:
            run.finished_at = datetime.now(UTC)
            self.session.add(
                AuditEvent(
                    event_type="business_case.shadow_audit",
                    actor_type="system",
                    entity_type="business_case_run",
                    entity_id=run.id,
                    payload={"status": run.status, "summary": run.summary_json},
                )
            )
            self.session.flush()
        return run

    def _evaluate_case_in_shadow(self, spec: BusinessCaseSpec) -> dict[str, Any]:
        shadow = self.session.begin_nested()
        try:
            payload = self._evaluate_case(spec)
        except Exception as error:
            payload = self._error_payload(spec, error)
        finally:
            shadow.rollback()
            self.session.expire_all()
        return payload

    def _evaluate_case(self, spec: BusinessCaseSpec) -> dict[str, Any]:
        researcher, cluster, scenario_used, researcher_was_existing = self._prepare_case_graph(spec)
        if not researcher:
            return self._not_found_payload(spec, "No matching real source record was available for the negative-control case.")

        self._run_shadow_pipeline(researcher, spec)
        PlausibilityService(self.session).run()
        self.session.flush()

        cluster = self._best_case_cluster(researcher, spec, existing=cluster)
        score = 0
        if cluster:
            score = Scorer(self.session).score_cluster(cluster, researcher).score

        workbench = OpportunityWorkbench(self.session)
        match = workbench.best_window_for_cluster(cluster) if cluster else None
        route_summary = self._route_summary(cluster, match, scenario_used)
        fit_summary = self._fit_summary(researcher, cluster, score)
        evidence_summary = self._evidence_summary(researcher)
        price_summary = self._price_summary(cluster)
        draft_gate = self._draft_gate(researcher, cluster, match, route_summary, evidence_summary)
        blockers = self._blockers(spec, researcher, cluster, fit_summary, route_summary, evidence_summary, price_summary, draft_gate)
        verdict = self._verdict(spec, researcher, cluster, fit_summary, route_summary, evidence_summary, draft_gate, blockers)

        return {
            "researcher_id": researcher.id if researcher_was_existing else None,
            "case_key": spec.key,
            "display_name": spec.display_name,
            "target_name": researcher.name,
            "verdict": verdict,
            "score": score,
            "data_found": True,
            "kof_fit_status": fit_summary["status"],
            "route_status": route_summary["status"],
            "evidence_status": evidence_summary["status"],
            "draft_status": draft_gate["status"],
            "price_status": price_summary["status"],
            "evidence_summary_json": evidence_summary,
            "fit_summary_json": fit_summary,
            "route_summary_json": route_summary,
            "price_summary_json": price_summary,
            "draft_gate_json": draft_gate,
            "blockers": blockers,
            "source_links_json": self._source_links(researcher),
            "metadata_json": {
                "mode": "shadow",
                "scenario_used": scenario_used,
                "normal_records_created": False,
                "case_expectations": {
                    "expected_superstar": spec.expected_superstar,
                    "negative_control": spec.negative_control,
                },
            },
        }

    def _prepare_case_graph(self, spec: BusinessCaseSpec) -> tuple[Researcher | None, TripCluster | None, bool, bool]:
        if spec.negative_control:
            researcher, cluster, scenario_used = self._negative_control_case()
            return researcher, cluster, scenario_used, bool(researcher)

        researcher = self._find_researcher(spec.target_name)
        researcher_was_existing = bool(researcher)
        if not researcher:
            researcher = Biographer(self.session).get_or_create_researcher(
                spec.target_name,
                home_institution=spec.home_institution_hint,
            )
        elif spec.home_institution_hint and not researcher.home_institution:
            researcher.home_institution = spec.home_institution_hint

        cluster = self._best_case_cluster(researcher, spec)
        scenario_used = False
        if not cluster and spec.route_scenario:
            cluster = self._build_scenario_cluster(researcher, spec)
            scenario_used = True
        elif spec.route_scenario:
            self._add_scenario_windows(spec)
            scenario_used = True
        return researcher, cluster, scenario_used, researcher_was_existing

    def _negative_control_case(self) -> tuple[Researcher | None, TripCluster | None, bool]:
        clusters = self.session.scalars(
            select(TripCluster)
            .options(selectinload(TripCluster.researcher))
            .order_by(asc(TripCluster.opportunity_score), asc(TripCluster.start_date))
        ).all()
        for cluster in clusters:
            if not cluster.researcher:
                continue
            rationale_labels = {str(item.get("label") or "") for item in cluster.rationale or []}
            if "KOF Research Fit" not in rationale_labels and "Superstar Priority" not in rationale_labels:
                return cluster.researcher, cluster, False
        return None, None, False

    def _run_shadow_pipeline(self, researcher: Researcher, spec: BusinessCaseSpec) -> None:
        pipeline = BiographerPipeline(self.session)
        if spec.expected_superstar:
            pipeline.sync_top_authors(limit=200)
        pipeline.sync_repec(researcher.id)
        pipeline.search_trusted_evidence(researcher.id)

    def _find_researcher(self, name: str) -> Researcher | None:
        return self.session.scalar(
            select(Researcher)
            .where(Researcher.normalized_name == normalize_name(name))
            .options(
                selectinload(Researcher.facts),
                selectinload(Researcher.fact_candidates),
                selectinload(Researcher.identities),
                selectinload(Researcher.documents),
                selectinload(Researcher.talk_events),
                selectinload(Researcher.trip_clusters),
            )
        )

    def _best_case_cluster(
        self,
        researcher: Researcher,
        spec: BusinessCaseSpec,
        existing: TripCluster | None = None,
    ) -> TripCluster | None:
        if existing:
            return existing
        clusters = sorted(researcher.trip_clusters, key=lambda item: (-item.opportunity_score, item.start_date))
        if not clusters:
            return None
        if spec.route_scenario == "bonn_zurich_milan":
            for cluster in clusters:
                cities = [str(item.get("city") or "").lower() for item in cluster.itinerary or []]
                if "bonn" in cities and "milan" in cities:
                    return cluster
        if spec.route_scenario == "munich_zurich_milan":
            for cluster in clusters:
                cities = [str(item.get("city") or "").lower() for item in cluster.itinerary or []]
                if "milan" in cities:
                    return cluster
        return clusters[0]

    def _build_scenario_cluster(self, researcher: Researcher, spec: BusinessCaseSpec) -> TripCluster:
        tz = ZoneInfo(settings.default_timezone)
        if spec.route_scenario == "bonn_zurich_milan":
            itinerary = [
                {
                    "city": "Bonn",
                    "country": "Germany",
                    "starts_at": datetime(2026, 5, 13, 16, 0, tzinfo=tz).isoformat(),
                    "title": "Bonn seminar",
                    "url": "shadow://business-case/rahul-deb/bonn",
                    "source_name": "business_case_shadow",
                },
                {
                    "city": "Milan",
                    "country": "Italy",
                    "starts_at": datetime(2026, 5, 19, 16, 0, tzinfo=tz).isoformat(),
                    "title": "Bocconi seminar",
                    "url": "shadow://business-case/rahul-deb/milan",
                    "source_name": "business_case_shadow",
                },
            ]
            start_date = date(2026, 5, 13)
            end_date = date(2026, 5, 19)
        else:
            itinerary = [
                {
                    "city": "Milan",
                    "country": "Italy",
                    "starts_at": datetime(2026, 5, 12, 16, 0, tzinfo=tz).isoformat(),
                    "title": "Bocconi macro seminar",
                    "url": "shadow://business-case/mirko-wiederholt/milan",
                    "source_name": "business_case_shadow",
                }
            ]
            start_date = date(2026, 5, 12)
            end_date = date(2026, 5, 12)
        cluster = TripCluster(
            researcher=researcher,
            start_date=start_date,
            end_date=end_date,
            itinerary=itinerary,
            opportunity_score=0,
            rationale=[],
        )
        self.session.add(cluster)
        self.session.flush()
        self._add_scenario_windows(spec)
        return cluster

    def _add_scenario_windows(self, spec: BusinessCaseSpec) -> None:
        tz = ZoneInfo(settings.default_timezone)
        windows = []
        if spec.route_scenario == "bonn_zurich_milan":
            windows = [
                datetime(2026, 5, 12, 16, 15, tzinfo=tz),
                datetime(2026, 5, 16, 16, 15, tzinfo=tz),
            ]
        elif spec.route_scenario == "munich_zurich_milan":
            windows = [datetime(2026, 5, 11, 16, 15, tzinfo=tz)]
        for starts_at in windows:
            self.session.add(
                OpenSeminarWindow(
                    starts_at=starts_at,
                    ends_at=datetime.combine(starts_at.date(), time(17, 30), tzinfo=tz),
                    source="business_case_shadow",
                    metadata_json={"label": f"Business case slot for {spec.display_name}"},
                )
            )
        self.session.flush()

    def _evidence_summary(self, researcher: Researcher) -> dict[str, Any]:
        approved = [
            {
                "fact_type": fact.fact_type,
                "value": fact.value,
                "confidence": fact.confidence,
                "source_url": fact.source_url,
            }
            for fact in researcher.facts
        ]
        pending = [
            {
                "fact_type": candidate.fact_type,
                "value": candidate.value,
                "confidence": candidate.confidence,
                "source_url": candidate.source_url,
                "status": candidate.status,
                "review_note": candidate.review_note,
            }
            for candidate in researcher.fact_candidates
            if candidate.status == "pending"
        ]
        required = {
            "phd_institution": bool(best_fact(researcher, "phd_institution")),
            "nationality": bool(best_fact(researcher, "nationality")),
        }
        if all(required.values()):
            status = "approved"
        elif pending:
            status = "pending_review"
        else:
            status = "missing"
        return {
            "status": status,
            "approved_required_facts": required,
            "approved_fact_count": len(approved),
            "pending_candidate_count": len(pending),
            "documents_checked": len(researcher.documents),
            "identities_checked": len(researcher.identities),
            "approved_facts": approved,
            "pending_candidates": pending,
        }

    def _fit_summary(self, researcher: Researcher, cluster: TripCluster | None, score: int) -> dict[str, Any]:
        rationale = list(cluster.rationale or []) if cluster else []
        labels = {str(item.get("label") or "") for item in rationale}
        repec_rank = self._best_repec_rank(researcher)
        superstar = "Superstar Priority" in labels or (repec_rank is not None and repec_rank <= 200)
        research_fit = next((item for item in rationale if item.get("label") == "KOF Research Fit"), None)
        if research_fit and superstar:
            status = "strong"
        elif research_fit or superstar:
            status = "medium"
        else:
            status = "weak"
        return {
            "status": status,
            "score": score,
            "rationale": rationale,
            "matched_kof_research_fit": research_fit,
            "superstar_priority": superstar,
            "best_repec_rank": repec_rank,
            "repec_identities": [
                {
                    "external_id": identity.external_id,
                    "canonical_name": identity.canonical_name,
                    "profile_url": identity.profile_url,
                    "ranking_label": identity.ranking_label,
                    "metadata_json": identity.metadata_json,
                }
                for identity in researcher.identities
                if identity.provider == "repec"
            ],
        }

    def _route_summary(self, cluster: TripCluster | None, match, scenario_used: bool) -> dict[str, Any]:
        if not cluster:
            return {"status": "no_current_trip", "scenario_used": scenario_used}
        if not match:
            return {
                "status": "no_kof_slot",
                "scenario_used": scenario_used,
                "itinerary": cluster.itinerary,
                "start_date": cluster.start_date.isoformat(),
                "end_date": cluster.end_date.isoformat(),
            }
        travel_fit = match.travel_fit or {}
        severity = match.travel_fit_severity
        status = "plausible" if severity in {"strong", "good"} else "needs_route_review" if severity == "review" else "risky"
        return {
            "status": status,
            "scenario_used": scenario_used,
            "itinerary": cluster.itinerary,
            "best_window": {
                "id": match.window.id,
                "starts_at": match.window.starts_at.isoformat(),
                "ends_at": match.window.ends_at.isoformat(),
                "source": match.window.source,
                "fit_type": match.fit_type,
                "distance_days": match.distance_days,
            },
            "travel_fit": travel_fit,
            "planning_warnings": match.planning_warnings,
        }

    def _price_summary(self, cluster: TripCluster | None) -> dict[str, Any]:
        if not cluster:
            return {"status": "not_checked", "components": []}
        try:
            tour_leg = RoadshowService(self.session).propose_tour_leg(cluster)
        except ValueError as error:
            return {"status": "failed", "error": str(error), "components": []}
        components = list((tour_leg.cost_split_json or {}).get("components") or [])
        statuses = {str(component.get("price_status") or "") for component in components if component.get("price_status")}
        if "failed" in statuses:
            status = "failed"
        elif "estimate_requires_review" in statuses:
            status = "estimate_requires_review"
        elif {"live", "cached"} & statuses:
            status = "checked"
        else:
            status = "hospitality_or_not_checked"
        return {
            "status": status,
            "tour_leg_title": tour_leg.title,
            "estimated_travel_total_chf": tour_leg.estimated_travel_total_chf,
            "estimated_fee_total_chf": tour_leg.estimated_fee_total_chf,
            "cost_split": tour_leg.cost_split_json,
            "stops": [
                {
                    "city": stop.city,
                    "sequence": stop.sequence,
                    "format": stop.format,
                    "travel_share_chf": stop.travel_share_chf,
                }
                for stop in tour_leg.stops
            ],
            "components": components,
        }

    def _draft_gate(
        self,
        researcher: Researcher,
        cluster: TripCluster | None,
        match,
        route_summary: dict[str, Any],
        evidence_summary: dict[str, Any],
    ) -> dict[str, Any]:
        if not cluster:
            return {"status": "blocked", "reason": "No current trip cluster is available."}
        if not match:
            return {"status": "blocked", "reason": "No KOF slot is attached."}
        if route_summary["status"] == "risky":
            return {"status": "blocked", "reason": "Route-rest logic is too risky for an invitation draft."}
        if evidence_summary["status"] != "approved":
            return {
                "status": "blocked_preview",
                "reason": "Approved PhD institution and nationality facts are required before creating a sendable draft.",
                "missing_required_facts": [
                    fact_type
                    for fact_type, ready in evidence_summary["approved_required_facts"].items()
                    if not ready
                ],
            }
        try:
            draft = DraftGenerator(self.session).generate(researcher, cluster)
        except ReviewRequiredError as error:
            return {"status": "blocked_preview", "reason": str(error)}

        body = draft.body or ""
        copy_blockers = []
        if any(term.lower() in body.lower() for term in MONEY_TERMS):
            copy_blockers.append("Draft body contains internal money or fare language.")
        if self._is_europe_based(researcher) and any(term.lower() in body.lower() for term in EUROPE_VISIT_TERMS):
            copy_blockers.append("Draft body uses Europe-visit wording for a Europe-based speaker.")
        if copy_blockers:
            return {
                "status": "blocked_copy_review",
                "reason": "Draft copy failed business-case language checks.",
                "copy_blockers": copy_blockers,
                "subject_preview": draft.subject,
            }
        return {
            "status": "allowed_shadow_preview",
            "subject_preview": draft.subject,
            "body_preview": body,
            "candidate_slot": (draft.metadata_json or {}).get("candidate_slot"),
            "send_brief": (draft.metadata_json or {}).get("send_brief") or [],
        }

    def _blockers(
        self,
        spec: BusinessCaseSpec,
        researcher: Researcher,
        cluster: TripCluster | None,
        fit_summary: dict[str, Any],
        route_summary: dict[str, Any],
        evidence_summary: dict[str, Any],
        price_summary: dict[str, Any],
        draft_gate: dict[str, Any],
    ) -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []
        if not cluster:
            blockers.append(
                self._blocker(
                    "no_current_trip",
                    "No current seminar route found",
                    "Roadshow found the person but not a current European planning window.",
                    "Run real source sync",
                    "/",
                    "Refreshes watched sources and may create a current trip cluster.",
                )
            )
        if fit_summary["status"] == "weak":
            blockers.append(
                self._blocker(
                    "weak_kof_fit",
                    "KOF fit needs review",
                    "No deterministic KOF research-area match or RePEc superstar signal was found.",
                    "Inspect researcher evidence",
                    f"/researchers/{researcher.id}",
                    "Opens the dossier so topics, identities, and evidence can be reviewed.",
                )
            )
        if spec.expected_superstar and not fit_summary["superstar_priority"]:
            blockers.append(
                self._blocker(
                    "superstar_not_verified",
                    "Superstar priority not verified",
                    "The RePEc top-200 signal was not confirmed during the shadow audit.",
                    "Search trusted evidence",
                    f"/researchers/{researcher.id}",
                    "Opens the researcher dossier where trusted evidence search can be run.",
                )
            )
        if route_summary["status"] in {"no_kof_slot", "needs_route_review", "risky"}:
            blockers.append(
                self._blocker(
                    "route_or_slot_review",
                    "Route or KOF slot needs action",
                    "The planner could not mark the Zurich stop as fully ready.",
                    "Review route and KOF slot",
                    "/opportunities",
                    "Opens the opportunity workspace with route and slot actions.",
                )
            )
        if evidence_summary["status"] != "approved":
            blockers.append(
                self._blocker(
                    "evidence_not_approved",
                    "Approved evidence is missing",
                    "Drafts require approved PhD institution and nationality facts.",
                    "Approve evidence for outreach",
                    f"/review?status=pending&researcher_id={researcher.id}",
                    "Opens the exact review queue for this researcher.",
                )
            )
        if price_summary["status"] == "estimate_requires_review":
            blockers.append(
                self._blocker(
                    "fare_estimate_review",
                    "First-class fare estimate needs review",
                    "At least one rail leg uses a conservative fallback estimate.",
                    "Refresh first-class fares",
                    "/tour-legs",
                    "Opens tour-leg price actions for live or reviewed fare checks.",
                )
            )
        if draft_gate["status"].startswith("blocked") and not any(blocker["code"] == "evidence_not_approved" for blocker in blockers):
            blockers.append(
                self._blocker(
                    "draft_blocked",
                    "Draft is not sendable",
                    str(draft_gate.get("reason") or "Roadshow blocked the draft gate."),
                    "Inspect draft blockers",
                    "/opportunities",
                    "Shows the exact blocker before any invitation is created.",
                )
            )
        return blockers

    def _verdict(
        self,
        spec: BusinessCaseSpec,
        researcher: Researcher,
        cluster: TripCluster | None,
        fit_summary: dict[str, Any],
        route_summary: dict[str, Any],
        evidence_summary: dict[str, Any],
        draft_gate: dict[str, Any],
        blockers: list[dict[str, Any]],
    ) -> str:
        if not researcher:
            return "blocked_not_found"
        if not cluster:
            return "blocked_no_current_trip"
        if spec.negative_control and fit_summary["status"] == "weak":
            return "blocked_low_kof_fit"
        if route_summary["status"] == "no_kof_slot":
            return "blocked_no_kof_slot"
        if route_summary["status"] == "risky":
            return "blocked_route_risk"
        if evidence_summary["status"] != "approved":
            return "blocked_missing_evidence"
        if draft_gate["status"] == "allowed_shadow_preview":
            return "draft_allowed_shadow_preview"
        if blockers:
            return "ready_for_admin_review"
        return "ready_for_admin_review"

    def _not_found_payload(self, spec: BusinessCaseSpec, reason: str) -> dict[str, Any]:
        blocker = self._blocker(
            "not_found",
            "Case data was not found",
            reason,
            "Run real source sync",
            "/",
            "Refreshes watched sources and evidence before running the audit again.",
        )
        return {
            "researcher_id": None,
            "case_key": spec.key,
            "display_name": spec.display_name,
            "target_name": spec.target_name,
            "verdict": "blocked_not_found",
            "score": 0,
            "data_found": False,
            "kof_fit_status": "not_evaluated",
            "route_status": "not_evaluated",
            "evidence_status": "not_evaluated",
            "draft_status": "blocked",
            "price_status": "not_checked",
            "evidence_summary_json": {"status": "not_evaluated"},
            "fit_summary_json": {"status": "not_evaluated"},
            "route_summary_json": {"status": "not_evaluated"},
            "price_summary_json": {"status": "not_checked"},
            "draft_gate_json": {"status": "blocked", "reason": reason},
            "blockers": [blocker],
            "source_links_json": [],
            "metadata_json": {"mode": "shadow", "normal_records_created": False},
        }

    def _error_payload(self, spec: BusinessCaseSpec, error: Exception) -> dict[str, Any]:
        payload = self._not_found_payload(spec, f"Shadow audit failed for this case: {error}")
        payload["verdict"] = "audit_error"
        payload["metadata_json"] = {"mode": "shadow", "error": str(error), "normal_records_created": False}
        return payload

    def _source_links(self, researcher: Researcher) -> list[dict[str, Any]]:
        links: list[dict[str, Any]] = []
        for identity in researcher.identities:
            if identity.profile_url:
                links.append({"type": identity.provider, "label": identity.canonical_name, "url": identity.profile_url})
        for document in researcher.documents:
            links.append({"type": "document", "label": document.title or document.fetch_status, "url": document.url})
        for event in researcher.talk_events:
            links.append({"type": "event", "label": event.source_name, "url": event.url})
        seen: set[str] = set()
        deduped = []
        for link in links:
            if link["url"] in seen:
                continue
            seen.add(link["url"])
            deduped.append(link)
        return deduped[:20]

    def _best_repec_rank(self, researcher: Researcher) -> int | None:
        ranks = []
        identities = list(researcher.identities)
        if not identities and researcher.id:
            identities = self.session.scalars(
                select(ResearcherIdentity).where(ResearcherIdentity.researcher_id == researcher.id)
            ).all()
        for identity in identities:
            if identity.provider != "repec":
                continue
            rank = (identity.metadata_json or {}).get("rank")
            if isinstance(rank, int):
                ranks.append(rank)
            elif isinstance(rank, str) and rank.isdigit():
                ranks.append(int(rank))
        return min(ranks) if ranks else None

    def _is_europe_based(self, researcher: Researcher) -> bool:
        home = (researcher.home_institution or "").lower()
        return any(marker in home for marker in ("munich", "milan", "bonn", "mannheim", "zurich", "london", "paris", "europe"))

    def _blocker(
        self,
        code: str,
        title: str,
        explanation: str,
        action_label: str,
        action_href: str,
        consequence: str,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "title": title,
            "explanation": explanation,
            "action_label": action_label,
            "action_href": action_href,
            "consequence": consequence,
        }

    def _summarize(self, results: list[BusinessCaseResult]) -> dict[str, Any]:
        verdicts = [result.verdict for result in results]
        return {
            "case_count": len(results),
            "draft_allowed_count": sum(1 for verdict in verdicts if verdict == "draft_allowed_shadow_preview"),
            "blocked_count": sum(1 for verdict in verdicts if verdict.startswith("blocked")),
            "audit_error_count": sum(1 for verdict in verdicts if verdict == "audit_error"),
            "failing_cases": [
                result.case_key
                for result in results
                if result.verdict in {"audit_error"} or (result.case_key == "daron_acemoglu" and result.kof_fit_status == "weak")
            ],
            "verdicts": verdicts,
        }
