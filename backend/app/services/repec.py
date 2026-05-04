from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any

from bs4 import BeautifulSoup
import httpx


def _normalize_person_name(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"\b(professor|prof|dr|ph\.?d\.?)\b", " ", lowered)
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _extract_external_id(url: str) -> str:
    match = re.search(r"/[ef]/([^/?#]+?)(?:\.html)?(?:[?#]|$)", url)
    if match:
        return match.group(1)
    return url.rstrip("/").rsplit("/", 1)[-1]


@dataclass(slots=True)
class RepecMatch:
    external_id: str
    canonical_name: str
    profile_url: str
    match_confidence: float
    ranking_percentile: float | None
    ranking_label: str | None
    metadata_json: dict[str, Any]


class RepecClient:
    def __init__(self, client: httpx.Client | None = None, base_url: str = "https://ideas.repec.org") -> None:
        self.client = client or httpx.Client(timeout=20.0, follow_redirects=True)
        self.base_url = base_url.rstrip("/")

    def search_author(self, name: str) -> RepecMatch | None:
        candidates = self._search_json_endpoint(name)
        if not candidates:
            candidates = self._search_html_endpoint(name)
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate.match_confidence)

    def top_authors(self, limit: int = 200) -> list[RepecMatch]:
        response = self.client.get(f"{self.base_url}/top/top.person.all.html")
        response.raise_for_status()
        return self._parse_top_authors(response.text, limit)

    def _search_json_endpoint(self, name: str) -> list[RepecMatch]:
        response = self.client.get(f"{self.base_url}/cgi-bin/esearch.cgi", params={"q": name})
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            return []
        raw_results = payload.get("results", [])
        candidates: list[RepecMatch] = []
        for raw_result in raw_results:
            candidate = self._candidate_from_json(name, raw_result)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _candidate_from_json(self, query_name: str, raw_result: dict[str, Any]) -> RepecMatch | None:
        profile_url = (
            raw_result.get("profile_url")
            or raw_result.get("url")
            or raw_result.get("id")
            or raw_result.get("link")
        )
        if not profile_url:
            return None
        if profile_url.startswith("/"):
            profile_url = f"{self.base_url}{profile_url}"

        canonical_name = raw_result.get("canonical_name") or raw_result.get("text") or raw_result.get("name")
        if not canonical_name:
            return None

        return RepecMatch(
            external_id=raw_result.get("external_id") or _extract_external_id(profile_url),
            canonical_name=canonical_name.strip(),
            profile_url=profile_url,
            match_confidence=self._name_similarity(query_name, canonical_name),
            ranking_percentile=self._coerce_float(raw_result.get("ranking_percentile") or raw_result.get("rank_percentile")),
            ranking_label=raw_result.get("ranking_label") or raw_result.get("rank_label"),
            metadata_json=raw_result,
        )

    def _search_html_endpoint(self, name: str) -> list[RepecMatch]:
        responses = [
            self.client.get(f"{self.base_url}/search.html", params={"q": name}),
            self.client.post(f"{self.base_url}/cgi-bin/htsearch2", data={"q": name}),
        ]
        for response in responses:
            if response.status_code >= 400:
                continue
            candidates = self._parse_html_candidates(name, response.text)
            if candidates:
                return candidates
        return []

    def _parse_html_candidates(self, query_name: str, html: str) -> list[RepecMatch]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[RepecMatch] = []
        seen_profile_urls: set[str] = set()
        for anchor in soup.select('a[href*="/e/"], a[href*="/f/"]'):
            profile_url = str(anchor.get("href"))
            if profile_url.startswith("/"):
                profile_url = f"{self.base_url}{profile_url}"
            if profile_url in seen_profile_urls:
                continue
            seen_profile_urls.add(profile_url)
            canonical_name = anchor.get_text(" ", strip=True)
            if not canonical_name:
                continue
            candidate = RepecMatch(
                external_id=_extract_external_id(profile_url),
                canonical_name=canonical_name,
                profile_url=profile_url,
                match_confidence=self._name_similarity(query_name, canonical_name),
                ranking_percentile=None,
                ranking_label=None,
                metadata_json={"discovered_via": "html_search"},
            )
            if candidate.match_confidence >= 0.45:
                candidates.append(candidate)
        return candidates

    def _parse_top_authors(self, html: str, limit: int) -> list[RepecMatch]:
        soup = BeautifulSoup(html, "html.parser")
        total_authors = self._extract_total_authors(soup.get_text(" ", strip=True))
        matches: list[RepecMatch] = []
        seen_ids: set[str] = set()
        for row in soup.select("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            try:
                rank = int(cells[0].get_text(" ", strip=True))
            except ValueError:
                continue
            if rank > limit:
                break
            author_anchor = None
            for anchor in cells[1].select('a[href*="/e/"], a[href*="/f/"]'):
                label = anchor.get_text(" ", strip=True)
                if label:
                    author_anchor = anchor
                    break
            if author_anchor is None:
                continue
            profile_url = str(author_anchor.get("href"))
            if profile_url.startswith("/"):
                profile_url = f"{self.base_url}{profile_url}"
            canonical_name = author_anchor.get_text(" ", strip=True).replace(" †", "").strip()
            external_id = _extract_external_id(profile_url)
            if external_id in seen_ids:
                continue
            seen_ids.add(external_id)
            score = self._coerce_float(cells[2].get_text(" ", strip=True)) if len(cells) > 2 else None
            percentile = round((rank / total_authors) * 100, 4) if total_authors else None
            matches.append(
                RepecMatch(
                    external_id=external_id,
                    canonical_name=canonical_name,
                    profile_url=profile_url,
                    match_confidence=1.0,
                    ranking_percentile=percentile,
                    ranking_label=f"RePEc worldwide rank #{rank}",
                    metadata_json={
                        "source": "repec_top_authors",
                        "ranking_url": f"{self.base_url}/top/top.person.all.html",
                        "rank": rank,
                        "score": score,
                        "total_authors": total_authors,
                    },
                )
            )
            if len(matches) >= limit:
                break
        return matches

    def _extract_total_authors(self, text: str) -> int | None:
        match = re.search(r"There are\s+([0-9, ]+)\s+registered authors", text, re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1).replace(",", "").replace(" ", ""))
        except ValueError:
            return None

    def _name_similarity(self, left: str, right: str) -> float:
        return SequenceMatcher(None, _normalize_person_name(left), _normalize_person_name(right)).ratio()

    def _coerce_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
