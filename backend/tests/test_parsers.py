from __future__ import annotations

from pathlib import Path

from app.scraping.base import RawPage
from app.scraping.sources import (
    BOCCONI_SOURCE,
    BIS_SOURCE,
    BONN_SOURCE,
    ECB_SOURCE,
    MANNHEIM_SOURCE,
    BisPdfConferenceSource,
    GenericEventSource,
    KofHostCalendarAdapter,
    source_registry_by_name,
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


def test_mannheim_parser_repairs_joint_labels_split_affiliations_and_cancelled_names() -> None:
    adapter = GenericEventSource(MANNHEIM_SOURCE)
    events = adapter.extract(
        RawPage(
            url="https://www.vwl.uni-mannheim.de/forschung/forschungsseminare/mannheim-applied-seminar/",
            html="""
            <table>
              <tr><th>Date/ Time</th><th>Location</th><th>Name</th><th>Title</th></tr>
              <tr>
                <td>29.04.2026</td><td>ZEW, Room Medienraum</td>
                <td>Joint AEE/ ZEW Seminar Christian Moser (Columbia Business School, NY)</td>
                <td>Entrepreneurship and Aggregate Productivity</td>
              </tr>
              <tr>
                <td>06.05.2026</td><td>University of Mannheim</td>
                <td>cancelled - Fabrizio Zilibotti, Yale University</td>
                <td>CANCELLED</td>
              </tr>
              <tr>
                <td>13.05.2026</td><td>University of Mannheim</td>
                <td>Anna Aizer Brown University)</td>
                <td>Family Spillovers</td>
              </tr>
            </table>
            """,
        )
    )

    assert [event.speaker_name for event in events] == ["Christian Moser", "Fabrizio Zilibotti", "Anna Aizer"]
    assert events[0].speaker_affiliation == "Columbia Business School, NY"
    assert events[1].speaker_affiliation == "Yale University"
    assert events[2].speaker_affiliation == "Brown University"
    assert all("(" not in event.speaker_name and ")" not in event.speaker_name for event in events)
    assert all("cancel" not in event.speaker_name.lower() for event in events)


def test_parser_splits_multiple_speakers_without_treating_affiliation_commas_as_people() -> None:
    adapter = GenericEventSource(MANNHEIM_SOURCE)
    events = adapter.extract(
        RawPage(
            url="https://www.vwl.uni-mannheim.de/forschung/forschungsseminare/mannheim-applied-seminar/",
            html="""
            <table>
              <tr><th>Date/ Time</th><th>Location</th><th>Name</th><th>Title</th></tr>
              <tr>
                <td>29.04.2026</td><td>University of Mannheim</td>
                <td>Melina Cosentino, Philipp Hamelmann</td>
                <td>Eliciting information from multiple experts via grouping</td>
              </tr>
              <tr>
                <td>06.05.2026</td><td>University of Mannheim</td>
                <td>Wenjun Zheng and Stylianos Fragkiskos Skavdis</td>
                <td>Robust Optimal Insurance under Moral Hazard</td>
              </tr>
              <tr>
                <td>13.05.2026</td><td>University of Mannheim</td>
                <td>Marco Caliendo, Universitaet Potsdam</td>
                <td>Compensating Wage Differentials</td>
              </tr>
              <tr>
                <td>20.05.2026</td><td>University of Mannheim</td>
                <td>Laura Alfaro, Harvard</td>
                <td>Global Supply Chains</td>
              </tr>
              <tr>
                <td>27.05.2026</td><td>University of Mannheim</td>
                <td>Uwe Sunde, LMU, Munich</td>
                <td>Labor Markets and Demographics</td>
              </tr>
            </table>
            """,
        )
    )

    assert [event.speaker_name for event in events] == [
        "Melina Cosentino",
        "Philipp Hamelmann",
        "Wenjun Zheng",
        "Stylianos Fragkiskos Skavdis",
        "Marco Caliendo",
        "Laura Alfaro",
        "Uwe Sunde",
    ]
    assert events[-3].speaker_affiliation == "Universitaet Potsdam"
    assert events[-2].speaker_affiliation == "Harvard"
    assert events[-1].speaker_affiliation == "LMU, Munich"


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


def test_expanded_watchlist_sources_are_registered() -> None:
    registry = source_registry_by_name()
    for name in ["lse", "pse", "oxford", "tse", "lmu_munich", "goethe_frankfurt", "uzh", "eth", "snb", "bank_of_england", "bse_barcelona", "carlos_iii_madrid", "eui"]:
        assert name in registry
        assert registry[name].official_url.startswith("https://")
        assert registry[name].needs_adapter is True


def test_bis_parser_extracts_event() -> None:
    adapter = GenericEventSource(BIS_SOURCE)
    events = adapter.extract(RawPage(url="https://www.bis.org/events/index.htm", html=fixture_text("bis.html")))
    assert len(events) == 1
    assert events[0].speaker_name == "Prof. Dario Sample"
    assert events[0].city == "Basel"


def test_bis_pdf_conference_source_extracts_keynote_speakers() -> None:
    adapter = BisPdfConferenceSource()
    events = adapter.extract(
        RawPage(
            url="https://www.bis.org/events/260526_cfp_heterogeneity_inflation.pdf",
            html="""
            Conference Dates: 26-27 May 2026 | Host: BIS, Basel.
            Academic keynote speakers:
            - Klaus Adam (University of Mannheim, UCL, & CEPR)
            - Xavier Jaravel (LSE & CEPR)
            Focus areas:
            Inflation heterogeneity.
            """,
        )
    )
    assert len(events) == 2
    assert events[0].speaker_name == "Klaus Adam"
    assert events[0].speaker_affiliation == "University of Mannheim, UCL, & CEPR"
    assert events[0].starts_at.isoformat().startswith("2026-05-26T09:00:00")
    assert events[1].speaker_name == "Xavier Jaravel"


def test_kof_index_discovers_detail_urls() -> None:
    adapter = KofHostCalendarAdapter()
    urls = adapter.discover_detail_urls(
        RawPage(url="https://kof.ethz.ch/en/news-und-veranstaltungen/event-calendar-page.html", html=fixture_text("kof_index.html"))
    )
    assert len(urls) == 2
    assert all("veranstaltungsarchiv" not in url for url in urls)


def test_kof_index_discovers_eth_calendar_api_url() -> None:
    adapter = KofHostCalendarAdapter()
    api_url = adapter.discover_api_url(
        RawPage(
            url="https://kof.ethz.ch/en/news-und-veranstaltungen/event-calendar-page.html",
            html="""
            <div
              data-init="eventCalendar"
              data-events-url="https://idapps.ethz.ch/pcm-pub-services/v2/entries?filters%5B0%5D.org-units=02544wd&amp;lang=en">
            </div>
            """,
        )
    )
    assert api_url == "https://idapps.ethz.ch/pcm-pub-services/v2/entries?filters%5B0%5D.org-units=02544wd&lang=en"


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


def test_kof_api_payload_extracts_host_events() -> None:
    adapter = KofHostCalendarAdapter()
    events = adapter.extract_api_events(
        {
            "entry-array": [
                {
                    "id": 76655,
                    "content": {"title": "KOF Research Seminar- Alena WABITSCH: Incentivizing Inflation Expectations"},
                    "classification": {
                        "entry-type-desc": "Seminar",
                        "series-name": "KOF Research Seminars",
                    },
                    "location": {
                        "internal": {
                            "area-desc": "Zurich Zentrum",
                            "building": "LEE",
                            "floor": "F",
                            "room": "118",
                        }
                    },
                    "date-time-indication": {
                        "in-progress-timerange-array": [
                            {
                                "date-time-from": "2026-04-29 16:15",
                                "date-time-to": "2026-04-29 17:30",
                            }
                        ]
                    },
                    "function-owner-array": [
                        {
                            "function-desc": "Speaker",
                            "first-name": "Alena",
                            "last-name": "Wabitsch ",
                            "person-url": "https://www.alenawabitsch.eu/",
                        }
                    ],
                }
            ]
        },
        api_url="https://idapps.ethz.ch/pcm-pub-services/v2/entries",
        index_url="https://kof.ethz.ch/en/news-and-events/event-calendar-page.html",
    )
    assert len(events) == 1
    assert events[0].starts_at.isoformat().startswith("2026-04-29T16:15:00")
    assert events[0].ends_at is not None
    assert events[0].location == "LEE, F, 118, Zurich Zentrum"
    assert events[0].metadata_json["series_name"] == "KOF Research Seminars"
    assert events[0].metadata_json["speakers"][0]["last_name"] == "Wabitsch"
