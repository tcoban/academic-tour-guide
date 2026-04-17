from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import OpenSeminarWindow, OutreachDraft, Researcher, TripCluster
from app.services.enrichment import best_fact


class DraftGenerator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def generate(self, researcher: Researcher, cluster: TripCluster) -> OutreachDraft:
        phd_fact = best_fact(researcher, "phd_institution")
        nationality_fact = best_fact(researcher, "nationality")
        if not phd_fact or phd_fact.confidence < settings.evidence_confidence_threshold:
            draft = OutreachDraft(
                researcher_id=researcher.id,
                trip_cluster_id=cluster.id,
                subject=f"Blocked draft for {researcher.name}",
                body="Draft generation is blocked until the PhD institution is confirmed with sufficient evidence.",
                status="blocked",
                blocked_reason="Missing PhD evidence",
            )
            self.session.add(draft)
            self.session.flush()
            return draft
        if not nationality_fact or nationality_fact.confidence < settings.evidence_confidence_threshold:
            draft = OutreachDraft(
                researcher_id=researcher.id,
                trip_cluster_id=cluster.id,
                subject=f"Blocked draft for {researcher.name}",
                body="Draft generation is blocked until nationality is confirmed with sufficient evidence.",
                status="blocked",
                blocked_reason="Missing nationality evidence",
            )
            self.session.add(draft)
            self.session.flush()
            return draft

        matching_window = self._best_window_for_cluster(cluster)
        hook = self._build_hook(researcher, cluster, phd_fact.value, nationality_fact.value)
        subject = f"KOF Zurich invitation around your European visit"
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
            "\nDraft email opening:\n"
            f"Professor {researcher.name.split()[-1]}, we noticed your European itinerary and thought KOF could be a natural Zurich stop during that window.\n"
        )

        draft = OutreachDraft(
            researcher_id=researcher.id,
            trip_cluster_id=cluster.id,
            subject=subject,
            body=body,
            status="draft",
        )
        self.session.add(draft)
        self.session.flush()
        return draft

    def _best_window_for_cluster(self, cluster: TripCluster) -> OpenSeminarWindow | None:
        tzinfo = None
        if cluster.itinerary:
            tzinfo = datetime.fromisoformat(cluster.itinerary[0]["starts_at"]).tzinfo
        cluster_start = datetime.combine(cluster.start_date, datetime.min.time(), tzinfo=tzinfo)
        windows = (
            self.session.query(OpenSeminarWindow)
            .filter(OpenSeminarWindow.starts_at >= cluster_start)
            .order_by(OpenSeminarWindow.starts_at)
            .all()
        )
        return windows[0] if windows else None

    def _build_hook(self, researcher: Researcher, cluster: TripCluster, phd_institution: str, nationality: str) -> str:
        hook_fragments = [f"Biographic hook: {researcher.name} earned their PhD at {phd_institution}."]
        if nationality.lower() in {"german", "austrian", "swiss"} and researcher.home_institution:
            hook_fragments.append(
                f"They are currently based at {researcher.home_institution}, which strengthens the home-visit angle for a DACH trip."
            )
        if any(city["city"].lower() in {"milan", "munich"} for city in cluster.itinerary):
            hook_fragments.append("The current itinerary already includes a Zurich-adjacent hub.")
        return " ".join(hook_fragments)
