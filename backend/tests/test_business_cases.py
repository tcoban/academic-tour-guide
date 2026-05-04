from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.entities import (
    OpenSeminarWindow,
    OutreachDraft,
    Researcher,
    ResearcherFact,
    ResearcherIdentity,
    TalkEvent,
    TourLeg,
    TravelPriceCheck,
    TripCluster,
)
from app.services.business_cases import BusinessCaseService
from app.services.enrichment import normalize_name


def _approved_fact(fact_type: str, value: str) -> ResearcherFact:
    return ResearcherFact(
        fact_type=fact_type,
        value=value,
        confidence=0.95,
        source_url="https://evidence.example/profile",
        evidence_snippet=f"{fact_type}: {value}",
        verified=True,
        approval_origin="manual",
    )


def test_business_case_shadow_audit_persists_results_without_operational_side_effects(
    client,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(BusinessCaseService, "_run_shadow_pipeline", lambda self, researcher, spec: None)
    tz = ZoneInfo("Europe/Zurich")

    mirko = Researcher(
        name="Mirko Wiederholt",
        normalized_name=normalize_name("Mirko Wiederholt"),
        home_institution="Ludwig-Maximilians University of Munich",
    )
    mirko.facts = [
        _approved_fact("phd_institution", "European University Institute"),
        _approved_fact("nationality", "German"),
    ]
    mirko_cluster = TripCluster(
        researcher=mirko,
        start_date=datetime(2026, 5, 12).date(),
        end_date=datetime(2026, 5, 12).date(),
        itinerary=[
            {
                "city": "Milan",
                "country": "Italy",
                "starts_at": "2026-05-12T16:00:00+02:00",
                "title": "Bocconi macro seminar",
                "url": "https://bocconi.example/mirko",
                "source_name": "bocconi",
            }
        ],
        opportunity_score=75,
        rationale=[],
    )

    rahul = Researcher(
        name="Rahul Deb",
        normalized_name=normalize_name("Rahul Deb"),
        home_institution="Boston University",
    )
    rahul_cluster = TripCluster(
        researcher=rahul,
        start_date=datetime(2026, 5, 13).date(),
        end_date=datetime(2026, 5, 19).date(),
        itinerary=[
            {
                "city": "Bonn",
                "country": "Germany",
                "starts_at": "2026-05-13T16:00:00+02:00",
                "title": "Bonn seminar",
                "url": "https://bonn.example/rahul",
                "source_name": "bonn",
            },
            {
                "city": "Milan",
                "country": "Italy",
                "starts_at": "2026-05-19T16:00:00+02:00",
                "title": "Bocconi seminar",
                "url": "https://bocconi.example/rahul",
                "source_name": "bocconi",
            },
        ],
        opportunity_score=80,
        rationale=[],
    )

    daron = Researcher(
        name="Daron Acemoglu",
        normalized_name=normalize_name("Daron Acemoglu"),
        home_institution="MIT",
    )
    daron.identities = [
        ResearcherIdentity(
            provider="repec",
            external_id="pac16",
            canonical_name="Daron Acemoglu",
            profile_url="https://ideas.repec.org/e/pac16.html",
            match_confidence=0.99,
            ranking_percentile=0.01,
            ranking_label="Top 1%",
            metadata_json={"rank": 1},
        )
    ]

    weak_fit = Researcher(name="Parser Noise", normalized_name=normalize_name("Parser Noise"))
    weak_cluster = TripCluster(
        researcher=weak_fit,
        start_date=datetime(2026, 6, 1).date(),
        end_date=datetime(2026, 6, 1).date(),
        itinerary=[
            {
                "city": "London",
                "country": "United Kingdom",
                "starts_at": "2026-06-01T12:00:00+01:00",
                "title": "Unrelated seminar",
                "url": "https://source.example/noise",
                "source_name": "source",
            }
        ],
        opportunity_score=1,
        rationale=[],
    )
    weak_event = TalkEvent(
        researcher=weak_fit,
        source_name="source",
        title="Unrelated seminar",
        speaker_name="Parser Noise",
        speaker_affiliation=None,
        city="London",
        country="United Kingdom",
        starts_at=datetime(2026, 6, 1, 12, 0, tzinfo=tz),
        url="https://source.example/noise",
        source_hash="business-case-negative-control",
        raw_payload={},
    )

    db_session.add_all(
        [
            mirko,
            mirko_cluster,
            rahul,
            rahul_cluster,
            daron,
            weak_fit,
            weak_cluster,
            weak_event,
            OpenSeminarWindow(
                starts_at=datetime(2026, 5, 11, 16, 15, tzinfo=tz),
                ends_at=datetime(2026, 5, 11, 17, 30, tzinfo=tz),
                source="template",
                metadata_json={"label": "Monday Seminar"},
            ),
            OpenSeminarWindow(
                starts_at=datetime(2026, 5, 12, 16, 15, tzinfo=tz),
                ends_at=datetime(2026, 5, 12, 17, 30, tzinfo=tz),
                source="template",
                metadata_json={"label": "Risky Arrival Slot"},
            ),
            OpenSeminarWindow(
                starts_at=datetime(2026, 5, 16, 16, 15, tzinfo=tz),
                ends_at=datetime(2026, 5, 16, 17, 30, tzinfo=tz),
                source="template",
                metadata_json={"label": "In Route Slot"},
            ),
        ]
    )
    db_session.commit()

    response = client.post("/api/business-cases/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "shadow"
    assert len(payload["results"]) == 4

    results = {result["case_key"]: result for result in payload["results"]}
    mirko_result = results["mirko_wiederholt"]
    rahul_result = results["rahul_deb"]
    daron_result = results["daron_acemoglu"]
    negative_result = results["negative_control:auto_selected_from_real_sources"]

    assert mirko_result["draft_status"] == "allowed_shadow_preview"
    assert "scheduled to be in Europe" not in mirko_result["draft_gate_json"]["body_preview"]
    assert "CHF" not in mirko_result["draft_gate_json"]["body_preview"]

    assert rahul_result["route_summary_json"]["best_window"]["starts_at"].startswith("2026-05-16")
    assert rahul_result["route_summary_json"]["travel_fit"]["previous_stop"]["city"] == "Bonn"
    assert rahul_result["route_summary_json"]["travel_fit"]["next_stop"]["city"] == "Milan"
    assert rahul_result["draft_status"] == "blocked_preview"

    assert daron_result["kof_fit_status"] == "medium"
    assert daron_result["fit_summary_json"]["superstar_priority"] is True
    assert daron_result["verdict"] == "blocked_no_current_trip"

    assert negative_result["verdict"] == "blocked_low_kof_fit"
    assert negative_result["blockers"]
    assert all(blocker["action_label"] and blocker["consequence"] for blocker in negative_result["blockers"])

    assert db_session.query(OutreachDraft).count() == 0
    assert db_session.query(TourLeg).count() == 0
    assert db_session.query(TravelPriceCheck).count() == 0


def test_business_case_scenario_route_is_shadow_only(client, db_session: Session, monkeypatch) -> None:
    monkeypatch.setattr(BusinessCaseService, "_run_shadow_pipeline", lambda self, researcher, spec: None)
    db_session.add(
        Researcher(
            name="Rahul Deb",
            normalized_name=normalize_name("Rahul Deb"),
            home_institution="Boston University",
        )
    )
    db_session.commit()

    before_clusters = db_session.query(TripCluster).count()
    response = client.post("/api/business-cases/run")
    after_clusters = db_session.query(TripCluster).count()

    assert response.status_code == 200
    rahul_result = next(result for result in response.json()["results"] if result["case_key"] == "rahul_deb")
    assert rahul_result["metadata_json"]["scenario_used"] is True
    assert rahul_result["route_summary_json"]["best_window"]["starts_at"].startswith("2026-05-16")
    assert after_clusters == before_clusters
