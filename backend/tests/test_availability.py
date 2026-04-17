from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.entities import HostCalendarEvent, SeminarSlotOverride, SeminarSlotTemplate
from app.services.availability import AvailabilityBuilder


def test_host_event_blocks_template_slot(db_session: Session) -> None:
    db_session.add(
        SeminarSlotTemplate(
            label="Tuesday Seminar",
            weekday=1,
            start_time=time(16, 15),
            end_time=time(17, 30),
            timezone="Europe/Zurich",
            active=True,
        )
    )
    db_session.add(
        HostCalendarEvent(
            title="Booked KOF Event",
            location="ETH Zurich",
            starts_at=datetime(2026, 5, 5, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
            ends_at=datetime(2026, 5, 5, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
            url="https://kof.ethz.ch/example",
            source_hash="host-event-1",
            metadata_json={"source": "kof"},
        )
    )
    db_session.commit()

    windows = AvailabilityBuilder(db_session).build(start_date=date(2026, 5, 4), end_date=date(2026, 5, 6))
    assert windows == []


def test_open_override_reopens_blocked_window(db_session: Session) -> None:
    db_session.add(
        SeminarSlotTemplate(
            label="Tuesday Seminar",
            weekday=1,
            start_time=time(16, 15),
            end_time=time(17, 30),
            timezone="Europe/Zurich",
            active=True,
        )
    )
    db_session.add(
        HostCalendarEvent(
            title="Booked KOF Event",
            location="ETH Zurich",
            starts_at=datetime(2026, 5, 5, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
            ends_at=datetime(2026, 5, 5, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
            url="https://kof.ethz.ch/example",
            source_hash="host-event-2",
            metadata_json={"source": "kof"},
        )
    )
    db_session.add(
        SeminarSlotOverride(
            start_at=datetime(2026, 5, 5, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
            end_at=datetime(2026, 5, 5, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
            status="open",
            reason="Admin reopened this slot",
        )
    )
    db_session.commit()

    windows = AvailabilityBuilder(db_session).build(start_date=date(2026, 5, 4), end_date=date(2026, 5, 6))
    assert len(windows) == 1
    assert windows[0].source == "override"

