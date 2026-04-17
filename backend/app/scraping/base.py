from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import httpx


@dataclass(slots=True)
class RawPage:
    url: str
    html: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ExtractedTalkEvent:
    source_name: str
    title: str
    speaker_name: str
    speaker_affiliation: str | None
    city: str
    country: str
    starts_at: datetime
    ends_at: datetime | None
    url: str
    raw_payload: dict


@dataclass(slots=True)
class ExtractedHostEvent:
    title: str
    location: str | None
    starts_at: datetime
    ends_at: datetime | None
    url: str
    metadata_json: dict


class SourceAdapter(Protocol):
    name: str

    def fetch_pages(self, client: httpx.Client | None = None) -> list[RawPage]: ...

    def extract(self, raw_page: RawPage) -> list[ExtractedTalkEvent]: ...


class HostCalendarAdapter(Protocol):
    name: str

    def fetch_occupied(self, client: httpx.Client | None = None) -> list[ExtractedHostEvent]: ...
