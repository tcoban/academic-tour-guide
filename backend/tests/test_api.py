from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.entities import OpenSeminarWindow, Researcher, ResearcherFact, TalkEvent, TripCluster
from app.services.enrichment import normalize_name


def seed_researcher_graph(db_session: Session) -> tuple[str, str]:
    researcher = Researcher(
        name="Prof. Elsa Example",
        normalized_name=normalize_name("Prof. Elsa Example"),
        home_institution="Yale",
        repec_rank=12.5,
    )
    researcher.facts = [
        ResearcherFact(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.92,
            source_url="https://cv.example/elsa",
            evidence_snippet="PhD, University of Mannheim",
        ),
        ResearcherFact(
            fact_type="nationality",
            value="German",
            confidence=0.91,
            source_url="https://cv.example/elsa",
            evidence_snippet="Nationality: German",
        ),
    ]
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="bocconi",
        title="Macro Networks",
        speaker_name=researcher.name,
        speaker_affiliation="Yale",
        city="Milan",
        country="Italy",
        starts_at=datetime(2026, 5, 3, 16, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://bocconi.example/macro-networks",
        source_hash="talk-event-api-1",
        raw_payload={"test": True},
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 3).date(),
        end_date=datetime(2026, 5, 8).date(),
        itinerary=[
            {"city": "Milan", "starts_at": "2026-05-03T16:00:00+02:00", "title": "Macro Networks", "url": "x", "source_name": "bocconi"},
            {"city": "Munich", "starts_at": "2026-05-08T12:30:00+02:00", "title": "Regional Policy", "url": "y", "source_name": "mannheim"},
        ],
        rationale=[],
        opportunity_score=95,
    )
    open_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 6, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 6, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Tuesday Seminar"},
    )
    db_session.add_all([researcher, talk_event, cluster, open_window])
    db_session.commit()
    return researcher.id, cluster.id


def test_daily_catch_and_draft_creation(client, db_session: Session) -> None:
    researcher_id, cluster_id = seed_researcher_graph(db_session)

    catch_response = client.get("/api/dashboard/daily-catch")
    assert catch_response.status_code == 200
    payload = catch_response.json()
    assert len(payload["recent_events"]) == 1
    assert len(payload["top_clusters"]) == 1

    draft_response = client.post(
        "/api/outreach-drafts",
        json={"researcher_id": researcher_id, "trip_cluster_id": cluster_id},
    )
    assert draft_response.status_code == 200
    draft_payload = draft_response.json()
    assert draft_payload["status"] == "draft"
    assert "Biographic hook" in draft_payload["body"]


def test_enrichment_endpoint_adds_fact(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Bruno Test", normalized_name=normalize_name("Prof. Bruno Test"))
    db_session.add(researcher)
    db_session.commit()

    response = client.post(
        f"/api/researchers/{researcher.id}/enrich",
        json={
            "cv_text": "Nationality: Swiss. PhD in Economics from University of Mannheim.",
            "source_url": "https://cv.example/bruno",
            "home_institution": "MIT",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    fact_types = {fact["fact_type"] for fact in payload["facts"]}
    assert {"phd_institution", "nationality"}.issubset(fact_types)

