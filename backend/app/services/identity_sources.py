from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from app.scraping.name_quality import person_identity_key


def normalize_name(value: str) -> str:
    return person_identity_key(value)


def normalize_institution_name(value: str) -> str:
    lowered = person_identity_key(value)
    return re.sub(r"\s+", " ", lowered).strip()


def _name_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_name(left), normalize_name(right)).ratio()


def _text_value(value: Any) -> str | None:
    if isinstance(value, dict):
        raw = value.get("value")
        return str(raw).strip() if raw else None
    if isinstance(value, str):
        return value.strip()
    return None


def _orcid_date(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    year = _text_value(value.get("year"))
    month = _text_value(value.get("month"))
    day = _text_value(value.get("day"))
    return "-".join(part for part in [year, month, day] if part) or None


@dataclass(slots=True)
class OrcidMatch:
    external_id: str
    canonical_name: str
    profile_url: str
    match_confidence: float
    metadata_json: dict[str, Any]


@dataclass(slots=True)
class OrcidRecord:
    external_id: str
    profile_url: str
    canonical_name: str
    extracted_text: str
    linked_urls: list[str]
    education_facts: list[dict[str, Any]]
    employment_facts: list[dict[str, Any]]
    metadata_json: dict[str, Any]


class OrcidClient:
    def __init__(self, client: httpx.Client | None = None, base_url: str = "https://pub.orcid.org") -> None:
        self.client = client or httpx.Client(timeout=20.0, follow_redirects=True)
        self.base_url = base_url.rstrip("/")

    def search_person(self, name: str, affiliation: str | None = None) -> OrcidMatch | None:
        query = self._query_for_name(name, affiliation)
        response = self.client.get(
            f"{self.base_url}/v3.0/expanded-search/",
            params={"q": query, "rows": 10},
            headers={"Accept": "application/vnd.orcid+json"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        raw_results = payload.get("expanded-result") or []
        if not isinstance(raw_results, list):
            return None
        candidates = [self._match_from_result(name, affiliation, result) for result in raw_results]
        candidates = [candidate for candidate in candidates if candidate and candidate.match_confidence >= 0.7]
        return max(candidates, key=lambda candidate: candidate.match_confidence) if candidates else None

    def fetch_record(self, external_id: str) -> OrcidRecord | None:
        response = self.client.get(
            f"{self.base_url}/v3.0/{external_id}/record",
            headers={"Accept": "application/vnd.orcid+json"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        canonical_name = self._name_from_record(payload) or external_id
        linked_urls = self._researcher_urls(payload)
        education_facts = self._affiliation_facts(payload, "educations")
        employment_facts = self._affiliation_facts(payload, "employments")
        extracted_text = self._record_text(canonical_name, education_facts, employment_facts, linked_urls)
        return OrcidRecord(
            external_id=external_id,
            profile_url=f"https://orcid.org/{external_id}",
            canonical_name=canonical_name,
            extracted_text=extracted_text,
            linked_urls=linked_urls,
            education_facts=education_facts,
            employment_facts=employment_facts,
            metadata_json={
                "source": "orcid_record",
                "linked_urls": linked_urls,
                "education_count": len(education_facts),
                "employment_count": len(employment_facts),
            },
        )

    def _query_for_name(self, name: str, affiliation: str | None) -> str:
        tokens = normalize_name(name).split()
        if len(tokens) >= 2:
            query = f'given-names:{tokens[0]} AND family-name:{tokens[-1]}'
        else:
            query = f'text:"{name}"'
        if affiliation:
            cleaned_affiliation = normalize_institution_name(affiliation)
            if cleaned_affiliation:
                query = f"{query} AND affiliation-org-name:({cleaned_affiliation})"
        return query

    def _match_from_result(self, query_name: str, affiliation: str | None, result: dict[str, Any]) -> OrcidMatch | None:
        external_id = result.get("orcid-id")
        if not external_id:
            return None
        given = result.get("given-names") or ""
        family = result.get("family-names") or ""
        credit = result.get("credit-name") or ""
        canonical_name = (credit or f"{given} {family}").strip()
        if not canonical_name:
            return None
        confidence = _name_similarity(query_name, canonical_name)
        institutions = result.get("institution-name") or []
        if isinstance(institutions, str):
            institutions = [institutions]
        if affiliation and any(normalize_institution_name(affiliation) in normalize_institution_name(item) for item in institutions):
            confidence = min(1.0, confidence + 0.12)
        return OrcidMatch(
            external_id=external_id,
            canonical_name=canonical_name,
            profile_url=f"https://orcid.org/{external_id}",
            match_confidence=confidence,
            metadata_json={"source": "orcid_expanded_search", "institutions": institutions},
        )

    def _name_from_record(self, payload: dict[str, Any]) -> str | None:
        name = (payload.get("person") or {}).get("name") or {}
        credit = _text_value(name.get("credit-name"))
        given = _text_value(name.get("given-names"))
        family = _text_value(name.get("family-name"))
        return credit or " ".join(part for part in [given, family] if part).strip() or None

    def _researcher_urls(self, payload: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        person = payload.get("person") or {}
        entries = ((person.get("researcher-urls") or {}).get("researcher-url")) or []
        for entry in entries:
            raw_url = ((entry.get("url") or {}).get("value")) if isinstance(entry, dict) else None
            if raw_url and raw_url not in urls:
                urls.append(raw_url)
        return urls

    def _affiliation_facts(self, payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        activity_summary = payload.get("activities-summary") or {}
        container = activity_summary.get(key) or {}
        facts: list[dict[str, Any]] = []
        for group in container.get("affiliation-group") or []:
            for item in group.get("summaries") or []:
                summary = item.get("education-summary") if key == "educations" else item.get("employment-summary")
                if not summary:
                    continue
                org = summary.get("organization") or {}
                org_name = org.get("name")
                role_title = summary.get("role-title")
                if not org_name and not role_title:
                    continue
                facts.append(
                    {
                        "organization": org_name,
                        "role_title": role_title,
                        "start_date": _orcid_date(summary.get("start-date")),
                        "end_date": _orcid_date(summary.get("end-date")),
                        "source": key[:-1],
                    }
                )
        return facts

    def _record_text(
        self,
        canonical_name: str,
        education_facts: list[dict[str, Any]],
        employment_facts: list[dict[str, Any]],
        linked_urls: list[str],
    ) -> str:
        lines = [canonical_name]
        for fact in education_facts:
            lines.append(
                "Education: "
                + ", ".join(str(value) for value in [fact.get("role_title"), fact.get("organization"), fact.get("end_date")] if value)
            )
        for fact in employment_facts:
            lines.append(
                "Employment: "
                + ", ".join(str(value) for value in [fact.get("role_title"), fact.get("organization"), fact.get("start_date")] if value)
            )
        lines.extend(f"Researcher URL: {url}" for url in linked_urls)
        return "\n".join(lines)


@dataclass(slots=True)
class RepecGenealogyEntry:
    external_id: str
    canonical_name: str
    profile_url: str
    terminal_degree_institution: str | None
    graduation_year: int | None
    advisors: list[str]
    extracted_text: str
    linked_urls: list[str]


class RepecGenealogyClient:
    def __init__(self, client: httpx.Client | None = None, base_url: str = "https://genealogy.repec.org") -> None:
        self.client = client or httpx.Client(timeout=20.0, follow_redirects=True)
        self.base_url = base_url.rstrip("/")

    def fetch_by_repec_id(self, external_id: str) -> RepecGenealogyEntry | None:
        response = self.client.get(f"{self.base_url}/pages/{external_id}.html")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return self._parse_entry(response.text, f"{self.base_url}/pages/{external_id}.html", external_id)

    def search_by_name(self, name: str) -> RepecGenealogyEntry | None:
        response = self.client.get(f"{self.base_url}/list.html")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        query_key = normalize_name(name)
        best: tuple[float, str] | None = None
        for anchor in soup.select('a[href*="/pages/"], a[href^="pages/"]'):
            label = anchor.get_text(" ", strip=True)
            score = _name_similarity(name, self._display_name_from_list_label(label))
            if score < 0.86:
                continue
            href = str(anchor.get("href"))
            external_id = href.rstrip("/").rsplit("/", 1)[-1].replace(".html", "")
            if normalize_name(label) == query_key:
                best = (1.0, external_id)
                break
            if best is None or score > best[0]:
                best = (score, external_id)
        return self.fetch_by_repec_id(best[1]) if best else None

    def _parse_entry(self, html: str, url: str, external_id: str) -> RepecGenealogyEntry | None:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        title = soup.find("h1")
        canonical_name = ""
        if title:
            canonical_name = re.sub(r"^RePEc Genealogy page for\s+", "", title.get_text(" ", strip=True), flags=re.IGNORECASE)
        degree_match = re.search(
            r"(.+?)\s+got the terminal degree from\s+(.+?)\s+in\s+(\d{4})\.",
            re.sub(r"\s+", " ", text),
            re.IGNORECASE,
        )
        terminal_degree_institution = degree_match.group(2).strip() if degree_match else None
        graduation_year = int(degree_match.group(3)) if degree_match else None
        if not canonical_name and degree_match:
            canonical_name = degree_match.group(1).strip()
        advisors = self._parse_advisors(text)
        linked_urls = []
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href"))
            joined = urljoin(url, href)
            if joined not in linked_urls:
                linked_urls.append(joined)
        if not canonical_name:
            return None
        return RepecGenealogyEntry(
            external_id=external_id,
            canonical_name=canonical_name,
            profile_url=url,
            terminal_degree_institution=terminal_degree_institution,
            graduation_year=graduation_year,
            advisors=advisors,
            extracted_text=text,
            linked_urls=linked_urls,
        )

    def _parse_advisors(self, text: str) -> list[str]:
        if "No advisor listed" in text:
            return []
        match = re.search(r"## Advisor\s+(.*?)\s+## Students", text, re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        advisor_block = match.group(1)
        advisors = [line.strip(" 0123456789.") for line in advisor_block.splitlines() if line.strip()]
        return [advisor for advisor in advisors if advisor and "advisor" not in advisor.lower()]

    def _display_name_from_list_label(self, label: str) -> str:
        label = re.sub(r"\(\d{4}\)\s*$", "", label).strip()
        if "," in label:
            family, given = [part.strip() for part in label.split(",", 1)]
            return f"{given} {family}".strip()
        return label


@dataclass(slots=True)
class CeprProfile:
    external_id: str
    canonical_name: str
    profile_url: str
    title: str
    extracted_text: str
    linked_urls: list[str]
    orcid_id: str | None
    home_institution: str | None
    phd_institution: str | None
    metadata_json: dict[str, Any]


class CeprClient:
    def __init__(self, client: httpx.Client | None = None, base_url: str = "https://cepr.org") -> None:
        self.client = client or httpx.Client(timeout=20.0, follow_redirects=True)
        self.base_url = base_url.rstrip("/")

    def fetch_profile(self, name: str) -> CeprProfile | None:
        slug = self._slug_for_name(name)
        if not slug:
            return None
        url = f"{self.base_url}/about/people/{slug}"
        response = self.client.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        profile = self._parse_profile(response.text, url, slug)
        if not profile or _name_similarity(name, profile.canonical_name) < 0.82:
            return None
        return profile

    def _parse_profile(self, html: str, url: str, slug: str) -> CeprProfile | None:
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find("h1")
        canonical_name = heading.get_text(" ", strip=True) if heading else ""
        if not canonical_name:
            return None
        title = soup.title.get_text(" ", strip=True) if soup.title else f"{canonical_name} | CEPR"
        extracted_text = " ".join(soup.stripped_strings)
        linked_urls = self._linked_urls(soup, url)
        role_line = self._role_line(soup, canonical_name)
        return CeprProfile(
            external_id=slug,
            canonical_name=canonical_name,
            profile_url=url,
            title=title,
            extracted_text=extracted_text,
            linked_urls=linked_urls,
            orcid_id=self._orcid_id(extracted_text),
            home_institution=self._home_institution(role_line),
            phd_institution=self._phd_institution(extracted_text),
            metadata_json={
                "source": "cepr_profile",
                "role_line": role_line,
                "linked_urls": linked_urls,
            },
        )

    def _slug_for_name(self, name: str) -> str:
        tokens = normalize_name(name).split()
        return "-".join(tokens)

    def _linked_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls: list[str] = []
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href")).strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            joined = urljoin(base_url, href)
            if joined not in urls:
                urls.append(joined)
        return urls

    def _role_line(self, soup: BeautifulSoup, canonical_name: str) -> str | None:
        heading = soup.find("h1")
        if heading:
            for sibling in heading.find_all_next(["h2", "h3", "h4", "p"], limit=4):
                text = sibling.get_text(" ", strip=True)
                if text and canonical_name not in text and " at " in text.lower():
                    return text
        text = soup.get_text("\n", strip=True)
        for line in text.splitlines():
            if " at " in line.lower() and len(line) < 180:
                return line.strip()
        return None

    def _orcid_id(self, text: str) -> str | None:
        match = re.search(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", text)
        return match.group(0) if match else None

    def _home_institution(self, role_line: str | None) -> str | None:
        if not role_line:
            return None
        match = re.search(r"\bat\s+(.+)$", role_line, re.IGNORECASE)
        if not match:
            return None
        institution = re.sub(r"\([^)]*\)", "", match.group(1)).strip(" .")
        return institution or None

    def _phd_institution(self, text: str) -> str | None:
        patterns = [
            r"obtained (?:his|her|their)?\s*PhD(?:\s+in\s+[A-Za-z ]+)?\s+from\s+(?:the\s+)?([^.;,]+)",
            r"received (?:his|her|their)?\s*Ph\.?D\.?(?:\s+in\s+[A-Za-z ]+)?\s+from\s+(?:the\s+)?([^.;,]+)",
            r"Ph\.?D\.?(?:\s+in\s+[A-Za-z ]+)?\s+from\s+(?:the\s+)?([^.;,]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .")
                return value or None
        return None
