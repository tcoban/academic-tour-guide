from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.entities import AuditEvent, Researcher, SourceDocument, TripCluster
from app.services.enrichment import Biographer, CandidateFact
from app.services.tenancy import get_session_tenant


DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
ALLOWED_AI_FACT_TYPES = {"phd_institution", "nationality", "birth_month", "home_institution", "research_topic", "field"}
NORMAL_DRAFT_BANNED_TERMS = ("CHF", "cost", "costs", "fare", "fares", "savings", "cost-sharing", "cost sharing")
ALLOWED_AUTOPILOT_ACTIONS = {
    "real_sync",
    "morning_sweep",
    "evidence_search",
    "biographer_refresh",
    "review_evidence",
    "set_host_slot",
    "propose_tour_leg",
    "refresh_prices",
    "create_draft",
    "review_draft",
    "capture_feedback",
    "open_workspace",
}


class AIClient(Protocol):
    def generate_json(self, prompt: str, model_name: str | None = None) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class GeminiGenerationResult:
    text: str
    model_name: str


@dataclass(slots=True)
class AIJsonResult:
    payload: dict[str, Any]
    status: str
    model_name: str
    audit_event_id: str | None = None
    error: str | None = None


def build_gemini_model(model_name: str | None = None):
    import vertexai
    from vertexai.generative_models import GenerativeModel

    vertexai.init(project="kof-gcloud", location="europe-west6")
    return GenerativeModel(model_name or settings.vertex_model or DEFAULT_GEMINI_MODEL)


class VertexGeminiClient:
    def generate_text(self, prompt: str, model_name: str | None = None) -> GeminiGenerationResult:
        selected_model = model_name or settings.vertex_model or DEFAULT_GEMINI_MODEL
        response = build_gemini_model(selected_model).generate_content(prompt)
        return GeminiGenerationResult(text=getattr(response, "text", "") or "", model_name=selected_model)

    def generate_json(self, prompt: str, model_name: str | None = None) -> dict[str, Any]:
        selected_model = model_name or settings.vertex_model or DEFAULT_GEMINI_MODEL
        response = build_gemini_model(selected_model).generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        return _parse_json_payload(getattr(response, "text", "") or "{}")


class RoadshowAIService:
    def __init__(self, session: Session, client: AIClient | None = None) -> None:
        self.session = session
        self.tenant = get_session_tenant(session)
        self.client = client or VertexGeminiClient()

    def generate_json(
        self,
        *,
        prompt_type: str,
        prompt: str,
        entity_type: str,
        entity_id: str,
        input_source_ids: list[str],
        feature_enabled: bool,
        fallback: dict[str, Any],
    ) -> AIJsonResult:
        model_name = settings.vertex_model or DEFAULT_GEMINI_MODEL
        if not feature_enabled:
            event = self._record_event(
                prompt_type=prompt_type,
                model_name=model_name,
                entity_type=entity_type,
                entity_id=entity_id,
                input_source_ids=input_source_ids,
                status="skipped",
                output_summary={"reason": "feature_disabled"},
                error=None,
            )
            return AIJsonResult(payload=fallback, status="skipped", model_name=model_name, audit_event_id=event.id)

        try:
            payload = self._generate_json_with_timeout(prompt, model_name)
        except Exception as error:  # pragma: no cover - exercised with provider outages
            event = self._record_event(
                prompt_type=prompt_type,
                model_name=model_name,
                entity_type=entity_type,
                entity_id=entity_id,
                input_source_ids=input_source_ids,
                status="error",
                output_summary={},
                error=str(error),
            )
            return AIJsonResult(payload=fallback, status="error", model_name=model_name, audit_event_id=event.id, error=str(error))

        event = self._record_event(
            prompt_type=prompt_type,
            model_name=model_name,
            entity_type=entity_type,
            entity_id=entity_id,
            input_source_ids=input_source_ids,
            status="ok",
            output_summary=_summarize_payload(payload),
            error=None,
        )
        return AIJsonResult(payload=payload, status="ok", model_name=model_name, audit_event_id=event.id)

    def _record_event(
        self,
        *,
        prompt_type: str,
        model_name: str,
        entity_type: str,
        entity_id: str,
        input_source_ids: list[str],
        status: str,
        output_summary: dict[str, Any],
        error: str | None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=self.tenant.id,
            event_type=f"ai.{prompt_type}",
            actor_type="ai",
            entity_type=entity_type,
            entity_id=entity_id,
            payload={
                "prompt_type": prompt_type,
                "model_name": model_name,
                "input_source_ids": input_source_ids,
                "output_summary": output_summary,
                "status": status,
                "error": error,
            },
        )
        self.session.add(event)
        self.session.flush()
        return event

    def _generate_json_with_timeout(self, prompt: str, model_name: str) -> dict[str, Any]:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.client.generate_json, prompt, model_name)
        try:
            return future.result(timeout=settings.ai_timeout_seconds)
        except FuturesTimeoutError as error:
            future.cancel()
            raise TimeoutError(f"AI provider timed out after {settings.ai_timeout_seconds} seconds") from error
        finally:
            executor.shutdown(wait=False, cancel_futures=True)


class AIEvidenceAssistant:
    def __init__(self, session: Session, ai_service: RoadshowAIService | None = None) -> None:
        self.session = session
        self.ai = ai_service or RoadshowAIService(session)

    def search_researcher(self, researcher: Researcher) -> dict[str, int]:
        documents = [
            document
            for document in self.session.scalars(
                select(SourceDocument)
                .where(SourceDocument.researcher_id == researcher.id)
                .order_by(SourceDocument.created_at.desc())
            ).all()
            if self._usable_document(document)
        ]
        created = 0
        updated = 0
        biographer = Biographer(self.session)
        for document in documents:
            result = self.ai.generate_json(
                prompt_type="evidence_assistant",
                prompt=self._prompt(researcher, document),
                entity_type="researcher",
                entity_id=researcher.id,
                input_source_ids=[document.id],
                feature_enabled=settings.ai_evidence_enabled,
                fallback={"facts": []},
            )
            for fact in self._valid_facts(result.payload, document):
                was_existing = self._candidate_exists(researcher, fact["fact_type"], fact["value"])
                biographer.store_candidate_fact(
                    researcher=researcher,
                    candidate=CandidateFact(
                        fact_type=fact["fact_type"],
                        value=fact["value"],
                        confidence=fact["confidence"],
                        evidence_snippet=fact["evidence_snippet"],
                        origin="ai_evidence",
                    ),
                    source_url=document.url,
                    source_document=document,
                    status="pending",
                )
                if was_existing:
                    updated += 1
                else:
                    created += 1
        return {"processed_count": len(documents), "created_count": created, "updated_count": updated}

    def refresh_all(self, researcher_id: str | None = None) -> dict[str, int]:
        query = select(Researcher).options(selectinload(Researcher.documents))
        if researcher_id:
            query = query.where(Researcher.id == researcher_id)
        summary = {"processed_count": 0, "created_count": 0, "updated_count": 0}
        for researcher in self.session.scalars(query).all():
            result = self.search_researcher(researcher)
            summary["processed_count"] += result["processed_count"]
            summary["created_count"] += result["created_count"]
            summary["updated_count"] += result["updated_count"]
        return summary

    def _usable_document(self, document: SourceDocument) -> bool:
        metadata = document.metadata_json or {}
        return (
            document.fetch_status == "fetched"
            and bool(document.extracted_text)
            and metadata.get("source") != "manual_profile_link"
            and metadata.get("plausibility_status") not in {"quarantined", "skipped"}
        )

    def _prompt(self, researcher: Researcher, document: SourceDocument) -> str:
        text = (document.extracted_text or "")[:12000]
        return (
            "You are Roadshow's evidence assistant. Extract only facts that are explicitly supported by the source text. "
            "Return strict JSON with key facts as an array. Allowed fact_type values are "
            f"{sorted(ALLOWED_AI_FACT_TYPES)}. Each fact must include fact_type, value, confidence from 0 to 1, and evidence_snippet copied verbatim from the text. "
            "If no supported fact exists, return {\"facts\": []}.\n\n"
            f"Researcher: {researcher.name}\n"
            f"Source URL: {document.url}\n"
            f"Source text:\n{text}"
        )

    def _valid_facts(self, payload: dict[str, Any], document: SourceDocument) -> list[dict[str, Any]]:
        facts = payload.get("facts")
        if not isinstance(facts, list):
            return []
        valid: list[dict[str, Any]] = []
        for raw in facts:
            if not isinstance(raw, dict):
                continue
            fact_type = str(raw.get("fact_type") or "").strip()
            value = str(raw.get("value") or "").strip()
            snippet = str(raw.get("evidence_snippet") or "").strip()
            if fact_type not in ALLOWED_AI_FACT_TYPES or not value or not snippet:
                continue
            if not _contains_snippet(document.extracted_text or "", snippet):
                continue
            valid.append(
                {
                    "fact_type": fact_type,
                    "value": value[:255],
                    "confidence": _bounded_confidence(raw.get("confidence")),
                    "evidence_snippet": snippet[:1000],
                }
            )
        return valid

    def _candidate_exists(self, researcher: Researcher, fact_type: str, value: str) -> bool:
        normalized = value.strip().lower()
        return any(
            candidate.fact_type == fact_type and candidate.value.strip().lower() == normalized
            for candidate in researcher.fact_candidates
        )


class AIResearchFitExplainer:
    def __init__(self, session: Session, ai_service: RoadshowAIService | None = None) -> None:
        self.session = session
        self.tenant = get_session_tenant(session)
        self.ai = ai_service or RoadshowAIService(session)

    def explain(self, cluster: TripCluster) -> dict[str, Any]:
        researcher = cluster.researcher or self.session.get(Researcher, cluster.researcher_id)
        if not researcher:
            return {"status": "missing_researcher", "detail": "No researcher is attached to this opportunity."}
        original_score = cluster.opportunity_score
        context = self._context(cluster, researcher)
        fallback = {"explanation": "insufficient evidence", "confidence": 0}
        result = self.ai.generate_json(
            prompt_type="research_fit_explainer",
            prompt=self._prompt(context),
            entity_type="trip_cluster",
            entity_id=cluster.id,
            input_source_ids=[cluster.id],
            feature_enabled=settings.ai_fit_enabled,
            fallback=fallback,
        )
        explanation = str(result.payload.get("explanation") or "insufficient evidence").strip()[:1200]
        confidence = _bounded_confidence(result.payload.get("confidence"))
        if not explanation or confidence < 0.2:
            explanation = "insufficient evidence"
        rationale = [entry for entry in (cluster.rationale or []) if entry.get("label") != "AI Research Fit Explanation"]
        rationale.append(
            {
                "label": "AI Research Fit Explanation",
                "points": 0,
                "detail": explanation,
                "ai_generated": result.status == "ok",
                "ai_status": result.status,
                "model_name": result.model_name,
                "audit_event_id": result.audit_event_id,
                "confidence": confidence,
            }
        )
        cluster.rationale = rationale
        cluster.opportunity_score = original_score
        self.session.add(cluster)
        self.session.flush()
        return {"status": result.status, "detail": explanation, "audit_event_id": result.audit_event_id}

    def _context(self, cluster: TripCluster, researcher: Researcher) -> dict[str, Any]:
        facts = [
            {"fact_type": fact.fact_type, "value": fact.value, "approved": True}
            for fact in researcher.facts
            if fact.fact_type in {"research_topic", "field", "home_institution"}
        ]
        facts.extend(
            {"fact_type": candidate.fact_type, "value": candidate.value, "approved": False}
            for candidate in researcher.fact_candidates
            if candidate.fact_type in {"research_topic", "field", "home_institution"} and candidate.status == "pending"
        )
        return {
            "tenant_name": self.tenant.name,
            "research_focuses": self.tenant.settings.research_focuses if self.tenant.settings else [],
            "researcher_name": researcher.name,
            "home_institution": researcher.home_institution,
            "speaker_topics": researcher.speaker_profile.topics if researcher.speaker_profile else [],
            "talk_titles": [item.get("title") for item in cluster.itinerary],
            "deterministic_rationale": cluster.rationale or [],
            "research_facts": facts,
            "repec_rank": researcher.repec_rank,
        }

    def _prompt(self, context: dict[str, Any]) -> str:
        return (
            "Explain whether the speaker's work fits the host institution's research priorities. "
            "Do not assign score points. Do not invent publications, fields, or affiliations. "
            "If the supplied context is weak, answer with explanation='insufficient evidence'. "
            "Return strict JSON with keys explanation and confidence.\n\n"
            f"Context JSON:\n{json.dumps(context, default=str, ensure_ascii=True)}"
        )


class AIDraftAssistant:
    def __init__(self, session: Session, ai_service: RoadshowAIService | None = None) -> None:
        self.session = session
        self.ai = ai_service or RoadshowAIService(session)

    def suggest_body(
        self,
        *,
        researcher: Researcher,
        cluster: TripCluster,
        deterministic_body: str,
        factual_context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        context_hash = sha256(json.dumps(factual_context, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        result = self.ai.generate_json(
            prompt_type="draft_body",
            prompt=self._prompt(factual_context, deterministic_body),
            entity_type="trip_cluster",
            entity_id=cluster.id,
            input_source_ids=[cluster.id],
            feature_enabled=settings.ai_draft_enabled,
            fallback={"body": deterministic_body},
        )
        body = str(result.payload.get("body") or deterministic_body).strip()
        validation_error = self._validation_error(body, factual_context)
        if validation_error:
            return deterministic_body, {
                "ai_generated_body": False,
                "ai_status": "rejected",
                "ai_rejection_reason": validation_error,
                "model_name": result.model_name,
                "factual_context_hash": context_hash,
                "audit_event_id": result.audit_event_id,
            }
        return body, {
            "ai_generated_body": result.status == "ok",
            "ai_status": result.status,
            "model_name": result.model_name,
            "factual_context_hash": context_hash,
            "audit_event_id": result.audit_event_id,
        }

    def _prompt(self, factual_context: dict[str, Any], deterministic_body: str) -> str:
        return (
            "Write one professional, precise, friendly academic seminar invitation email. "
            "Use only the supplied factual context. Do not add facts, affiliations, publications, money, fares, costs, savings, or cost-sharing. "
            "Use the exact proposed seminar slot. Do not say a Europe-based speaker is scheduled to be in Europe. "
            "Return strict JSON with one key: body.\n\n"
            f"Factual context JSON:\n{json.dumps(factual_context, default=str, ensure_ascii=True)}\n\n"
            f"Deterministic baseline body:\n{deterministic_body}"
        )

    def _validation_error(self, body: str, factual_context: dict[str, Any]) -> str | None:
        if not body:
            return "empty_body"
        lowered = body.lower()
        for term in NORMAL_DRAFT_BANNED_TERMS:
            if term.lower() in lowered:
                return f"banned_term:{term}"
        if "scheduled to be in europe" in lowered:
            return "bad_europe_visit_language"
        slot_text = str(factual_context.get("slot") or "")
        if slot_text and not any(part and part in body for part in re.findall(r"\b\d{1,2}:\d{2}\b|\b20\d{2}\b", slot_text)):
            return "missing_specific_slot"
        return None


class AIAutopilotPlanner:
    def __init__(self, session: Session, ai_service: RoadshowAIService | None = None) -> None:
        self.session = session
        self.ai = ai_service or RoadshowAIService(session)

    def plan(self, cockpit: dict[str, Any]) -> dict[str, Any]:
        available_actions = self._available_actions(cockpit)
        fallback_action = cockpit.get("primary_flow") or {}
        fallback = {
            "status": "deterministic",
            "explanation": "Using the deterministic Roadshow next action.",
            "action": fallback_action,
        }
        result = self.ai.generate_json(
            prompt_type="autopilot_plan",
            prompt=self._prompt(cockpit, available_actions),
            entity_type="operator",
            entity_id="cockpit",
            input_source_ids=[str(item.get("id") or item.get("label")) for item in available_actions],
            feature_enabled=settings.ai_autopilot_enabled,
            fallback=fallback,
        )
        payload_action = result.payload.get("action") if isinstance(result.payload.get("action"), dict) else {}
        validated = self._validate_action(payload_action, available_actions)
        if not validated:
            return {
                "status": "invalid_ai_action" if result.status == "ok" else result.status,
                "explanation": "Roadshow kept the deterministic next action because the AI suggestion was not executable.",
                "action": fallback_action,
                "audit_event_id": result.audit_event_id,
            }
        return {
            "status": result.status,
            "explanation": str(result.payload.get("explanation") or "Roadshow AI selected a validated next action."),
            "action": validated,
            "audit_event_id": result.audit_event_id,
        }

    def _available_actions(self, cockpit: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []

        def add(action: dict[str, Any] | None, source_id: str) -> None:
            if not action:
                return
            action_key = action.get("action_key")
            href = action.get("href")
            if action_key not in ALLOWED_AUTOPILOT_ACTIONS and not href:
                return
            if action.get("disabled_reason"):
                return
            actions.append({**action, "id": source_id})

        add(cockpit.get("primary_flow"), "primary_flow")
        for blocker in cockpit.get("setup_blockers") or []:
            add(blocker.get("action"), str(blocker.get("id")))
        for group in cockpit.get("groups") or []:
            for task in group.get("tasks") or []:
                add(task.get("primary_action"), str(task.get("id")))
        return actions[:20]

    def _validate_action(self, action: dict[str, Any], available_actions: list[dict[str, Any]]) -> dict[str, Any] | None:
        action_key = action.get("action_key")
        href = action.get("href")
        for available in available_actions:
            if action_key and action_key == available.get("action_key"):
                return available
            if href and href == available.get("href"):
                return available
        return None

    def _prompt(self, cockpit: dict[str, Any], available_actions: list[dict[str, Any]]) -> str:
        summary = {
            "posture": cockpit.get("posture"),
            "data_state": cockpit.get("data_state"),
            "summary_metrics": cockpit.get("summary_metrics"),
            "available_actions": available_actions,
        }
        return (
            "Choose the single best next operational action for a time-poor seminar manager. "
            "You must choose only from available_actions. Return strict JSON with keys explanation and action. "
            "The action must be copied from available_actions.\n\n"
            f"Roadshow cockpit JSON:\n{json.dumps(summary, default=str, ensure_ascii=True)}"
        )


def _parse_json_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    payload = json.loads(stripped or "{}")
    if not isinstance(payload, dict):
        return {}
    return payload


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"keys": sorted(payload.keys())[:12]}
    for key in ("facts", "explanation", "body", "action"):
        value = payload.get(key)
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, str):
            summary[key] = value[:240]
        elif isinstance(value, dict):
            summary[key] = {item_key: value.get(item_key) for item_key in ("label", "action_key", "href")}
    return summary


def _bounded_confidence(value: Any) -> float:
    try:
        return min(0.99, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _contains_snippet(text: str, snippet: str) -> bool:
    compact_text = re.sub(r"\s+", " ", text).lower()
    compact_snippet = re.sub(r"\s+", " ", snippet).lower()
    return compact_snippet in compact_text
