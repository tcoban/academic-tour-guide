from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import TalkEvent, TripCluster


class TripClusterer:
    def __init__(self, session: Session) -> None:
        self.session = session

    def rebuild_all(self) -> list[TripCluster]:
        researcher_ids = self.session.scalars(select(TalkEvent.researcher_id).distinct()).all()
        clusters: list[TripCluster] = []
        for researcher_id in researcher_ids:
            if researcher_id:
                clusters.extend(self.rebuild_for_researcher(researcher_id))
        return clusters

    def rebuild_for_researcher(self, researcher_id: str) -> list[TripCluster]:
        events = self.session.scalars(
            select(TalkEvent).where(TalkEvent.researcher_id == researcher_id).order_by(TalkEvent.starts_at)
        ).all()
        self.session.execute(delete(TripCluster).where(TripCluster.researcher_id == researcher_id))
        if not events:
            return []

        clusters: list[list[TalkEvent]] = []
        current_cluster: list[TalkEvent] = [events[0]]
        for event in events[1:]:
            previous = current_cluster[-1]
            if event.starts_at.date() - previous.starts_at.date() <= timedelta(days=settings.cluster_gap_days):
                current_cluster.append(event)
            else:
                clusters.append(current_cluster)
                current_cluster = [event]
        clusters.append(current_cluster)

        persisted: list[TripCluster] = []
        for grouped_events in clusters:
            itinerary = [
                {
                    "title": event.title,
                    "city": event.city,
                    "country": event.country,
                    "starts_at": event.starts_at.isoformat(),
                    "url": event.url,
                    "source_name": event.source_name,
                }
                for event in grouped_events
            ]
            cluster = TripCluster(
                researcher_id=researcher_id,
                start_date=grouped_events[0].starts_at.date(),
                end_date=grouped_events[-1].starts_at.date(),
                itinerary=itinerary,
                opportunity_score=0,
                rationale=[],
            )
            self.session.add(cluster)
            persisted.append(cluster)
        self.session.flush()
        return persisted

