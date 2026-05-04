from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, FactCandidate, OpenSeminarWindow, Researcher, ResearcherFact, SourceDocument, TripCluster
from app.services.ai import AIAutopilotPlanner, AIEvidenceAssistant, AIResearchFitExplainer, RoadshowAIService
from app.services.enrichment import normalize_name


class FakeAIClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def generate_json(self, prompt: str, model_name: str | None = None) -> dict:
        return self.payload


def enable_ai(monkeypatch, feature: str) -> None:
    monkeypatch.setenv("ROADSHOW_AI_ENABLED", "true")
    monkeypatch.setenv(feature, "true")


def test_ai_evidence_creates_pending_candidate_from_source_document(monkeypatch, db_session: Session) -> None:
    enable_ai(monkeypatch, "ROADSHOW_AI_EVIDENCE_ENABLED")
    researcher = Researcher(name="Jane Evidence", normalized_name=normalize_name("Jane Evidence"))
    document = SourceDocument(
        researcher=researcher,
        url="https://example.edu/jane/cv.pdf",
        content_type="application/pdf",
        fetch_status="fetched",
        extracted_text="Jane Evidence earned her PhD from University of Mannheim before joining Example University.",
        metadata_json={"source": "institution_profile"},
    )
    db_session.add_all([researcher, document])
    db_session.commit()

    service = AIEvidenceAssistant(
        db_session,
        RoadshowAIService(
            db_session,
            client=FakeAIClient(
                {
                    "facts": [
                        {
                            "fact_type": "phd_institution",
                            "value": "University of Mannheim",
                            "confidence": 0.91,
                            "evidence_snippet": "earned her PhD from University of Mannheim",
                        }
                    ]
                }
            ),
        ),
    )

    summary = service.search_researcher(researcher)
    candidates = db_session.scalars(select(FactCandidate).where(FactCandidate.researcher_id == researcher.id)).all()

    assert summary == {"processed_count": 1, "created_count": 1, "updated_count": 0}
    assert len(candidates) == 1
    assert candidates[0].origin == "ai_evidence"
    assert candidates[0].status == "pending"
    assert candidates[0].source_document_id == document.id
    assert not researcher.facts


def test_ai_evidence_rejects_candidates_without_verbatim_snippet(monkeypatch, db_session: Session) -> None:
    enable_ai(monkeypatch, "ROADSHOW_AI_EVIDENCE_ENABLED")
    researcher = Researcher(name="No Snippet", normalized_name=normalize_name("No Snippet"))
    document = SourceDocument(
        researcher=researcher,
        url="https://example.edu/no-snippet",
        fetch_status="fetched",
        extracted_text="This profile only says the person is a professor.",
        metadata_json={"source": "institution_profile"},
    )
    db_session.add_all([researcher, document])
    db_session.commit()

    summary = AIEvidenceAssistant(
        db_session,
        RoadshowAIService(
            db_session,
            client=FakeAIClient(
                {
                    "facts": [
                        {
                            "fact_type": "nationality",
                            "value": "German",
                            "confidence": 0.9,
                            "evidence_snippet": "Nationality: German",
                        }
                    ]
                }
            ),
        ),
    ).search_researcher(researcher)

    assert summary["created_count"] == 0
    assert db_session.scalars(select(FactCandidate)).all() == []


def test_ai_research_fit_adds_zero_point_explanation_without_changing_score(monkeypatch, db_session: Session) -> None:
    enable_ai(monkeypatch, "ROADSHOW_AI_FIT_ENABLED")
    researcher = Researcher(
        name="Fit Scholar",
        normalized_name=normalize_name("Fit Scholar"),
        home_institution="Example University",
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 12).date(),
        end_date=datetime(2026, 5, 12).date(),
        itinerary=[{"city": "Milan", "starts_at": "2026-05-12T16:00:00+02:00", "title": "Macroeconomic forecasting", "url": "x", "source_name": "bocconi"}],
        opportunity_score=77,
        rationale=[{"label": "Deterministic Fit", "points": 10, "detail": "forecasting"}],
    )
    db_session.add_all([researcher, cluster])
    db_session.commit()

    AIResearchFitExplainer(
        db_session,
        RoadshowAIService(db_session, client=FakeAIClient({"explanation": "The talk fits forecasting priorities.", "confidence": 0.8})),
    ).explain(cluster)

    assert cluster.opportunity_score == 77
    ai_entries = [entry for entry in cluster.rationale if entry["label"] == "AI Research Fit Explanation"]
    assert ai_entries
    assert ai_entries[0]["points"] == 0
    assert ai_entries[0]["ai_generated"] is True


def test_ai_draft_endpoint_uses_approved_context_and_blocks_cost_language(monkeypatch, client, db_session: Session) -> None:
    enable_ai(monkeypatch, "ROADSHOW_AI_DRAFT_ENABLED")

    from app.services.ai import VertexGeminiClient

    def fake_generate_json(self, prompt: str, model_name: str | None = None) -> dict:
        return {
            "body": (
                "Dear Professor Example,\n\n"
                "We would be pleased to invite you to give a research seminar at KOF in Zurich. "
                "The slot we have in mind is Wednesday, 06 May 2026, 16:15-17:30 Zurich time.\n\n"
                "With best regards,\nThe KOF seminar team\n"
            )
        }

    monkeypatch.setattr(VertexGeminiClient, "generate_json", fake_generate_json)
    researcher = Researcher(name="Prof. Draft Example", normalized_name=normalize_name("Prof. Draft Example"), home_institution="Yale")
    researcher.facts = [
        ResearcherFact(fact_type="phd_institution", value="University of Mannheim", confidence=0.92, source_url="x", evidence_snippet="PhD"),
        ResearcherFact(fact_type="nationality", value="German", confidence=0.91, source_url="x", evidence_snippet="German"),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 3).date(),
        end_date=datetime(2026, 5, 8).date(),
        itinerary=[{"city": "Milan", "starts_at": "2026-05-03T16:00:00+02:00", "title": "Macro", "url": "x", "source_name": "bocconi"}],
        opportunity_score=88,
    )
    window = OpenSeminarWindow(
        starts_at=datetime(2026, 5, 6, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=datetime(2026, 5, 6, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
        source="template",
    )
    db_session.add_all([researcher, cluster, window])
    db_session.commit()

    response = client.post(
        "/api/outreach-drafts",
        json={"researcher_id": researcher.id, "trip_cluster_id": cluster.id, "use_ai": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata_json"]["ai_generated_body"] is True
    assert "16:15-17:30 Zurich time" in payload["body"]
    assert "CHF" not in payload["body"]
    assert "cost" not in payload["body"].lower()


def test_ai_autopilot_rejects_non_executable_action(monkeypatch, db_session: Session) -> None:
    enable_ai(monkeypatch, "ROADSHOW_AI_AUTOPILOT_ENABLED")
    cockpit = {
        "primary_flow": {
            "label": "Run real source sync",
            "consequence": "Refreshes watched sources.",
            "action_key": "real_sync",
            "href": None,
            "disabled_reason": None,
        },
        "setup_blockers": [],
        "groups": [],
    }
    planner = AIAutopilotPlanner(
        db_session,
        RoadshowAIService(
            db_session,
            client=FakeAIClient(
                {
                    "explanation": "Try an unsafe action.",
                    "action": {"label": "Send external emails", "action_key": "send_email", "href": None},
                }
            ),
        ),
    )

    plan = planner.plan(cockpit)

    assert plan["status"] == "invalid_ai_action"
    assert plan["action"]["action_key"] == "real_sync"
    assert db_session.scalars(select(AuditEvent).where(AuditEvent.event_type == "ai.autopilot_plan")).first()
