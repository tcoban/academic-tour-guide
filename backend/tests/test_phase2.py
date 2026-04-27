from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import FactCandidate, OpenSeminarWindow, Researcher, ResearcherFact, SourceDocument, TalkEvent, TripCluster
from app.services.enrichment import Biographer, BiographerPipeline, normalize_name
from app.services.repec import RepecMatch
from app.services.review import FactReviewService
from app.services.scoring import Scorer


class StubRepecClient:
    def search_author(self, _: str) -> RepecMatch:
        return RepecMatch(
            external_id="par7",
            canonical_name="Alice Example",
            profile_url="https://ideas.repec.org/e/par7.html",
            match_confidence=0.97,
            ranking_percentile=4.2,
            ranking_label="Top 5%",
            metadata_json={"source": "stub"},
        )


def test_repec_identity_sync_prevents_duplicate_researchers_for_name_variants(db_session: Session) -> None:
    biographer = Biographer(db_session)
    primary = biographer.get_or_create_researcher("Prof. Alice Example", home_institution="MIT")
    pipeline = BiographerPipeline(
        db_session,
        repec_client=StubRepecClient(),
        document_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))),
    )

    summary = pipeline.sync_repec(primary.id)
    matched = biographer.get_or_create_researcher("Alice Example", home_institution="MIT", repec_external_id="par7")

    assert summary.created_count == 1
    assert matched.id == primary.id
    assert db_session.query(Researcher).count() == 1


def test_biographer_refresh_discovers_documents_and_extracts_candidates(db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Alice Example",
        normalized_name=normalize_name("Prof. Alice Example"),
        home_institution="Yale University",
    )
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="bocconi",
        title="Networks in Macro",
        speaker_name=researcher.name,
        speaker_affiliation="Yale University",
        city="Milan",
        country="Italy",
        starts_at=datetime(2026, 5, 3, 16, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://dept.example/seminars/alice",
        source_hash="phase2-talk-1",
        raw_payload={},
    )
    db_session.add_all([researcher, talk_event])
    db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://dept.example/seminars/alice":
            html = """
            <html><head><title>Seminar</title></head><body>
            <a href="/people/alice-cv.html">Curriculum Vitae</a>
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        if str(request.url) == "https://ideas.repec.org/e/par7.html":
            html = """
            <html><head><title>IDEAS profile</title></head><body>
            Terminal Degree: University of Mannheim
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        if str(request.url) == "https://dept.example/people/alice-cv.html":
            html = """
            <html><head><title>Alice CV</title></head><body>
            Nationality: German
            Born: May 12, 1980
            Assistant Professor at Yale University
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        raise AssertionError(f"Unexpected URL fetched during test: {request.url}")

    pipeline = BiographerPipeline(
        db_session,
        repec_client=StubRepecClient(),
        document_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    summary = pipeline.refresh(researcher.id)

    candidates = db_session.scalars(select(FactCandidate).where(FactCandidate.researcher_id == researcher.id)).all()
    candidate_types = {candidate.fact_type for candidate in candidates}

    assert summary.processed_count == 1
    assert db_session.query(SourceDocument).count() >= 2
    assert {"phd_institution", "nationality", "birth_month", "home_institution"}.issubset(candidate_types)


def test_pending_evidence_contributes_to_score_but_blocks_outreach(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Carla Pending",
        normalized_name=normalize_name("Prof. Carla Pending"),
        home_institution="MIT",
    )
    researcher.fact_candidates = [
        FactCandidate(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.84,
            evidence_snippet="Terminal Degree: University of Mannheim",
            source_url="https://ideas.repec.org/e/par7.html",
            status="pending",
            origin="repec_profile",
        ),
        FactCandidate(
            fact_type="nationality",
            value="German",
            confidence=0.82,
            evidence_snippet="Nationality: German",
            source_url="https://cv.example/carla",
            status="pending",
            origin="cv_html",
        ),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 3).date(),
        end_date=datetime(2026, 5, 8).date(),
        itinerary=[
            {"city": "Milan", "starts_at": "2026-05-03T16:00:00+02:00", "title": "Bocconi", "url": "x", "source_name": "bocconi"},
            {"city": "Munich", "starts_at": "2026-05-08T12:30:00+02:00", "title": "Munich", "url": "y", "source_name": "mannheim"},
        ],
        rationale=[],
        opportunity_score=0,
    )
    db_session.add_all(
        [
            researcher,
            cluster,
            OpenSeminarWindow(
                starts_at=datetime(2026, 5, 6, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
                ends_at=datetime(2026, 5, 6, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
                source="template",
                metadata_json={"label": "Tuesday Seminar"},
            ),
        ]
    )
    db_session.commit()

    result = Scorer(db_session).score_cluster(cluster, researcher)
    db_session.commit()

    response = client.post("/api/outreach-drafts", json={"researcher_id": researcher.id, "trip_cluster_id": cluster.id})

    assert result.score == 100
    assert cluster.uses_unreviewed_evidence is True
    assert response.status_code == 409
    assert "requires approval" in response.json()["detail"]


def test_approved_candidates_enable_draft_generation(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Dana Review",
        normalized_name=normalize_name("Prof. Dana Review"),
        home_institution="MIT",
    )
    researcher.fact_candidates = [
        FactCandidate(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.84,
            evidence_snippet="Terminal Degree: University of Mannheim",
            source_url="https://ideas.repec.org/e/par7.html",
            status="pending",
            origin="repec_profile",
        ),
        FactCandidate(
            fact_type="nationality",
            value="German",
            confidence=0.82,
            evidence_snippet="Nationality: German",
            source_url="https://cv.example/dana",
            status="pending",
            origin="cv_html",
        ),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 3).date(),
        end_date=datetime(2026, 5, 8).date(),
        itinerary=[
            {"city": "Milan", "starts_at": "2026-05-03T16:00:00+02:00", "title": "Bocconi", "url": "x", "source_name": "bocconi"},
            {"city": "Munich", "starts_at": "2026-05-08T12:30:00+02:00", "title": "Munich", "url": "y", "source_name": "mannheim"},
        ],
        rationale=[],
        opportunity_score=0,
    )
    db_session.add_all(
        [
            researcher,
            cluster,
            OpenSeminarWindow(
                starts_at=datetime(2026, 5, 6, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
                ends_at=datetime(2026, 5, 6, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
                source="template",
                metadata_json={"label": "Tuesday Seminar"},
            ),
        ]
    )
    db_session.commit()

    review_service = FactReviewService(db_session)
    for candidate in researcher.fact_candidates:
        review_service.approve(candidate)
    Scorer(db_session).score_cluster(cluster, researcher)
    db_session.commit()

    response = client.post("/api/outreach-drafts", json={"researcher_id": researcher.id, "trip_cluster_id": cluster.id})
    researcher_facts = db_session.scalars(select(ResearcherFact).where(ResearcherFact.researcher_id == researcher.id)).all()

    assert response.status_code == 200
    assert "Biographic hook" in response.json()["body"]
    assert {fact.fact_type for fact in researcher_facts} == {"phd_institution", "nationality"}
