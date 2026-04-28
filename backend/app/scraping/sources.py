from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import re
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import httpx

from app.core.config import settings
from app.scraping.base import ExtractedHostEvent, ExtractedTalkEvent, RawPage


def _fetch_urls(urls: list[str], client: httpx.Client | None = None) -> list[RawPage]:
    owns_client = client is None
    http_client = client or httpx.Client(timeout=20.0, follow_redirects=True)
    pages: list[RawPage] = []
    try:
        for url in urls:
            response = http_client.get(url)
            response.raise_for_status()
            pages.append(RawPage(url=url, html=response.text))
    finally:
        if owns_client:
            http_client.close()
    return pages


def _text_or_none(node) -> str | None:
    if node is None:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def _first_match(root, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = root.select_one(selector)
        value = _text_or_none(node)
        if value:
            return value
    return None


def _first_attr(root, selectors: list[str], attribute: str) -> str | None:
    for selector in selectors:
        node = root.select_one(selector)
        if node and node.get(attribute):
            return str(node.get(attribute))
    return None


def _parse_datetime(value: str, fallback_tz: str = settings.default_timezone, *, dayfirst: bool = False) -> datetime:
    parsed = date_parser.parse(
        value,
        fuzzy=True,
        dayfirst=dayfirst,
        tzinfos={"CET": ZoneInfo(fallback_tz), "CEST": ZoneInfo(fallback_tz)},
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(fallback_tz))
    return parsed


def _clean_speaker_name(speaker_name: str, affiliation: str | None) -> str:
    cleaned = " ".join(speaker_name.split())
    if affiliation:
        cleaned = cleaned.replace(affiliation, "").strip(" ,;-")
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[0].strip()
    return cleaned


def _normalize_speaker(speaker_name: str, affiliation: str | None) -> tuple[str, str | None]:
    raw_speaker_name = " ".join(speaker_name.split())
    normalized_affiliation = affiliation
    if normalized_affiliation is None and "," in raw_speaker_name:
        raw_speaker_name, normalized_affiliation = [part.strip() for part in raw_speaker_name.split(",", 1)]
    if normalized_affiliation is None and raw_speaker_name.endswith(")") and " (" in raw_speaker_name:
        raw_speaker_name, normalized_affiliation = raw_speaker_name.rsplit(" (", 1)
        normalized_affiliation = normalized_affiliation.rstrip(")")
    return _clean_speaker_name(raw_speaker_name, normalized_affiliation), normalized_affiliation


def _derive_title_and_speaker(title: str, speaker_name: str | None) -> tuple[str, str | None]:
    if " - " not in title:
        return title, speaker_name
    possible_speaker, possible_title = [part.strip() for part in title.split(" - ", 1)]
    if speaker_name is None:
        return possible_title or title, possible_speaker or None
    if possible_speaker.lower() in speaker_name.lower() or speaker_name.lower() in possible_speaker.lower():
        return possible_title or title, speaker_name
    return title, speaker_name


def _uses_dotted_european_date(value: str) -> bool:
    return bool(re.search(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", value))


def _build_source_hash(*parts: str) -> str:
    return sha256("||".join(parts).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class SourceConfig:
    name: str
    urls: list[str]
    city: str
    country: str
    card_selectors: list[str]
    title_selectors: list[str]
    speaker_selectors: list[str]
    affiliation_selectors: list[str]
    date_selectors: list[str]
    link_selectors: list[str]
    text_fallback: str | None = None


class GenericEventSource:
    def __init__(self, config: SourceConfig) -> None:
        self.config = config
        self.name = config.name

    def fetch_pages(self, client: httpx.Client | None = None) -> list[RawPage]:
        return _fetch_urls(self.config.urls, client=client)

    def extract(self, raw_page: RawPage) -> list[ExtractedTalkEvent]:
        soup = BeautifulSoup(raw_page.html, "html.parser")
        cards = []
        for selector in self.config.card_selectors:
            cards.extend(soup.select(selector))
        if not cards:
            cards = [soup]

        events: list[ExtractedTalkEvent] = []
        seen_event_keys: set[tuple[str, str, str, str]] = set()
        for card in cards:
            speaker_name = (
                card.get("data-speaker")
                or _first_attr(card, self.config.speaker_selectors, "data-speaker")
                or _first_match(card, self.config.speaker_selectors)
            )
            date_text = _first_attr(card, self.config.date_selectors, "datetime") or _first_match(card, self.config.date_selectors)
            title = _first_match(card, self.config.title_selectors)
            if not speaker_name or not date_text or not title:
                continue

            try:
                starts_at = _parse_datetime(date_text, dayfirst=_uses_dotted_european_date(date_text))
            except (TypeError, ValueError):
                continue
            ends_at = None
            duration_text = card.get("data-end")
            if duration_text:
                try:
                    ends_at = _parse_datetime(duration_text)
                except (TypeError, ValueError):
                    ends_at = None
            link = _first_attr(card, self.config.link_selectors, "href") or raw_page.url
            if link.startswith("/"):
                parsed = httpx.URL(raw_page.url)
                link = str(parsed.join(link))
            affiliation = _first_match(card, self.config.affiliation_selectors)
            speaker_name, affiliation = _normalize_speaker(str(speaker_name), affiliation)
            title, speaker_name = _derive_title_and_speaker(title, speaker_name)
            signature = (title, speaker_name, starts_at.isoformat(), link)
            if signature in seen_event_keys:
                continue
            seen_event_keys.add(signature)
            events.append(
                ExtractedTalkEvent(
                    source_name=self.name,
                    title=title,
                    speaker_name=speaker_name,
                    speaker_affiliation=affiliation,
                    city=self.config.city,
                    country=self.config.country,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    url=link,
                    raw_payload={"discovered_from": raw_page.url},
                )
            )
        if not events and self.config.text_fallback == "dated_speaker_lines":
            events.extend(self._extract_dated_speaker_lines(raw_page, soup, seen_event_keys))
        return events

    def _extract_dated_speaker_lines(
        self,
        raw_page: RawPage,
        soup: BeautifulSoup,
        seen_event_keys: set[tuple[str, str, str, str]],
    ) -> list[ExtractedTalkEvent]:
        lines = [line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip()]
        pattern = re.compile(r"^(?P<date>\d{2}\.\d{2}\.\d{4})\s+(?P<speaker>[^-]+?)\s+-\s+(?P<affiliation>.+)$")
        events: list[ExtractedTalkEvent] = []
        for index, line in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            speaker_name = _clean_speaker_name(match.group("speaker"), None)
            affiliation = match.group("affiliation").strip()
            try:
                starts_at = _parse_datetime(match.group("date"), dayfirst=True)
            except (TypeError, ValueError):
                continue
            title = f"Seminar with {speaker_name}"
            if index + 1 < len(lines) and not re.match(r"^\d{2}\.\d{2}\.\d{4}", lines[index + 1]):
                possible_title = lines[index + 1].strip().strip('"')
                if possible_title and "term " not in possible_title.lower():
                    title = possible_title
            signature = (title, speaker_name, starts_at.isoformat(), raw_page.url)
            if signature in seen_event_keys:
                continue
            seen_event_keys.add(signature)
            events.append(
                ExtractedTalkEvent(
                    source_name=self.name,
                    title=title,
                    speaker_name=speaker_name,
                    speaker_affiliation=affiliation,
                    city=self.config.city,
                    country=self.config.country,
                    starts_at=starts_at,
                    ends_at=None,
                    url=raw_page.url,
                    raw_payload={"discovered_from": raw_page.url, "fallback": self.config.text_fallback},
                )
            )
        return events


class KofHostCalendarAdapter:
    name = "kof_host_calendar"
    index_url = "https://kof.ethz.ch/en/news-und-veranstaltungen/event-calendar-page.html"

    def fetch_occupied(self, client: httpx.Client | None = None) -> list[ExtractedHostEvent]:
        index_page = _fetch_urls([self.index_url], client=client)[0]
        events: list[ExtractedHostEvent] = []

        detail_urls = self.discover_detail_urls(index_page)
        if detail_urls:
            detail_pages = _fetch_urls(detail_urls, client=client)
            for page in detail_pages:
                event = self.extract_detail(page)
                if event:
                    events.append(event)

        api_url = self.discover_api_url(index_page)
        if api_url:
            http_client = client or httpx.Client(timeout=20.0, follow_redirects=True)
            owns_client = client is None
            try:
                response = http_client.get(api_url)
                response.raise_for_status()
                api_events = self.extract_api_events(response.json(), api_url=api_url, index_url=index_page.url)
                events.extend(api_events)
            finally:
                if owns_client:
                    http_client.close()

        unique: dict[tuple[str, str], ExtractedHostEvent] = {}
        for event in events:
            unique[(event.title, event.starts_at.isoformat())] = event
        return sorted(unique.values(), key=lambda item: item.starts_at)

    def discover_detail_urls(self, raw_page: RawPage) -> list[str]:
        soup = BeautifulSoup(raw_page.html, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        pattern = re.compile(r"event-calendar-page.*\.html$")
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href"))
            if not pattern.search(href):
                continue
            if "veranstaltungsarchiv" in href.lower():
                continue
            absolute = str(httpx.URL(raw_page.url).join(href))
            if absolute == raw_page.url or absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
        return urls

    def discover_api_url(self, raw_page: RawPage) -> str | None:
        soup = BeautifulSoup(raw_page.html, "html.parser")
        calendar = soup.select_one("[data-init='eventCalendar'][data-events-url]")
        if calendar and calendar.get("data-events-url"):
            return str(calendar.get("data-events-url"))
        match = re.search(r'data-events-url="([^"]+)"', raw_page.html)
        if match:
            return match.group(1)
        return None

    def extract_api_events(self, payload: dict, *, api_url: str, index_url: str) -> list[ExtractedHostEvent]:
        events: list[ExtractedHostEvent] = []
        for entry in payload.get("entry-array", []):
            event_id = entry.get("id")
            content = entry.get("content") or {}
            title = content.get("title")
            if not title:
                continue
            for start_at, end_at in self._entry_time_ranges(entry):
                events.append(
                    ExtractedHostEvent(
                        title=title,
                        location=self._entry_location(entry),
                        starts_at=start_at,
                        ends_at=end_at,
                        url=f"{index_url}#event-{event_id}" if event_id else index_url,
                        metadata_json={
                            "source": "kof_api",
                            "event_id": event_id,
                            "api_url": api_url,
                            "series_name": (entry.get("classification") or {}).get("series-name"),
                            "entry_type": (entry.get("classification") or {}).get("entry-type-desc"),
                            "speakers": self._entry_speakers(entry),
                        },
                    )
                )
        return events

    def _entry_time_ranges(self, entry: dict) -> list[tuple[datetime, datetime | None]]:
        indication = entry.get("date-time-indication") or {}
        ranges: list[tuple[datetime, datetime | None]] = []
        for timerange in indication.get("in-progress-timerange-array", []):
            start_text = timerange.get("date-time-from")
            end_text = timerange.get("date-time-to")
            if not start_text:
                continue
            start_at = _parse_datetime(start_text)
            end_at = _parse_datetime(end_text) if end_text else None
            ranges.append((start_at, end_at))

        if ranges:
            return ranges

        for item in indication.get("date-with-times-array", []):
            date_text = item.get("date")
            if not date_text:
                continue
            start_text = f"{date_text} {item.get('time-from') or '00:00'}"
            end_text = f"{date_text} {item.get('time-to')}" if item.get("time-to") else None
            start_at = _parse_datetime(start_text)
            end_at = _parse_datetime(end_text) if end_text else None
            ranges.append((start_at, end_at))
        return ranges

    def _entry_location(self, entry: dict) -> str | None:
        location = entry.get("location") or {}
        internal = location.get("internal") or {}
        external = location.get("external") or {}
        if internal:
            parts = [
                internal.get("building"),
                internal.get("floor"),
                internal.get("room"),
                internal.get("area-desc"),
            ]
            return ", ".join(str(part).strip() for part in parts if part)
        if external:
            return ", ".join(str(value).strip() for value in external.values() if value)
        return None

    def _entry_speakers(self, entry: dict) -> list[dict]:
        speakers: list[dict] = []
        for owner in entry.get("function-owner-array", []):
            if owner.get("function-desc") != "Speaker":
                continue
            speakers.append(
                {
                    "first_name": str(owner.get("first-name") or "").strip(),
                    "last_name": str(owner.get("last-name") or "").strip(),
                    "person_url": owner.get("person-url"),
                }
            )
        return speakers

    def extract_detail(self, raw_page: RawPage) -> ExtractedHostEvent | None:
        soup = BeautifulSoup(raw_page.html, "html.parser")
        title = _first_match(soup, ["h1", ".event-title", "title"])
        date_text = _first_match(
            soup,
            [
                "[data-event-date]",
                ".event-date",
                ".date",
                ".main-information",
                ".content",
            ],
        )
        if not title or not date_text:
            return None
        starts_at = _parse_datetime(date_text)
        ends_at = starts_at + timedelta(hours=1, minutes=30)
        location = _first_match(soup, [".location", ".event-location", "address", "body"])
        return ExtractedHostEvent(
            title=title,
            location=location,
            starts_at=starts_at,
            ends_at=ends_at,
            url=raw_page.url,
            metadata_json={"source": "kof"},
        )


BOCCONI_SOURCE = SourceConfig(
    name="bocconi",
    urls=["https://economics.unibocconi.eu/events-research"],
    city="Milan",
    country="Italy",
    card_selectors=["article.node--event", ".views-row article", ".event-card", ".seminar-card", "article[data-speaker]"],
    title_selectors=[".node__title", "h3", "h2", ".event-title"],
    speaker_selectors=["[data-speaker]", ".event__speaker--speaker", ".speaker", ".speaker-name"],
    affiliation_selectors=[".c-speaker__university", ".affiliation", ".speaker-affiliation", ".institution"],
    date_selectors=["time", ".event-date", "[data-date]"],
    link_selectors=["a[href]"],
)

MANNHEIM_SOURCE = SourceConfig(
    name="mannheim",
    urls=["https://www.vwl.uni-mannheim.de/forschung/forschungsseminare/mannheim-applied-seminar/"],
    city="Mannheim",
    country="Germany",
    card_selectors=["table tr", ".seminar-list__item", ".event-card", "article[data-speaker]"],
    title_selectors=["td:nth-of-type(4)", "h3", "h2", ".event-title"],
    speaker_selectors=["td:nth-of-type(3)", ".speaker", "[data-speaker]", ".speaker-name"],
    affiliation_selectors=[".affiliation", ".speaker-affiliation", ".institution"],
    date_selectors=["td:nth-of-type(1)", "time", ".date", ".event-date", "[data-date]"],
    link_selectors=["a[href]"],
)

BONN_SOURCE = SourceConfig(
    name="bonn",
    urls=["https://www.econ.uni-bonn.de/micro/en/seminars"],
    city="Bonn",
    country="Germany",
    card_selectors=[".event-item", ".seminar-item", "article[data-speaker]"],
    title_selectors=["h3", "h2", ".event-title"],
    speaker_selectors=[".speaker", "[data-speaker]", ".speaker-name"],
    affiliation_selectors=[".affiliation", ".speaker-affiliation", ".institution"],
    date_selectors=["time", ".date", ".event-date", "[data-date]"],
    link_selectors=["a[href]"],
    text_fallback="dated_speaker_lines",
)

ECB_SOURCE = SourceConfig(
    name="ecb",
    urls=["https://www.ecb.europa.eu/press/conferences/html/index.en.html"],
    city="Frankfurt",
    country="Germany",
    card_selectors=[".event-card", ".seminar-item", "article[data-speaker]"],
    title_selectors=["h3", "h2", ".title"],
    speaker_selectors=[".speaker", "[data-speaker]", ".speaker-name"],
    affiliation_selectors=[".affiliation", ".speaker-affiliation", ".institution"],
    date_selectors=["time", ".date", ".event-date", "[data-date]"],
    link_selectors=["a[href]"],
)

BIS_SOURCE = SourceConfig(
    name="bis",
    urls=["https://www.bis.org/events/index.htm"],
    city="Basel",
    country="Switzerland",
    card_selectors=[".event-card", ".event-item", "article[data-speaker]"],
    title_selectors=["h3", "h2", ".title"],
    speaker_selectors=[".speaker", "[data-speaker]", ".speaker-name"],
    affiliation_selectors=[".affiliation", ".speaker-affiliation", ".institution"],
    date_selectors=["time", ".date", ".event-date", "[data-date]"],
    link_selectors=["a[href]"],
)


def iter_source_adapters() -> list[GenericEventSource]:
    return [
        GenericEventSource(BOCCONI_SOURCE),
        GenericEventSource(MANNHEIM_SOURCE),
        GenericEventSource(BONN_SOURCE),
        GenericEventSource(ECB_SOURCE),
        GenericEventSource(BIS_SOURCE),
    ]


def get_host_calendar_adapter() -> KofHostCalendarAdapter:
    return KofHostCalendarAdapter()


__all__ = [
    "_build_source_hash",
    "GenericEventSource",
    "KofHostCalendarAdapter",
    "get_host_calendar_adapter",
    "iter_source_adapters",
]
