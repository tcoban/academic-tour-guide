from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Institution, OpenSeminarWindow, OutreachDraft, RelationshipBrief, Researcher, SpeakerProfile, TripCluster
from app.services.enrichment import best_fact, best_fact_candidate
from app.services.logistics import CostSharingCalculator
from app.services.opportunities import OpportunityWorkbench
from app.services.roadshow import KOF_INSTITUTION_NAME


class ReviewRequiredError(RuntimeError):
    pass


TEMPLATES = {
    "concierge": {
        "label": "Concierge invitation",
        "subject": "KOF Zurich invitation around your European visit",
        "opening": "we noticed your European itinerary and thought KOF could be a natural Zurich stop during that window",
    },
    "academic_home": {
        "label": "Academic-home hook",
        "subject": "A Zurich seminar stop while you are back near your academic home",
        "opening": "your European seminar schedule seems like a timely moment to reconnect with the region through a KOF visit",
    },
    "cost_share": {
        "label": "Cost-sharing angle",
        "subject": "Coordinating a KOF Zurich stop with your European itinerary",
        "opening": "we saw an opportunity to coordinate a Zurich seminar stop with travel that already brings you to Europe",
    },
}


class DraftGenerator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cost_sharing = CostSharingCalculator()

    def generate(self, researcher: Researcher, cluster: TripCluster, template_key: str = "concierge") -> OutreachDraft:
        template = TEMPLATES.get(template_key, TEMPLATES["concierge"])
        phd_fact = best_fact(researcher, "phd_institution")
        nationality_fact = best_fact(researcher, "nationality")
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

        matching_window = self._best_window_for_cluster(cluster)
        cost_share = self.cost_sharing.estimate(cluster, researcher, matching_window)
        hook = self._build_hook(researcher, cluster, phd_fact.value, nationality_fact.value, template_key)
        subject = template["subject"]
        checklist = self._build_checklist(researcher, cluster, matching_window)
        roadshow_context = self._roadshow_context(researcher)
        metadata = {
            "template_key": template_key if template_key in TEMPLATES else "concierge",
            "template_label": template["label"],
            "used_facts": [
                self._fact_metadata(phd_fact),
                self._fact_metadata(nationality_fact),
            ],
            "candidate_slot": self._slot_metadata(matching_window),
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
            ),
            "itinerary": cluster.itinerary,
            "checklist": checklist,
            "roadshow_context": roadshow_context,
            "approved_fact_gate": True,
        }
        body = self._build_body(
            researcher=researcher,
            cluster=cluster,
            hook=hook,
            opening=template["opening"],
            matching_window=matching_window,
            cost_share=cost_share,
            checklist=checklist,
            roadshow_context=roadshow_context,
        )

        draft = OutreachDraft(
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

    def _best_window_for_cluster(self, cluster: TripCluster) -> OpenSeminarWindow | None:
        match = OpportunityWorkbench(self.session).best_window_for_cluster(cluster)
        return match.window if match else None

    def _build_hook(self, researcher: Researcher, cluster: TripCluster, phd_institution: str, nationality: str, template_key: str) -> str:
        hook_fragments = [f"Biographic hook: {researcher.name} earned their PhD at {phd_institution}."]
        if nationality.lower() in {"german", "austrian", "swiss"} and researcher.home_institution:
            hook_fragments.append(
                f"They are currently based at {researcher.home_institution}, which strengthens the home-visit angle for a DACH trip."
            )
        if any(city["city"].lower() in {"milan", "munich"} for city in cluster.itinerary):
            hook_fragments.append("The current itinerary already includes a Zurich-adjacent hub.")
        if template_key == "cost_share":
            hook_fragments.append("The message should emphasize coordination and cost-sharing rather than a standalone Zurich trip.")
        if template_key == "academic_home":
            hook_fragments.append("The message should lead with the academic-home connection before logistics.")
        return " ".join(hook_fragments)

    def _build_body(
        self,
        researcher: Researcher,
        cluster: TripCluster,
        hook: str,
        opening: str,
        matching_window: OpenSeminarWindow | None,
        cost_share: dict | None,
        checklist: list[dict],
        roadshow_context: dict,
    ) -> str:
        itinerary_cities = ", ".join(item["city"] for item in cluster.itinerary) or "Europe"
        last_name = researcher.name.split()[-1]
        slot_sentence = (
            f"We currently see a possible KOF slot on {matching_window.starts_at.strftime('%A, %d %B %Y at %H:%M')} Zurich time."
            if matching_window
            else "We can keep the date flexible around your European window."
        )
        cost_sentence = ""
        if cost_share:
            cost_sentence = (
                f" Because Zurich appears to be a {cost_share['recommended_mode']} add-on from {cost_share['nearest_itinerary_city']}, "
                f"the incremental travel estimate is CHF {cost_share['multi_city_incremental_chf']} rather than roughly "
                f"CHF {cost_share['baseline_round_trip_chf']} for a standalone trip."
            )

        return (
            "Dear KOF admin,\n\n"
            f"{researcher.name} appears to be in Europe between {cluster.start_date.isoformat()} and {cluster.end_date.isoformat()}.\n"
            f"{hook}\n\n"
            "Admin notes:\n"
            f"- Home institution: {researcher.home_institution or 'Unknown'}\n"
            f"- Opportunity score: {cluster.opportunity_score}\n"
            f"- Existing itinerary: {itinerary_cities}\n"
            f"- Roadshow relationship memory: {roadshow_context['relationship_summary']}\n"
            f"- Speaker preference/rider check: {roadshow_context['preference_summary']}\n"
            + (
                f"- Candidate KOF slot: {matching_window.starts_at.isoformat()} to {matching_window.ends_at.isoformat()}\n"
                if matching_window
                else ""
            )
            + (
                f"- Cost-sharing estimate: CHF {cost_share['multi_city_incremental_chf']} Zurich add-on vs "
                f"CHF {cost_share['baseline_round_trip_chf']} standalone round trip "
                f"(CHF {cost_share['estimated_savings_chf']} estimated savings, {cost_share['roi_percent']}% ROI)\n"
                if cost_share
                else ""
            )
            + "\nPre-send checklist:\n"
            + "\n".join(f"- {item['label']}: {item['status']}" for item in checklist)
            + "\n\nSuggested email draft:\n"
            f"Dear Professor {last_name},\n\n"
            f"I hope this finds you well. We noticed that {opening}. "
            f"Given your connection to {itinerary_cities}, we wondered whether a KOF seminar visit in Zurich could fit naturally into the same trip. "
            f"{slot_sentence}{cost_sentence}\n\n"
            "If this is of interest, we would be delighted to explore a suitable seminar date and coordinate the logistics with your existing itinerary.\n\n"
            "Warm regards,\n"
            "KOF seminar team\n"
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

    def _slot_metadata(self, window: OpenSeminarWindow | None) -> dict | None:
        if not window:
            return None
        return {
            "id": window.id,
            "starts_at": window.starts_at.isoformat(),
            "ends_at": window.ends_at.isoformat(),
            "source": window.source,
            "metadata_json": window.metadata_json,
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
    ) -> list[dict]:
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
                "detail": "Invite for a KOF seminar stop, but keep wording conditional pending admin schedule confirmation.",
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
        if cost_share:
            brief.append(
                {
                    "label": "Logistics angle",
                    "detail": (
                        f"Zurich add-on estimate is CHF {cost_share['multi_city_incremental_chf']} vs "
                        f"CHF {cost_share['baseline_round_trip_chf']} standalone, with CHF "
                        f"{cost_share['estimated_savings_chf']} estimated savings."
                    ),
                }
            )
        return brief

    def _roadshow_context(self, researcher: Researcher) -> dict:
        profile = researcher.speaker_profile or self.session.scalar(
            select(SpeakerProfile).where(SpeakerProfile.researcher_id == researcher.id)
        )
        kof = self.session.scalar(select(Institution).where(Institution.name == KOF_INSTITUTION_NAME))
        relationship_summary = "No prior Roadshow relationship memory yet."
        if kof:
            brief = self.session.scalar(
                select(RelationshipBrief).where(
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

    def _build_checklist(self, researcher: Researcher, cluster: TripCluster, matching_window: OpenSeminarWindow | None) -> list[dict]:
        return [
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
                "label": "Open KOF slot selected",
                "status": "ready" if matching_window else "needs_review",
                "detail": matching_window.starts_at.isoformat() if matching_window else "No matching open slot is currently attached.",
            },
            {
                "label": "Existing itinerary checked",
                "status": "ready" if cluster.itinerary else "needs_review",
                "detail": ", ".join(item["city"] for item in cluster.itinerary) or "No itinerary cities found.",
            },
            {
                "label": "Recipient/name sanity check",
                "status": "needs_review",
                "detail": f"Confirm salutation and current institution for {researcher.name}.",
            },
        ]
