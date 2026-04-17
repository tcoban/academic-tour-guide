from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import HostCalendarEvent, OpenSeminarWindow, SeminarSlotOverride, SeminarSlotTemplate


@dataclass(slots=True)
class AvailabilityWindow:
    starts_at: datetime
    ends_at: datetime
    source: str
    metadata_json: dict
    derived_from_template_id: str | None = None


def overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=ZoneInfo(settings.default_timezone))


class AvailabilityBuilder:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build(self, start_date: date, end_date: date) -> list[AvailabilityWindow]:
        templates = self.session.scalars(
            select(SeminarSlotTemplate).where(SeminarSlotTemplate.active.is_(True))
        ).all()
        host_events = self.session.scalars(
            select(HostCalendarEvent).where(
                HostCalendarEvent.starts_at >= datetime.combine(start_date, datetime.min.time()),
                HostCalendarEvent.starts_at <= datetime.combine(end_date, datetime.max.time()),
            )
        ).all()
        overrides = self.session.scalars(
            select(SeminarSlotOverride).where(
                SeminarSlotOverride.start_at >= datetime.combine(start_date, datetime.min.time()),
                SeminarSlotOverride.start_at <= datetime.combine(end_date, datetime.max.time()),
            )
        ).all()

        blocked_ranges = [
            (
                ensure_timezone(event.starts_at),
                ensure_timezone(event.ends_at or event.starts_at + timedelta(hours=2)),
            )
            for event in host_events
        ]
        blocked_ranges.extend(
            (
                ensure_timezone(override.start_at),
                ensure_timezone(override.end_at),
            )
            for override in overrides
            if override.status.lower() == "blocked"
        )
        open_overrides = [override for override in overrides if override.status.lower() == "open"]

        windows: list[AvailabilityWindow] = []
        current = start_date
        while current <= end_date:
            for template in templates:
                if current.weekday() != template.weekday:
                    continue
                tz = ZoneInfo(template.timezone or settings.default_timezone)
                start_at = datetime.combine(current, template.start_time, tzinfo=tz)
                end_at = datetime.combine(current, template.end_time, tzinfo=tz)
                if any(overlaps(start_at, end_at, blocked_start, blocked_end) for blocked_start, blocked_end in blocked_ranges):
                    continue
                windows.append(
                    AvailabilityWindow(
                        starts_at=start_at,
                        ends_at=end_at,
                        source="template",
                        metadata_json={"label": template.label},
                        derived_from_template_id=template.id,
                    )
                )
            current += timedelta(days=1)

        for override in open_overrides:
            windows.append(
                    AvailabilityWindow(
                        starts_at=ensure_timezone(override.start_at),
                        ends_at=ensure_timezone(override.end_at),
                        source="override",
                        metadata_json={"reason": override.reason or "Manual opening"},
                        derived_from_template_id=None,
                )
            )

        unique: dict[tuple[str, str], AvailabilityWindow] = {}
        for window in windows:
            key = (window.starts_at.isoformat(), window.ends_at.isoformat())
            unique[key] = window
        return sorted(unique.values(), key=lambda item: item.starts_at)

    def rebuild_persisted(self, start_date: date | None = None, horizon_days: int | None = None) -> list[OpenSeminarWindow]:
        start_date = start_date or datetime.now(tz=ZoneInfo(settings.default_timezone)).date()
        horizon_days = horizon_days or settings.opportunity_horizon_days
        end_date = start_date + timedelta(days=horizon_days)
        windows = self.build(start_date=start_date, end_date=end_date)

        self.session.execute(
            delete(OpenSeminarWindow).where(
                OpenSeminarWindow.starts_at >= datetime.combine(start_date, datetime.min.time()),
                OpenSeminarWindow.starts_at <= datetime.combine(end_date, datetime.max.time()),
            )
        )
        persisted: list[OpenSeminarWindow] = []
        for window in windows:
            item = OpenSeminarWindow(
                starts_at=window.starts_at,
                ends_at=window.ends_at,
                source=window.source,
                metadata_json=window.metadata_json,
                derived_from_template_id=window.derived_from_template_id,
            )
            self.session.add(item)
            persisted.append(item)
        self.session.flush()
        return persisted
