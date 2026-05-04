from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import HostCalendarEvent, TalkEvent
from app.scraping.sources import _build_source_hash, get_host_calendar_adapter, iter_implemented_source_adapters
from app.services.availability import AvailabilityBuilder
from app.services.clustering import TripClusterer
from app.services.enrichment import Biographer
from app.services.scoring import Scorer
from app.services.tenancy import get_session_tenant


@dataclass(slots=True)
class IngestSummary:
    source_counts: dict[str, int]
    created_count: int
    updated_count: int


class IngestionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.biographer = Biographer(session)
        self.tenant = get_session_tenant(session)

    def ingest_sources(self) -> IngestSummary:
        created = 0
        updated = 0
        counts: dict[str, int] = {}
        for adapter in iter_implemented_source_adapters():
            adapter_count = 0
            try:
                for raw_page in adapter.fetch_pages():
                    for event in adapter.extract(raw_page):
                        status = self._upsert_talk_event(event)
                        adapter_count += 1
                        if status == "created":
                            created += 1
                        else:
                            updated += 1
            except Exception:
                adapter_count = 0
            counts[adapter.name] = adapter_count

        TripClusterer(self.session).rebuild_all()
        AvailabilityBuilder(self.session).rebuild_persisted()
        Scorer(self.session).score_all_clusters()
        self.session.flush()
        return IngestSummary(source_counts=counts, created_count=created, updated_count=updated)

    def sync_host_calendar(self) -> IngestSummary:
        adapter = get_host_calendar_adapter()
        created = 0
        updated = 0
        counts: dict[str, int] = {adapter.name: 0}
        for event in adapter.fetch_occupied():
            counts[adapter.name] += 1
            status = self._upsert_host_event(event)
            if status == "created":
                created += 1
            else:
                updated += 1

        AvailabilityBuilder(self.session).rebuild_persisted()
        Scorer(self.session).score_all_clusters()
        self.session.flush()
        return IngestSummary(source_counts=counts, created_count=created, updated_count=updated)

    def _upsert_talk_event(self, extracted) -> str:
        source_hash = _build_source_hash(
            extracted.source_name,
            extracted.url,
            extracted.speaker_name,
            extracted.starts_at.isoformat(),
        )
        event = self.session.scalar(select(TalkEvent).where(TalkEvent.source_hash == source_hash))
        researcher = self.biographer.get_or_create_researcher(
            extracted.speaker_name,
            home_institution=extracted.speaker_affiliation,
        )
        if event:
            event.title = extracted.title
            event.speaker_affiliation = extracted.speaker_affiliation
            event.city = extracted.city
            event.country = extracted.country
            event.starts_at = extracted.starts_at
            event.ends_at = extracted.ends_at
            event.url = extracted.url
            event.raw_payload = extracted.raw_payload
            event.researcher_id = researcher.id
            self.session.add(event)
            return "updated"

        event = TalkEvent(
            researcher_id=researcher.id,
            source_name=extracted.source_name,
            title=extracted.title,
            speaker_name=extracted.speaker_name,
            speaker_affiliation=extracted.speaker_affiliation,
            city=extracted.city,
            country=extracted.country,
            starts_at=extracted.starts_at,
            ends_at=extracted.ends_at,
            url=extracted.url,
            source_hash=source_hash,
            raw_payload=extracted.raw_payload,
        )
        self.session.add(event)
        self.session.flush()
        return "created"

    def _upsert_host_event(self, extracted) -> str:
        source_hash = sha256(f"{extracted.url}||{extracted.title}||{extracted.starts_at.isoformat()}".encode("utf-8")).hexdigest()
        event = self.session.scalar(
            select(HostCalendarEvent).where(
                HostCalendarEvent.tenant_id == self.tenant.id,
                HostCalendarEvent.source_hash == source_hash,
            )
        )
        if event:
            event.title = extracted.title
            event.location = extracted.location
            event.starts_at = extracted.starts_at
            event.ends_at = extracted.ends_at
            event.url = extracted.url
            event.metadata_json = extracted.metadata_json
            self.session.add(event)
            return "updated"

        event = HostCalendarEvent(
            tenant_id=self.tenant.id,
            title=extracted.title,
            location=extracted.location,
            starts_at=extracted.starts_at,
            ends_at=extracted.ends_at,
            url=extracted.url,
            source_hash=source_hash,
            metadata_json=extracted.metadata_json,
        )
        self.session.add(event)
        self.session.flush()
        return "created"
