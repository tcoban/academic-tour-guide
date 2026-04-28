from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.entities import OpenSeminarWindow, Researcher, ResearcherFact, SourceHealthCheck, TalkEvent, TripCluster
from app.services.audit import SourceAuditResult
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
    assert draft_payload["metadata_json"]["template_key"] == "concierge"
    assert {fact["fact_type"] for fact in draft_payload["metadata_json"]["used_facts"]} == {"phd_institution", "nationality"}
    assert any(item["label"] == "Open KOF slot selected" for item in draft_payload["metadata_json"]["checklist"])

    cost_share_response = client.post(
        "/api/outreach-drafts",
        json={"researcher_id": researcher_id, "trip_cluster_id": cluster_id, "template_key": "cost_share"},
    )
    assert cost_share_response.status_code == 200
    assert cost_share_response.json()["metadata_json"]["template_key"] == "cost_share"
    assert "cost-sharing" in cost_share_response.json()["body"]

    list_response = client.get("/api/outreach-drafts")
    assert list_response.status_code == 200
    drafts = list_response.json()
    assert len(drafts) == 2
    assert drafts[0]["researcher_name"] == "Prof. Elsa Example"
    assert drafts[0]["cluster_score"] == 95
    assert drafts[0]["template_label"] in {"Concierge invitation", "Cost-sharing angle"}


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


def test_source_health_endpoint_reports_audit_results(client, monkeypatch) -> None:
    class StubAuditor:
        def audit(self) -> list[SourceAuditResult]:
            return [
                SourceAuditResult(
                    source_name="kof_host_calendar",
                    source_type="host_calendar",
                    status="ok",
                    page_count=1,
                    event_count=7,
                    samples=["2026-04-29 - KOF Research Seminar"],
                )
            ]

    monkeypatch.setattr("app.api.routes.SourceAuditor", StubAuditor)
    response = client.get("/api/source-health")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["source_name"] == "kof_host_calendar"
    assert payload[0]["event_count"] == 7
    assert payload[0]["source_type"] == "host_calendar"


def test_source_health_history_lists_persisted_records(client, db_session: Session) -> None:
    db_session.add(
        SourceHealthCheck(
            source_name="bis",
            source_type="external_opportunity",
            status="ok",
            page_count=1,
            event_count=2,
            samples=["2026-05-26 - Klaus Adam - Heterogeneity and Inflation"],
        )
    )
    db_session.commit()

    response = client.get("/api/source-health/history")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["source_name"] == "bis"
    assert payload[0]["event_count"] == 2
    assert payload[0]["samples"] == ["2026-05-26 - Klaus Adam - Heterogeneity and Inflation"]


def test_audit_sources_job_records_results(client, monkeypatch) -> None:
    class StubAuditor:
        def record(self, session: Session) -> list[SourceHealthCheck]:
            record = SourceHealthCheck(
                source_name="bocconi",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=6,
                samples=["2026-06-03 - Nikita Melnikov - Gang Crackdowns"],
            )
            session.add(record)
            session.flush()
            return [record]

    monkeypatch.setattr("app.api.routes.SourceAuditor", StubAuditor)
    response = client.post("/api/jobs/audit-sources")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["source_name"] == "bocconi"
    assert payload[0]["event_count"] == 6


def test_source_health_reliability_flags_degrading_sources(client, db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            SourceHealthCheck(
                source_name="ecb",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=4,
                samples=["2026-05-01 - Example Speaker"],
                checked_at=now - timedelta(hours=2),
            ),
            SourceHealthCheck(
                source_name="ecb",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=0,
                samples=[],
                checked_at=now,
            ),
            SourceHealthCheck(
                source_name="bis",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=2,
                samples=["2026-05-26 - Klaus Adam"],
                checked_at=now,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/source-health/reliability")
    assert response.status_code == 200
    payload = response.json()
    ecb = next(item for item in payload if item["source_name"] == "ecb")
    bis = next(item for item in payload if item["source_name"] == "bis")
    assert ecb["trend"] == "empty"
    assert ecb["needs_attention"] is True
    assert ecb["previous_event_count"] == 4
    assert bis["trend"] == "new"
    assert bis["needs_attention"] is False


def test_opportunity_workbench_returns_best_slot_and_draft_readiness(client, db_session: Session) -> None:
    seed_researcher_graph(db_session)

    response = client.get("/api/opportunities/workbench")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["opportunities"]) == 1
    opportunity = payload["opportunities"][0]
    assert opportunity["researcher"]["name"] == "Prof. Elsa Example"
    assert opportunity["draft_ready"] is True
    assert opportunity["draft_blockers"] == []
    assert opportunity["best_window"]["fit_type"] == "overlap"
    assert opportunity["best_window"]["within_scoring_window"] is True
    assert opportunity["itinerary_cities"] == ["Milan", "Munich"]
    assert opportunity["draft_count"] == 0
