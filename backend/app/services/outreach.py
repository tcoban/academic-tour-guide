from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Institution, OpenSeminarWindow, OutreachDraft, RelationshipBrief, Researcher, SpeakerProfile, TripCluster
from app.services.ai import AIDraftAssistant
from app.services.enrichment import best_fact, best_fact_candidate
from app.services.logistics import CostSharingCalculator
from app.services.opportunities import OpportunityWorkbench
from app.services.roadshow import KOF_INSTITUTION_NAME
from app.services.tenancy import get_session_tenant


class ReviewRequiredError(RuntimeError):
    pass


TEMPLATES = {
    "kof_invitation": {
        "label": "KOF invitation",
        "subject": "KOF Zurich seminar invitation",
    },
    "multi_host_tour": {
        "label": "Multi-host Roadshow tour",
        "subject": "A coordinated European Roadshow tour around your visit",
    },
}
NORMAL_TEMPLATE_KEYS = {"kof_invitation", "concierge", "academic_home", "cost_share"}


class DraftGenerator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cost_sharing = CostSharingCalculator()
        self.tenant = get_session_tenant(session)

    def generate(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        template_key: str = "kof_invitation",
        tour_assembly_context: dict | None = None,
        use_ai: bool = False,
    ) -> OutreachDraft:
        resolved_template_key = self._resolve_template_key(template_key)
        template = TEMPLATES[resolved_template_key]
        phd_fact = best_fact(researcher, "phd_institution", tenant_id=self.tenant.id)
        nationality_fact = best_fact(researcher, "nationality", tenant_id=self.tenant.id)
        if not phd_fact or phd_fact.confidence < settings.evidence_confidence_threshold:
            pending_phd = best_fact_candidate(researcher, "phd_institution", statuses=("pending",))
            if pending_phd:
                raise ReviewRequiredError(
                    f"Draft generation requires approval of the pending PhD institution evidence: {pending_phd.value}."
                )
            raise ReviewRequiredError(
                "Draft generation requires an approved PhD institution fact before the biographic hook can be used."
            )
        if not nationality_fact or nationality_fact.confidence < settings.evidence_confidence_threshold:
            pending_nationality = best_fact_candidate(researcher, "nationality", statuses=("pending",))
            if pending_nationality:
                raise ReviewRequiredError(
                    f"Draft generation requires approval of the pending nationality evidence: {pending_nationality.value}."
                )
            raise ReviewRequiredError(
                "Draft generation requires an approved nationality fact before the biographic hook can be used."
            )

        matching_slot = self._best_slot_for_cluster(cluster)
        matching_window = matching_slot.window if matching_slot else None
        cost_share = self.cost_sharing.estimate(cluster, researcher, matching_window)
        internal_rationale = self._internal_rationale(researcher, cluster, phd_fact.value, nationality_fact.value, resolved_template_key)
        subject = self._subject_for_cluster(cluster, resolved_template_key, template["subject"])
        checklist = self._build_checklist(researcher, cluster, matching_window, matching_slot.travel_fit if matching_slot else None)
        roadshow_context = self._roadshow_context(researcher)
        metadata = {
            "template_key": resolved_template_key,
            "legacy_template_key": template_key if template_key != resolved_template_key else None,
            "template_label": template["label"],
            "used_facts": [
                self._fact_metadata(phd_fact),
                self._fact_metadata(nationality_fact),
            ],
            "candidate_slot": self._slot_metadata(matching_slot),
            "cost_share": cost_share,
            "send_brief": self._build_send_brief(
                researcher=researcher,
                cluster=cluster,
                phd_institution=phd_fact.value,
                nationality=nationality_fact.value,
                matching_window=matching_window,
                cost_share=cost_share,
                template_label=template["label"],
                roadshow_context=roadshow_context,
                tour_assembly_context=tour_assembly_context,
                travel_fit=matching_slot.travel_fit if matching_slot else None,
            ),
            "itinerary": cluster.itinerary,
            "checklist": checklist,
            "roadshow_context": roadshow_context,
            "operator_notes": self._operator_notes(
                researcher=researcher,
                cluster=cluster,
                internal_rationale=internal_rationale,
                matching_window=matching_window,
                checklist=checklist,
                roadshow_context=roadshow_context,
                tour_assembly_context=tour_assembly_context,
            ),
            "internal_rationale": internal_rationale,
            "approved_fact_gate": True,
            "tour_assembly_context": tour_assembly_context,
        }
        body = self._build_email_body(
            researcher=researcher,
            cluster=cluster,
            matching_window=matching_window,
            template_key=resolved_template_key,
            tour_assembly_context=tour_assembly_context,
        )
        if use_ai:
            body, ai_metadata = AIDraftAssistant(self.session).suggest_body(
                researcher=researcher,
                cluster=cluster,
                deterministic_body=body,
                factual_context=self._ai_factual_context(
                    researcher=researcher,
                    cluster=cluster,
                    matching_window=matching_window,
                    phd_fact=phd_fact,
                    nationality_fact=nationality_fact,
                    metadata=metadata,
                ),
            )
            metadata.update(ai_metadata)
        else:
            metadata["ai_generated_body"] = False

        draft = OutreachDraft(
            tenant_id=self.tenant.id,
            researcher_id=researcher.id,
            trip_cluster_id=cluster.id,
            subject=subject,
            body=body,
            status="draft",
            metadata_json=metadata,
        )
        self.session.add(draft)
        self.session.flush()
        return draft

    def _ai_factual_context(
        self,
        *,
        researcher: Researcher,
        cluster: TripCluster,
        matching_window: OpenSeminarWindow | None,
        phd_fact,
        nationality_fact,
        metadata: dict,
    ) -> dict:
        slot = self._specific_slot_sentence(matching_window)
        return {
            "tenant_name": self.tenant.name,
            "tenant_city": self.tenant.city,
            "seminar_team": (self.tenant.branding_json or {}).get("seminar_team") or f"{self.tenant.name} seminar team",
            "speaker_name": researcher.name,
            "speaker_home_institution": researcher.home_institution,
            "approved_facts": [self._fact_metadata(phd_fact), self._fact_metadata(nationality_fact)],
            "slot": slot,
            "candidate_slot": metadata.get("candidate_slot"),
            "itinerary": cluster.itinerary,
            "relationship_summary": (metadata.get("roadshow_context") or {}).get("relationship_summary"),
            "preference_summary": (metadata.get("roadshow_context") or {}).get("preference_summary"),
            "checklist": metadata.get("checklist"),
        }

    def _resolve_template_key(self, template_key: str) -> str:
        if template_key == "multi_host_tour":
            return "multi_host_tour"
        if template_key in NORMAL_TEMPLATE_KEYS:
            return "kof_invitation"
        return "kof_invitation"

    def _best_slot_for_cluster(self, cluster: TripCluster):
        return OpportunityWorkbench(self.session).best_window_for_cluster(cluster)

    def _internal_rationale(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        phd_institution: str,
        nationality: str,
        template_key: str,
    ) -> list[dict]:
        rationale = [{"label": "Biographic hook", "detail": f"{researcher.name} earned their PhD at {phd_institution}."}]
        if nationality.lower() in {"german", "austrian", "swiss"} and researcher.home_institution:
            rationale.append(
                {
                    "label": "DACH/home-visit signal",
                    "detail": f"Nationality evidence and current base at {researcher.home_institution} support a home-region visit hypothesis.",
                }
            )
        if any(city["city"].lower() in {"milan", "munich"} for city in cluster.itinerary):
            rationale.append({"label": "Zurich-adjacent itinerary", "detail": "The current itinerary includes Milan or Munich."})
        if template_key == "multi_host_tour":
            rationale.append({"label": "Tour assembly", "detail": "Frame the invitation as a coordinated multi-stop European itinerary."})
        return rationale

    def _operator_notes(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        matching_window: OpenSeminarWindow | None,
        checklist: list[dict],
        internal_rationale: list[dict],
        roadshow_context: dict,
        tour_assembly_context: dict | None = None,
    ) -> list[dict]:
        itinerary_cities = ", ".join(item["city"] for item in cluster.itinerary) or "Europe"
        notes = [
            {"label": "Home institution", "detail": researcher.home_institution or "Unknown"},
            {"label": "Opportunity score", "detail": str(cluster.opportunity_score)},
            {"label": "Existing itinerary", "detail": itinerary_cities},
            {"label": "Relationship memory", "detail": roadshow_context["relationship_summary"]},
            {"label": "Preference/rider check", "detail": roadshow_context["preference_summary"]},
        ]
        notes.extend(internal_rationale)
        if matching_window:
            notes.append(
                {
                    "label": "Candidate KOF slot",
                    "detail": f"{matching_window.starts_at.isoformat()} to {matching_window.ends_at.isoformat()}",
                }
            )
        notes.extend({"label": f"Checklist: {item['label']}", "detail": item["status"]} for item in checklist)
        if tour_assembly_context:
            budget = tour_assembly_context.get("budget_summary") or {}
            host_count = int(tour_assembly_context.get("host_count") or budget.get("host_count") or 0)
            notes.append({"label": "Anonymous Roadshow assembly", "detail": f"{host_count} host stops modeled for internal review."})
        return notes

    def _build_email_body(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        matching_window: OpenSeminarWindow | None,
        template_key: str,
        tour_assembly_context: dict | None = None,
    ) -> str:
        last_name = researcher.name.split()[-1]
        opening_sentence = self._opening_sentence(cluster, template_key)
        slot_sentence = self._specific_slot_sentence(matching_window)
        assembly_email = ""
        if template_key == "multi_host_tour" and tour_assembly_context:
            budget = tour_assembly_context.get("budget_summary") or {}
            host_count = int(tour_assembly_context.get("host_count") or budget.get("host_count") or 0)
            assembly_email = (
                f"We are also reviewing whether this could fit into a compact multi-stop European tour with {host_count} seminar hosts. "
            )
        seminar_team = (self.tenant.branding_json or {}).get("seminar_team") or f"{self.tenant.name} seminar team"
        host_city = self.tenant.city or "the host city"

        return (
            f"Dear Professor {last_name},\n\n"
            f"I hope this finds you well. {opening_sentence}\n\n"
            f"{slot_sentence} {assembly_email}If this timing is feasible, we would be glad to coordinate the local arrangements for your {host_city} visit.\n\n"
            "With best regards,\n"
            f"The {seminar_team}\n"
        )

    def _subject_for_cluster(self, cluster: TripCluster, template_key: str, default_subject: str) -> str:
        host_short_name = (self.tenant.branding_json or {}).get("short_name") or self.tenant.name
        host_city = self.tenant.city or "the host city"
        if template_key == "multi_host_tour":
            return default_subject
        cities = self._unique_itinerary_cities(cluster)
        if len(cities) == 1:
            return f"{host_short_name} {host_city} seminar invitation around your {cities[0]} visit"
        if len(cities) == 2:
            return f"{host_short_name} {host_city} seminar invitation around your {cities[0]} and {cities[1]} visits"
        if len(cities) > 2:
            return f"{host_short_name} {host_city} seminar invitation around your itinerary"
        return default_subject

    def _opening_sentence(self, cluster: TripCluster, template_key: str) -> str:
        if template_key == "multi_host_tour":
            host_short_name = (self.tenant.branding_json or {}).get("short_name") or self.tenant.name
            host_city = self.tenant.city or "our host city"
            return f"We are preparing a compact seminar itinerary and would be very pleased to include a {host_city} stop at {host_short_name}."
        itinerary_phrase = self._itinerary_phrase(cluster)
        host_short_name = (self.tenant.branding_json or {}).get("short_name") or self.tenant.name
        host_city = self.tenant.city or "our host city"
        return (
            f"We saw {itinerary_phrase} and would be very pleased to invite you to give a research seminar "
            f"at {host_short_name} in {host_city} around that trip."
        )

    def _itinerary_phrase(self, cluster: TripCluster) -> str:
        unique_cities = self._unique_itinerary_cities(cluster)
        if not unique_cities:
            return "your planned seminar travel"
        if len(unique_cities) == 1:
            return f"your planned visit to {unique_cities[0]}"
        if len(unique_cities) == 2:
            return f"your planned visits to {unique_cities[0]} and {unique_cities[1]}"
        return f"your planned visits to {', '.join(unique_cities[:-1])}, and {unique_cities[-1]}"

    def _unique_itinerary_cities(self, cluster: TripCluster) -> list[str]:
        cities = [str(item.get("city") or "").strip() for item in cluster.itinerary if item.get("city")]
        return list(dict.fromkeys(city for city in cities if city))

    def _specific_slot_sentence(self, matching_window: OpenSeminarWindow | None) -> str:
        if not matching_window:
            host_short_name = (self.tenant.branding_json or {}).get("short_name") or self.tenant.name
            return f"We do not yet have a specific open {host_short_name} slot attached, so this draft should not be sent before the calendar is confirmed."
        start = matching_window.starts_at
        end = matching_window.ends_at
        timezone_label = "Zurich" if self.tenant.timezone == "Europe/Zurich" else self.tenant.timezone
        return (
            f"The slot we have in mind is {start.strftime('%A, %d %B %Y, %H:%M')}"
            f"-{end.strftime('%H:%M')} {timezone_label} time."
        )

    def _fact_metadata(self, fact) -> dict:
        return {
            "id": fact.id,
            "fact_type": fact.fact_type,
            "value": fact.value,
            "confidence": fact.confidence,
            "source_url": fact.source_url,
            "evidence_snippet": fact.evidence_snippet,
            "approval_origin": fact.approval_origin,
            "approved_at": fact.approved_at.isoformat() if fact.approved_at else None,
        }

    def _slot_metadata(self, slot_match) -> dict | None:
        if not slot_match:
            return None
        window = slot_match.window
        return {
            "id": window.id,
            "starts_at": window.starts_at.isoformat(),
            "ends_at": window.ends_at.isoformat(),
            "source": window.source,
            "metadata_json": window.metadata_json,
            "fit_type": slot_match.fit_type,
            "travel_fit_score": slot_match.travel_fit_score,
            "travel_fit_label": slot_match.travel_fit_label,
            "travel_fit_summary": slot_match.travel_fit_summary,
            "travel_fit_severity": slot_match.travel_fit_severity,
            "planning_warnings": slot_match.planning_warnings,
            "travel_fit": slot_match.travel_fit,
        }

    def _build_send_brief(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        phd_institution: str,
        nationality: str,
        matching_window: OpenSeminarWindow | None,
        cost_share: dict | None,
        template_label: str,
        roadshow_context: dict,
        tour_assembly_context: dict | None = None,
        travel_fit: dict | None = None,
    ) -> list[dict]:
        host_short_name = (self.tenant.branding_json or {}).get("short_name") or self.tenant.name
        brief = [
            {
                "label": "Template angle",
                "detail": template_label,
            },
            {
                "label": "Biographic hook",
                "detail": f"Lead with {phd_institution} PhD evidence and {nationality} home-visit relevance.",
            },
            {
                "label": "Trip context",
                "detail": f"Existing European window runs {cluster.start_date.isoformat()} to {cluster.end_date.isoformat()}.",
            },
            {
                "label": "Suggested ask",
                "detail": f"Invite for the specific {host_short_name} slot attached to this draft; do not imply the date is still open-ended.",
            },
            {
                "label": "Relationship memory",
                "detail": roadshow_context["relationship_summary"],
            },
            {
                "label": "Preference/rider check",
                "detail": roadshow_context["preference_summary"],
            },
        ]
        if matching_window:
            brief.append(
                {
                    "label": "Candidate slot",
                    "detail": f"{matching_window.starts_at.isoformat()} to {matching_window.ends_at.isoformat()}",
                }
            )
        if travel_fit:
            brief.append(
                {
                    "label": "Planner route check",
                    "detail": travel_fit.get("summary") or "Route fit needs review.",
                }
            )
        if cost_share:
            brief.append(
                {
                    "label": "Internal logistics note",
                    "detail": (
                        f"Zurich add-on estimate is CHF {cost_share['multi_city_incremental_chf']} vs "
                        f"CHF {cost_share['baseline_round_trip_chf']} standalone, with CHF "
                        f"{cost_share['estimated_savings_chf']} estimated savings. Keep this internal; do not mention costs in the invitation."
                    ),
                }
            )
        if tour_assembly_context:
            budget = tour_assembly_context.get("budget_summary") or {}
            brief.append(
                {
                    "label": "Anonymous tour assembly",
                    "detail": (
                        f"{tour_assembly_context.get('host_count') or budget.get('host_count')} modeled host stops with "
                        f"CHF {budget.get('per_host_travel_share_chf', 'n/a')} per-host travel share."
                    ),
                }
            )
        return brief

    def _roadshow_context(self, researcher: Researcher) -> dict:
        profile = researcher.speaker_profile or self.session.scalar(
            select(SpeakerProfile).where(SpeakerProfile.researcher_id == researcher.id)
        )
        kof = self.tenant.host_institution or self.session.scalar(select(Institution).where(Institution.name == KOF_INSTITUTION_NAME))
        relationship_summary = "No prior Roadshow relationship memory yet."
        if kof:
            brief = self.session.scalar(
                select(RelationshipBrief).where(
                    RelationshipBrief.tenant_id == self.tenant.id,
                    RelationshipBrief.researcher_id == researcher.id,
                    RelationshipBrief.institution_id == kof.id,
                )
            )
            if brief and brief.summary:
                relationship_summary = brief.summary

        preference_summary = "No Roadshow speaker preferences or rider notes captured yet."
        if profile:
            fragments: list[str] = []
            if profile.notice_period_days is not None:
                fragments.append(f"{profile.notice_period_days}-day notice preference")
            if profile.fee_floor_chf is not None:
                fragments.append(f"fee floor CHF {profile.fee_floor_chf}")
            if profile.travel_preferences:
                fragments.append(f"travel preferences: {profile.travel_preferences}")
            if profile.rider:
                fragments.append(f"rider: {profile.rider}")
            if profile.availability_notes:
                fragments.append(f"availability notes: {profile.availability_notes}")
            if fragments:
                preference_summary = "; ".join(fragments)

        return {
            "relationship_summary": relationship_summary,
            "preference_summary": preference_summary,
        }

    def _build_checklist(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        matching_window: OpenSeminarWindow | None,
        travel_fit: dict | None = None,
    ) -> list[dict]:
        checklist = [
            {
                "label": "Approved PhD hook evidence",
                "status": "ready",
                "detail": "Required biographic fact has passed human review.",
            },
            {
                "label": "Approved nationality/home-visit evidence",
                "status": "ready",
                "detail": "Required DACH/home-visit fact has passed human review.",
            },
            {
                "label": f"Open {(self.tenant.branding_json or {}).get('short_name') or self.tenant.name} slot selected",
                "status": "ready" if matching_window else "needs_review",
                "detail": matching_window.starts_at.isoformat() if matching_window else "No matching open slot is currently attached.",
            },
            {
                "label": "Existing itinerary checked",
                "status": "ready" if cluster.itinerary else "needs_review",
                "detail": ", ".join(item["city"] for item in cluster.itinerary) or "No itinerary cities found.",
            },
            {
                "label": "Travel-rest sanity check",
                "status": "needs_review" if travel_fit and travel_fit.get("severity") == "risky" else "ready",
                "detail": (travel_fit or {}).get("summary") or "No route warning attached.",
            },
            {
                "label": "Recipient/name sanity check",
                "status": "needs_review",
                "detail": f"Confirm salutation and current institution for {researcher.name}.",
            },
        ]
        return checklist
