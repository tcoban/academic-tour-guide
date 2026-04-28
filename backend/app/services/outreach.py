from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import OpenSeminarWindow, OutreachDraft, Researcher, TripCluster
from app.services.enrichment import best_fact, best_fact_candidate


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
        hook = self._build_hook(researcher, cluster, phd_fact.value, nationality_fact.value, template_key)
        subject = template["subject"]
        checklist = self._build_checklist(researcher, cluster, matching_window)
        metadata = {
            "template_key": template_key if template_key in TEMPLATES else "concierge",
            "template_label": template["label"],
            "used_facts": [
                self._fact_metadata(phd_fact),
                self._fact_metadata(nationality_fact),
            ],
            "candidate_slot": self._slot_metadata(matching_window),
            "itinerary": cluster.itinerary,
            "checklist": checklist,
            "approved_fact_gate": True,
        }
        body = (
            f"Dear KOF admin,\n\n"
            f"{researcher.name} appears to be in Europe between {cluster.start_date.isoformat()} and {cluster.end_date.isoformat()}.\n"
            f"{hook}\n\n"
            f"Suggested angle:\n"
            f"- Home institution: {researcher.home_institution or 'Unknown'}\n"
            f"- Opportunity score: {cluster.opportunity_score}\n"
            f"- Existing itinerary: {', '.join(item['city'] for item in cluster.itinerary)}\n"
        )
        if matching_window:
            body += f"- Candidate KOF slot: {matching_window.starts_at.isoformat()} to {matching_window.ends_at.isoformat()}\n"
        body += (
            "\nPre-send checklist:\n"
            + "\n".join(f"- {item['label']}: {item['status']}" for item in checklist)
            + "\n"
            "\nDraft email opening:\n"
            f"Professor {researcher.name.split()[-1]}, {template['opening']}.\n"
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
        tzinfo = None
        if cluster.itinerary:
            tzinfo = datetime.fromisoformat(cluster.itinerary[0]["starts_at"]).tzinfo
        cluster_start = datetime.combine(cluster.start_date, datetime.min.time(), tzinfo=tzinfo)
        windows = self.session.scalars(
            select(OpenSeminarWindow).where(OpenSeminarWindow.starts_at >= cluster_start).order_by(OpenSeminarWindow.starts_at)
        ).all()
        return windows[0] if windows else None

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
