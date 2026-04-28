from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import SourceHealthCheck
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


@dataclass(slots=True)
class SourceReliabilityResult:
    source_name: str
    source_type: str
    latest_status: str
    latest_event_count: int
    previous_event_count: int | None
    checks_recorded: int
    success_rate: float
    average_event_count: float
    trend: str
    needs_attention: bool
    attention_reason: str | None
    latest_checked_at: datetime


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

    def record(self, session: Session) -> list[SourceHealthCheck]:
        records: list[SourceHealthCheck] = []
        for result in self.audit():
            record = SourceHealthCheck(
                source_name=result.source_name,
                source_type=result.source_type,
                status=result.status,
                page_count=result.page_count,
                event_count=result.event_count,
                samples=result.samples,
                error=result.error,
                checked_at=result.checked_at,
            )
            session.add(record)
            records.append(record)
        session.flush()
        return records


class SourceReliabilityService:
    def summarize(self, session: Session, per_source_limit: int = 10) -> list[SourceReliabilityResult]:
        records = session.scalars(select(SourceHealthCheck).order_by(SourceHealthCheck.source_name, SourceHealthCheck.checked_at.desc())).all()
        grouped: dict[str, list[SourceHealthCheck]] = {}
        for record in records:
            group = grouped.setdefault(record.source_name, [])
            if len(group) < per_source_limit:
                group.append(record)

        summaries = [self._summarize_group(group) for group in grouped.values() if group]
        return sorted(summaries, key=lambda item: (not item.needs_attention, item.source_name))

    def _summarize_group(self, records: list[SourceHealthCheck]) -> SourceReliabilityResult:
        latest = records[0]
        previous = records[1] if len(records) > 1 else None
        ok_count = sum(1 for record in records if record.status == "ok")
        average_event_count = sum(record.event_count for record in records) / len(records)
        trend, needs_attention, attention_reason = self._trend(latest, previous)
        return SourceReliabilityResult(
            source_name=latest.source_name,
            source_type=latest.source_type,
            latest_status=latest.status,
            latest_event_count=latest.event_count,
            previous_event_count=previous.event_count if previous else None,
            checks_recorded=len(records),
            success_rate=round(ok_count / len(records), 3),
            average_event_count=round(average_event_count, 2),
            trend=trend,
            needs_attention=needs_attention,
            attention_reason=attention_reason,
            latest_checked_at=latest.checked_at,
        )

    def _trend(self, latest: SourceHealthCheck, previous: SourceHealthCheck | None) -> tuple[str, bool, str | None]:
        if latest.status != "ok":
            return "failing", True, latest.error or "Latest audit failed."
        if latest.event_count == 0:
            return "empty", True, "Latest audit found no extractable events."
        if previous is None:
            return "new", False, None
        if latest.event_count < previous.event_count:
            return "degrading", True, f"Event count fell from {previous.event_count} to {latest.event_count}."
        if latest.event_count > previous.event_count:
            return "improving", False, None
        return "stable", False, None
