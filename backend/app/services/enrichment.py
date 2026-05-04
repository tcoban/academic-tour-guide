from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import re
import unicodedata
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import FactCandidate, Institution, Researcher, ResearcherFact, ResearcherIdentity, SourceDocument
from app.scraping.name_quality import clean_person_display_name, person_identity_key
from app.schemas.api import EnrichRequest
from app.services.identity_sources import CeprClient, CeprProfile, OrcidClient, OrcidRecord, RepecGenealogyClient, RepecGenealogyEntry
from app.services.plausibility import document_targets_researcher, is_profileish_url, link_targets_researcher
from app.services.repec import RepecClient, RepecMatch

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised only when optional dependency is missing
    PdfReader = None


HONORIFICS = {"prof", "professor", "dr", "phd", "ph", "md"}
DOC_KEYWORDS = ("cv", "vitae", "resume", "profile", "homepage", "faculty", "people", "staff")
MANUAL_PROFILE_HOSTS = ("linkedin.com", "scholar.google.", "orcid.org")
PUBLIC_PROFILE_HOSTS = ("orcid.org", "genealogy.repec.org", "cepr.org")
MONTH_LOOKUP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
KNOWN_NATIONALITIES = {
    "american",
    "austrian",
    "british",
    "canadian",
    "french",
    "german",
    "italian",
    "spanish",
    "swiss",
}


def normalize_name(value: str) -> str:
    return person_identity_key(value)


def normalize_institution_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"[^a-zA-Z0-9 ]+", " ", ascii_value)
    return re.sub(r"\s+", " ", ascii_value).strip().lower()


def best_fact(researcher: Researcher, fact_type: str) -> ResearcherFact | None:
    matches = [fact for fact in researcher.facts if fact.fact_type == fact_type]
    if not matches:
        return None
    return max(matches, key=lambda fact: (fact.verified, fact.confidence, _sortable_datetime(fact.approved_at)))


def best_fact_candidate(researcher: Researcher, fact_type: str, statuses: tuple[str, ...] = ("pending", "approved")) -> FactCandidate | None:
    matches = [candidate for candidate in researcher.fact_candidates if candidate.fact_type == fact_type and candidate.status in statuses]
    if not matches:
        return None
    return max(matches, key=lambda candidate: (candidate.status == "approved", candidate.confidence, _sortable_datetime(candidate.created_at)))


def _sortable_datetime(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


@dataclass(slots=True)
class CandidateFact:
    fact_type: str
    value: str
    confidence: float
    evidence_snippet: str
    origin: str = "extracted"


@dataclass(slots=True)
class EvidenceResolution:
    fact_type: str
    value: str
    confidence: float
    source_url: str | None
    evidence_snippet: str | None
    approved: bool
    source_kind: str


@dataclass(slots=True)
class RefreshSummary:
    processed_count: int = 0
    created_count: int = 0
    updated_count: int = 0


def best_available_fact(researcher: Researcher, fact_type: str) -> EvidenceResolution | None:
    approved_fact = best_fact(researcher, fact_type)
    if approved_fact:
        return EvidenceResolution(
            fact_type=fact_type,
            value=approved_fact.value,
            confidence=approved_fact.confidence,
            source_url=approved_fact.source_url,
            evidence_snippet=approved_fact.evidence_snippet,
            approved=True,
            source_kind="approved_fact",
        )
    pending_candidate = best_fact_candidate(researcher, fact_type, statuses=("pending",))
    if pending_candidate:
        return EvidenceResolution(
            fact_type=fact_type,
            value=pending_candidate.value,
            confidence=pending_candidate.confidence,
            source_url=pending_candidate.source_url,
            evidence_snippet=pending_candidate.evidence_snippet,
            approved=False,
            source_kind="pending_candidate",
        )
    return None


class Biographer:
    phd_patterns = [
        re.compile(r"(?:PhD|Doctorate|Terminal Degree).*?(?:from|at|:)\s+([A-Z][A-Za-z0-9&.,'() -]+)", re.IGNORECASE),
        re.compile(r"([A-Z][A-Za-z0-9&.,'() -]+)\s*\((?:PhD|Doctorate)\)", re.IGNORECASE),
    ]
    nationality_patterns = [
        re.compile(r"(?:Nationality|Citizen(?:ship)?)\s*:\s*([A-Za-z -]+)", re.IGNORECASE),
        re.compile(r"\b([A-Z][a-z]+)\s+citizen\b", re.IGNORECASE),
    ]
    birth_month_patterns = [
        re.compile(r"(?:Born|Date of Birth)\s*:?\s*([A-Z][a-z]+)\s+\d{1,2}(?:,|\s)\s*\d{4}", re.IGNORECASE),
        re.compile(r"\b([A-Z][a-z]+)\s+\d{1,2},\s*\d{4}\b"),
    ]
    home_institution_patterns = [
        re.compile(r"(?:Professor|Associate Professor|Assistant Professor|Economist|Faculty)\s+(?:of|at)\s+([A-Z][A-Za-z0-9&.,'() -]+)", re.IGNORECASE),
        re.compile(r"Department of Economics,\s*([A-Z][A-Za-z0-9&.,'() -]+)", re.IGNORECASE),
    ]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_researcher(
        self,
        name: str,
        home_institution: str | None = None,
        repec_external_id: str | None = None,
    ) -> Researcher:
        if repec_external_id:
            existing_identity = self.session.scalar(
                select(ResearcherIdentity).where(
                    ResearcherIdentity.provider == "repec",
                    ResearcherIdentity.external_id == repec_external_id,
                )
            )
            if existing_identity:
                researcher = existing_identity.researcher
                if home_institution:
                    self.apply_home_institution(researcher, home_institution)
                return researcher

        normalized = normalize_name(name)
        researcher = self.session.scalar(select(Researcher).where(Researcher.normalized_name == normalized))
        if not researcher and home_institution:
            researcher = self._find_by_name_and_institution(name, home_institution)
        if researcher:
            if home_institution:
                self.apply_home_institution(researcher, home_institution)
            if researcher.name != name and len(name) < len(researcher.name):
                researcher.name = name
            return researcher

        researcher = Researcher(name=name.strip(), normalized_name=normalized)
        if home_institution:
            self.apply_home_institution(researcher, home_institution)
        self.session.add(researcher)
        self.session.flush()
        return researcher

    def apply_home_institution(self, researcher: Researcher, institution_name: str) -> None:
        institution = self.ensure_institution(institution_name)
        researcher.home_institution = institution.name
        researcher.home_institution_id = institution.id

    def ensure_institution(self, institution_name: str) -> Institution:
        cleaned = institution_name.strip(" .")
        normalized = normalize_institution_name(cleaned)
        institution = self.session.scalar(select(Institution).where(Institution.name.ilike(cleaned)))
        if institution:
            return institution
        for candidate in self.session.scalars(select(Institution)).all():
            if normalize_institution_name(candidate.name) == normalized:
                return candidate
        institution = Institution(name=cleaned)
        self.session.add(institution)
        self.session.flush()
        return institution

    def enrich(self, researcher: Researcher, request: EnrichRequest) -> Researcher:
        if request.home_institution:
            self.apply_home_institution(researcher, request.home_institution)
        if request.repec_rank is not None:
            researcher.repec_rank = request.repec_rank
        if request.birth_month is not None:
            researcher.birth_month = request.birth_month
            self.store_approved_fact(
                researcher=researcher,
                fact_type="birth_month",
                value=str(request.birth_month),
                confidence=0.99,
                source_url=request.source_url,
                evidence_snippet=request.evidence_snippet or "Explicit user-provided birth month.",
                approval_origin="manual",
                verified=True,
            )

        approved_facts: list[CandidateFact] = []
        if request.phd_institution:
            approved_facts.append(
                CandidateFact(
                    fact_type="phd_institution",
                    value=request.phd_institution.strip(),
                    confidence=0.95,
                    evidence_snippet=request.evidence_snippet or "Explicit user-provided PhD institution.",
                    origin="manual",
                )
            )
        if request.nationality:
            approved_facts.append(
                CandidateFact(
                    fact_type="nationality",
                    value=request.nationality.strip(),
                    confidence=0.95,
                    evidence_snippet=request.evidence_snippet or "Explicit user-provided nationality.",
                    origin="manual",
                )
            )
        if request.cv_text:
            approved_facts.extend(self.extract_from_text(request.cv_text))

        for candidate in approved_facts:
            if candidate.fact_type == "home_institution":
                self.apply_home_institution(researcher, candidate.value)
            elif candidate.fact_type == "birth_month":
                researcher.birth_month = int(candidate.value)
            self.store_approved_fact(
                researcher=researcher,
                fact_type=candidate.fact_type,
                value=candidate.value,
                confidence=candidate.confidence,
                source_url=request.source_url,
                evidence_snippet=candidate.evidence_snippet,
                approval_origin="manual",
                verified=True,
            )

        self.session.add(researcher)
        self.session.flush()
        self.session.refresh(researcher)
        return researcher

    def extract_from_text(self, raw_text: str) -> list[CandidateFact]:
        candidates: list[CandidateFact] = []
        normalized = " ".join(raw_text.split())

        for pattern in self.phd_patterns:
            match = pattern.search(normalized)
            if match:
                candidates.append(
                    CandidateFact(
                        fact_type="phd_institution",
                        value=match.group(1).strip(" ."),
                        confidence=0.78,
                        evidence_snippet=match.group(0),
                    )
                )
                break

        for pattern in self.nationality_patterns:
            match = pattern.search(normalized)
            if match:
                nationality = match.group(1).strip(" .")
                confidence = 0.72 if nationality.lower() in KNOWN_NATIONALITIES else 0.6
                candidates.append(
                    CandidateFact(
                        fact_type="nationality",
                        value=nationality,
                        confidence=confidence,
                        evidence_snippet=match.group(0),
                    )
                )
                break

        for pattern in self.birth_month_patterns:
            match = pattern.search(normalized)
            if match:
                month = MONTH_LOOKUP.get(match.group(1).strip().lower())
                if month:
                    candidates.append(
                        CandidateFact(
                            fact_type="birth_month",
                            value=str(month),
                            confidence=0.68,
                            evidence_snippet=match.group(0),
                        )
                    )
                    break

        for pattern in self.home_institution_patterns:
            match = pattern.search(normalized)
            if match:
                candidates.append(
                    CandidateFact(
                        fact_type="home_institution",
                        value=match.group(1).strip(" ."),
                        confidence=0.58,
                        evidence_snippet=match.group(0),
                    )
                )
                break

        return candidates

    def store_approved_fact(
        self,
        researcher: Researcher,
        fact_type: str,
        value: str,
        confidence: float,
        source_url: str | None,
        evidence_snippet: str | None,
        approval_origin: str,
        verified: bool,
        source_document: SourceDocument | None = None,
        approved_via_candidate: FactCandidate | None = None,
    ) -> ResearcherFact:
        cleaned_value = value.strip()
        existing = next(
            (
                fact
                for fact in researcher.facts
                if fact.fact_type == fact_type and fact.value.strip().lower() == cleaned_value.lower()
            ),
            None,
        )
        institution = self.ensure_institution(cleaned_value) if fact_type in {"phd_institution", "home_institution"} else None
        if fact_type == "home_institution":
            self.apply_home_institution(researcher, cleaned_value)
        elif fact_type == "birth_month":
            researcher.birth_month = int(cleaned_value)
        if existing:
            existing.confidence = max(existing.confidence, confidence)
            existing.verified = existing.verified or verified
            existing.source_url = source_url or existing.source_url
            existing.evidence_snippet = evidence_snippet or existing.evidence_snippet
            existing.approval_origin = approval_origin
            existing.source_document_id = source_document.id if source_document else existing.source_document_id
            existing.approved_via_candidate_id = approved_via_candidate.id if approved_via_candidate else existing.approved_via_candidate_id
            if institution:
                existing.institution_id = institution.id
            return existing

        fact = ResearcherFact(
            fact_type=fact_type,
            value=cleaned_value,
            confidence=confidence,
            source_url=source_url,
            evidence_snippet=evidence_snippet,
            verified=verified,
            approval_origin=approval_origin,
            source_document_id=source_document.id if source_document else None,
            approved_via_candidate_id=approved_via_candidate.id if approved_via_candidate else None,
            institution_id=institution.id if institution else None,
        )
        researcher.facts.append(fact)
        self.session.flush()
        return fact

    def store_candidate_fact(
        self,
        researcher: Researcher,
        candidate: CandidateFact,
        source_url: str | None,
        source_document: SourceDocument | None,
        status: str = "pending",
    ) -> FactCandidate:
        cleaned_value = candidate.value.strip()
        existing = next(
            (
                stored
                for stored in researcher.fact_candidates
                if stored.fact_type == candidate.fact_type
                and stored.value.strip().lower() == cleaned_value.lower()
                and stored.source_url == source_url
            ),
            None,
        )
        approved_match = best_fact(researcher, candidate.fact_type)
        if approved_match and approved_match.value.strip().lower() == cleaned_value.lower():
            status = "approved"
        institution = self.ensure_institution(cleaned_value) if candidate.fact_type in {"phd_institution", "home_institution"} else None
        if existing:
            existing.confidence = max(existing.confidence, candidate.confidence)
            existing.evidence_snippet = candidate.evidence_snippet or existing.evidence_snippet
            existing.status = "approved" if existing.status == "approved" or status == "approved" else existing.status
            existing.source_document_id = source_document.id if source_document else existing.source_document_id
            existing.origin = candidate.origin
            if institution:
                existing.institution_id = institution.id
            return existing

        fact_candidate = FactCandidate(
            fact_type=candidate.fact_type,
            value=cleaned_value,
            confidence=candidate.confidence,
            evidence_snippet=candidate.evidence_snippet,
            source_url=source_url,
            status=status,
            origin=candidate.origin,
            source_document_id=source_document.id if source_document else None,
            institution_id=institution.id if institution else None,
        )
        researcher.fact_candidates.append(fact_candidate)
        self.session.flush()
        return fact_candidate

    def _find_by_name_and_institution(self, name: str, home_institution: str) -> Researcher | None:
        normalized_home = normalize_institution_name(home_institution)
        for candidate in self.session.scalars(select(Researcher)).all():
            if not candidate.home_institution:
                continue
            if normalize_institution_name(candidate.home_institution) != normalized_home:
                continue
            if self._names_compatible(candidate.name, name):
                return candidate
        return None

    def _names_compatible(self, left: str, right: str) -> bool:
        left_tokens = normalize_name(left).split()
        right_tokens = normalize_name(right).split()
        if not left_tokens or not right_tokens:
            return False
        if left_tokens == right_tokens:
            return True
        return left_tokens[-1] == right_tokens[-1] and left_tokens[0][0] == right_tokens[0][0]


class BiographerPipeline:
    def __init__(
        self,
        session: Session,
        repec_client: RepecClient | None = None,
        document_client: httpx.Client | None = None,
        orcid_client: OrcidClient | None = None,
        genealogy_client: RepecGenealogyClient | None = None,
        cepr_client: CeprClient | None = None,
        public_identity_lookup_enabled: bool | None = None,
    ) -> None:
        self.session = session
        self.biographer = Biographer(session)
        self.repec_client = repec_client or RepecClient()
        self.orcid_client = orcid_client or OrcidClient()
        self.genealogy_client = genealogy_client or RepecGenealogyClient()
        self.cepr_client = cepr_client or CeprClient()
        self.public_identity_lookup_enabled = (
            public_identity_lookup_enabled
            if public_identity_lookup_enabled is not None
            else repec_client is None and document_client is None and orcid_client is None and genealogy_client is None and cepr_client is None
        )
        self.document_client = document_client or httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Roadshow KOF biographer; contact: kof.ethz.ch"},
        )

    def sync_repec(self, researcher_id: str | None = None) -> RefreshSummary:
        summary = RefreshSummary()
        for researcher in self._iter_researchers(researcher_id):
            summary.processed_count += 1
            match = self.repec_client.search_author(researcher.name)
            if not match:
                continue
            created, updated = self._upsert_repec_identity(researcher, match)
            summary.created_count += created
            summary.updated_count += updated
        self.session.flush()
        return summary

    def sync_top_authors(self, limit: int = 200) -> RefreshSummary:
        summary = RefreshSummary()
        for match in self.repec_client.top_authors(limit=limit):
            summary.processed_count += 1
            display_name = clean_person_display_name(match.canonical_name) or match.canonical_name
            researcher = self.biographer.get_or_create_researcher(
                display_name,
                repec_external_id=match.external_id,
            )
            created, updated = self._upsert_repec_identity(researcher, match)
            summary.created_count += created
            summary.updated_count += updated
        self.session.flush()
        return summary

    def refresh(self, researcher_id: str | None = None) -> RefreshSummary:
        summary = self.sync_repec(researcher_id)
        for researcher in self._iter_researchers(researcher_id):
            self._seed_home_institution_candidate(researcher)
            if self.public_identity_lookup_enabled:
                summary.updated_count += self._refresh_repec_genealogy(researcher)
                summary.updated_count += self._refresh_orcid(researcher)
                summary.updated_count += self._refresh_cepr(researcher)
            url_queue = self._collect_document_urls(researcher)
            fetched_documents: dict[str, SourceDocument] = {}
            seen_urls = {url for url, _ in url_queue}
            while url_queue:
                url, discovered_from = url_queue.pop(0)
                if self._is_manual_only_profile_url(url):
                    summary.created_count += self._record_manual_profile_link(researcher, url, discovered_from)
                    continue
                document, created, updated = self._fetch_document(researcher, url, discovered_from)
                summary.created_count += created
                summary.updated_count += updated
                fetched_documents[document.url] = document
                summary.created_count += self._record_manual_profile_links(researcher, document)
                for linked_url in document.metadata_json.get("linked_urls", []):
                    if linked_url not in seen_urls:
                        seen_urls.add(linked_url)
                        url_queue.append((linked_url, document.url))
            for document in fetched_documents.values():
                summary.updated_count += self._extract_fact_candidates(researcher, document)
            summary.updated_count += self._cross_verify_candidates(researcher)
        self.session.flush()
        return summary

    def search_trusted_evidence(self, researcher_id: str | None = None) -> RefreshSummary:
        """Run the full evidence agent against trusted public sources.

        `refresh()` preserves the constructor's lookup policy so tests and narrowly
        scoped jobs can disable network identity lookups. This explicit job is the
        operator-facing action: it always searches RePEc, RePEc Genealogy, ORCID,
        CEPR, and source-linked CV/profile pages, then leaves extracted claims in
        the review queue.
        """
        previous_lookup_policy = self.public_identity_lookup_enabled
        self.public_identity_lookup_enabled = True
        try:
            return self.refresh(researcher_id)
        finally:
            self.public_identity_lookup_enabled = previous_lookup_policy

    def _iter_researchers(self, researcher_id: str | None) -> list[Researcher]:
        if researcher_id:
            researcher = self.session.get(Researcher, researcher_id)
            return [researcher] if researcher else []
        return self.session.scalars(select(Researcher).order_by(Researcher.created_at)).all()

    def _upsert_repec_identity(self, researcher: Researcher, match: RepecMatch) -> tuple[int, int]:
        identity = next(
            (
                item
                for item in researcher.identities
                if item.provider == "repec" and item.external_id == match.external_id
            ),
            None,
        )
        if not identity:
            identity = ResearcherIdentity(
                provider="repec",
                external_id=match.external_id,
                canonical_name=match.canonical_name,
                profile_url=match.profile_url,
                match_confidence=match.match_confidence,
                ranking_percentile=match.ranking_percentile,
                ranking_label=match.ranking_label,
                metadata_json=match.metadata_json,
            )
            researcher.identities.append(identity)
            created = 1
            updated = 0
        else:
            identity.canonical_name = match.canonical_name
            identity.profile_url = match.profile_url
            identity.match_confidence = match.match_confidence
            identity.ranking_percentile = match.ranking_percentile
            identity.ranking_label = match.ranking_label
            identity.metadata_json = match.metadata_json
            identity.synced_at = datetime.now(UTC)
            created = 0
            updated = 1
        if match.ranking_percentile is not None:
            researcher.repec_rank = match.ranking_percentile
        return created, updated

    def _seed_home_institution_candidate(self, researcher: Researcher) -> None:
        if not researcher.home_institution or best_fact(researcher, "home_institution"):
            return
        source_url = None
        if researcher.talk_events:
            source_url = researcher.talk_events[0].url
        self.biographer.store_candidate_fact(
            researcher=researcher,
            candidate=CandidateFact(
                fact_type="home_institution",
                value=researcher.home_institution,
                confidence=0.7,
                evidence_snippet="Speaker affiliation observed on a linked seminar source page.",
                origin="event_affiliation",
            ),
            source_url=source_url,
            source_document=None,
        )

    def _refresh_repec_genealogy(self, researcher: Researcher) -> int:
        entry = self._fetch_repec_genealogy_entry(researcher)
        if not entry:
            return 0

        updated = self._upsert_identity(
            researcher=researcher,
            provider="repec_genealogy",
            external_id=entry.external_id,
            canonical_name=entry.canonical_name,
            profile_url=entry.profile_url,
            match_confidence=0.98,
            metadata_json={
                "source": "repec_genealogy",
                "graduation_year": entry.graduation_year,
                "advisors": entry.advisors,
            },
        )
        document, created, changed = self._store_synthetic_document(
            researcher=researcher,
            url=entry.profile_url,
            content_type="text/html",
            extracted_text=entry.extracted_text,
            title=f"RePEc Genealogy: {entry.canonical_name}",
            metadata_json={
                "source": "repec_genealogy",
                "linked_urls": entry.linked_urls,
                "graduation_year": entry.graduation_year,
                "advisors": entry.advisors,
            },
        )
        updated += created + changed
        if entry.terminal_degree_institution:
            self.biographer.store_candidate_fact(
                researcher=researcher,
                candidate=CandidateFact(
                    fact_type="phd_institution",
                    value=entry.terminal_degree_institution,
                    confidence=0.88,
                    evidence_snippet=self._genealogy_degree_snippet(entry),
                    origin="repec_genealogy",
                ),
                source_url=entry.profile_url,
                source_document=document,
            )
            updated += 1
        return updated

    def _fetch_repec_genealogy_entry(self, researcher: Researcher) -> RepecGenealogyEntry | None:
        repec_identity = next((identity for identity in researcher.identities if identity.provider == "repec"), None)
        try:
            if repec_identity:
                entry = self.genealogy_client.fetch_by_repec_id(repec_identity.external_id)
                if entry and self._names_compatible(researcher.name, entry.canonical_name):
                    return entry
            entry = self.genealogy_client.search_by_name(researcher.name)
            if entry and self._names_compatible(researcher.name, entry.canonical_name):
                return entry
        except httpx.HTTPError:
            return None
        return None

    def _refresh_orcid(self, researcher: Researcher) -> int:
        updated = 0
        existing_identity = next((identity for identity in researcher.identities if identity.provider == "orcid"), None)
        match = None
        if not existing_identity:
            try:
                match = self.orcid_client.search_person(researcher.name, researcher.home_institution)
            except httpx.HTTPError:
                match = None
            if match and not self._names_compatible(researcher.name, match.canonical_name):
                match = None
            if match:
                updated += self._upsert_identity(
                    researcher=researcher,
                    provider="orcid",
                    external_id=match.external_id,
                    canonical_name=match.canonical_name,
                    profile_url=match.profile_url,
                    match_confidence=match.match_confidence,
                    metadata_json=match.metadata_json,
                )
                external_id = match.external_id
            else:
                return updated
        else:
            external_id = existing_identity.external_id

        try:
            record = self.orcid_client.fetch_record(external_id)
        except httpx.HTTPError:
            return updated
        if not record:
            return updated
        updated += self._store_orcid_record(researcher, record)
        return updated

    def _store_orcid_record(self, researcher: Researcher, record: OrcidRecord) -> int:
        document, created, changed = self._store_synthetic_document(
            researcher=researcher,
            url=record.profile_url,
            content_type="application/vnd.orcid+json",
            extracted_text=record.extracted_text,
            title=f"ORCID record: {record.canonical_name}",
            metadata_json={
                **record.metadata_json,
                "linked_urls": self._queueable_profile_links(record.linked_urls),
                "manual_profile_urls": [url for url in record.linked_urls if self._is_manual_only_profile_url(url)],
            },
        )
        updated = created + changed
        for linked_url in record.linked_urls:
            if self._is_manual_only_profile_url(linked_url):
                updated += self._record_manual_profile_link(researcher, linked_url, record.profile_url)
        for fact in record.education_facts:
            organization = fact.get("organization")
            role_title = str(fact.get("role_title") or "")
            if organization and re.search(r"\b(phd|ph\.d|doctorate|doctoral)\b", role_title, re.IGNORECASE):
                self.biographer.store_candidate_fact(
                    researcher=researcher,
                    candidate=CandidateFact(
                        fact_type="phd_institution",
                        value=organization,
                        confidence=0.82,
                        evidence_snippet=f"ORCID education entry: {role_title}, {organization}",
                        origin="orcid",
                    ),
                    source_url=record.profile_url,
                    source_document=document,
                )
                updated += 1
        current_employment = next((fact for fact in record.employment_facts if fact.get("organization")), None)
        if current_employment:
            organization = str(current_employment["organization"])
            self.biographer.store_candidate_fact(
                researcher=researcher,
                candidate=CandidateFact(
                    fact_type="home_institution",
                    value=organization,
                    confidence=0.72,
                    evidence_snippet=f"ORCID employment entry: {current_employment.get('role_title') or 'employment'}, {organization}",
                    origin="orcid",
                ),
                source_url=record.profile_url,
                source_document=document,
            )
            updated += 1
        return updated

    def _refresh_cepr(self, researcher: Researcher) -> int:
        try:
            profile = self.cepr_client.fetch_profile(researcher.name)
        except httpx.HTTPError:
            return 0
        if not profile or not self._names_compatible(researcher.name, profile.canonical_name):
            return 0
        return self._store_cepr_profile(researcher, profile)

    def _store_cepr_profile(self, researcher: Researcher, profile: CeprProfile) -> int:
        updated = self._upsert_identity(
            researcher=researcher,
            provider="cepr",
            external_id=profile.external_id,
            canonical_name=profile.canonical_name,
            profile_url=profile.profile_url,
            match_confidence=0.94,
            metadata_json={**profile.metadata_json, "orcid_id": profile.orcid_id},
        )
        document, created, changed = self._store_synthetic_document(
            researcher=researcher,
            url=profile.profile_url,
            content_type="text/html",
            extracted_text=profile.extracted_text,
            title=profile.title,
            metadata_json={
                **profile.metadata_json,
                "linked_urls": self._queueable_profile_links(profile.linked_urls),
                "manual_profile_urls": [url for url in profile.linked_urls if self._is_manual_only_profile_url(url)],
            },
        )
        updated += created + changed
        if profile.orcid_id:
            updated += self._upsert_identity(
                researcher=researcher,
                provider="orcid",
                external_id=profile.orcid_id,
                canonical_name=profile.canonical_name,
                profile_url=f"https://orcid.org/{profile.orcid_id}",
                match_confidence=0.9,
                metadata_json={"source": "cepr_profile", "cepr_profile_url": profile.profile_url},
            )
        for linked_url in profile.linked_urls:
            if self._is_manual_only_profile_url(linked_url):
                updated += self._record_manual_profile_link(researcher, linked_url, profile.profile_url)
        if profile.home_institution:
            self.biographer.store_candidate_fact(
                researcher=researcher,
                candidate=CandidateFact(
                    fact_type="home_institution",
                    value=profile.home_institution,
                    confidence=0.78,
                    evidence_snippet=self._cepr_home_snippet(profile),
                    origin="cepr_profile",
                ),
                source_url=profile.profile_url,
                source_document=document,
            )
            updated += 1
        if profile.phd_institution:
            self.biographer.store_candidate_fact(
                researcher=researcher,
                candidate=CandidateFact(
                    fact_type="phd_institution",
                    value=profile.phd_institution,
                    confidence=0.86,
                    evidence_snippet=self._cepr_phd_snippet(profile),
                    origin="cepr_profile",
                ),
                source_url=profile.profile_url,
                source_document=document,
            )
            updated += 1
        return updated

    def _upsert_identity(
        self,
        researcher: Researcher,
        provider: str,
        external_id: str,
        canonical_name: str,
        profile_url: str | None,
        match_confidence: float,
        metadata_json: dict,
        ranking_percentile: float | None = None,
        ranking_label: str | None = None,
    ) -> int:
        identity = next(
            (
                item
                for item in researcher.identities
                if item.provider == provider and item.external_id == external_id
            ),
            None,
        )
        if not identity:
            researcher.identities.append(
                ResearcherIdentity(
                    provider=provider,
                    external_id=external_id,
                    canonical_name=canonical_name,
                    profile_url=profile_url,
                    match_confidence=match_confidence,
                    ranking_percentile=ranking_percentile,
                    ranking_label=ranking_label,
                    metadata_json=metadata_json,
                )
            )
            return 1
        identity.canonical_name = canonical_name
        identity.profile_url = profile_url
        identity.match_confidence = match_confidence
        identity.ranking_percentile = ranking_percentile
        identity.ranking_label = ranking_label
        identity.metadata_json = metadata_json
        identity.synced_at = datetime.now(UTC)
        return 1

    def _store_synthetic_document(
        self,
        researcher: Researcher,
        url: str,
        content_type: str,
        extracted_text: str | None,
        title: str,
        metadata_json: dict,
    ) -> tuple[SourceDocument, int, int]:
        document = self.session.scalar(
            select(SourceDocument).where(SourceDocument.researcher_id == researcher.id, SourceDocument.url == url)
        )
        created = 0
        updated = 0
        checksum = sha256((extracted_text or "").encode("utf-8")).hexdigest()
        if not document:
            document = SourceDocument(researcher_id=researcher.id, url=url)
            self.session.add(document)
            created = 1
        elif document.checksum != checksum or document.fetch_status != "fetched":
            updated = 1
        document.content_type = content_type
        document.checksum = checksum
        document.fetch_status = "fetched"
        document.http_status = 200
        document.title = title
        document.extracted_text = extracted_text
        document.metadata_json = metadata_json
        document.fetched_at = datetime.now(UTC)
        self.session.flush()
        return document, created, updated

    def _genealogy_degree_snippet(self, entry: RepecGenealogyEntry) -> str:
        year = f" in {entry.graduation_year}" if entry.graduation_year else ""
        return f"{entry.canonical_name} got the terminal degree from {entry.terminal_degree_institution}{year}."

    def _cepr_home_snippet(self, profile: CeprProfile) -> str:
        role_line = (profile.metadata_json or {}).get("role_line")
        if role_line:
            return f"CEPR profile role line: {role_line}"
        return f"CEPR profile lists current institution as {profile.home_institution}."

    def _cepr_phd_snippet(self, profile: CeprProfile) -> str:
        compact_text = re.sub(r"\s+", " ", profile.extracted_text or "")
        match = re.search(
            r"[^.]*\b(?:obtained|received)[^.]*\bPh\.?D[^.]*\bfrom[^.]*\.",
            compact_text,
            re.IGNORECASE,
        )
        if match:
            return match.group(0).strip()
        return f"CEPR profile biography identifies PhD institution as {profile.phd_institution}."

    def _collect_document_urls(self, researcher: Researcher) -> list[tuple[str, str | None]]:
        queue: list[tuple[str, str | None]] = []
        seen: set[str] = {document.url for document in researcher.documents if document.fetch_status in {"fetched", "unsupported"}}
        for event in researcher.talk_events:
            if event.url not in seen:
                seen.add(event.url)
                queue.append((event.url, None))
        for identity in researcher.identities:
            if identity.provider == "orcid":
                continue
            if identity.profile_url and identity.profile_url not in seen:
                seen.add(identity.profile_url)
                queue.append((identity.profile_url, None))
        for document in list(researcher.documents):
            if (document.metadata_json or {}).get("plausibility_status") in {"quarantined", "skipped"}:
                continue
            document_allows_generic_links = (
                document.fetch_status == "fetched"
                and bool(document.extracted_text)
                and is_profileish_url(document.url)
                and self._url_targets_researcher(document.url, researcher)
                and document_targets_researcher(document, researcher)
            )
            for linked_url in document.metadata_json.get("linked_urls", []):
                if not document_allows_generic_links and not link_targets_researcher(linked_url, linked_url, researcher):
                    continue
                if linked_url not in seen:
                    seen.add(linked_url)
                    queue.append((linked_url, document.url))
        return queue

    def _fetch_document(self, researcher: Researcher, url: str, discovered_from_url: str | None) -> tuple[SourceDocument, int, int]:
        existing = self.session.scalar(
            select(SourceDocument).where(SourceDocument.researcher_id == researcher.id, SourceDocument.url == url)
        )
        if not existing:
            document = SourceDocument(researcher_id=researcher.id, url=url, discovered_from_url=discovered_from_url)
            self.session.add(document)
            created = 1
            updated = 0
        else:
            document = existing
            if discovered_from_url and not document.discovered_from_url:
                document.discovered_from_url = discovered_from_url
            created = 0
            updated = 1

        try:
            response = self.document_client.get(url)
            document.http_status = response.status_code
            response.raise_for_status()
        except httpx.HTTPError as error:
            document.fetch_status = "error"
            document.metadata_json = {"error": str(error)}
            document.fetched_at = datetime.now(UTC)
            return document, created, updated

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        document.content_type = content_type or None
        document.checksum = sha256(response.content).hexdigest()
        document.fetched_at = datetime.now(UTC)

        if "html" in content_type or url.lower().endswith((".html", ".htm")):
            soup = BeautifulSoup(response.text, "html.parser")
            document.title = soup.title.get_text(" ", strip=True) if soup.title else None
            document.extracted_text = " ".join(soup.stripped_strings)
            document.metadata_json = {
                "linked_urls": self._discover_linked_urls(url, soup, researcher),
                "manual_profile_urls": self._discover_manual_profile_urls(url, soup),
            }
            document.fetch_status = "fetched"
        elif "pdf" in content_type or url.lower().endswith(".pdf"):
            if PdfReader is None:
                document.fetch_status = "unsupported"
                document.metadata_json = {"reason": "pypdf not installed"}
            else:
                reader = PdfReader(BytesIO(response.content))
                document.extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip() or None
                document.title = (reader.metadata.title if reader.metadata else None) or document.title
                document.metadata_json = {"linked_urls": []}
                document.fetch_status = "fetched"
        else:
            document.fetch_status = "unsupported"
            document.metadata_json = {"linked_urls": [], "reason": content_type or "unknown content type"}

        self.session.flush()
        return document, created, updated

    def _discover_linked_urls(self, base_url: str, soup: BeautifulSoup, researcher: Researcher) -> list[str]:
        base_host = urlparse(base_url).netloc
        discovered: list[str] = []
        seen: set[str] = set()
        page_text = soup.get_text(" ", strip=True)
        allow_generic_cv_links = is_profileish_url(base_url) and link_targets_researcher(
            base_url,
            page_text[:500],
            researcher,
        ) and self._url_targets_researcher(base_url, researcher)
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href")).strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            label = anchor.get_text(" ", strip=True).lower()
            joined = urljoin(base_url, href)
            joined_host = urlparse(joined).netloc
            if not self._is_host_related(base_host, joined_host):
                continue
            lowered_href = joined.lower()
            if not any(keyword in lowered_href or keyword in label for keyword in DOC_KEYWORDS):
                continue
            if not allow_generic_cv_links and not link_targets_researcher(joined, label, researcher):
                continue
            if joined in seen:
                continue
            seen.add(joined)
            discovered.append(joined)
        return discovered

    def _discover_manual_profile_urls(self, base_url: str, soup: BeautifulSoup) -> list[str]:
        discovered: list[str] = []
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href")).strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            joined = urljoin(base_url, href)
            if self._is_manual_only_profile_url(joined) and joined not in discovered:
                discovered.append(joined)
        return discovered

    def _queueable_profile_links(self, urls: list[str]) -> list[str]:
        return [url for url in urls if not self._is_manual_only_profile_url(url)]

    def _record_manual_profile_links(self, researcher: Researcher, document: SourceDocument) -> int:
        created = 0
        for url in (document.metadata_json or {}).get("manual_profile_urls", []):
            created += self._record_manual_profile_link(researcher, url, document.url)
        return created

    def _record_manual_profile_link(self, researcher: Researcher, url: str, discovered_from_url: str | None) -> int:
        existing = self.session.scalar(
            select(SourceDocument).where(SourceDocument.researcher_id == researcher.id, SourceDocument.url == url)
        )
        if existing:
            if discovered_from_url and not existing.discovered_from_url:
                existing.discovered_from_url = discovered_from_url
            return 0
        document = SourceDocument(
            researcher_id=researcher.id,
            url=url,
            discovered_from_url=discovered_from_url,
            content_type="external_profile",
            fetch_status="unsupported",
            title=self._manual_profile_title(url),
            metadata_json={
                "reason": "Manual verification profile; Roadshow records the link but does not scrape access-restricted pages.",
                "source": "manual_profile_link",
                "linked_urls": [],
            },
            fetched_at=datetime.now(UTC),
        )
        self.session.add(document)
        self.session.flush()
        return 1

    def _manual_profile_title(self, url: str) -> str:
        host = urlparse(url).netloc.lower()
        if "linkedin.com" in host:
            return "LinkedIn profile link"
        if "scholar.google." in host:
            return "Google Scholar profile link"
        return "External profile link"

    def _is_manual_only_profile_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(marker in host for marker in MANUAL_PROFILE_HOSTS) and not any(
            marker in host for marker in PUBLIC_PROFILE_HOSTS
        )

    def _cross_verify_candidates(self, researcher: Researcher) -> int:
        updated = 0
        grouped: dict[tuple[str, str], list[FactCandidate]] = {}
        for candidate in researcher.fact_candidates:
            if candidate.status not in {"pending", "approved"}:
                continue
            normalized_value = normalize_institution_name(candidate.value) if candidate.fact_type in {"phd_institution", "home_institution"} else candidate.value.strip().lower()
            grouped.setdefault((candidate.fact_type, normalized_value), []).append(candidate)

        for (fact_type, _), candidates in grouped.items():
            origins = sorted({candidate.origin for candidate in candidates if candidate.origin})
            source_urls = sorted({candidate.source_url for candidate in candidates if candidate.source_url})
            if len(origins) < 2 and len(source_urls) < 2:
                continue
            note = f"Cross-verified {fact_type} evidence across {', '.join(origins or ['multiple sources'])}."
            for candidate in candidates:
                before = (candidate.confidence, candidate.review_note)
                candidate.confidence = max(candidate.confidence, 0.9)
                candidate.review_note = note
                if before != (candidate.confidence, candidate.review_note):
                    updated += 1
        return updated

    def _names_compatible(self, left: str, right: str) -> bool:
        return self.biographer._names_compatible(left, right)

    def _url_targets_researcher(self, url: str, researcher: Researcher) -> bool:
        normalized_url = normalize_name(urlparse(url).path.replace("-", " ").replace("_", " "))
        name_tokens = normalize_name(researcher.name).split()
        if len(name_tokens) < 2:
            return False
        return name_tokens[0] in normalized_url and name_tokens[-1] in normalized_url

    def _is_host_related(self, base_host: str, candidate_host: str) -> bool:
        if not base_host or not candidate_host:
            return False
        if base_host == candidate_host:
            return True
        base_parts = base_host.split(".")
        candidate_parts = candidate_host.split(".")
        return base_parts[-2:] == candidate_parts[-2:]

    def _extract_fact_candidates(self, researcher: Researcher, document: SourceDocument) -> int:
        if document.fetch_status != "fetched" or not document.extracted_text:
            return 0
        if not document_targets_researcher(document, researcher):
            metadata = dict(document.metadata_json or {})
            metadata["plausibility_status"] = "skipped"
            metadata["plausibility_reason"] = "document_not_researcher_specific"
            document.metadata_json = metadata
            return 0
        updates = 0
        for candidate in self.biographer.extract_from_text(document.extracted_text):
            self.biographer.store_candidate_fact(
                researcher=researcher,
                candidate=candidate,
                source_url=document.url,
                source_document=document,
            )
            updates += 1
        return updates
