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


def test_bocconi_current_parser_cleans_speaker_and_title() -> None:
    adapter = GenericEventSource(BOCCONI_SOURCE)
    events = adapter.extract(
        RawPage(
            url="https://economics.unibocconi.eu/events-research",
            html="""
            <article class="node--event">
              <h3 class="node__title"><a href="/event/demo">Nikita Melnikov - Gang Crackdowns</a></h3>
              <div class="event__speaker--speaker">Nikita Melnikov, <span class="c-speaker__university">Nova School of Business and Economics</span></div>
              <time datetime="2026-06-03T10:15:00Z">03 June 2026 12:15pm</time>
            </article>
            """,
        )
    )
    assert len(events) == 1
    assert events[0].speaker_name == "Nikita Melnikov"
    assert events[0].speaker_affiliation == "Nova School of Business and Economics"
    assert events[0].title == "Gang Crackdowns"
    assert events[0].starts_at.isoformat().startswith("2026-06-03T10:15:00")


def test_mannheim_parser_extracts_event() -> None:
    adapter = GenericEventSource(MANNHEIM_SOURCE)
    events = adapter.extract(RawPage(url="https://www.uni-mannheim.de/en/events/", html=fixture_text("mannheim.html")))
    assert len(events) == 1
    assert events[0].speaker_affiliation == "MIT"
    assert events[0].starts_at.isoformat().startswith("2026-05-08T12:30:00")


def test_mannheim_current_table_parser_extracts_rows() -> None:
    adapter = GenericEventSource(MANNHEIM_SOURCE)
    events = adapter.extract(
        RawPage(
            url="https://www.vwl.uni-mannheim.de/forschung/forschungsseminare/mannheim-applied-seminar/",
            html="""
            <table>
              <tr><th>Date/ Time</th><th>Location</th><th>Name</th><th>Title</th></tr>
              <tr>
                <td>29.04.2026</td><td>ZEW, Room Medienraum</td>
                <td>Marco Caliendo, Universitaet Potsdam</td>
                <td>Compensating Wage Differentials and the Health Cost of Job Strain</td>
              </tr>
            </table>
            """,
        )
    )
    assert len(events) == 1
    assert events[0].speaker_name == "Marco Caliendo"
    assert events[0].speaker_affiliation == "Universitaet Potsdam"
    assert events[0].starts_at.isoformat().startswith("2026-04-29T00:00:00")


def test_bonn_parser_extracts_event() -> None:
    adapter = GenericEventSource(BONN_SOURCE)
    events = adapter.extract(RawPage(url="https://www.econ.uni-bonn.de/events", html=fixture_text("bonn.html")))
    assert len(events) == 1
    assert events[0].speaker_name == "Prof. Bruno Test"
    assert events[0].country == "Germany"


def test_bonn_current_text_fallback_extracts_events() -> None:
    adapter = GenericEventSource(BONN_SOURCE)
    events = adapter.extract(
        RawPage(
            url="https://www.econ.uni-bonn.de/micro/en/seminars",
            html="""
            <main>
              <p>Summer Term 2026</p>
              <p>22.04.2026 Ariel Rubinstein - Tel Aviv University, New York University</p>
              <p>"Magical Implementation"</p>
              <p>29.04.2026 Bruno Strulovici - Northwestern University</p>
              <p>"Public Insurance Design and Coverage Gaps under Electoral Competition"</p>
            </main>
            """,
        )
    )
    assert len(events) == 2
    assert events[0].speaker_name == "Ariel Rubinstein"
    assert events[0].title == "Magical Implementation"
    assert events[1].starts_at.isoformat().startswith("2026-04-29T00:00:00")


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
