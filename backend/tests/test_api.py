from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.core.config import settings
from app.services.enrichment import RefreshSummary
from app.services.ingestion import IngestSummary
from app.models.entities import (
    FactCandidate,
    Institution,
    InstitutionProfile,
    OpenSeminarWindow,
    OutreachDraft,
    Researcher,
    ResearcherFact,
    SeminarSlotOverride,
    SeminarSlotTemplate,
    SpeakerProfile,
    SourceHealthCheck,
    TalkEvent,
    TourLeg,
    TripCluster,
    TravelPriceCheck,
    WishlistEntry,
)
from app.services.audit import SourceAuditResult
from app.services.enrichment import normalize_name
from app.services.travel_prices import PriceQuote, PriceQuoteRequest, TravelPriceChecker


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
    assert "Biographic hook" not in draft_payload["body"]
    assert "Suggested email draft" not in draft_payload["body"]
    assert draft_payload["metadata_json"]["template_key"] == "kof_invitation"
    assert draft_payload["metadata_json"]["template_label"] == "KOF invitation"
    assert {fact["fact_type"] for fact in draft_payload["metadata_json"]["used_facts"]} == {"phd_institution", "nationality"}
    assert draft_payload["metadata_json"]["cost_share"]["recommendation"] == "strong"
    assert draft_payload["metadata_json"]["cost_share"]["estimated_savings_chf"] > 0
    assert {item["label"] for item in draft_payload["metadata_json"]["send_brief"]} >= {
        "Biographic hook",
        "Internal logistics note",
        "Suggested ask",
    }
    assert any(item["label"] == "Open KOF slot selected" for item in draft_payload["metadata_json"]["checklist"])
    suggested_email = draft_payload["body"]
    assert "we noticed that we noticed" not in suggested_email.lower()
    assert "cost" not in suggested_email.lower()
    assert "CHF" not in suggested_email
    assert "explore a suitable seminar date" not in suggested_email
    assert "16:15-17:30 Zurich time" in suggested_email
    assert "KOF in Zurich" in suggested_email
    assert "planned visits to Milan and Munich" in suggested_email
    assert "Cost-sharing estimate" not in draft_payload["body"]

    cost_share_response = client.post(
        "/api/outreach-drafts",
        json={"researcher_id": researcher_id, "trip_cluster_id": cluster_id, "template_key": "cost_share"},
    )
    assert cost_share_response.status_code == 200
    assert cost_share_response.json()["metadata_json"]["template_key"] == "kof_invitation"
    assert cost_share_response.json()["metadata_json"]["legacy_template_key"] == "cost_share"
    assert cost_share_response.json()["metadata_json"]["template_label"] == "KOF invitation"
    assert cost_share_response.json()["metadata_json"]["cost_share"]["recommended_mode"] == "rail"
    assert "Cost-sharing estimate" not in cost_share_response.json()["body"]
    assert "CHF" not in cost_share_response.json()["body"]
    assert cost_share_response.json()["body"] == draft_payload["body"]

    list_response = client.get("/api/outreach-drafts")
    assert list_response.status_code == 200
    drafts = list_response.json()
    assert len(drafts) == 2
    assert drafts[0]["researcher_name"] == "Prof. Elsa Example"
    assert drafts[0]["cluster_score"] == 95
    assert drafts[0]["template_label"] == "KOF invitation"

    status_response = client.patch(
        f"/api/outreach-drafts/{drafts[0]['id']}/status",
        json={
            "status": "reviewed",
            "note": "Ready for admin send",
            "checklist_confirmations": ["Recipient/name sanity check"],
        },
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "reviewed"
    assert status_payload["metadata_json"]["status_history"][-1]["to"] == "reviewed"

    reviewed_response = client.get("/api/outreach-drafts?status=reviewed")
    assert reviewed_response.status_code == 200
    reviewed_payload = reviewed_response.json()
    assert len(reviewed_payload) == 1
    assert reviewed_payload[0]["status"] == "reviewed"

    unreviewed_send_response = client.patch(
        f"/api/outreach-drafts/{drafts[1]['id']}/status",
        json={"status": "sent_manually", "send_confirmed": True},
    )
    assert unreviewed_send_response.status_code == 409

    sent_response = client.patch(
        f"/api/outreach-drafts/{drafts[0]['id']}/status",
        json={"status": "sent_manually", "send_confirmed": True, "note": "Sent outside the app."},
    )
    assert sent_response.status_code == 200
    assert sent_response.json()["status"] == "sent_manually"
    assert sent_response.json()["metadata_json"]["manual_send_confirmed_at"]

    bad_status_response = client.patch(
        f"/api/outreach-drafts/{drafts[0]['id']}/status",
        json={"status": "emailed"},
    )
    assert bad_status_response.status_code == 400


def test_opportunity_workbench_exposes_autonomy_assessment(client, db_session: Session) -> None:
    seed_researcher_graph(db_session)

    response = client.get("/api/opportunities/workbench")

    assert response.status_code == 200
    opportunity = response.json()["opportunities"][0]
    assessment = opportunity["automation_assessment"]
    assert assessment["score"] > 0
    assert assessment["next_action"]["label"]
    assert {signal["label"] for signal in assessment["signals"]} >= {
        "Approved evidence",
        "KOF slot fit",
        "Route logic",
    }
    assert assessment["can_build_tour_leg"] is True
    assert assessment["next_action"]["action_key"] == "propose_tour_leg"
    assert assessment["requires_human_approval"] is True


def test_autopilot_next_action_searches_trusted_evidence_when_facts_are_missing(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Evidence Missing",
        normalized_name=normalize_name("Prof. Evidence Missing"),
        home_institution="Boston University",
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 19).date(),
        end_date=datetime(2026, 5, 19).date(),
        itinerary=[
            {
                "city": "Milan",
                "starts_at": "2026-05-19T16:00:00+02:00",
                "title": "Bocconi seminar",
                "url": "https://example.test/milan",
                "source_name": "bocconi",
            }
        ],
        opportunity_score=70,
    )
    open_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 20, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 20, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Wednesday Seminar"},
    )
    db_session.add_all([researcher, cluster, open_window])
    db_session.commit()

    response = client.get("/api/opportunities/workbench")

    assert response.status_code == 200
    assessment = response.json()["opportunities"][0]["automation_assessment"]
    assert assessment["can_search_evidence"] is True
    assert assessment["next_action"]["action_key"] == "evidence_search"
    assert assessment["next_action"]["label"] == "Search trusted evidence"


def test_autopilot_flow_moves_from_price_refresh_to_draft_after_fare_check(client, db_session: Session) -> None:
    researcher_id, cluster_id = seed_researcher_graph(db_session)
    cluster = db_session.get(TripCluster, cluster_id)
    tour_leg = TourLeg(
        researcher_id=researcher_id,
        trip_cluster_id=cluster_id,
        title="Legacy route review without fare provenance",
        status="proposed",
        start_date=cluster.start_date,
        end_date=cluster.end_date,
        estimated_fee_total_chf=0,
        estimated_travel_total_chf=180,
        cost_split_json={
            "slot_starts_at": "2026-05-06T16:15:00+02:00",
            "components": [
                {
                    "payer": "KOF",
                    "category": "home_zurich_travel",
                    "route": "Milan -> Zurich",
                    "amount_chf": 180,
                    "mode": "rail",
                }
            ],
        },
        rationale=[],
    )
    db_session.add(tour_leg)
    db_session.commit()

    refresh_needed_response = client.get("/api/opportunities/workbench")
    refresh_needed = refresh_needed_response.json()["opportunities"][0]["automation_assessment"]

    assert refresh_needed_response.status_code == 200
    assert refresh_needed["can_refresh_prices"] is True
    assert refresh_needed["next_action"]["action_key"] == "refresh_prices"

    price_response = client.post(f"/api/tour-legs/{tour_leg.id}/refresh-prices")
    draft_ready_response = client.get("/api/opportunities/workbench")
    draft_ready = draft_ready_response.json()["opportunities"][0]["automation_assessment"]

    assert price_response.status_code == 200
    assert draft_ready_response.status_code == 200
    assert draft_ready["can_refresh_prices"] is False
    assert draft_ready["can_prepare_draft"] is True
    assert draft_ready["next_action"]["action_key"] == "create_draft"


def test_legacy_normal_draft_templates_are_normalized_to_one_kof_invitation(client, db_session: Session) -> None:
    researcher_id, cluster_id = seed_researcher_graph(db_session)

    responses = [
        client.post("/api/outreach-drafts", json={"researcher_id": researcher_id, "trip_cluster_id": cluster_id, "template_key": key})
        for key in ["concierge", "academic_home", "cost_share"]
    ]

    assert all(response.status_code == 200 for response in responses)
    payloads = [response.json() for response in responses]
    bodies = {payload["body"] for payload in payloads}
    assert len(bodies) == 1
    assert {payload["metadata_json"]["template_key"] for payload in payloads} == {"kof_invitation"}
    assert {payload["metadata_json"]["template_label"] for payload in payloads} == {"KOF invitation"}
    assert {payload["metadata_json"]["legacy_template_key"] for payload in payloads} == {"concierge", "academic_home", "cost_share"}
    assert "CHF" not in payloads[0]["body"]
    assert "cost" not in payloads[0]["body"].lower()
    assert "16:15-17:30 Zurich time" in payloads[0]["body"]


def test_europe_based_speaker_draft_does_not_claim_they_are_scheduled_to_be_in_europe(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Mirko Wiederholt",
        normalized_name=normalize_name("Mirko Wiederholt"),
        home_institution="Ludwig-Maximilians University of Munich",
    )
    researcher.facts = [
        ResearcherFact(
            fact_type="phd_institution",
            value="European University Institute",
            confidence=0.95,
            source_url="https://cepr.org/about/people/mirko-wiederholt",
            evidence_snippet="He obtained his PhD in Economics from the European University Institute.",
        ),
        ResearcherFact(
            fact_type="nationality",
            value="German",
            confidence=0.9,
            source_url="https://example.test/cv",
            evidence_snippet="Nationality: German.",
        ),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 12).date(),
        end_date=datetime(2026, 5, 12).date(),
        itinerary=[
            {
                "city": "Milan",
                "starts_at": "2026-05-12T16:00:00+02:00",
                "title": "Bocconi macro seminar",
                "url": "https://bocconi.example/mirko",
                "source_name": "bocconi",
            }
        ],
        opportunity_score=90,
    )
    window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 11, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 11, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Monday Seminar"},
    )
    db_session.add_all([researcher, cluster, window])
    db_session.commit()

    response = client.post("/api/outreach-drafts", json={"researcher_id": researcher.id, "trip_cluster_id": cluster.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["subject"] == "KOF Zurich seminar invitation around your Milan visit"
    assert "scheduled to be in Europe" not in payload["body"]
    assert "your planned visit to Milan" in payload["body"]
    assert "at KOF in Zurich around that trip" in payload["body"]


def test_draft_uses_same_best_slot_as_opportunity_workbench(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Felix Slot",
        normalized_name=normalize_name("Prof. Felix Slot"),
        home_institution="Yale",
    )
    researcher.facts = [
        ResearcherFact(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.92,
            source_url="https://cv.example/felix",
            evidence_snippet="PhD, University of Mannheim",
        ),
        ResearcherFact(
            fact_type="nationality",
            value="German",
            confidence=0.91,
            source_url="https://cv.example/felix",
            evidence_snippet="Nationality: German",
        ),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 10).date(),
        end_date=datetime(2026, 5, 12).date(),
        itinerary=[
            {"city": "Milan", "starts_at": "2026-05-10T16:00:00+02:00", "title": "Bocconi", "url": "x", "source_name": "bocconi"},
        ],
        rationale=[],
        opportunity_score=80,
    )
    best_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 8, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 8, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Friday Seminar"},
    )
    later_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 20, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 20, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Later Seminar"},
    )
    db_session.add_all([researcher, cluster, best_window, later_window])
    db_session.commit()

    workbench_response = client.get("/api/opportunities/workbench")
    draft_response = client.post(
        "/api/outreach-drafts",
        json={"researcher_id": researcher.id, "trip_cluster_id": cluster.id},
    )

    assert workbench_response.status_code == 200
    opportunity = workbench_response.json()["opportunities"][0]
    assert opportunity["best_window"]["id"] == best_window.id
    assert opportunity["best_window"]["fit_type"] == "nearby"
    assert draft_response.status_code == 200
    assert draft_response.json()["metadata_json"]["candidate_slot"]["id"] == best_window.id


def test_workbench_prefers_in_route_zurich_stop_between_ordered_stops(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Rahul Deb",
        normalized_name=normalize_name("Rahul Deb"),
        home_institution="Boston University",
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 13).date(),
        end_date=datetime(2026, 5, 19).date(),
        itinerary=[
            {
                "city": "Bonn",
                "starts_at": "2026-05-13T16:00:00+02:00",
                "title": "Bonn seminar",
                "url": "https://example.test/bonn",
                "source_name": "bonn",
            },
            {
                "city": "Milan",
                "starts_at": "2026-05-19T16:00:00+02:00",
                "title": "Bocconi seminar",
                "url": "https://example.test/milan",
                "source_name": "bocconi",
            },
        ],
        opportunity_score=90,
    )
    risky_arrival_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 12, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 12, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Tuesday Seminar"},
    )
    in_route_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 16, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 16, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Saturday Seminar"},
    )
    db_session.add_all([researcher, cluster, risky_arrival_window, in_route_window])
    db_session.commit()

    response = client.get("/api/opportunities/workbench")

    assert response.status_code == 200
    best_window = response.json()["opportunities"][0]["best_window"]
    assert best_window["id"] == in_route_window.id
    assert best_window["travel_fit_label"] == "In-route Zurich stop"
    assert best_window["travel_fit"]["previous_stop"]["city"] == "Bonn"
    assert best_window["travel_fit"]["next_stop"]["city"] == "Milan"


def test_workbench_avoids_day_before_first_stop_after_likely_long_haul_arrival(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Transatlantic Visitor",
        normalized_name=normalize_name("Prof. Transatlantic Visitor"),
        home_institution="Boston University",
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 19).date(),
        end_date=datetime(2026, 5, 19).date(),
        itinerary=[
            {
                "city": "Milan",
                "starts_at": "2026-05-19T16:00:00+02:00",
                "title": "Bocconi seminar",
                "url": "https://example.test/milan",
                "source_name": "bocconi",
            }
        ],
        opportunity_score=80,
    )
    day_before = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 18, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 18, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Monday Seminar"},
    )
    day_after = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 20, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 20, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Wednesday Seminar"},
    )
    db_session.add_all([researcher, cluster, day_before, day_after])
    db_session.commit()

    response = client.get("/api/opportunities/workbench")

    assert response.status_code == 200
    best_window = response.json()["opportunities"][0]["best_window"]
    assert best_window["id"] == day_after.id
    assert best_window["travel_fit_label"] == "Practical Zurich stop"
    assert "long-haul" not in best_window["travel_fit_summary"]


def test_route_review_warning_returns_action_and_resolves_after_tour_leg_review(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Route Warning",
        normalized_name=normalize_name("Prof. Route Warning"),
        home_institution="Boston University",
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 19).date(),
        end_date=datetime(2026, 5, 19).date(),
        itinerary=[
            {
                "city": "Milan",
                "starts_at": "2026-05-19T16:00:00+02:00",
                "title": "Bocconi seminar",
                "url": "https://example.test/milan",
                "source_name": "bocconi",
            }
        ],
        opportunity_score=80,
    )
    risky_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 18, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 18, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Monday Seminar"},
    )
    db_session.add_all([researcher, cluster, risky_window])
    db_session.commit()

    warning_response = client.get("/api/opportunities/workbench")
    warning = warning_response.json()["opportunities"][0]

    assert warning_response.status_code == 200
    assert warning["route_review_required"] is True
    assert warning["route_review_resolved"] is False
    assert warning["route_review_action"]["label"] == "Review route and cost split"
    assert warning["route_review_action"]["action_key"] == "propose_tour_leg"

    tour_leg_response = client.post("/api/tour-legs/propose", json={"trip_cluster_id": cluster.id})
    resolved_response = client.get("/api/opportunities/workbench")
    resolved = resolved_response.json()["opportunities"][0]

    assert tour_leg_response.status_code == 200
    assert resolved_response.status_code == 200
    assert resolved["route_review_required"] is True
    assert resolved["route_review_resolved"] is True
    assert resolved["latest_tour_leg_id"] == tour_leg_response.json()["id"]
    assert resolved["route_review_action"]["label"] == "Open route review"
    assert resolved["route_review_action"]["href"] == f"/tour-legs/{tour_leg_response.json()['id']}"


def test_draft_list_skips_orphaned_historical_rows(client, db_session: Session) -> None:
    db_session.add(
        OutreachDraft(
            researcher_id="missing-researcher",
            trip_cluster_id="missing-cluster",
            subject="Historical orphan",
            body="This row should not break the draft library.",
            status="draft",
            metadata_json={},
        )
    )
    db_session.commit()

    response = client.get("/api/outreach-drafts")

    assert response.status_code == 200
    assert response.json() == []


def test_enrichment_endpoint_adds_fact(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Bruno Test", normalized_name=normalize_name("Prof. Bruno Test"))
    db_session.add(researcher)
    db_session.commit()

    response = client.post(
        f"/api/researchers/{researcher.id}/enrich",
        json={
            "cv_text": "Nationality: Swiss. PhD in Economics from University of Mannheim.",
            "source_url": "https://cv.example/bruno",
            "evidence_snippet": "Manual review of Bruno Test CV.",
            "home_institution": "MIT",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    fact_types = {fact["fact_type"] for fact in payload["facts"]}
    assert {"phd_institution", "nationality"}.issubset(fact_types)

    manual_response = client.post(
        f"/api/researchers/{researcher.id}/enrich",
        json={
            "phd_institution": "University of Zurich",
            "nationality": "Swiss",
            "source_url": "https://profile.example/bruno",
            "evidence_snippet": "Profile lists Swiss nationality and University of Zurich PhD.",
        },
    )
    assert manual_response.status_code == 200
    manual_payload = manual_response.json()
    manual_fact = next(fact for fact in manual_payload["facts"] if fact["value"] == "University of Zurich")
    assert manual_fact["approval_origin"] == "manual"
    assert manual_fact["verified"] is True
    assert manual_fact["evidence_snippet"] == "Profile lists Swiss nationality and University of Zurich PhD."


def test_researcher_evidence_search_endpoint_runs_trusted_source_pipeline(client, db_session: Session, monkeypatch) -> None:
    researcher = Researcher(name="Prof. Mira Evidence", normalized_name=normalize_name("Prof. Mira Evidence"))
    db_session.add(researcher)
    db_session.commit()
    calls: list[str | None] = []

    class StubBiographerPipeline:
        def __init__(self, session: Session) -> None:
            self.session = session

        def search_trusted_evidence(self, researcher_id=None) -> RefreshSummary:
            calls.append(researcher_id)
            return RefreshSummary(processed_count=1, created_count=3, updated_count=4)

    monkeypatch.setattr("app.api.routes.BiographerPipeline", StubBiographerPipeline)

    response = client.post(f"/api/researchers/{researcher.id}/evidence-search")

    assert response.status_code == 200
    assert response.json() == {"processed_count": 1, "created_count": 3, "updated_count": 4}
    assert calls == [researcher.id]


def test_review_approval_can_merge_candidate_value(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Clara Merge", normalized_name=normalize_name("Prof. Clara Merge"))
    researcher.fact_candidates = [
        FactCandidate(
            fact_type="nationality",
            value="German citizen",
            confidence=0.82,
            evidence_snippet="German citizen",
            source_url="https://cv.example/clara",
            status="pending",
        )
    ]
    db_session.add(researcher)
    db_session.commit()
    candidate = researcher.fact_candidates[0]

    response = client.post(
        f"/api/review/facts/{candidate.id}/approve",
        json={"merged_value": "German", "note": "Normalized parser output."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["value"] == "German"
    approved_facts = db_session.query(ResearcherFact).filter(ResearcherFact.researcher_id == researcher.id).all()
    assert len(approved_facts) == 1
    assert approved_facts[0].value == "German"
    assert approved_facts[0].approval_origin == "review_queue"


def test_review_facts_endpoint_filters_review_history(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Filter Target", normalized_name=normalize_name("Prof. Filter Target"))
    researcher.fact_candidates = [
        FactCandidate(
            fact_type="nationality",
            value="German",
            confidence=0.91,
            evidence_snippet="Nationality: German",
            source_url="https://cv.example/filter",
            status="pending",
        ),
        FactCandidate(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.74,
            evidence_snippet="PhD: University of Mannheim",
            source_url="https://profile.example/filter",
            status="approved",
        ),
        FactCandidate(
            fact_type="birth_month",
            value="5",
            confidence=0.65,
            evidence_snippet="Born: May 1, 1980",
            source_url="https://cv.example/filter",
            status="rejected",
        ),
    ]
    db_session.add(researcher)
    db_session.commit()

    pending_response = client.get("/api/review/facts?status=pending&fact_type=nationality&min_confidence=0.9&source_contains=cv")
    all_response = client.get("/api/review/facts?status=all&source_contains=filter")
    rejected_response = client.get("/api/review/facts?status=rejected")
    bad_response = client.get("/api/review/facts?status=maybe")

    assert pending_response.status_code == 200
    assert len(pending_response.json()) == 1
    assert pending_response.json()[0]["fact_type"] == "nationality"
    assert all_response.status_code == 200
    assert len(all_response.json()) == 3
    assert rejected_response.status_code == 200
    assert rejected_response.json()[0]["status"] == "rejected"
    assert bad_response.status_code == 400


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


def test_api_access_token_protects_api_when_configured(client, monkeypatch) -> None:
    monkeypatch.setenv("ATG_API_ACCESS_TOKEN", "secret-token")

    health_response = client.get("/api/health")
    blocked_response = client.get("/api/researchers")
    allowed_response = client.get("/api/researchers", headers={"x-atg-api-key": "secret-token"})

    assert health_response.status_code == 200
    assert blocked_response.status_code == 401
    assert allowed_response.status_code == 200


def test_production_mode_uses_session_auth_without_legacy_edge_secrets(monkeypatch) -> None:
    monkeypatch.setenv("ROADSHOW_ENV", "production")
    monkeypatch.delenv("ROADSHOW_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ATG_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ROADSHOW_API_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ATG_API_ACCESS_TOKEN", raising=False)

    assert settings.production_validation_errors() == []


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


def test_source_health_reliability_flags_empty_implemented_sources(client, db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            SourceHealthCheck(
                source_name="implemented_pilot",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=4,
                samples=["2026-05-01 - Example Speaker"],
                checked_at=now - timedelta(hours=2),
            ),
            SourceHealthCheck(
                source_name="implemented_pilot",
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
    implemented_pilot = next(item for item in payload if item["source_name"] == "implemented_pilot")
    bis = next(item for item in payload if item["source_name"] == "bis")
    assert implemented_pilot["trend"] == "empty"
    assert implemented_pilot["needs_attention"] is True
    assert implemented_pilot["previous_event_count"] == 4
    assert implemented_pilot["last_event_count"] == 0
    assert "official_url" in implemented_pilot
    assert bis["trend"] == "new"
    assert bis["needs_attention"] is False


def test_source_health_treats_adapter_backlog_as_non_blocking(client, db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(
        SourceHealthCheck(
            source_name="pse",
            source_type="external_opportunity",
            status="error",
            page_count=0,
            event_count=0,
            samples=[],
            error="HTTPStatusError: 418",
            checked_at=now,
        )
    )
    db_session.commit()

    response = client.get("/api/source-health/reliability")

    assert response.status_code == 200
    pse = next(item for item in response.json() if item["source_name"] == "pse")
    assert pse["trend"] == "needs_adapter"
    assert pse["needs_adapter"] is True
    assert pse["needs_attention"] is False


def test_source_health_treats_host_calendar_count_drop_as_normal_change(client, db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            SourceHealthCheck(
                source_name="kof_host_calendar",
                source_type="host_calendar",
                status="ok",
                page_count=1,
                event_count=7,
                samples=[],
                checked_at=now - timedelta(hours=2),
            ),
            SourceHealthCheck(
                source_name="kof_host_calendar",
                source_type="host_calendar",
                status="ok",
                page_count=1,
                event_count=6,
                samples=[],
                checked_at=now,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/source-health/reliability")

    assert response.status_code == 200
    kof = next(item for item in response.json() if item["source_name"] == "kof_host_calendar")
    assert kof["trend"] == "changed"
    assert kof["needs_attention"] is False


def test_source_reliability_exposes_unimplemented_watchlist_sources(client) -> None:
    response = client.get("/api/source-health/reliability")

    assert response.status_code == 200
    payload = response.json()
    lse = next(item for item in payload if item["source_name"] == "lse")
    assert lse["latest_status"] == "not_checked"
    assert lse["needs_adapter"] is True
    assert lse["official_url"] == "https://www.lse.ac.uk/economics/events-and-seminars"
    assert lse["action_label"] == "Open official source"
    assert lse["action_href"] == "https://www.lse.ac.uk/economics/events-and-seminars"
    assert "verify" in lse["consequence"]


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
    assert opportunity["draft_blocker_details"] == []
    assert opportunity["best_window"]["fit_type"] == "overlap"
    assert opportunity["best_window"]["within_scoring_window"] is True
    assert opportunity["itinerary_cities"] == ["Milan", "Munich"]
    assert opportunity["draft_count"] == 0
    assert opportunity["cost_share"]["nearest_itinerary_city"] == "Milan"
    assert opportunity["cost_share"]["recommended_mode"] == "rail"
    assert opportunity["cost_share"]["estimated_savings_chf"] > opportunity["cost_share"]["multi_city_incremental_chf"]


def test_opportunity_workbench_returns_actionable_draft_blockers(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Blocked Speaker",
        normalized_name=normalize_name("Prof. Blocked Speaker"),
        home_institution="Yale",
    )
    pending = FactCandidate(
        researcher=researcher,
        fact_type="phd_institution",
        value="University of Mannheim",
        confidence=0.85,
        evidence_snippet="PhD, University of Mannheim",
        source_url="https://cv.example/blocked",
        status="pending",
        origin="cv_html",
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime.now(UTC).date() + timedelta(days=3),
        end_date=datetime.now(UTC).date() + timedelta(days=4),
        itinerary=[
            {
                "title": "Macro Networks",
                "city": "Milan",
                "country": "Italy",
                "starts_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "url": "https://example.edu/talk",
                "source_name": "bocconi",
            }
        ],
        opportunity_score=75,
    )
    db_session.add_all([researcher, pending, cluster])
    db_session.commit()

    response = client.get("/api/opportunities/workbench")

    assert response.status_code == 200
    opportunity = response.json()["opportunities"][0]
    assert opportunity["draft_ready"] is False
    assert opportunity["draft_blockers"] == [
        "Approve pending PhD institution: University of Mannheim",
        "Add approved nationality",
    ]
    assert opportunity["draft_blocker_details"][0]["code"] == "pending_fact_review"
    assert opportunity["draft_blocker_details"][0]["action_href"].startswith("/review?status=pending")
    assert opportunity["draft_blocker_details"][0]["pending_candidate_id"] == pending.id
    assert opportunity["draft_blocker_details"][1]["code"] == "missing_approved_fact"
    assert opportunity["draft_blocker_details"][1]["action_href"].endswith("#manual-facts")


def test_opportunity_workbench_excludes_past_clusters(client, db_session: Session) -> None:
    seed_researcher_graph(db_session)
    old_researcher = Researcher(
        name="Prof. Past Visitor",
        normalized_name=normalize_name("Prof. Past Visitor"),
        home_institution="Archive University",
    )
    old_start = datetime.now(UTC).date() - timedelta(days=30)
    db_session.add(old_researcher)
    db_session.flush()
    db_session.add(
        TripCluster(
            researcher_id=old_researcher.id,
            start_date=old_start,
            end_date=old_start,
            itinerary=[
                {
                    "title": "Past seminar",
                    "city": "Milan",
                    "country": "Italy",
                    "starts_at": datetime.combine(old_start, datetime.min.time(), tzinfo=UTC).isoformat(),
                    "url": "https://example.edu/past",
                    "source_name": "bocconi",
                }
            ],
            opportunity_score=100,
        )
    )
    db_session.commit()

    response = client.get("/api/opportunities/workbench")

    assert response.status_code == 200
    names = [item["researcher"]["name"] for item in response.json()["opportunities"]]
    assert "Prof. Past Visitor" not in names


def test_operator_runbook_summarizes_daily_admin_work(client, db_session: Session) -> None:
    researcher_id, cluster_id = seed_researcher_graph(db_session)
    db_session.add_all(
        [
            FactCandidate(
                researcher_id=researcher_id,
                fact_type="nationality",
                value="German",
                confidence=0.86,
                evidence_snippet="Nationality: German",
                source_url="https://cv.example/elsa",
            ),
            SourceHealthCheck(
                source_name="implemented_pilot",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=0,
                samples=[],
                checked_at=datetime.now(UTC),
            ),
        ]
    )
    db_session.commit()

    draft_response = client.post(
        "/api/outreach-drafts",
        json={"researcher_id": researcher_id, "trip_cluster_id": cluster_id},
    )
    assert draft_response.status_code == 200

    response = client.get("/api/operator/runbook")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_attention_count"] == 1
    assert payload["pending_fact_count"] == 1
    assert payload["draft_ready_opportunity_count"] == 1
    assert payload["open_window_count"] == 1
    assert payload["draft_counts_by_status"]["draft"] == 1
    assert [step["key"] for step in payload["recommended_steps"]] == [
        "source-audit",
        "fact-review",
        "opportunities",
        "draft-library",
    ]
    assert payload["recommended_steps"][0]["status"] == "needs_attention"


def test_calendar_overlay_is_read_only_by_default(client, db_session: Session, monkeypatch) -> None:
    db_session.add(
        OpenSeminarWindow(
            starts_at=datetime(2026, 5, 12, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
            ends_at=datetime(2026, 5, 12, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
            source="template",
            metadata_json={"label": "Existing KOF window"},
        )
    )
    db_session.commit()

    class ExplodingAvailabilityBuilder:
        def __init__(self, session: Session) -> None:
            self.session = session

        def rebuild_persisted(self):
            raise AssertionError("calendar overlay must not rebuild on a default GET")

    monkeypatch.setattr("app.api.routes.AvailabilityBuilder", ExplodingAvailabilityBuilder)
    response = client.get("/api/calendar/overlay")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["open_windows"]) == 1
    assert payload["open_windows"][0]["metadata_json"]["label"] == "Existing KOF window"


def test_calendar_overlay_can_rebuild_when_explicitly_requested(client, monkeypatch) -> None:
    calls: list[str] = []

    class StubAvailabilityBuilder:
        def __init__(self, session: Session) -> None:
            self.session = session

        def rebuild_persisted(self):
            calls.append("availability")
            window = OpenSeminarWindow(
                starts_at=datetime(2026, 5, 19, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
                ends_at=datetime(2026, 5, 19, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
                source="template",
                metadata_json={"label": "Explicit rebuild window"},
            )
            self.session.add(window)
            self.session.flush()
            return [window]

    class StubScorer:
        def __init__(self, session: Session) -> None:
            self.session = session

        def score_all_clusters(self):
            calls.append("scoring")
            return []

    monkeypatch.setattr("app.api.routes.AvailabilityBuilder", StubAvailabilityBuilder)
    monkeypatch.setattr("app.api.routes.Scorer", StubScorer)
    response = client.get("/api/calendar/overlay?rebuild=true")

    assert response.status_code == 200
    assert calls == ["availability", "scoring"]
    assert response.json()["open_windows"][0]["metadata_json"]["label"] == "Explicit rebuild window"


def test_operator_cockpit_prioritizes_admin_next_action(client, db_session: Session) -> None:
    researcher_id, _ = seed_researcher_graph(db_session)
    db_session.add_all(
        [
            FactCandidate(
                researcher_id=researcher_id,
                fact_type="nationality",
                value="German",
                confidence=0.86,
                evidence_snippet="Nationality: German",
                source_url="https://cv.example/elsa",
            ),
            SourceHealthCheck(
                source_name="bocconi",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=2,
                samples=["2026-05-03 - Prof. Elsa Example"],
                checked_at=datetime.now(UTC),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/operator/cockpit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["posture"] == "needs_attention"
    assert payload["summary_metrics"]["pending_evidence"] == 1
    assert payload["next_best_action"]["primary_action"]["label"] == "Approve evidence for outreach"
    assert [group["key"] for group in payload["groups"]] == [
        "freshness",
        "evidence",
        "calendar",
        "wishlist",
        "opportunity",
        "draft",
        "tour_leg",
        "feedback",
    ]
    evidence_group = next(group for group in payload["groups"] if group["key"] == "evidence")
    assert evidence_group["tasks"][0]["status"] == "blocks_outreach"


def test_operator_cockpit_guides_empty_database_to_real_sync(client) -> None:
    response = client.get("/api/operator/cockpit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_state"] == "empty"
    assert payload["primary_flow"]["label"] == "Run real source sync"
    assert payload["primary_flow"]["action_key"] == "real_sync"
    assert payload["setup_blockers"][0]["id"] == "run-real-source-sync"
    assert payload["source_snapshot"]["sources_tracked"] >= 5


def test_operator_cockpit_exposes_seeded_development_opportunity_path(client, monkeypatch) -> None:
    monkeypatch.setenv("ROADSHOW_ENABLE_DEMO_TOOLS", "true")
    seed_response = client.post("/api/jobs/seed-demo")
    cockpit_response = client.get("/api/operator/cockpit")
    workbench_response = client.get("/api/opportunities/workbench")

    assert seed_response.status_code == 200
    assert cockpit_response.status_code == 200
    cockpit = cockpit_response.json()
    assert cockpit["data_state"] in {"demo", "real", "stale"}
    assert cockpit["summary_metrics"]["speaker_visits"] >= 2
    assert cockpit["summary_metrics"]["active_kof_slots"] >= 1
    assert cockpit["primary_flow"]["label"] in {"Approve evidence", "Draft invitation", "Run real source sync"}

    assert workbench_response.status_code == 200
    assert workbench_response.json()["opportunities"]


def test_seed_demo_endpoint_is_hidden_without_development_flag(client) -> None:
    response = client.post("/api/jobs/seed-demo")
    assert response.status_code == 404


def test_operator_real_sync_reports_safe_pipeline(client, monkeypatch) -> None:
    class StubAuditor:
        def record(self, session: Session) -> list[SourceHealthCheck]:
            record = SourceHealthCheck(
                source_name="bocconi",
                source_type="external_opportunity",
                status="ok",
                page_count=1,
                event_count=3,
                samples=["2026-05-03 - Example"],
            )
            session.add(record)
            session.flush()
            return [record]

    class StubIngestion:
        def __init__(self, session: Session) -> None:
            self.session = session

        def sync_host_calendar(self) -> IngestSummary:
            return IngestSummary(source_counts={"kof_host_calendar": 2}, created_count=1, updated_count=1)

        def ingest_sources(self) -> IngestSummary:
            return IngestSummary(source_counts={"bocconi": 3, "bis": 1}, created_count=2, updated_count=2)

    class StubBiographerPipeline:
        def __init__(self, session: Session) -> None:
            self.session = session

        def sync_repec(self, researcher_id=None) -> RefreshSummary:
            return RefreshSummary(processed_count=2, created_count=1, updated_count=1)

        def sync_top_authors(self, limit=200) -> RefreshSummary:
            return RefreshSummary(processed_count=200, created_count=2, updated_count=198)

        def refresh(self, researcher_id=None) -> RefreshSummary:
            return RefreshSummary(processed_count=2, created_count=0, updated_count=2)

        def search_trusted_evidence(self, researcher_id=None) -> RefreshSummary:
            return RefreshSummary(processed_count=2, created_count=0, updated_count=2)

    class StubAvailability:
        def __init__(self, session: Session) -> None:
            self.session = session

        def rebuild_persisted(self) -> list:
            return []

    class StubScorer:
        def __init__(self, session: Session) -> None:
            self.session = session

        def score_all_clusters(self) -> list:
            return []

    monkeypatch.setattr("app.services.operator.SourceAuditor", StubAuditor)
    monkeypatch.setattr("app.services.operator.IngestionService", StubIngestion)
    monkeypatch.setattr("app.services.operator.BiographerPipeline", StubBiographerPipeline)
    monkeypatch.setattr("app.services.operator.AvailabilityBuilder", StubAvailability)
    monkeypatch.setattr("app.services.operator.Scorer", StubScorer)

    response = client.post("/api/operator/real-sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert [step["key"] for step in payload["steps"]] == [
        "source_audit",
        "kof_calendar",
        "speaker_visits",
        "repec_top_authors",
        "repec_sync",
        "evidence_search",
        "plausibility",
        "availability",
        "scoring",
        "wishlist_alerts",
        "wishlist_matches",
    ]
    assert payload["summary_metrics"]["created_count"] >= 4
    assert payload["summary_metrics"]["failed_steps"] == 0
    audit_events = client.get("/api/audit-events").json()
    assert audit_events[0]["event_type"] == "operator.real_sync"


def test_seminar_admin_can_update_and_delete_templates_and_overrides(client, db_session: Session) -> None:
    template = SeminarSlotTemplate(
        label="Old Seminar",
        weekday=1,
        start_time=datetime(2026, 5, 5, 16, 15).time(),
        end_time=datetime(2026, 5, 5, 17, 30).time(),
        timezone="Europe/Zurich",
    )
    override = SeminarSlotOverride(
        start_at=datetime(2026, 5, 5, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        end_at=datetime(2026, 5, 5, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        status="blocked",
        reason="Old block",
    )
    db_session.add_all([template, override])
    db_session.commit()

    template_response = client.patch(
        f"/api/seminar/templates/{template.id}",
        json={
            "label": "Updated Seminar",
            "weekday": 2,
            "start_time": "15:00:00",
            "end_time": "16:00:00",
            "timezone": "Europe/Zurich",
            "active": True,
        },
    )
    override_response = client.patch(
        f"/api/seminar/overrides/{override.id}",
        json={
            "start_at": "2026-05-06T15:00:00+02:00",
            "end_at": "2026-05-06T16:00:00+02:00",
            "status": "open",
            "reason": "Updated opening",
        },
    )
    delete_template_response = client.delete(f"/api/seminar/templates/{template.id}")
    delete_override_response = client.delete(f"/api/seminar/overrides/{override.id}")

    assert template_response.status_code == 200
    assert template_response.json()["label"] == "Updated Seminar"
    assert override_response.status_code == 200
    assert override_response.json()["status"] == "open"
    assert delete_template_response.status_code == 204
    assert delete_override_response.status_code == 204


def test_roadshow_branding_and_tables_exist(db_session: Session) -> None:
    assert settings.app_name == "Roadshow"
    table_names = set(inspect(db_session.bind).get_table_names())
    assert {
        "speaker_profiles",
        "institution_profiles",
        "wishlist_entries",
        "wishlist_alerts",
        "wishlist_match_groups",
        "wishlist_match_participants",
        "tour_assembly_proposals",
        "tour_legs",
        "tour_stops",
        "relationship_briefs",
        "feedback_signals",
        "audit_events",
    }.issubset(table_names)


def test_roadshow_profiles_wishlist_tour_leg_feedback_and_audit(client, db_session: Session) -> None:
    researcher_id, cluster_id = seed_researcher_graph(db_session)
    kof = db_session.query(Institution).filter(Institution.name == "KOF Swiss Economic Institute").one()

    speaker_profile_response = client.get(f"/api/speakers/{researcher_id}/profile")
    speaker_update_response = client.patch(
        f"/api/speakers/{researcher_id}/profile",
        json={
            "topics": ["macro networks", "regional policy"],
            "fee_floor_chf": 4200,
            "notice_period_days": 21,
            "travel_preferences": {"rail_first_under_hours": 4},
            "rider": {"hotel_tier": "business"},
            "availability_notes": "Prefers compact European legs.",
            "communication_preferences": {"tone": "concise"},
            "consent_status": "pre_consent",
            "verification_status": "shadow",
        },
    )
    institution_update_response = client.patch(
        f"/api/institutions/{kof.id}/profile",
        json={
            "wishlist_topics": ["macro networks"],
            "procurement_notes": "Keep v1 below PO threshold.",
            "po_threshold_chf": 5000,
            "grant_code_support": True,
            "coordinator_contacts": [{"name": "KOF Desk"}],
            "av_notes": "Hybrid ready.",
            "hospitality_notes": "Rail arrivals preferred.",
            "host_quality_score": 90,
        },
    )
    wishlist_response = client.post(
        "/api/wishlist",
        json={
            "institution_id": kof.id,
            "researcher_id": researcher_id,
            "speaker_name": "Prof. Elsa Example",
            "topic": "macro networks",
            "priority": 95,
            "status": "active",
            "notes": "Anchor Roadshow target.",
            "metadata_json": {},
        },
    )
    alerts_response = client.get("/api/wishlist-alerts")
    tour_leg_response = client.post("/api/tour-legs/propose", json={"trip_cluster_id": cluster_id, "fee_per_stop_chf": 3500})
    tour_leg_payload = tour_leg_response.json()
    relationship_response = client.patch(
        f"/api/relationship-briefs/{researcher_id}/{kof.id}",
        json={
            "summary": "Strong KOF fit; lead with compact itinerary and cost split.",
            "communication_preferences": {"tone": "warm"},
            "decision_patterns": {"hooks": ["cost split"]},
            "relationship_history": [],
            "operational_memory": {"venue": "KOF"},
            "forward_signals": {},
        },
    )
    feedback_response = client.post(
        "/api/feedback-signals",
        json={
            "researcher_id": researcher_id,
            "institution_id": kof.id,
            "tour_leg_id": tour_leg_payload["id"],
            "party": "institution",
            "signal_type": "rebook_intent",
            "value": "strong",
            "sentiment_score": 0.8,
            "notes": "Admin captured after demo.",
            "metadata_json": {},
        },
    )
    refreshed_relationship_response = client.get(f"/api/relationship-briefs/{researcher_id}/{kof.id}")

    assert speaker_profile_response.status_code == 200
    assert speaker_update_response.status_code == 200
    assert speaker_update_response.json()["fee_floor_chf"] == 4200
    assert institution_update_response.status_code == 200
    assert institution_update_response.json()["grant_code_support"] is True
    assert wishlist_response.status_code == 200
    assert alerts_response.status_code == 200
    assert alerts_response.json()[0]["researcher_name"] == "Prof. Elsa Example"
    assert "explicitly on the KOF Roadshow wishlist" in alerts_response.json()[0]["match_reason"]
    alert_id = alerts_response.json()[0]["id"]
    triage_response = client.patch(
        f"/api/wishlist-alerts/{alert_id}",
        json={"status": "reviewed", "note": "Useful match for the next KOF seminar slot."},
    )
    assert tour_leg_response.status_code == 200
    assert tour_leg_payload["cost_split_json"]["deterministic"] is True
    assert tour_leg_payload["cost_split_json"]["co_booking_stop_count"] == 3
    assert any(stop["city"] == "Zurich" and stop["format"] == "kof_seminar" for stop in tour_leg_payload["stops"])
    assert relationship_response.status_code == 200
    assert triage_response.status_code == 200
    assert triage_response.json()["status"] == "reviewed"
    assert triage_response.json()["resolved_at"] is not None
    assert feedback_response.status_code == 200
    assert refreshed_relationship_response.json()["forward_signals"]["rebook_intent"] == "strong"
    audit_response = client.get("/api/audit-events")
    assert {event["event_type"] for event in audit_response.json()} >= {
        "speaker_profile.updated",
        "institution_profile.updated",
        "wishlist_entry.created",
        "wishlist_alert.created",
        "wishlist_alert.status_updated",
        "tour_leg.proposed",
        "relationship_brief.updated",
        "feedback_signal.created",
    }


def test_tour_leg_splits_munich_zurich_milan_without_default_speaker_fee(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Mirko Wiederholt",
        normalized_name=normalize_name("Mirko Wiederholt"),
        home_institution="Ludwig-Maximilians University of Munich",
    )
    cluster = TripCluster(
        researcher=researcher,
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
        rationale=[],
        opportunity_score=90,
    )
    open_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 11, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 11, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "KOF Monday Seminar"},
    )
    db_session.add_all([researcher, cluster, open_window])
    db_session.commit()

    response = client.post("/api/tour-legs/propose", json={"trip_cluster_id": cluster.id})

    assert response.status_code == 200
    payload = response.json()
    cost_split = payload["cost_split_json"]
    assert payload["estimated_fee_total_chf"] == 0
    assert cost_split["speaker_fee_source"] == "not_assumed"
    assert cost_split["home_city"] == "Munich"
    assert cost_split["external_city"] == "Milan"
    assert cost_split["zurich_stop_position"] == "before_external"
    assert cost_split["kof_total_chf"] == cost_split["kof_travel_chf"] + cost_split["kof_hospitality_chf"]
    assert any(component["payer"] == "KOF" and component["route"] == "Munich -> Zurich" for component in cost_split["components"])
    assert any(component["payer"] == "Bocconi host" and component["route"] == "Zurich -> Milan" for component in cost_split["components"])
    rail_components = [component for component in cost_split["components"] if component["category"] != "zurich_hospitality"]
    hospitality_component = next(component for component in cost_split["components"] if component["category"] == "zurich_hospitality")
    assert all(component["fare_class"] == "first" for component in rail_components)
    assert all(component["fare_policy"] == "full_fare" for component in rail_components)
    assert all(component["price_status"] == "estimate_requires_review" for component in rail_components)
    assert all(component["action_href"] for component in rail_components)
    assert hospitality_component["price_status"] == "hospitality_estimate"
    assert hospitality_component["provider"] == "kof_hospitality_defaults"
    assert hospitality_component.get("mode") != "review"
    assert [stop["city"] for stop in payload["stops"]] == ["Zurich", "Milan"]
    assert payload["stops"][0]["travel_share_chf"] == cost_split["kof_total_chf"]
    assert payload["stops"][1]["travel_share_chf"] == cost_split["partner_total_chf"]

    price_checks_response = client.get(f"/api/travel-price-checks?tour_leg_id={payload['id']}")
    assert price_checks_response.status_code == 200
    assert len(price_checks_response.json()) >= 2
    refresh_response = client.post(f"/api/tour-legs/{payload['id']}/refresh-prices")
    assert refresh_response.status_code == 200
    refreshed_split = refresh_response.json()["cost_split_json"]
    assert refreshed_split["kof_total_chf"] == refreshed_split["kof_travel_chf"] + refreshed_split["kof_hospitality_chf"]
    assert all(
        component["price_status"] in {"estimate_requires_review", "hospitality_estimate"}
        for component in refreshed_split["components"]
    )


def test_travel_price_check_endpoint_falls_back_and_caches(client, monkeypatch) -> None:
    monkeypatch.delenv("OPENTRANSPORTDATA_API_TOKEN", raising=False)
    monkeypatch.delenv("RAIL_EUROPE_API_TOKEN", raising=False)
    monkeypatch.delenv("RAIL_EUROPE_API_BASE_URL", raising=False)

    payload = {
        "origin_city": "Zurich",
        "destination_city": "Milan",
        "departure_at": "2026-05-11T16:15:00+02:00",
    }
    first_response = client.post("/api/travel-price-checks", json=payload)
    second_response = client.post("/api/travel-price-checks", json=payload)
    forced_response = client.post("/api/travel-price-checks", json={**payload, "force_refresh": True})

    assert first_response.status_code == 200
    first = first_response.json()
    assert first["travel_class"] == "first"
    assert first["fare_policy"] == "full_fare"
    assert first["provider"] == "fallback_first_class_estimate"
    assert first["status"] == "estimate_requires_review"
    assert first["amount_chf"] >= 100
    assert first["action_href"]
    assert second_response.json()["id"] == first["id"]
    assert forced_response.status_code == 200
    assert forced_response.json()["id"] != first["id"]


def test_live_provider_updates_tour_leg_components(db_session: Session) -> None:
    class FakeLiveProvider:
        provider_name = "fake_live_provider"

        def quote(self, request: PriceQuoteRequest) -> PriceQuote:
            return PriceQuote(
                provider=self.provider_name,
                status="live",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_at=request.departure_at,
                travel_class=request.travel_class,
                fare_policy=request.fare_policy,
                amount=88.0,
                currency="CHF",
                amount_chf=88,
                confidence=0.95,
                source_url="https://provider.example/fare",
                action_href="https://provider.example/book",
                raw_summary={"fare": "mocked"},
            )

    researcher = Researcher(name="Live Fare Speaker", normalized_name=normalize_name("Live Fare Speaker"))
    tour_leg = TourLeg(
        researcher=researcher,
        title="Live Fare Roadshow leg",
        status="proposed",
        start_date=datetime(2026, 5, 11).date(),
        end_date=datetime(2026, 5, 11).date(),
        estimated_fee_total_chf=0,
        estimated_travel_total_chf=340,
        cost_split_json={
            "deterministic": True,
            "source": "test",
            "slot_starts_at": "2026-05-11T16:15:00+02:00",
            "kof_hospitality_chf": 340,
            "kof_total_chf": 340,
            "modeled_total_chf": 340,
            "components": [
                {
                    "payer": "KOF",
                    "category": "home_zurich_travel",
                    "route": "Zurich -> Bern",
                    "amount_chf": 0,
                    "mode": "rail",
                    "responsibility": "KOF rail leg.",
                },
                {
                    "payer": "KOF",
                    "category": "zurich_hospitality",
                    "route": "Zurich stay and dinner",
                    "amount_chf": 340,
                    "items": {"hotel_chf": 220, "dinner_chf": 90, "local_transport_chf": 30},
                    "responsibility": "KOF hospitality.",
                },
            ],
        },
        rationale=[],
    )
    db_session.add(tour_leg)
    db_session.flush()

    TravelPriceChecker(db_session, providers=[FakeLiveProvider()]).refresh_tour_leg(tour_leg, force=True)
    db_session.commit()

    component = tour_leg.cost_split_json["components"][0]
    hospitality = tour_leg.cost_split_json["components"][1]
    assert component["price_status"] == "live"
    assert component["amount_chf"] == 88
    assert component["fare_class"] == "first"
    assert component["fare_policy"] == "full_fare"
    assert component["provider"] == "fake_live_provider"
    assert hospitality["price_status"] == "hospitality_estimate"
    assert tour_leg.estimated_travel_total_chf == 428


def test_tour_leg_models_zurich_as_in_route_stop_between_bonn_and_milan(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Rahul Deb",
        normalized_name=normalize_name("Rahul Deb"),
        home_institution="Boston University",
    )
    cluster = TripCluster(
        researcher=researcher,
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
        opportunity_score=90,
    )
    in_route_window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 16, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 16, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
        metadata_json={"label": "Saturday Seminar"},
    )
    db_session.add_all([researcher, cluster, in_route_window])
    db_session.commit()

    response = client.post("/api/tour-legs/propose", json={"trip_cluster_id": cluster.id})

    assert response.status_code == 200
    payload = response.json()
    cost_split = payload["cost_split_json"]
    assert cost_split["zurich_stop_position"] == "between_external_stops"
    assert cost_split["previous_city"] == "Bonn"
    assert cost_split["next_city"] == "Milan"
    assert cost_split["kof_travel_chf"] == 0
    assert cost_split["kof_total_chf"] == cost_split["kof_hospitality_chf"]
    assert any(component["payer"] == "BONN host" and component["route"] == "Bonn -> Zurich" for component in cost_split["components"])
    assert any(component["payer"] == "Bocconi host" and component["route"] == "Zurich -> Milan" for component in cost_split["components"])
    assert [stop["city"] for stop in payload["stops"]] == ["Bonn", "Zurich", "Milan"]
    assert payload["stops"][0]["travel_share_chf"] == cost_split["external_leg_shares"]["bonn"]
    assert payload["stops"][1]["travel_share_chf"] == cost_split["kof_total_chf"]
    assert payload["stops"][2]["travel_share_chf"] == cost_split["external_leg_shares"]["milan"]


def _add_institution(
    db_session: Session,
    name: str,
    city: str,
    country: str,
    latitude: float,
    longitude: float,
    po_threshold_chf: int | None = None,
) -> Institution:
    institution = Institution(name=name, city=city, country=country, latitude=latitude, longitude=longitude, metadata_json={})
    db_session.add(institution)
    db_session.flush()
    if po_threshold_chf is not None:
        db_session.add(
            InstitutionProfile(
                institution_id=institution.id,
                wishlist_topics=[],
                po_threshold_chf=po_threshold_chf,
                grant_code_support=True,
                coordinator_contacts=[],
            )
        )
    return institution


def test_anonymous_wishlist_match_refresh_creates_masked_group_for_nearby_hosts(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Nearby Tour", normalized_name=normalize_name("Prof. Nearby Tour"))
    kof = db_session.query(Institution).filter(Institution.name == "KOF Swiss Economic Institute").one()
    basel = _add_institution(db_session, "Basel Policy Lab", "Basel", "Switzerland", 47.5596, 7.5886)
    db_session.add_all(
        [
            researcher,
            WishlistEntry(institution_id=kof.id, researcher=researcher, speaker_name=researcher.name, priority=90),
            WishlistEntry(institution_id=basel.id, researcher=researcher, speaker_name=researcher.name, priority=80),
        ]
    )
    db_session.commit()

    refresh_response = client.post("/api/wishlist-matches/refresh")
    second_refresh_response = client.post("/api/wishlist-matches/refresh")

    assert refresh_response.status_code == 200
    payload = refresh_response.json()
    assert len(payload) == 1
    assert payload[0]["display_speaker_name"] == "Prof. Nearby Tour"
    assert payload[0]["participant_count"] == 2
    assert {participant["masked_label"] for participant in payload[0]["participants"]} == {"KOF anchor", "Nearby institution 2"}
    assert "Basel Policy Lab" not in str(payload)
    assert second_refresh_response.status_code == 200
    assert len(second_refresh_response.json()) == 1
    assert len(client.get("/api/wishlist-matches").json()) == 1


def test_anonymous_wishlist_match_refresh_excludes_far_hosts(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Far Tour", normalized_name=normalize_name("Prof. Far Tour"))
    zurich = _add_institution(db_session, "Zurich Host", "Zurich", "Switzerland", 47.3769, 8.5417)
    london = _add_institution(db_session, "London Host", "London", "United Kingdom", 51.5072, -0.1276)
    db_session.add_all(
        [
            researcher,
            WishlistEntry(institution_id=zurich.id, researcher=researcher, speaker_name=researcher.name, priority=80),
            WishlistEntry(institution_id=london.id, researcher=researcher, speaker_name=researcher.name, priority=80),
        ]
    )
    db_session.commit()

    response = client.post("/api/wishlist-matches/refresh")

    assert response.status_code == 200
    assert response.json() == []


def test_anonymous_wishlist_match_resolves_researcher_id_and_normalized_speaker_name(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Ada Match", normalized_name=normalize_name("Prof. Ada Match"))
    zurich = _add_institution(db_session, "Zurich Research Forum", "Zurich", "Switzerland", 47.3769, 8.5417)
    winterthur = _add_institution(db_session, "Winterthur Economics Forum", "Winterthur", "Switzerland", 47.499, 8.724)
    db_session.add_all(
        [
            researcher,
            WishlistEntry(institution_id=zurich.id, researcher=researcher, priority=95),
            WishlistEntry(institution_id=winterthur.id, speaker_name="Prof. Ada Match", priority=70),
        ]
    )
    db_session.commit()

    response = client.post("/api/wishlist-matches/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["researcher_id"] == researcher.id
    assert payload[0]["participant_count"] == 2


def test_tour_assembly_proposal_records_budget_blockers(client, db_session: Session) -> None:
    researcher = Researcher(name="Prof. Budget Block", normalized_name=normalize_name("Prof. Budget Block"))
    researcher.speaker_profile = SpeakerProfile(
        topics=[],
        fee_floor_chf=6000,
        travel_preferences={},
        rider={},
        communication_preferences={},
    )
    zurich = _add_institution(db_session, "Budget Zurich Host", "Zurich", "Switzerland", 47.3769, 8.5417, po_threshold_chf=6500)
    basel = _add_institution(db_session, "Budget Basel Host", "Basel", "Switzerland", 47.5596, 7.5886, po_threshold_chf=1000)
    db_session.add_all(
        [
            researcher,
            TripCluster(
                researcher=researcher,
                start_date=datetime(2026, 6, 1).date(),
                end_date=datetime(2026, 6, 3).date(),
                itinerary=[{"city": "Milan", "starts_at": "2026-06-01T16:00:00+02:00", "title": "Talk", "url": "x", "source_name": "bocconi"}],
                opportunity_score=75,
            ),
            WishlistEntry(institution_id=zurich.id, researcher=researcher, priority=90),
            WishlistEntry(institution_id=basel.id, researcher=researcher, priority=90),
        ]
    )
    db_session.commit()
    match_group = client.post("/api/wishlist-matches/refresh").json()[0]

    response = client.post("/api/tour-assemblies/propose", json={"match_group_id": match_group["id"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert any(blocker["code"] == "host_budget_below_estimate" for blocker in payload["blockers"])
    assert "Budget Basel Host" not in str(payload)


def test_anonymous_tour_assembly_creates_speaker_tour_draft_when_evidence_is_approved(client, db_session: Session) -> None:
    researcher_id, _cluster_id = seed_researcher_graph(db_session)
    researcher = db_session.get(Researcher, researcher_id)
    kof = db_session.query(Institution).filter(Institution.name == "KOF Swiss Economic Institute").one()
    basel = _add_institution(db_session, "Ready Basel Host", "Basel", "Switzerland", 47.5596, 7.5886, po_threshold_chf=10000)
    db_session.add_all(
        [
            SpeakerProfile(
                researcher_id=researcher_id,
                topics=[],
                fee_floor_chf=4200,
                travel_preferences={},
                rider={},
                communication_preferences={},
            ),
            InstitutionProfile(
                institution_id=kof.id,
                wishlist_topics=[],
                po_threshold_chf=10000,
                grant_code_support=True,
                coordinator_contacts=[],
            ),
            WishlistEntry(institution_id=kof.id, researcher_id=researcher_id, speaker_name=researcher.name, priority=95),
            WishlistEntry(institution_id=basel.id, researcher_id=researcher_id, speaker_name=researcher.name, priority=85),
        ]
    )
    db_session.commit()
    match_group = client.post("/api/wishlist-matches/refresh").json()[0]
    proposal_response = client.post("/api/tour-assemblies/propose", json={"match_group_id": match_group["id"]})
    proposal = proposal_response.json()

    draft_response = client.post(f"/api/tour-assemblies/{proposal['id']}/speaker-draft")

    assert proposal_response.status_code == 200
    assert proposal["status"] == "ready_for_review"
    assert proposal["tour_leg_id"]
    assert proposal["budget_summary_json"]["deterministic"] is True
    assert "Ready Basel Host" not in str(proposal)
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["metadata_json"]["template_key"] == "multi_host_tour"
    assert draft["metadata_json"]["tour_assembly_proposal_id"] == proposal["id"]
    assert "multi-stop European tour" in draft["body"]
    assert "seminar hosts" in draft["body"]
