from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.scraping.sources import get_host_calendar_adapter, iter_source_adapters


@dataclass(slots=True)
class SourceAuditResult:
    source_name: str
    source_type: str
    status: str
    page_count: int = 0
    event_count: int = 0
    samples: list[str] = field(default_factory=list)
    error: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SourceAuditor:
    def audit(self) -> list[SourceAuditResult]:
        results: list[SourceAuditResult] = []
        for adapter in iter_source_adapters():
            try:
                pages = adapter.fetch_pages()
                events = []
                for page in pages:
                    events.extend(adapter.extract(page))
                results.append(
                    SourceAuditResult(
                        source_name=adapter.name,
                        source_type="external_opportunity",
                        status="ok",
                        page_count=len(pages),
                        event_count=len(events),
                        samples=[
                            f"{event.starts_at.date().isoformat()} - {event.speaker_name} - {event.title[:80]}"
                            for event in events[:3]
                        ],
                    )
                )
            except Exception as exc:  # pragma: no cover - live network audit path
                results.append(
                    SourceAuditResult(
                        source_name=adapter.name,
                        source_type="external_opportunity",
                        status="error",
                        error=f"{type(exc).__name__}: {str(exc)[:300]}",
                    )
                )

        adapter = get_host_calendar_adapter()
        try:
            host_events = adapter.fetch_occupied()
            results.append(
                SourceAuditResult(
                    source_name=adapter.name,
                    source_type="host_calendar",
                    status="ok",
                    event_count=len(host_events),
                    samples=[
                        f"{event.starts_at.date().isoformat()} - {event.title[:100]}"
                        for event in host_events[:3]
                    ],
                )
            )
        except Exception as exc:  # pragma: no cover - live network audit path
            results.append(
                SourceAuditResult(
                    source_name=adapter.name,
                    source_type="host_calendar",
                    status="error",
                    error=f"{type(exc).__name__}: {str(exc)[:300]}",
                )
            )
        return results
