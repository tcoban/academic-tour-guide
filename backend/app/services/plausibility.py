from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import re
import unicodedata
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import FactCandidate, Researcher, ResearcherFact, SourceDocument, TalkEvent
from app.scraping.name_quality import (
    clean_person_display_name,
    looks_like_institution_name,
    normalize_speaker_identity,
    person_identity_key,
    speaker_name_quality_flags,
    split_speaker_names,
)
from app.scraping.sources import _build_source_hash


GENERIC_LONG_VALUE_THRESHOLD = 80
REPEATED_VALUE_RESEARCHER_THRESHOLD = 3
QUARANTINE_NOTE = "Rejected by Roadshow plausibility check: evidence source does not uniquely support this researcher."
HONORIFICS = {"dr", "ph", "phd", "prof", "professor"}


@dataclass(slots=True)
class PlausibilitySummary:
    processed_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)


def _ascii_tokens(value: str) -> list[str]:
    transliterated = (value or "").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    ascii_value = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", ascii_value).lower()
    return [token for token in re.sub(r"\s+", " ", cleaned).split() if token]


def _name_tokens(researcher: Researcher) -> list[str]:
    return [token for token in _ascii_tokens(researcher.name) if token not in {"prof", "professor", "dr", "phd"}]


def _normalized_researcher_name(value: str) -> str:
    return person_identity_key(value)


def _has_name_match(candidate_text: str, researcher: Researcher) -> bool:
    tokens = _name_tokens(researcher)
    if not tokens:
        return False
    text_tokens = set(_ascii_tokens(candidate_text))
    last_name = tokens[-1]
    if last_name not in text_tokens:
        return False
    first_name = tokens[0]
    return first_name in text_tokens


def is_profileish_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    host = parsed.netloc.lower()
    return (
        "ideas.repec.org" in host
        or ("cepr.org" in host and "/about/people/" in path)
        or any(part in path for part in ("/faculty/", "/people/", "/staff/", "/profile", "/homepage", "/cv", "vitae"))
        or path.endswith(".pdf")
    )


def link_targets_researcher(url: str, label: str, researcher: Researcher) -> bool:
    return _has_name_match(f"{url} {label}", researcher)


def document_targets_researcher(document: SourceDocument, researcher: Researcher) -> bool:
    url_and_title = " ".join(part for part in (document.url, document.title or "") if part)
    if _has_name_match(url_and_title, researcher):
        return True

    body_text = document.extracted_text or ""
    if not _has_name_match(body_text, researcher):
        return False
    if document.url.lower().endswith(".pdf") or "pdf" in (document.content_type or "").lower():
        return False
    return is_profileish_url(document.url)


class PlausibilityService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self) -> PlausibilitySummary:
        summary = PlausibilitySummary()
        summary.updated_count += self._repair_speaker_names(summary)
        summary.updated_count += self._remove_institution_speaker_artifacts(summary)
        summary.updated_count += self._repair_researcher_names(summary)
        summary.updated_count += self._merge_transliteration_aliases(summary)
        summary.updated_count += self._dedupe_talk_events(summary)
        summary.updated_count += self._quarantine_off_target_documents(summary)
        summary.updated_count += self._quarantine_repeated_generic_values(summary)
        summary.updated_count += self._restore_home_institutions(summary)
        self.session.flush()
        return summary

    def _repair_speaker_names(self, summary: PlausibilitySummary) -> int:
        updated = 0
        events = self.session.scalars(
            select(TalkEvent).options(
                selectinload(TalkEvent.researcher).selectinload(Researcher.fact_candidates),
                selectinload(TalkEvent.researcher).selectinload(Researcher.facts),
            )
        ).all()
        for event in events:
            summary.processed_count += 1
            before_name = event.speaker_name
            before_affiliation = event.speaker_affiliation
            raw_split_names = split_speaker_names(before_name, before_affiliation)
            if raw_split_names:
                normalized_affiliation = normalize_speaker_identity(raw_split_names[0], before_affiliation).affiliation
                updated += self._replace_event_with_individual_speakers(
                    event,
                    raw_split_names,
                    normalized_affiliation,
                    summary,
                )
                continue

            normalized = normalize_speaker_identity(event.speaker_name, event.speaker_affiliation)
            flags = speaker_name_quality_flags(before_name) + normalized.flags
            if not flags and normalized.speaker_name == before_name and normalized.affiliation == before_affiliation:
                continue
            if not normalized.speaker_name:
                continue
            split_names = split_speaker_names(normalized.speaker_name, normalized.affiliation)
            if split_names:
                updated += self._replace_event_with_individual_speakers(event, split_names, normalized.affiliation, summary)
                continue

            new_hash = _build_source_hash(
                event.source_name,
                event.url,
                normalized.speaker_name,
                event.starts_at.isoformat(),
            )
            duplicate = self.session.scalar(
                select(TalkEvent).where(TalkEvent.source_hash == new_hash, TalkEvent.id != event.id)
            )
            if duplicate:
                self._repair_event_researcher(duplicate, normalized.speaker_name, normalized.affiliation)
                self.session.delete(event)
                updated += 1
                summary.source_counts["duplicate_speaker_events_removed"] = (
                    summary.source_counts.get("duplicate_speaker_events_removed", 0) + 1
                )
                continue

            event.speaker_name = normalized.speaker_name
            event.speaker_affiliation = normalized.affiliation
            event.source_hash = new_hash
            event.raw_payload = {
                **(event.raw_payload or {}),
                "speaker_quality_flags": list(dict.fromkeys(flags)),
                "speaker_name_before_plausibility": before_name,
                "speaker_affiliation_before_plausibility": before_affiliation,
            }
            self._repair_event_researcher(event, normalized.speaker_name, normalized.affiliation)
            updated += 1
            summary.source_counts["speaker_names_repaired"] = summary.source_counts.get("speaker_names_repaired", 0) + 1
        return updated

    def _replace_event_with_individual_speakers(
        self,
        event: TalkEvent,
        speaker_names: list[str],
        affiliation: str | None,
        summary: PlausibilitySummary,
    ) -> int:
        updated = 0
        original_name = event.speaker_name
        original_hash = event.source_hash
        base_payload = {
            **(event.raw_payload or {}),
            "speaker_quality_flags": list(
                dict.fromkeys([*((event.raw_payload or {}).get("speaker_quality_flags") or []), "multiple_speakers_split"])
            ),
            "original_speaker_name": original_name,
            "source_hash_before_split": original_hash,
        }
        used_original = False
        for speaker_name in speaker_names:
            source_hash = _build_source_hash(event.source_name, event.url, speaker_name, event.starts_at.isoformat())
            duplicate = self.session.scalar(
                select(TalkEvent).where(TalkEvent.source_hash == source_hash, TalkEvent.id != event.id)
            )
            if duplicate:
                duplicate.title = event.title
                duplicate.speaker_affiliation = affiliation
                duplicate.city = event.city
                duplicate.country = event.country
                duplicate.starts_at = event.starts_at
                duplicate.ends_at = event.ends_at
                duplicate.url = event.url
                duplicate.raw_payload = base_payload
                self._repair_event_researcher(duplicate, speaker_name, affiliation)
                updated += 1
                continue

            if not used_original:
                target = event
                used_original = True
            else:
                target = TalkEvent(
                    source_name=event.source_name,
                    title=event.title,
                    speaker_name=speaker_name,
                    speaker_affiliation=affiliation,
                    city=event.city,
                    country=event.country,
                    starts_at=event.starts_at,
                    ends_at=event.ends_at,
                    url=event.url,
                    source_hash=source_hash,
                    raw_payload=base_payload,
                )
                self.session.add(target)

            target.speaker_name = speaker_name
            target.speaker_affiliation = affiliation
            target.source_hash = source_hash
            target.raw_payload = base_payload
            self._repair_event_researcher(target, speaker_name, affiliation)
            updated += 1

        if not used_original:
            self.session.delete(event)
            updated += 1
        summary.source_counts["multi_speaker_events_split"] = summary.source_counts.get("multi_speaker_events_split", 0) + 1
        return updated

    def _remove_institution_speaker_artifacts(self, summary: PlausibilitySummary) -> int:
        updated = 0
        candidate_researchers: dict[str, Researcher] = {}
        events = self.session.scalars(
            select(TalkEvent).options(selectinload(TalkEvent.researcher).selectinload(Researcher.trip_clusters))
        ).all()
        for event in events:
            if not looks_like_institution_name(event.speaker_name):
                continue
            if event.researcher:
                candidate_researchers[event.researcher.id] = event.researcher
            self.session.delete(event)
            updated += 1
            summary.source_counts["institution_speaker_events_removed"] = (
                summary.source_counts.get("institution_speaker_events_removed", 0) + 1
            )

        if not candidate_researchers:
            return updated

        self.session.flush()
        for researcher in candidate_researchers.values():
            if self._delete_if_orphan_institution_researcher(researcher):
                updated += 1
                summary.source_counts["institution_speaker_profiles_removed"] = (
                    summary.source_counts.get("institution_speaker_profiles_removed", 0) + 1
                )
        return updated

    def _delete_if_orphan_institution_researcher(self, researcher: Researcher) -> bool:
        if not looks_like_institution_name(researcher.name):
            return False
        remaining_event_id = self.session.scalar(
            select(TalkEvent.id).where(TalkEvent.researcher_id == researcher.id).limit(1)
        )
        if remaining_event_id:
            return False
        blocking_relationships = (
            researcher.facts,
            researcher.fact_candidates,
            researcher.identities,
            researcher.documents,
            researcher.outreach_drafts,
            researcher.wishlist_entries,
            researcher.wishlist_match_groups,
            researcher.tour_assembly_proposals,
            researcher.tour_legs,
            researcher.relationship_briefs,
            researcher.feedback_signals,
        )
        if any(blocking_relationships) or researcher.speaker_profile:
            return False
        for cluster in list(researcher.trip_clusters):
            self.session.delete(cluster)
        self.session.delete(researcher)
        return True

    def _repair_researcher_names(self, summary: PlausibilitySummary) -> int:
        updated = 0
        researchers = self.session.scalars(
            select(Researcher).options(selectinload(Researcher.talk_events))
        ).all()
        for researcher in researchers:
            flags = speaker_name_quality_flags(researcher.name)
            if not flags:
                continue

            if researcher.talk_events:
                names = [event.speaker_name for event in researcher.talk_events if event.speaker_name]
                affiliations = [event.speaker_affiliation for event in researcher.talk_events if event.speaker_affiliation]
                clean_name = Counter(names).most_common(1)[0][0] if names else clean_person_display_name(researcher.name)
                clean_affiliation = Counter(affiliations).most_common(1)[0][0] if affiliations else researcher.home_institution
            elif researcher.home_institution:
                normalized = normalize_speaker_identity(researcher.name, researcher.home_institution)
                clean_name = normalized.speaker_name
                clean_affiliation = normalized.affiliation
            else:
                clean_name = clean_person_display_name(researcher.name)
                clean_affiliation = None

            if not clean_name:
                continue
            normalized_name = _normalized_researcher_name(clean_name)
            if not normalized_name:
                continue

            existing = self.session.scalar(
                select(Researcher).where(Researcher.normalized_name == normalized_name, Researcher.id != researcher.id)
            )
            if existing:
                self._merge_researcher_records(researcher, existing)
                self._apply_affiliation(existing, clean_affiliation)
                updated += 1
                summary.source_counts["researcher_profiles_merged"] = summary.source_counts.get("researcher_profiles_merged", 0) + 1
                continue

            researcher.name = clean_name
            researcher.normalized_name = normalized_name
            self._apply_affiliation(researcher, clean_affiliation)
            updated += 1
            summary.source_counts["researcher_names_repaired"] = summary.source_counts.get("researcher_names_repaired", 0) + 1
        return updated

    def _merge_transliteration_aliases(self, summary: PlausibilitySummary) -> int:
        updated = 0
        researchers = self.session.scalars(select(Researcher)).all()
        grouped: dict[str, list[Researcher]] = defaultdict(list)
        for researcher in researchers:
            normalized_name = _normalized_researcher_name(researcher.name)
            if normalized_name:
                grouped[normalized_name].append(researcher)

        for normalized_name, matches in grouped.items():
            if len(matches) == 1:
                researcher = matches[0]
                if researcher.normalized_name != normalized_name:
                    researcher.normalized_name = normalized_name
                    updated += 1
                    summary.source_counts["researcher_identity_keys_repaired"] = (
                        summary.source_counts.get("researcher_identity_keys_repaired", 0) + 1
                    )
                continue

            target = max(matches, key=self._researcher_quality_rank)
            target.normalized_name = normalized_name
            for researcher in matches:
                if researcher.id == target.id:
                    continue
                self._merge_researcher_records(researcher, target)
                updated += 1
                summary.source_counts["transliteration_profiles_merged"] = (
                    summary.source_counts.get("transliteration_profiles_merged", 0) + 1
                )
        return updated

    def _researcher_quality_rank(self, researcher: Researcher) -> tuple[int, int, int, int, int]:
        name_penalty = len(speaker_name_quality_flags(researcher.name))
        return (
            len(researcher.identities),
            len(researcher.talk_events),
            len(researcher.facts),
            len(researcher.fact_candidates),
            -name_penalty,
        )

    def _merge_researcher_records(self, source: Researcher, target: Researcher) -> None:
        if source.id == target.id:
            return
        for relationship_name in (
            "facts",
            "fact_candidates",
            "identities",
            "documents",
            "talk_events",
            "trip_clusters",
            "outreach_drafts",
            "wishlist_entries",
            "wishlist_match_groups",
            "tour_assembly_proposals",
            "tour_legs",
            "relationship_briefs",
            "feedback_signals",
        ):
            for item in list(getattr(source, relationship_name, [])):
                if hasattr(item, "researcher"):
                    item.researcher = target
                else:
                    item.researcher_id = target.id
        if source.speaker_profile and not target.speaker_profile:
            source.speaker_profile.researcher = target
        self.session.flush()
        self.session.delete(source)

    def _dedupe_talk_events(self, summary: PlausibilitySummary) -> int:
        updated = 0
        events = self.session.scalars(select(TalkEvent).order_by(TalkEvent.created_at.desc())).all()
        grouped: dict[tuple[str, str, str, str, str], list[TalkEvent]] = defaultdict(list)
        for event in events:
            key = (
                event.source_name.lower(),
                event.url.strip().lower(),
                event.speaker_name.strip().lower(),
                event.starts_at.isoformat(),
                event.title.strip().lower(),
            )
            grouped[key].append(event)
        for matches in grouped.values():
            if len(matches) <= 1:
                continue
            keep = max(matches, key=self._talk_event_quality_rank)
            for event in matches:
                if event.id == keep.id:
                    continue
                self.session.delete(event)
                updated += 1
            summary.source_counts["duplicate_talk_events_removed"] = (
                summary.source_counts.get("duplicate_talk_events_removed", 0) + len(matches) - 1
            )
        return updated

    def _talk_event_quality_rank(self, event: TalkEvent) -> tuple[int, int, float]:
        payload = event.raw_payload or {}
        has_no_repair_history = 0 if payload.get("speaker_name_before_plausibility") else 1
        quality_flags = payload.get("speaker_quality_flags") or []
        created_at = event.created_at
        created_timestamp = created_at.timestamp() if created_at else 0.0
        return (has_no_repair_history, -len(quality_flags), created_timestamp)

    def _repair_event_researcher(self, event: TalkEvent, speaker_name: str, affiliation: str | None) -> None:
        normalized_name = _normalized_researcher_name(speaker_name)
        if not normalized_name:
            return

        current = event.researcher
        existing = self.session.scalar(select(Researcher).where(Researcher.normalized_name == normalized_name))
        if existing and current and existing.id != current.id:
            event.researcher_id = existing.id
            self._apply_affiliation(existing, affiliation)
            self._repair_event_affiliation_evidence(existing, event, affiliation)
            return

        researcher = current or existing
        if not researcher:
            researcher = Researcher(name=speaker_name, normalized_name=normalized_name)
            self.session.add(researcher)
            self.session.flush()
            event.researcher_id = researcher.id
        researcher.name = speaker_name
        researcher.normalized_name = normalized_name
        self._apply_affiliation(researcher, affiliation)
        self._repair_event_affiliation_evidence(researcher, event, affiliation)

    def _apply_affiliation(self, researcher: Researcher, affiliation: str | None) -> None:
        if affiliation:
            researcher.home_institution = affiliation

    def _repair_event_affiliation_evidence(self, researcher: Researcher, event: TalkEvent, affiliation: str | None) -> None:
        if not affiliation:
            return
        for candidate in researcher.fact_candidates:
            if candidate.fact_type == "home_institution" and candidate.origin == "event_affiliation" and candidate.source_url == event.url:
                candidate.value = affiliation
                candidate.evidence_snippet = "Speaker affiliation observed on a linked seminar source page."
        for fact in researcher.facts:
            if (
                fact.fact_type == "home_institution"
                and fact.source_url == event.url
                and fact.approval_origin != "manual"
            ):
                fact.value = affiliation

    def _quarantine_off_target_documents(self, summary: PlausibilitySummary) -> int:
        updated = 0
        documents = self.session.scalars(
            select(SourceDocument).options(
                selectinload(SourceDocument.researcher).selectinload(Researcher.fact_candidates),
                selectinload(SourceDocument.researcher).selectinload(Researcher.facts),
                selectinload(SourceDocument.fact_candidates),
                selectinload(SourceDocument.approved_facts),
            )
        ).all()
        for document in documents:
            summary.processed_count += 1
            if document.fetch_status != "fetched" or not document.extracted_text or not document.researcher:
                continue
            if document_targets_researcher(document, document.researcher):
                metadata = dict(document.metadata_json or {})
                if metadata.get("plausibility_status") == "quarantined":
                    metadata["plausibility_status"] = "accepted"
                    document.metadata_json = metadata
                    updated += 1
                continue
            updated += self._quarantine_document(document, reason="document_not_researcher_specific")
            summary.source_counts["off_target_documents"] = summary.source_counts.get("off_target_documents", 0) + 1
        return updated

    def _quarantine_document(self, document: SourceDocument, reason: str) -> int:
        updated = 0
        metadata = dict(document.metadata_json or {})
        metadata["plausibility_status"] = "quarantined"
        metadata["plausibility_reason"] = reason
        document.metadata_json = metadata

        now = datetime.now(UTC)
        for candidate in document.fact_candidates:
            if candidate.status != "rejected":
                candidate.status = "rejected"
                candidate.review_note = QUARANTINE_NOTE
                candidate.reviewed_at = now
                updated += 1

        for fact in list(document.approved_facts):
            if fact.approval_origin != "manual":
                self.session.delete(fact)
                updated += 1
        return updated

    def _quarantine_repeated_generic_values(self, summary: PlausibilitySummary) -> int:
        updated = 0
        candidates = self.session.scalars(
            select(FactCandidate).where(
                FactCandidate.status != "rejected",
                FactCandidate.origin == "extracted",
            )
        ).all()
        grouped: dict[tuple[str, str], list[FactCandidate]] = defaultdict(list)
        for candidate in candidates:
            if len(candidate.value.strip()) < GENERIC_LONG_VALUE_THRESHOLD:
                continue
            grouped[(candidate.fact_type, candidate.value.strip().lower())].append(candidate)

        now = datetime.now(UTC)
        for (_, _), matches in grouped.items():
            researcher_count = len({candidate.researcher_id for candidate in matches})
            if researcher_count <= REPEATED_VALUE_RESEARCHER_THRESHOLD:
                continue
            for candidate in matches:
                if candidate.status != "rejected":
                    candidate.status = "rejected"
                    candidate.review_note = "Rejected by Roadshow plausibility check: same long extracted value appears across many researchers."
                    candidate.reviewed_at = now
                    updated += 1
                linked_fact = candidate.approved_fact
                if linked_fact and linked_fact.approval_origin != "manual":
                    self.session.delete(linked_fact)
                    updated += 1
            summary.source_counts["repeated_generic_values"] = summary.source_counts.get("repeated_generic_values", 0) + len(matches)
        return updated

    def _restore_home_institutions(self, summary: PlausibilitySummary) -> int:
        updated = 0
        researchers = self.session.scalars(
            select(Researcher).options(
                selectinload(Researcher.fact_candidates),
                selectinload(Researcher.facts),
                selectinload(Researcher.talk_events),
            )
        ).all()
        for researcher in researchers:
            restored_value = self._best_home_institution_value(researcher)
            if restored_value and restored_value != researcher.home_institution:
                researcher.home_institution = restored_value
                updated += 1
                summary.source_counts["home_institution_restored"] = summary.source_counts.get("home_institution_restored", 0) + 1
        return updated

    def _best_home_institution_value(self, researcher: Researcher) -> str | None:
        event_affiliations = [
            candidate
            for candidate in researcher.fact_candidates
            if candidate.fact_type == "home_institution" and candidate.origin == "event_affiliation" and candidate.status != "rejected"
        ]
        if event_affiliations:
            best_candidate = max(event_affiliations, key=lambda item: (item.status == "approved", item.confidence, item.created_at))
            return best_candidate.value

        home_facts = [
            fact
            for fact in researcher.facts
            if fact.fact_type == "home_institution" and fact.approval_origin != "quarantined"
        ]
        if home_facts:
            best_fact = max(home_facts, key=lambda item: (item.verified, item.confidence, item.approved_at))
            return best_fact.value

        affiliations = [event.speaker_affiliation for event in researcher.talk_events if event.speaker_affiliation]
        if affiliations:
            return Counter(affiliations).most_common(1)[0][0]
        return None
