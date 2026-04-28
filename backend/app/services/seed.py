from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    HostCalendarEvent,
    Institution,
    Researcher,
    ResearcherIdentity,
    SeminarSlotTemplate,
    SourceDocument,
    TalkEvent,
    TourLeg,
    TripCluster,
    WishlistEntry,
)
from app.services.availability import AvailabilityBuilder
from app.services.clustering import TripClusterer
from app.services.enrichment import Biographer, CandidateFact, normalize_name
from app.services.scoring import Scorer
from app.services.roadshow import RoadshowService


REFERENCE_INSTITUTIONS = [
    ("ETH Zurich", "Zurich", "Switzerland", 47.3769, 8.5417),
    ("University of Zurich", "Zurich", "Switzerland", 47.3744, 8.5481),
    ("University of Mannheim", "Mannheim", "Germany", 49.4875, 8.4660),
    ("LMU Munich", "Munich", "Germany", 48.1508, 11.5805),
    ("Bocconi University", "Milan", "Italy", 45.4507, 9.1899),
    ("University of Bonn", "Bonn", "Germany", 50.7374, 7.0982),
    ("ECB", "Frankfurt", "Germany", 50.1109, 8.6821),
    ("BIS", "Basel", "Switzerland", 47.5596, 7.5886),
    ("KOF Swiss Economic Institute", "Zurich", "Switzerland", 47.3769, 8.5417),
]


def seed_reference_data(session: Session) -> None:
    for name, city, country, latitude, longitude in REFERENCE_INSTITUTIONS:
        exists = session.scalar(select(Institution).where(Institution.name == name))
        if exists:
            continue
        session.add(
            Institution(
                name=name,
                city=city,
                country=country,
                latitude=latitude,
                longitude=longitude,
            )
        )
    session.flush()


@dataclass(slots=True)
class DemoSeedSummary:
    processed_count: int
    created_count: int
    updated_count: int


def seed_demo_data(session: Session) -> DemoSeedSummary:
    created = 0
    updated = 0
    biographer = Biographer(session)
    tz = ZoneInfo(settings.default_timezone)
    seminar_date = _next_weekday(datetime.now(tz=tz).date(), weekday=1, min_days=14)

    created += _ensure_demo_template(session)
    created += _ensure_demo_host_event(session, seminar_date, tz)

    approved_researcher, approved_created = _ensure_researcher(
        biographer,
        name="Prof. Elsa Example",
        home_institution="Yale University",
    )
    created += approved_created
    _ensure_identity(
        session,
        approved_researcher,
        external_id="demo-elsa",
        canonical_name="Elsa Example",
        profile_url="https://ideas.repec.org/e/pde999.html",
    )
    biographer.store_approved_fact(
        researcher=approved_researcher,
        fact_type="phd_institution",
        value="University of Mannheim",
        confidence=0.94,
        source_url="https://demo.roadshow.local/elsa-cv",
        evidence_snippet="PhD in Economics, University of Mannheim",
        approval_origin="demo_seed",
        verified=True,
    )
    biographer.store_approved_fact(
        researcher=approved_researcher,
        fact_type="nationality",
        value="German",
        confidence=0.93,
        source_url="https://demo.roadshow.local/elsa-cv",
        evidence_snippet="Nationality: German",
        approval_origin="demo_seed",
        verified=True,
    )
    updated += _upsert_talk_event(
        session,
        researcher=approved_researcher,
        source_hash="demo-elsa-bocconi",
        source_name="bocconi",
        title="Macro Networks and Firm Expectations",
        city="Milan",
        country="Italy",
        starts_at=datetime.combine(seminar_date - timedelta(days=2), time(16, 0), tzinfo=tz),
        url="https://demo.roadshow.local/events/elsa-bocconi",
    )
    updated += _upsert_talk_event(
        session,
        researcher=approved_researcher,
        source_hash="demo-elsa-munich",
        source_name="mannheim",
        title="Regional Policy Spillovers",
        city="Munich",
        country="Germany",
        starts_at=datetime.combine(seminar_date + timedelta(days=3), time(12, 30), tzinfo=tz),
        url="https://demo.roadshow.local/events/elsa-munich",
    )

    pending_researcher, pending_created = _ensure_researcher(
        biographer,
        name="Prof. Luca Pending",
        home_institution="Northwestern University",
    )
    created += pending_created
    _ensure_identity(
        session,
        pending_researcher,
        external_id="demo-luca",
        canonical_name="Luca Pending",
        profile_url="https://ideas.repec.org/e/ppe999.html",
    )
    source_document = _ensure_source_document(
        session,
        pending_researcher,
        url="https://demo.roadshow.local/luca-cv",
        title="Luca Pending CV",
        extracted_text=(
            "Luca Pending. Nationality: Swiss. "
            "PhD in Economics from University of Mannheim. "
            "Born: May 12, 1982. Professor at Northwestern University."
        ),
    )
    for candidate in biographer.extract_from_text(source_document.extracted_text or ""):
        biographer.store_candidate_fact(
            researcher=pending_researcher,
            candidate=CandidateFact(
                fact_type=candidate.fact_type,
                value=candidate.value,
                confidence=max(candidate.confidence, 0.82 if candidate.fact_type in {"phd_institution", "nationality"} else candidate.confidence),
                evidence_snippet=candidate.evidence_snippet,
                origin="demo_cv",
            ),
            source_url=source_document.url,
            source_document=source_document,
        )
    updated += _upsert_talk_event(
        session,
        researcher=pending_researcher,
        source_hash="demo-luca-bis",
        source_name="bis",
        title="Financial Frictions in Small Open Economies",
        city="Basel",
        country="Switzerland",
        starts_at=datetime.combine(seminar_date + timedelta(days=1), time(14, 0), tzinfo=tz),
        url="https://demo.roadshow.local/events/luca-bis",
    )

    TripClusterer(session).rebuild_all()
    AvailabilityBuilder(session).rebuild_persisted(start_date=seminar_date - timedelta(days=7), horizon_days=45)
    Scorer(session).score_all_clusters()
    _ensure_roadshow_demo(session, approved_researcher)
    session.flush()
    return DemoSeedSummary(processed_count=2, created_count=created, updated_count=updated)


def _ensure_roadshow_demo(session: Session, researcher: Researcher) -> None:
    service = RoadshowService(session)
    kof = service.ensure_kof_institution()
    service.update_institution_profile(
        kof,
        {
            "wishlist_topics": ["macro networks", "regional policy"],
            "procurement_notes": "KOF-first Roadshow pilot. Keep contract, payment, and travel booking manual for v1.",
            "po_threshold_chf": 5000,
            "grant_code_support": True,
            "coordinator_contacts": [{"name": "KOF Seminar Desk", "role": "Coordinator", "email": "seminars@example.invalid"}],
            "av_notes": "Seminar room supports hybrid recording by request.",
            "hospitality_notes": "Prefer rail arrivals into Zurich HB when feasible.",
            "host_quality_score": 88.0,
        },
    )
    service.update_speaker_profile(
        researcher,
        {
            "topics": ["macro networks", "regional policy", "expectations"],
            "fee_floor_chf": 3500,
            "notice_period_days": 21,
            "travel_preferences": {"rail_first_under_hours": 4, "home_airport": "JFK"},
            "rider": {"hotel_tier": "business", "dietary": "vegetarian option"},
            "availability_notes": "Prefers talks clustered into compact European legs.",
            "communication_preferences": {"tone": "concise", "channel": "email"},
            "consent_status": "pre_consent",
            "verification_status": "shadow",
        },
    )
    brief = service.ensure_relationship_brief(researcher.id, kof.id)
    service.update_relationship_brief(
        brief,
        {
            "summary": "Demo memory: strong fit for KOF macro seminar audience; keep logistics framed as a Zurich add-on.",
            "communication_preferences": {"tone": "warm and concise"},
            "decision_patterns": {"likely_hooks": ["DACH visit", "cost split", "compact itinerary"]},
            "relationship_history": [{"type": "demo_seed", "detail": "No real prior outreach. Use as placeholder memory."}],
            "operational_memory": {"venue": "KOF main seminar room"},
            "forward_signals": {"rebook_intent": "unknown"},
        },
    )
    trip_cluster = session.scalar(
        select(TripCluster).where(TripCluster.researcher_id == researcher.id).order_by(TripCluster.opportunity_score.desc())
    )
    if trip_cluster and not session.scalar(select(TourLeg).where(TourLeg.trip_cluster_id == trip_cluster.id)):
        service.propose_tour_leg(trip_cluster)
    if not session.scalar(select(WishlistEntry).where(WishlistEntry.institution_id == kof.id, WishlistEntry.researcher_id == researcher.id)):
        service.create_wishlist_entry(
            {
                "institution_id": kof.id,
                "researcher_id": researcher.id,
                "speaker_name": researcher.name,
                "topic": "macro networks",
                "priority": 90,
                "status": "active",
                "notes": "Founding KOF Roadshow wishlist entry seeded for the demo.",
                "metadata_json": {"source": "demo_seed"},
            }
        )
    service.refresh_wishlist_alerts()


def _next_weekday(start_date, weekday: int, min_days: int):
    candidate = start_date + timedelta(days=min_days)
    days_ahead = (weekday - candidate.weekday()) % 7
    return candidate + timedelta(days=days_ahead)


def _ensure_demo_template(session: Session) -> int:
    template = session.scalar(
        select(SeminarSlotTemplate).where(
            SeminarSlotTemplate.label == "KOF Research Seminar",
            SeminarSlotTemplate.weekday == 1,
        )
    )
    if template:
        template.start_time = time(16, 15)
        template.end_time = time(17, 30)
        template.timezone = settings.default_timezone
        template.active = True
        return 0
    session.add(
        SeminarSlotTemplate(
            label="KOF Research Seminar",
            weekday=1,
            start_time=time(16, 15),
            end_time=time(17, 30),
            timezone=settings.default_timezone,
            active=True,
        )
    )
    return 1


def _ensure_demo_host_event(session: Session, seminar_date, tz: ZoneInfo) -> int:
    source_hash = "demo-kof-occupied-slot"
    event = session.scalar(select(HostCalendarEvent).where(HostCalendarEvent.source_hash == source_hash))
    starts_at = datetime.combine(seminar_date + timedelta(days=7), time(16, 15), tzinfo=tz)
    if event:
        event.starts_at = starts_at
        event.ends_at = starts_at + timedelta(hours=1, minutes=15)
        return 0
    session.add(
        HostCalendarEvent(
            title="KOF Internal Research Workshop",
            location="KOF Zurich",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1, minutes=15),
            url="https://demo.roadshow.local/kof/internal-workshop",
            source_hash=source_hash,
            metadata_json={"source": "demo"},
        )
    )
    return 1


def _ensure_researcher(biographer: Biographer, name: str, home_institution: str) -> tuple[Researcher, int]:
    existing = biographer.session.scalar(select(Researcher).where(Researcher.normalized_name == normalize_name(name)))
    researcher = biographer.get_or_create_researcher(name, home_institution=home_institution)
    return researcher, 0 if existing else 1


def _ensure_identity(
    session: Session,
    researcher: Researcher,
    external_id: str,
    canonical_name: str,
    profile_url: str,
) -> None:
    identity = session.scalar(
        select(ResearcherIdentity).where(
            ResearcherIdentity.provider == "repec",
            ResearcherIdentity.external_id == external_id,
        )
    )
    if identity:
        identity.researcher_id = researcher.id
        identity.canonical_name = canonical_name
        identity.profile_url = profile_url
        identity.match_confidence = 0.99
        identity.ranking_percentile = 5.0
        identity.ranking_label = "Demo top 5%"
        return
    researcher.identities.append(
        ResearcherIdentity(
            provider="repec",
            external_id=external_id,
            canonical_name=canonical_name,
            profile_url=profile_url,
            match_confidence=0.99,
            ranking_percentile=5.0,
            ranking_label="Demo top 5%",
            metadata_json={"source": "demo_seed"},
        )
    )


def _ensure_source_document(
    session: Session,
    researcher: Researcher,
    url: str,
    title: str,
    extracted_text: str,
) -> SourceDocument:
    document = session.scalar(select(SourceDocument).where(SourceDocument.researcher_id == researcher.id, SourceDocument.url == url))
    if document:
        document.title = title
        document.extracted_text = extracted_text
        document.fetch_status = "fetched"
        return document
    document = SourceDocument(
        researcher_id=researcher.id,
        url=url,
        content_type="text/html",
        fetch_status="fetched",
        http_status=200,
        title=title,
        extracted_text=extracted_text,
        metadata_json={"source": "demo_seed", "linked_urls": []},
    )
    researcher.documents.append(document)
    session.flush()
    return document


def _upsert_talk_event(
    session: Session,
    researcher: Researcher,
    source_hash: str,
    source_name: str,
    title: str,
    city: str,
    country: str,
    starts_at: datetime,
    url: str,
) -> int:
    event = session.scalar(select(TalkEvent).where(TalkEvent.source_hash == source_hash))
    if event:
        event.researcher_id = researcher.id
        event.title = title
        event.speaker_affiliation = researcher.home_institution
        event.city = city
        event.country = country
        event.starts_at = starts_at
        event.url = url
        event.raw_payload = {"source": "demo_seed"}
        return 1
    session.add(
        TalkEvent(
            researcher_id=researcher.id,
            source_name=source_name,
            title=title,
            speaker_name=researcher.name,
            speaker_affiliation=researcher.home_institution,
            city=city,
            country=country,
            starts_at=starts_at,
            ends_at=None,
            url=url,
            source_hash=source_hash,
            raw_payload={"source": "demo_seed"},
        )
    )
    return 1
