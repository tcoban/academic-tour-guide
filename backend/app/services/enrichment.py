from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Researcher, ResearcherFact
from app.schemas.api import EnrichRequest


def normalize_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"[^a-zA-Z0-9 ]+", " ", ascii_value)
    return re.sub(r"\s+", " ", ascii_value).strip().lower()


def best_fact(researcher: Researcher, fact_type: str) -> ResearcherFact | None:
    matches = [fact for fact in researcher.facts if fact.fact_type == fact_type]
    if not matches:
        return None
    return max(matches, key=lambda fact: (fact.verified, fact.confidence))


@dataclass(slots=True)
class CandidateFact:
    fact_type: str
    value: str
    confidence: float
    evidence_snippet: str


class Biographer:
    phd_patterns = [
        re.compile(r"(?:PhD|Doctorate).*?(?:from|at)\s+([A-Z][A-Za-z0-9&.,' -]+)", re.IGNORECASE),
        re.compile(r"([A-Z][A-Za-z0-9&.,' -]+)\s*\((?:PhD|Doctorate)\)", re.IGNORECASE),
    ]
    nationality_patterns = [
        re.compile(r"(?:Nationality|Citizen(?:ship)?)\s*:\s*([A-Za-z -]+)", re.IGNORECASE),
        re.compile(r"\b([A-Z][a-z]+)\s+citizen\b", re.IGNORECASE),
    ]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_researcher(self, name: str, home_institution: str | None = None) -> Researcher:
        normalized = normalize_name(name)
        researcher = self.session.scalar(select(Researcher).where(Researcher.normalized_name == normalized))
        if researcher:
            if home_institution and not researcher.home_institution:
                researcher.home_institution = home_institution
            return researcher

        researcher = Researcher(name=name, normalized_name=normalized, home_institution=home_institution)
        self.session.add(researcher)
        self.session.flush()
        return researcher

    def enrich(self, researcher: Researcher, request: EnrichRequest) -> Researcher:
        if request.home_institution:
            researcher.home_institution = request.home_institution
        if request.repec_rank is not None:
            researcher.repec_rank = request.repec_rank
        if request.birth_month is not None:
            researcher.birth_month = request.birth_month

        candidate_facts: list[CandidateFact] = []
        if request.phd_institution:
            candidate_facts.append(
                CandidateFact(
                    fact_type="phd_institution",
                    value=request.phd_institution.strip(),
                    confidence=0.95,
                    evidence_snippet="Explicit user-provided PhD institution.",
                )
            )
        if request.nationality:
            candidate_facts.append(
                CandidateFact(
                    fact_type="nationality",
                    value=request.nationality.strip(),
                    confidence=0.95,
                    evidence_snippet="Explicit user-provided nationality.",
                )
            )
        if request.cv_text:
            candidate_facts.extend(self.extract_from_cv_text(request.cv_text))

        for candidate in candidate_facts:
            self._store_fact(
                researcher=researcher,
                fact_type=candidate.fact_type,
                value=candidate.value,
                confidence=candidate.confidence,
                source_url=request.source_url,
                evidence_snippet=candidate.evidence_snippet,
            )

        self.session.add(researcher)
        self.session.flush()
        self.session.refresh(researcher)
        return researcher

    def extract_from_cv_text(self, cv_text: str) -> list[CandidateFact]:
        candidates: list[CandidateFact] = []
        normalized = " ".join(cv_text.split())
        for pattern in self.phd_patterns:
            match = pattern.search(normalized)
            if match:
                candidates.append(
                    CandidateFact(
                        fact_type="phd_institution",
                        value=match.group(1).strip(" ."),
                        confidence=0.75,
                        evidence_snippet=match.group(0),
                    )
                )
                break

        for pattern in self.nationality_patterns:
            match = pattern.search(normalized)
            if match:
                candidates.append(
                    CandidateFact(
                        fact_type="nationality",
                        value=match.group(1).strip(" ."),
                        confidence=0.7,
                        evidence_snippet=match.group(0),
                    )
                )
                break
        return candidates

    def _store_fact(
        self,
        researcher: Researcher,
        fact_type: str,
        value: str,
        confidence: float,
        source_url: str | None,
        evidence_snippet: str,
    ) -> None:
        existing = next(
            (
                fact
                for fact in researcher.facts
                if fact.fact_type == fact_type and fact.value.strip().lower() == value.strip().lower()
            ),
            None,
        )
        if existing:
            existing.confidence = max(existing.confidence, confidence)
            if source_url:
                existing.source_url = source_url
            if evidence_snippet:
                existing.evidence_snippet = evidence_snippet
            return
        researcher.facts.append(
            ResearcherFact(
                fact_type=fact_type,
                value=value.strip(),
                confidence=confidence,
                source_url=source_url,
                evidence_snippet=evidence_snippet,
            )
        )

