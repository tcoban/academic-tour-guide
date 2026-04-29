from __future__ import annotations

from datetime import datetime, timedelta

from app.core.datetime import UTC
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.core.config import settings
from app.models.entities import (
    FactCandidate,
    Institution,
    OpenSeminarWindow,
    Researcher,
    ResearcherFact,
    SeminarSlotOverride,
    SeminarSlotTemplate,
    SourceHealthCheck,
    TalkEvent,
    TripCluster,
)
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
    assert "Suggested email draft" in draft_payload["body"]
    assert draft_payload["metadata_json"]["template_key"] == "concierge"
    assert {fact["fact_type"] for fact in draft_payload["metadata_json"]["used_facts"]} == {"phd_institution", "nationality"}
    assert draft_payload["metadata_json"]["cost_share"]["recommendation"] == "strong"
    assert draft_payload["metadata_json"]["cost_share"]["estimated_savings_chf"] > 0
    assert {item["label"] for item in draft_payload["metadata_json"]["send_brief"]} >= {
        "Biographic hook",
        "Logistics angle",
        "Suggested ask",
    }
    assert any(item["label"] == "Open KOF slot selected" for item in draft_payload["metadata_json"]["checklist"])

    cost_share_response = client.post(
        "/api/outreach-drafts",
        json={"researcher_id": researcher_id, "trip_cluster_id": cluster_id, "template_key": "cost_share"},
    )
    assert cost_share_response.status_code == 200
    assert cost_share_response.json()["metadata_json"]["template_key"] == "cost_share"
    assert cost_share_response.json()["metadata_json"]["cost_share"]["recommended_mode"] == "rail"
    assert "cost-sharing" in cost_share_response.json()["body"]
    assert "Cost-sharing estimate" in cost_share_response.json()["body"]

    list_response = client.get("/api/outreach-drafts")
    assert list_response.status_code == 200
    drafts = list_response.json()
    assert len(drafts) == 2
    assert drafts[0]["researcher_name"] == "Prof. Elsa Example"
    assert drafts[0]["cluster_score"] == 95
    assert drafts[0]["template_label"] in {"Concierge invitation", "Cost-sharing angle"}

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
    assert opportunity["cost_share"]["nearest_itinerary_city"] == "Milan"
    assert opportunity["cost_share"]["recommended_mode"] == "rail"
    assert opportunity["cost_share"]["estimated_savings_chf"] > opportunity["cost_share"]["multi_city_incremental_chf"]


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
                source_name="ecb",
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
    audit_response = client.get("/api/audit-events")

    assert speaker_profile_response.status_code == 200
    assert speaker_update_response.status_code == 200
    assert speaker_update_response.json()["fee_floor_chf"] == 4200
    assert institution_update_response.status_code == 200
    assert institution_update_response.json()["grant_code_support"] is True
    assert wishlist_response.status_code == 200
    assert alerts_response.status_code == 200
    assert alerts_response.json()[0]["researcher_name"] == "Prof. Elsa Example"
    assert "explicitly on the KOF Roadshow wishlist" in alerts_response.json()[0]["match_reason"]
    assert tour_leg_response.status_code == 200
    assert tour_leg_payload["cost_split_json"]["deterministic"] is True
    assert tour_leg_payload["cost_split_json"]["co_booking_stop_count"] == 3
    assert any(stop["city"] == "Zurich" and stop["format"] == "kof_seminar" for stop in tour_leg_payload["stops"])
    assert relationship_response.status_code == 200
    assert feedback_response.status_code == 200
    assert refreshed_relationship_response.json()["forward_signals"]["rebook_intent"] == "strong"
    assert {event["event_type"] for event in audit_response.json()} >= {
        "speaker_profile.updated",
        "institution_profile.updated",
        "wishlist_entry.created",
        "wishlist_alert.created",
        "tour_leg.proposed",
        "relationship_brief.updated",
        "feedback_signal.created",
    }
