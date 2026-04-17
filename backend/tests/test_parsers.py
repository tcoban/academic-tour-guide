from __future__ import annotations

from pathlib import Path

from app.scraping.base import RawPage
from app.scraping.sources import (
    BOCCONI_SOURCE,
    BIS_SOURCE,
    BONN_SOURCE,
    ECB_SOURCE,
    MANNHEIM_SOURCE,
    GenericEventSource,
    KofHostCalendarAdapter,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_bocconi_parser_extracts_event() -> None:
    adapter = GenericEventSource(BOCCONI_SOURCE)
    events = adapter.extract(RawPage(url="https://www.unibocconi.eu/events", html=fixture_text("bocconi.html")))
    assert len(events) == 1
    assert events[0].speaker_name == "Prof. Alice Demo"
    assert events[0].city == "Milan"


def test_mannheim_parser_extracts_event() -> None:
    adapter = GenericEventSource(MANNHEIM_SOURCE)
    events = adapter.extract(RawPage(url="https://www.uni-mannheim.de/en/events/", html=fixture_text("mannheim.html")))
    assert len(events) == 1
    assert events[0].speaker_affiliation == "MIT"
    assert events[0].starts_at.isoformat().startswith("2026-05-08T12:30:00")


def test_bonn_parser_extracts_event() -> None:
    adapter = GenericEventSource(BONN_SOURCE)
    events = adapter.extract(RawPage(url="https://www.econ.uni-bonn.de/events", html=fixture_text("bonn.html")))
    assert len(events) == 1
    assert events[0].speaker_name == "Prof. Bruno Test"
    assert events[0].country == "Germany"


def test_ecb_parser_extracts_event() -> None:
    adapter = GenericEventSource(ECB_SOURCE)
    events = adapter.extract(
        RawPage(url="https://www.ecb.europa.eu/press/conferences/html/index.en.html", html=fixture_text("ecb.html"))
    )
    assert len(events) == 1
    assert events[0].speaker_name == "Prof. Carla Example"
    assert events[0].city == "Frankfurt"


def test_bis_parser_extracts_event() -> None:
    adapter = GenericEventSource(BIS_SOURCE)
    events = adapter.extract(RawPage(url="https://www.bis.org/events/index.htm", html=fixture_text("bis.html")))
    assert len(events) == 1
    assert events[0].speaker_name == "Prof. Dario Sample"
    assert events[0].city == "Basel"


def test_kof_index_discovers_detail_urls() -> None:
    adapter = KofHostCalendarAdapter()
    urls = adapter.discover_detail_urls(
        RawPage(url="https://kof.ethz.ch/en/news-und-veranstaltungen/event-calendar-page.html", html=fixture_text("kof_index.html"))
    )
    assert len(urls) == 2
    assert all("veranstaltungsarchiv" not in url for url in urls)


def test_kof_detail_extracts_host_event() -> None:
    adapter = KofHostCalendarAdapter()
    event = adapter.extract_detail(
        RawPage(
            url="https://kof.ethz.ch/en/news-und-veranstaltungen/event-calendar-page.kof-international-economic-policy-seminar.html",
            html=fixture_text("kof_detail.html"),
        )
    )
    assert event is not None
    assert event.title == "KOF International Economic Policy Seminar"
    assert event.location == "ETH Zurich, LEE G 116"

