from __future__ import annotations

from datetime import datetime

from app.core.datetime import UTC

from sqlalchemy.orm import Session

from app.models.entities import FactCandidate, ResearcherFact
from app.services.enrichment import Biographer


class FactReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.biographer = Biographer(session)

    def approve(self, candidate: FactCandidate, merged_value: str | None = None, note: str | None = None) -> ResearcherFact:
        candidate.status = "approved"
        candidate.review_note = note
        candidate.reviewed_at = datetime.now(UTC)
        if merged_value:
            candidate.value = merged_value.strip()

        approved_fact = self.biographer.store_approved_fact(
            researcher=candidate.researcher,
            fact_type=candidate.fact_type,
            value=candidate.value,
            confidence=candidate.confidence,
            source_url=candidate.source_url,
            evidence_snippet=candidate.evidence_snippet,
            approval_origin="review_queue",
            verified=True,
            source_document=candidate.source_document,
            approved_via_candidate=candidate,
        )
        self.session.flush()
        return approved_fact

    def reject(self, candidate: FactCandidate, note: str | None = None) -> FactCandidate:
        candidate.status = "rejected"
        candidate.review_note = note
        candidate.reviewed_at = datetime.now(UTC)
        self.session.flush()
        return candidate
