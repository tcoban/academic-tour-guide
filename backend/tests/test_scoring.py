from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.entities import OpenSeminarWindow, Researcher, ResearcherFact, ResearcherIdentity, SpeakerProfile, TripCluster
from app.services.scoring import Scorer


def test_scoring_combines_all_major_signals(db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Alice Demo",
        normalized_name="prof alice demo",
        home_institution="MIT",
        repec_rank=4.2,
    )
    researcher.facts = [
        ResearcherFact(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.9,
            source_url="https://cv.example/alice",
            evidence_snippet="PhD in Economics, University of Mannheim",
        ),
        ResearcherFact(
            fact_type="nationality",
            value="German",
            confidence=0.9,
            source_url="https://cv.example/alice",
            evidence_snippet="Nationality: German",
        ),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 3).date(),
        end_date=datetime(2026, 5, 8).date(),
        itinerary=[
            {"city": "Milan", "starts_at": "2026-05-03T16:00:00+02:00", "title": "Bocconi", "url": "x", "source_name": "bocconi"},
            {"city": "Mannheim", "starts_at": "2026-05-08T12:30:00+02:00", "title": "Mannheim", "url": "y", "source_name": "mannheim"},
        ],
        rationale=[],
        opportunity_score=0,
    )
    db_session.add(researcher)
    db_session.add(cluster)
    db_session.add(
        OpenSeminarWindow(
            starts_at=datetime(2026, 5, 6, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
            ends_at=datetime(2026, 5, 6, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
            source="template",
            metadata_json={"label": "Tuesday Seminar"},
        )
    )
    db_session.commit()

    result = Scorer(db_session).score_cluster(cluster, researcher)
    assert result.score == 106
    assert {item["label"] for item in result.rationale} == {
        "Alumni Loop",
        "DACH Link",
        "Hub Proximity",
        "Travel Density",
        "Slot Fit",
        "Superstar Priority",
    }


def test_scoring_adds_kof_research_fit_and_superstar_priority(db_session: Session) -> None:
    researcher = Researcher(
        name="Daron Acemoglu",
        normalized_name="daron acemoglu",
        home_institution="MIT",
        repec_rank=0.0027,
    )
    researcher.identities = [
        ResearcherIdentity(
            provider="repec",
            external_id="pac16",
            canonical_name="Daron Acemoglu",
            profile_url="https://ideas.repec.org/e/pac16.html",
            match_confidence=1.0,
            ranking_percentile=0.0027,
            ranking_label="RePEc worldwide rank #2",
            metadata_json={"source": "repec_top_authors", "rank": 2},
        )
    ]
    researcher.speaker_profile = SpeakerProfile(
        topics=["political economy", "labour markets", "innovation and technology"],
        travel_preferences={},
        rider={},
        communication_preferences={},
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 4).date(),
        end_date=datetime(2026, 5, 4).date(),
        itinerary=[
            {
                "city": "London",
                "starts_at": "2026-05-04T16:00:00+02:00",
                "title": "Innovation, technology, wages and the future of labour markets",
                "url": "x",
                "source_name": "lse",
            }
        ],
        rationale=[],
        opportunity_score=0,
    )
    db_session.add_all([researcher, cluster])
    db_session.commit()

    result = Scorer(db_session).score_cluster(cluster, researcher)
    rationale = {item["label"]: item for item in result.rationale}

    assert result.score == 40
    assert rationale["KOF Research Fit"]["points"] == 15
    assert "Swiss Labour Market" in rationale["KOF Research Fit"]["detail"]
    assert rationale["Superstar Priority"]["points"] == 25
    assert "rank #2" in rationale["Superstar Priority"]["detail"]
