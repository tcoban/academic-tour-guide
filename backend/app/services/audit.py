from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import SourceHealthCheck
from app.scraping.sources import get_host_calendar_adapter, iter_source_adapters, source_registry_by_name


@dataclass(slots=True)
class SourceAuditResult:
    source_name: str
    source_type: str
    status: str
    page_count: int = 0
    event_count: int = 0
    samples: list[str] = field(default_factory=list)
    error: str | None = None
    official_url: str | None = None
    parser_strategy: str | None = None
    needs_adapter: bool = False
    action_label: str | None = None
    action_href: str | None = None
    consequence: str | None = None
    disabled_reason: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class SourceReliabilityResult:
    source_name: str
    source_type: str
    latest_status: str
    latest_event_count: int
    last_event_count: int
    previous_event_count: int | None
    checks_recorded: int
    success_rate: float
    average_event_count: float
    trend: str
    needs_attention: bool
    attention_reason: str | None
    latest_checked_at: datetime | None
    last_success_at: datetime | None = None
    latest_error: str | None = None
    official_url: str | None = None
    parser_strategy: str | None = None
    needs_adapter: bool = False
    action_label: str | None = None
    action_href: str | None = None
    consequence: str | None = None
    disabled_reason: str | None = None


def _source_action(
    *,
    official_url: str | None,
    status: str,
    event_count: int,
    needs_adapter: bool,
) -> tuple[str | None, str | None, str | None, str | None]:
    if official_url and (status != "ok" or event_count == 0 or needs_adapter):
        return (
            "Open official source",
            official_url,
            "Opens the watched institution page so the operator can verify whether public future events exist.",
            None,
        )
    if status != "ok" or event_count == 0 or needs_adapter:
        return (
            "Run source operations",
            "/source-health#source-operations",
            "Reruns the source audit or source sync and records the latest parser status.",
            None,
        )
    return None, None, None, None


class SourceAuditor:
    def audit(self) -> list[SourceAuditResult]:
        results: list[SourceAuditResult] = []
        for adapter in iter_source_adapters():
            registry_entry = source_registry_by_name().get(adapter.name)
            needs_adapter = bool(getattr(adapter, "needs_adapter", False))
            if needs_adapter:
                official_url = registry_entry.official_url if registry_entry else getattr(adapter, "official_url", None)
                action_label, action_href, consequence, disabled_reason = _source_action(
                    official_url=official_url,
                    status="needs_adapter",
                    event_count=0,
                    needs_adapter=True,
                )
                results.append(
                    SourceAuditResult(
                        source_name=adapter.name,
                        source_type="external_opportunity",
                        status="needs_adapter",
                        error="Official source registered; extraction adapter is not production-ready yet.",
                        official_url=official_url,
                        parser_strategy=getattr(adapter, "parser_strategy", None),
                        needs_adapter=True,
                        action_label=action_label,
                        action_href=action_href,
                        consequence=consequence,
                        disabled_reason=disabled_reason,
                    )
                )
                continue
            try:
                pages = adapter.fetch_pages()
                events = []
                for page in pages:
                    events.extend(adapter.extract(page))
                official_url = registry_entry.official_url if registry_entry else getattr(adapter, "official_url", None)
                action_label, action_href, consequence, disabled_reason = _source_action(
                    official_url=official_url,
                    status="ok",
                    event_count=len(events),
                    needs_adapter=False,
                )
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
                        official_url=official_url,
                        parser_strategy=getattr(adapter, "parser_strategy", None),
                        needs_adapter=False,
                        action_label=action_label,
                        action_href=action_href,
                        consequence=consequence,
                        disabled_reason=disabled_reason,
                    )
                )
            except Exception as exc:  # pragma: no cover - live network audit path
                official_url = registry_entry.official_url if registry_entry else getattr(adapter, "official_url", None)
                action_label, action_href, consequence, disabled_reason = _source_action(
                    official_url=official_url,
                    status="error",
                    event_count=0,
                    needs_adapter=bool(getattr(adapter, "needs_adapter", False)),
                )
                results.append(
                    SourceAuditResult(
                        source_name=adapter.name,
                        source_type="external_opportunity",
                        status="error",
                        error=f"{type(exc).__name__}: {str(exc)[:300]}",
                        official_url=official_url,
                        parser_strategy=getattr(adapter, "parser_strategy", None),
                        needs_adapter=bool(getattr(adapter, "needs_adapter", False)),
                        action_label=action_label,
                        action_href=action_href,
                        consequence=consequence,
                        disabled_reason=disabled_reason,
                    )
                )

        adapter = get_host_calendar_adapter()
        registry_entry = source_registry_by_name().get(adapter.name)
        try:
            host_events = adapter.fetch_occupied()
            official_url = registry_entry.official_url if registry_entry else adapter.index_url
            action_label, action_href, consequence, disabled_reason = _source_action(
                official_url=official_url,
                status="ok",
                event_count=len(host_events),
                needs_adapter=False,
            )
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
                    official_url=official_url,
                    parser_strategy=registry_entry.parser_strategy if registry_entry else "eth_calendar_json_feed",
                    action_label=action_label,
                    action_href=action_href,
                    consequence=consequence,
                    disabled_reason=disabled_reason,
                )
            )
        except Exception as exc:  # pragma: no cover - live network audit path
            official_url = registry_entry.official_url if registry_entry else adapter.index_url
            action_label, action_href, consequence, disabled_reason = _source_action(
                official_url=official_url,
                status="error",
                event_count=0,
                needs_adapter=False,
            )
            results.append(
                SourceAuditResult(
                    source_name=adapter.name,
                    source_type="host_calendar",
                    status="error",
                    error=f"{type(exc).__name__}: {str(exc)[:300]}",
                    official_url=official_url,
                    parser_strategy=registry_entry.parser_strategy if registry_entry else "eth_calendar_json_feed",
                    action_label=action_label,
                    action_href=action_href,
                    consequence=consequence,
                    disabled_reason=disabled_reason,
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
        seen = {summary.source_name for summary in summaries}
        for entry in source_registry_by_name().values():
            if entry.name in seen:
                continue
            action_label, action_href, consequence, disabled_reason = _source_action(
                official_url=entry.official_url,
                status="not_checked",
                event_count=0,
                needs_adapter=entry.needs_adapter,
            )
            summaries.append(
                SourceReliabilityResult(
                    source_name=entry.name,
                    source_type=entry.source_type,
                    latest_status="not_checked",
                    latest_event_count=0,
                    last_event_count=0,
                    previous_event_count=None,
                    checks_recorded=0,
                    success_rate=0.0,
                    average_event_count=0.0,
                    trend="not_checked",
                    needs_attention=False,
                    attention_reason="No source audit has been recorded yet.",
                    latest_checked_at=None,
                    last_success_at=None,
                    latest_error=None,
                    official_url=entry.official_url,
                    parser_strategy=entry.parser_strategy,
                    needs_adapter=entry.needs_adapter,
                    action_label=action_label,
                    action_href=action_href,
                    consequence=consequence,
                    disabled_reason=disabled_reason,
                )
            )
        return sorted(summaries, key=lambda item: (not item.needs_attention, item.source_name))

    def _summarize_group(self, records: list[SourceHealthCheck]) -> SourceReliabilityResult:
        latest = records[0]
        previous = records[1] if len(records) > 1 else None
        ok_count = sum(1 for record in records if record.status == "ok")
        average_event_count = sum(record.event_count for record in records) / len(records)
        trend, needs_attention, attention_reason = self._trend(latest, previous)
        registry_entry = source_registry_by_name().get(latest.source_name)
        last_success = next((record.checked_at for record in records if record.status == "ok" and record.event_count > 0), None)
        latest_error = latest.error if latest.status != "ok" else None
        official_url = registry_entry.official_url if registry_entry else None
        needs_adapter = registry_entry.needs_adapter if registry_entry else latest.status == "needs_adapter"
        action_label, action_href, consequence, disabled_reason = _source_action(
            official_url=official_url,
            status=latest.status,
            event_count=latest.event_count,
            needs_adapter=needs_adapter,
        )
        return SourceReliabilityResult(
            source_name=latest.source_name,
            source_type=latest.source_type,
            latest_status=latest.status,
            latest_event_count=latest.event_count,
            last_event_count=latest.event_count,
            previous_event_count=previous.event_count if previous else None,
            checks_recorded=len(records),
            success_rate=round(ok_count / len(records), 3),
            average_event_count=round(average_event_count, 2),
            trend=trend,
            needs_attention=needs_attention,
            attention_reason=attention_reason,
            latest_checked_at=latest.checked_at,
            last_success_at=last_success,
            latest_error=latest_error,
            official_url=official_url,
            parser_strategy=registry_entry.parser_strategy if registry_entry else None,
            needs_adapter=needs_adapter,
            action_label=action_label,
            action_href=action_href,
            consequence=consequence,
            disabled_reason=disabled_reason,
        )

    def _trend(self, latest: SourceHealthCheck, previous: SourceHealthCheck | None) -> tuple[str, bool, str | None]:
        registry_entry = source_registry_by_name().get(latest.source_name)
        if latest.status == "needs_adapter" or (registry_entry and registry_entry.needs_adapter):
            return "needs_adapter", False, latest.error or "Official source is registered, but extraction needs a source-specific adapter."
        if latest.status != "ok":
            return "failing", True, latest.error or "Latest audit failed."
        if latest.event_count == 0:
            return "empty", True, "Latest audit found no extractable events."
        if previous is None:
            return "new", False, None
        if latest.event_count < previous.event_count:
            if latest.source_type == "host_calendar":
                return "changed", False, None
            return "degrading", True, f"Event count fell from {previous.event_count} to {latest.event_count}."
        if latest.event_count > previous.event_count:
            return "improving", False, None
        return "stable", False, None
