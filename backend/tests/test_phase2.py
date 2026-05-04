from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import FactCandidate, OpenSeminarWindow, Researcher, ResearcherFact, ResearcherIdentity, SourceDocument, TalkEvent, TripCluster
from app.services.enrichment import Biographer, BiographerPipeline, normalize_name
from app.services.identity_sources import CeprClient, CeprProfile, OrcidMatch, OrcidRecord, RepecGenealogyClient, RepecGenealogyEntry
from app.services.plausibility import PlausibilityService
from app.services.repec import RepecClient, RepecMatch
from app.services.review import FactReviewService
from app.services.scoring import Scorer


class StubRepecClient:
    def search_author(self, _: str) -> RepecMatch:
        return RepecMatch(
            external_id="par7",
            canonical_name="Alice Example",
            profile_url="https://ideas.repec.org/e/par7.html",
            match_confidence=0.97,
            ranking_percentile=4.2,
            ranking_label="Top 5%",
            metadata_json={"source": "stub"},
        )


class StubTopRepecClient(StubRepecClient):
    def top_authors(self, limit: int = 200) -> list[RepecMatch]:
        return [
            RepecMatch(
                external_id="pac16",
                canonical_name="Daron Acemoglu",
                profile_url="https://ideas.repec.org/e/pac16.html",
                match_confidence=1.0,
                ranking_percentile=0.01,
                ranking_label="RePEc worldwide rank #2",
                metadata_json={"source": "repec_top_authors", "rank": 2},
            ),
            RepecMatch(
                external_id="pha66",
                canonical_name="Eric Hanushek (Eric Hanusek)",
                profile_url="https://ideas.repec.org/f/pha66.html",
                match_confidence=1.0,
                ranking_percentile=0.02,
                ranking_label="RePEc worldwide rank #80",
                metadata_json={"source": "repec_top_authors", "rank": 80},
            ),
        ][:limit]


class StubNoRepecClient:
    def search_author(self, _: str) -> RepecMatch | None:
        return None

    def top_authors(self, limit: int = 200) -> list[RepecMatch]:
        return []


class StubOrcidClient:
    def search_person(self, name: str, affiliation: str | None = None) -> OrcidMatch | None:
        return OrcidMatch(
            external_id="0000-0002-1825-0097",
            canonical_name=name.replace("Prof. ", ""),
            profile_url="https://orcid.org/0000-0002-1825-0097",
            match_confidence=0.94,
            metadata_json={"source": "test_orcid", "affiliation": affiliation},
        )

    def fetch_record(self, external_id: str) -> OrcidRecord:
        return OrcidRecord(
            external_id=external_id,
            profile_url=f"https://orcid.org/{external_id}",
            canonical_name="Mirko Wiederholt",
            extracted_text=(
                "Mirko Wiederholt\n"
                "Education: PhD Economics, European University Institute, 2003\n"
                "Employment: Professor, Sciences Po"
            ),
            linked_urls=[
                "https://profiles.example.edu/mirko-wiederholt-cv.html",
                "https://scholar.google.com/citations?user=mirko",
                "https://www.linkedin.com/in/mirko-wiederholt/",
            ],
            education_facts=[
                {
                    "organization": "European University Institute",
                    "role_title": "PhD Economics",
                    "end_date": "2003",
                    "source": "education",
                }
            ],
            employment_facts=[
                {
                    "organization": "Sciences Po",
                    "role_title": "Professor",
                    "start_date": "2024",
                    "source": "employment",
                }
            ],
            metadata_json={"source": "orcid_record"},
        )


class StubGenealogyClient:
    def fetch_by_repec_id(self, external_id: str) -> RepecGenealogyEntry | None:
        return None

    def search_by_name(self, name: str) -> RepecGenealogyEntry:
        return RepecGenealogyEntry(
            external_id="pwi93",
            canonical_name=name.replace("Prof. ", ""),
            profile_url="https://genealogy.repec.org/pages/pwi93.html",
            terminal_degree_institution="Department of Economics, European University Institute, Firenze, Italy",
            graduation_year=2003,
            advisors=[],
            extracted_text=(
                "RePEc Genealogy page for Mirko Wiederholt\n"
                "Mirko Wiederholt got the terminal degree from Department of Economics, "
                "European University Institute, Firenze, Italy in 2003."
            ),
            linked_urls=["https://ideas.repec.org/e/pwi93.html"],
        )


class StubCeprClient:
    def fetch_profile(self, name: str) -> CeprProfile:
        return CeprProfile(
            external_id="mirko-wiederholt",
            canonical_name=name.replace("Prof. ", ""),
            profile_url="https://cepr.org/about/people/mirko-wiederholt",
            title="Mirko Wiederholt | CEPR",
            extracted_text=(
                "Mirko Wiederholt is Professor of Economics at Ludwig-Maximilians University of Munich. "
                "ORCID 0000-0002-9794-3288. He obtained his PhD in Economics from the European University Institute."
            ),
            linked_urls=[
                "https://sites.google.com/view/mirkowiederholt/startseite",
                "https://scholar.google.com/citations?user=mirko",
            ],
            orcid_id="0000-0002-9794-3288",
            home_institution="Ludwig-Maximilians University of Munich",
            phd_institution="European University Institute",
            metadata_json={
                "source": "cepr_profile",
                "role_line": "Professor of Economics at Ludwig-Maximilians University of Munich",
                "linked_urls": [
                    "https://sites.google.com/view/mirkowiederholt/startseite",
                    "https://scholar.google.com/citations?user=mirko",
                ],
            },
        )


def test_repec_identity_sync_prevents_duplicate_researchers_for_name_variants(db_session: Session) -> None:
    biographer = Biographer(db_session)
    primary = biographer.get_or_create_researcher("Prof. Alice Example", home_institution="MIT")
    pipeline = BiographerPipeline(
        db_session,
        repec_client=StubRepecClient(),
        document_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))),
    )

    summary = pipeline.sync_repec(primary.id)
    matched = biographer.get_or_create_researcher("Alice Example", home_institution="MIT", repec_external_id="par7")

    assert summary.created_count == 1
    assert matched.id == primary.id
    assert db_session.query(Researcher).count() == 1


def test_repec_top_authors_parser_handles_e_and_f_profile_paths() -> None:
    html = """
    <html><body>
      <p>There are 73,242 registered authors evaluated for all years.</p>
      <table>
        <tr><td>1</td><td><a name="psh93"></a><a href="https://ideas.repec.org/e/psh93.html">Andrei Shleifer</a></td><td>9.95</td></tr>
        <tr><td>2</td><td><a name="pac16"></a><a href="https://ideas.repec.org/e/pac16.html">Daron Acemoglu</a></td><td>9.96</td></tr>
        <tr><td>6</td><td><a name="pba251"></a><a href="https://ideas.repec.org/f/pba251.html">Robert J. Barro</a></td><td>9.99</td></tr>
      </table>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://ideas.repec.org/top/top.person.all.html"
        return httpx.Response(200, text=html)

    client = RepecClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    authors = client.top_authors(limit=200)

    assert [author.canonical_name for author in authors] == ["Andrei Shleifer", "Daron Acemoglu", "Robert J. Barro"]
    assert authors[1].external_id == "pac16"
    assert authors[2].external_id == "pba251"
    assert authors[1].metadata_json["rank"] == 2


def test_repec_top_authors_sync_creates_missing_star_researchers(db_session: Session) -> None:
    pipeline = BiographerPipeline(
        db_session,
        repec_client=StubTopRepecClient(),
        document_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))),
    )

    summary = pipeline.sync_top_authors(limit=200)
    db_session.commit()

    daron = db_session.scalar(select(Researcher).where(Researcher.normalized_name == normalize_name("Daron Acemoglu")))
    eric = db_session.scalar(select(Researcher).where(Researcher.normalized_name == normalize_name("Eric Hanushek")))
    identity = db_session.scalar(select(ResearcherIdentity).where(ResearcherIdentity.external_id == "pac16"))
    assert summary.created_count == 2
    assert daron is not None
    assert eric is not None
    assert eric.name == "Eric Hanushek"
    assert identity is not None
    assert identity.researcher_id == daron.id


def test_repec_genealogy_parser_extracts_terminal_degree() -> None:
    html = """
    <html><body>
      <h1>RePEc Genealogy page for Mirko Wiederholt</h1>
      <h2>Graduate studies</h2>
      <p>Mirko Wiederholt got the terminal degree from
      <a href="https://edirc.repec.org/data/deuieit.html">Department of Economics, European University Institute, Firenze, Italy</a>
      in 2003.</p>
      <h2>Advisor</h2><ol><li>No advisor listed, help complete this page.</li></ol>
      <h2>Students</h2>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://genealogy.repec.org/pages/pwi93.html"
        return httpx.Response(200, text=html)

    client = RepecGenealogyClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    entry = client.fetch_by_repec_id("pwi93")

    assert entry is not None
    assert entry.canonical_name == "Mirko Wiederholt"
    assert entry.terminal_degree_institution == "Department of Economics, European University Institute, Firenze, Italy"
    assert entry.graduation_year == 2003


def test_cepr_profile_parser_extracts_role_phd_and_orcid() -> None:
    html = """
    <html>
      <head><title>Mirko Wiederholt | CEPR</title></head>
      <body>
        <h1>Mirko Wiederholt</h1>
        <h4>Professor of Economics at Ludwig-Maximilians University of Munich (LMU)</h4>
        <a href="https://sites.google.com/view/mirkowiederholt/startseite">Website</a>
        <div>ORCID 0000-0002-9794-3288</div>
        <p>He obtained his PhD in Economics from the European University Institute, was an assistant professor at Humboldt University Berlin.</p>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://cepr.org/about/people/mirko-wiederholt"
        return httpx.Response(200, text=html)

    client = CeprClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    profile = client.fetch_profile("Mirko Wiederholt")

    assert profile is not None
    assert profile.canonical_name == "Mirko Wiederholt"
    assert profile.home_institution == "Ludwig-Maximilians University of Munich"
    assert profile.phd_institution == "European University Institute"
    assert profile.orcid_id == "0000-0002-9794-3288"
    assert profile.profile_url == "https://cepr.org/about/people/mirko-wiederholt"


def test_trusted_evidence_search_cross_checks_orcid_genealogy_cepr_and_cv_links(db_session: Session) -> None:
    researcher = Researcher(
        name="Mirko Wiederholt",
        normalized_name=normalize_name("Mirko Wiederholt"),
        home_institution="Sciences Po",
    )
    db_session.add(researcher)
    db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://profiles.example.edu/mirko-wiederholt-cv.html":
            return httpx.Response(
                200,
                text="""
                <html><head><title>Mirko Wiederholt CV</title></head><body>
                Mirko Wiederholt. Nationality: German. PhD from European University Institute.
                </body></html>
                """,
                headers={"content-type": "text/html"},
            )
        if str(request.url) == "https://sites.google.com/view/mirkowiederholt/startseite":
            return httpx.Response(
                200,
                text="<html><head><title>Mirko Wiederholt Homepage</title></head><body>Mirko Wiederholt homepage.</body></html>",
                headers={"content-type": "text/html"},
            )
        raise AssertionError(f"Unexpected document fetch: {request.url}")

    pipeline = BiographerPipeline(
        db_session,
        repec_client=StubNoRepecClient(),
        document_client=httpx.Client(transport=httpx.MockTransport(handler)),
        orcid_client=StubOrcidClient(),
        genealogy_client=StubGenealogyClient(),
        cepr_client=StubCeprClient(),
    )

    summary = pipeline.search_trusted_evidence(researcher.id)
    db_session.commit()

    identities = db_session.scalars(select(ResearcherIdentity).where(ResearcherIdentity.researcher_id == researcher.id)).all()
    candidates = db_session.scalars(select(FactCandidate).where(FactCandidate.researcher_id == researcher.id)).all()
    documents = db_session.scalars(select(SourceDocument).where(SourceDocument.researcher_id == researcher.id)).all()
    phd_candidates = [candidate for candidate in candidates if candidate.fact_type == "phd_institution"]
    manual_profile_docs = [document for document in documents if document.content_type == "external_profile"]

    assert summary.created_count >= 1
    assert summary.updated_count >= 5
    assert {identity.provider for identity in identities} == {"cepr", "orcid", "repec_genealogy"}
    assert {"cepr_profile", "orcid", "repec_genealogy", "extracted"}.issubset(
        {candidate.origin for candidate in phd_candidates}
    )
    assert any(candidate.confidence >= 0.9 and candidate.review_note for candidate in phd_candidates)
    assert any(candidate.fact_type == "nationality" and candidate.value == "German" for candidate in candidates)
    assert {document.title for document in manual_profile_docs} == {"Google Scholar profile link", "LinkedIn profile link"}
    assert any(document.url == "https://cepr.org/about/people/mirko-wiederholt" for document in documents)


def test_biographer_refresh_discovers_documents_and_extracts_candidates(db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Alice Example",
        normalized_name=normalize_name("Prof. Alice Example"),
        home_institution="Yale University",
    )
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="bocconi",
        title="Networks in Macro",
        speaker_name=researcher.name,
        speaker_affiliation="Yale University",
        city="Milan",
        country="Italy",
        starts_at=datetime(2026, 5, 3, 16, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://dept.example/seminars/alice",
        source_hash="phase2-talk-1",
        raw_payload={},
    )
    db_session.add_all([researcher, talk_event])
    db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://dept.example/seminars/alice":
            html = """
            <html><head><title>Seminar</title></head><body>
            <a href="/people/alice-cv.html">Alice Example curriculum vitae</a>
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        if str(request.url) == "https://ideas.repec.org/e/par7.html":
            html = """
            <html><head><title>IDEAS profile</title></head><body>
            Alice Example
            Terminal Degree: University of Mannheim
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        if str(request.url) == "https://dept.example/people/alice-cv.html":
            html = """
            <html><head><title>Alice CV</title></head><body>
            Alice Example
            Nationality: German
            Born: May 12, 1980
            Assistant Professor at Yale University
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        raise AssertionError(f"Unexpected URL fetched during test: {request.url}")

    pipeline = BiographerPipeline(
        db_session,
        repec_client=StubRepecClient(),
        document_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    summary = pipeline.refresh(researcher.id)

    candidates = db_session.scalars(select(FactCandidate).where(FactCandidate.researcher_id == researcher.id)).all()
    candidate_types = {candidate.fact_type for candidate in candidates}

    assert summary.processed_count == 1
    assert db_session.query(SourceDocument).count() >= 2
    assert {"phd_institution", "nationality", "birth_month", "home_institution"}.issubset(candidate_types)


def test_biographer_refresh_does_not_follow_unrelated_department_links(db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Alice Example",
        normalized_name=normalize_name("Prof. Alice Example"),
        home_institution="Yale University",
    )
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="bocconi",
        title="Networks in Macro",
        speaker_name=researcher.name,
        speaker_affiliation="Yale University",
        city="Milan",
        country="Italy",
        starts_at=datetime(2026, 5, 3, 16, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://dept.example/seminars/upcoming",
        source_hash="phase2-talk-broad",
        raw_payload={},
    )
    db_session.add_all([researcher, talk_event])
    db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://dept.example/seminars/upcoming":
            html = """
            <html><head><title>Department seminars</title></head><body>
            <h1>Upcoming seminars</h1>
            <p>Alice Example will present this week.</p>
            <a href="/faculty/bob-wrong">Bob Wrong profile</a>
            <a href="/sites/default/files/media/cv/Bob_Wrong_CV.pdf">Curriculum vitae</a>
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        if str(request.url) == "https://ideas.repec.org/e/par7.html":
            return httpx.Response(404)
        raise AssertionError(f"Unrelated link should not be fetched: {request.url}")

    pipeline = BiographerPipeline(
        db_session,
        repec_client=StubRepecClient(),
        document_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    summary = pipeline.refresh(researcher.id)

    candidates = db_session.scalars(select(FactCandidate).where(FactCandidate.researcher_id == researcher.id)).all()
    documents = db_session.scalars(select(SourceDocument).where(SourceDocument.researcher_id == researcher.id)).all()
    assert summary.processed_count == 1
    assert len(documents) == 2
    assert {candidate.origin for candidate in candidates} == {"event_affiliation"}


def test_plausibility_check_quarantines_off_target_evidence_and_restores_home_institution(db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Alice Example",
        normalized_name=normalize_name("Prof. Alice Example"),
        home_institution="economics at Bocconi, where he holds the Rodolfo Debenedetti chair in labor studies.",
    )
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="bocconi",
        title="Networks in Macro",
        speaker_name=researcher.name,
        speaker_affiliation="Yale University",
        city="Milan",
        country="Italy",
        starts_at=datetime(2026, 5, 3, 16, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://dept.example/seminars/alice-example",
        source_hash="phase2-talk-plausibility",
        raw_payload={},
    )
    event_candidate = FactCandidate(
        researcher=researcher,
        fact_type="home_institution",
        value="Yale University",
        confidence=0.7,
        evidence_snippet="Speaker affiliation observed on a linked seminar source page.",
        source_url=talk_event.url,
        status="approved",
        origin="event_affiliation",
    )
    off_target_document = SourceDocument(
        researcher=researcher,
        url="https://dept.example/faculty/bob-wrong",
        content_type="text/html",
        checksum="bob",
        fetch_status="fetched",
        title="Bob Wrong profile",
        extracted_text="Bob Wrong is Professor of Economics at Bocconi University. He received a PhD from Harvard.",
        metadata_json={"linked_urls": []},
    )
    bad_candidate = FactCandidate(
        researcher=researcher,
        source_document=off_target_document,
        fact_type="home_institution",
        value="Economics at Bocconi University",
        confidence=0.58,
        evidence_snippet="Bob Wrong is Professor of Economics at Bocconi University.",
        source_url=off_target_document.url,
        status="approved",
        origin="extracted",
    )
    bad_fact = ResearcherFact(
        researcher=researcher,
        source_document=off_target_document,
        approved_via_candidate=bad_candidate,
        fact_type="home_institution",
        value="Economics at Bocconi University",
        confidence=0.58,
        source_url=off_target_document.url,
        evidence_snippet="Bob Wrong is Professor of Economics at Bocconi University.",
        verified=True,
        approval_origin="review_queue",
    )
    db_session.add_all([researcher, talk_event, event_candidate, off_target_document, bad_candidate, bad_fact])
    db_session.commit()

    summary = PlausibilityService(db_session).run()
    db_session.commit()

    db_session.refresh(researcher)
    remaining_facts = db_session.scalars(select(ResearcherFact).where(ResearcherFact.researcher_id == researcher.id)).all()
    assert summary.updated_count >= 3
    assert bad_candidate.status == "rejected"
    assert off_target_document.metadata_json["plausibility_status"] == "quarantined"
    assert researcher.home_institution == "Yale University"
    assert all(fact.value != "Economics at Bocconi University" for fact in remaining_facts)


def test_plausibility_check_repairs_malformed_speaker_profiles(db_session: Session) -> None:
    researcher = Researcher(
        name="Joint AEE/ ZEW Seminar Christian Moser (Columbia Business School",
        normalized_name=normalize_name("Joint AEE/ ZEW Seminar Christian Moser Columbia Business School"),
        home_institution="NY)",
    )
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="mannheim",
        title="Entrepreneurship and Aggregate Productivity",
        speaker_name=researcher.name,
        speaker_affiliation="NY)",
        city="Mannheim",
        country="Germany",
        starts_at=datetime(2026, 5, 6, 12, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://www.vwl.uni-mannheim.de/forschung/forschungsseminare/mannheim-applied-seminar/",
        source_hash="bad-mannheim-speaker",
        raw_payload={},
    )
    db_session.add_all([researcher, talk_event])
    db_session.commit()

    summary = PlausibilityService(db_session).run()
    db_session.commit()
    db_session.refresh(researcher)
    db_session.refresh(talk_event)

    assert summary.source_counts["speaker_names_repaired"] == 1
    assert researcher.name == "Christian Moser"
    assert researcher.home_institution == "Columbia Business School, NY"
    assert talk_event.speaker_name == "Christian Moser"
    assert talk_event.speaker_affiliation == "Columbia Business School, NY"


def test_plausibility_check_splits_merged_speaker_event_and_researcher(db_session: Session) -> None:
    researcher = Researcher(
        name="Melina Cosentino, Philipp Hamelmann",
        normalized_name=normalize_name("Melina Cosentino, Philipp Hamelmann"),
        home_institution="BGSE",
    )
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="bonn",
        title="Eliciting information from multiple experts via grouping",
        speaker_name=researcher.name,
        speaker_affiliation="BGSE",
        city="Bonn",
        country="Germany",
        starts_at=datetime(2026, 5, 6, 12, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://www.econ.uni-bonn.de/micro/en/seminars",
        source_hash="bad-merged-speakers",
        raw_payload={},
    )
    db_session.add_all([researcher, talk_event])
    db_session.commit()

    summary = PlausibilityService(db_session).run()
    db_session.commit()

    events = db_session.scalars(select(TalkEvent).order_by(TalkEvent.speaker_name)).all()
    researchers = db_session.scalars(select(Researcher).order_by(Researcher.name)).all()
    assert summary.source_counts["multi_speaker_events_split"] == 1
    assert [event.speaker_name for event in events] == ["Melina Cosentino", "Philipp Hamelmann"]
    assert [item.name for item in researchers] == ["Melina Cosentino", "Philipp Hamelmann"]
    assert all("," not in item.name for item in researchers)


def test_plausibility_check_removes_institution_speaker_artifacts(db_session: Session) -> None:
    researcher = Researcher(
        name="SMU Singapore",
        normalized_name=normalize_name("SMU Singapore"),
        home_institution=None,
    )
    talk_event = TalkEvent(
        researcher=researcher,
        source_name="mannheim",
        title="TBA",
        speaker_name="SMU Singapore",
        speaker_affiliation=None,
        city="Mannheim",
        country="Germany",
        starts_at=datetime(2026, 5, 27, 12, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://www.vwl.uni-mannheim.de/forschung/forschungsseminare/mannheim-applied-seminar/",
        source_hash="bad-institution-speaker",
        raw_payload={
            "speaker_quality_flags": ["multiple_speakers_split"],
            "original_speaker_name": "Christine Ho, SMU Singapore",
        },
    )
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 27).date(),
        end_date=datetime(2026, 5, 27).date(),
        itinerary=[],
    )
    db_session.add_all([researcher, talk_event, cluster])
    db_session.commit()

    summary = PlausibilityService(db_session).run()
    db_session.commit()

    assert summary.source_counts["institution_speaker_events_removed"] == 1
    assert summary.source_counts["institution_speaker_profiles_removed"] == 1
    assert db_session.scalars(select(TalkEvent)).all() == []
    assert db_session.scalars(select(TripCluster)).all() == []
    assert db_session.scalars(select(Researcher)).all() == []


def test_plausibility_check_merges_umlaut_transliteration_aliases(db_session: Session) -> None:
    umlaut = Researcher(name="Axel Börsch-Supan", normalized_name="axel borsch supan", home_institution="MEA")
    ascii_alias = Researcher(name="Axel Boersch-Supan", normalized_name="axel boersch supan", home_institution="MEA")
    talk_event = TalkEvent(
        researcher=ascii_alias,
        source_name="mannheim",
        title="Individual and Population Ageing",
        speaker_name="Axel Boersch-Supan",
        speaker_affiliation="MEA",
        city="Mannheim",
        country="Germany",
        starts_at=datetime(2026, 11, 13, 12, 0, tzinfo=ZoneInfo("Europe/Zurich")),
        ends_at=None,
        url="https://www.vwl.uni-mannheim.de/forschung/forschungsseminare/mannheim-applied-seminar/",
        source_hash="umlaut-alias-event",
        raw_payload={},
    )
    db_session.add_all([umlaut, ascii_alias, talk_event])
    db_session.commit()

    summary = PlausibilityService(db_session).run()
    db_session.commit()

    researchers = db_session.scalars(select(Researcher)).all()
    assert summary.source_counts["transliteration_profiles_merged"] == 1
    assert len(researchers) == 1
    assert researchers[0].normalized_name == "axel boersch supan"
    assert len(researchers[0].talk_events) == 1


def test_pending_evidence_contributes_to_score_but_blocks_outreach(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Carla Pending",
        normalized_name=normalize_name("Prof. Carla Pending"),
        home_institution="MIT",
    )
    researcher.fact_candidates = [
        FactCandidate(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.84,
            evidence_snippet="Terminal Degree: University of Mannheim",
            source_url="https://ideas.repec.org/e/par7.html",
            status="pending",
            origin="repec_profile",
        ),
        FactCandidate(
            fact_type="nationality",
            value="German",
            confidence=0.82,
            evidence_snippet="Nationality: German",
            source_url="https://cv.example/carla",
            status="pending",
            origin="cv_html",
        ),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 3).date(),
        end_date=datetime(2026, 5, 8).date(),
        itinerary=[
            {"city": "Milan", "starts_at": "2026-05-03T16:00:00+02:00", "title": "Bocconi", "url": "x", "source_name": "bocconi"},
            {"city": "Munich", "starts_at": "2026-05-08T12:30:00+02:00", "title": "Munich", "url": "y", "source_name": "mannheim"},
        ],
        rationale=[],
        opportunity_score=0,
    )
    db_session.add_all(
        [
            researcher,
            cluster,
            OpenSeminarWindow(
                starts_at=datetime(2026, 5, 6, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
                ends_at=datetime(2026, 5, 6, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
                source="template",
                metadata_json={"label": "Tuesday Seminar"},
            ),
        ]
    )
    db_session.commit()

    result = Scorer(db_session).score_cluster(cluster, researcher)
    db_session.commit()

    response = client.post("/api/outreach-drafts", json={"researcher_id": researcher.id, "trip_cluster_id": cluster.id})

    assert result.score == 100
    assert cluster.uses_unreviewed_evidence is True
    assert response.status_code == 409
    assert "requires approval" in response.json()["detail"]


def test_approved_candidates_enable_draft_generation(client, db_session: Session) -> None:
    researcher = Researcher(
        name="Prof. Dana Review",
        normalized_name=normalize_name("Prof. Dana Review"),
        home_institution="MIT",
    )
    researcher.fact_candidates = [
        FactCandidate(
            fact_type="phd_institution",
            value="University of Mannheim",
            confidence=0.84,
            evidence_snippet="Terminal Degree: University of Mannheim",
            source_url="https://ideas.repec.org/e/par7.html",
            status="pending",
            origin="repec_profile",
        ),
        FactCandidate(
            fact_type="nationality",
            value="German",
            confidence=0.82,
            evidence_snippet="Nationality: German",
            source_url="https://cv.example/dana",
            status="pending",
            origin="cv_html",
        ),
    ]
    cluster = TripCluster(
        researcher=researcher,
        start_date=datetime(2026, 5, 3).date(),
        end_date=datetime(2026, 5, 8).date(),
        itinerary=[
            {"city": "Milan", "starts_at": "2026-05-03T16:00:00+02:00", "title": "Bocconi", "url": "x", "source_name": "bocconi"},
            {"city": "Munich", "starts_at": "2026-05-08T12:30:00+02:00", "title": "Munich", "url": "y", "source_name": "mannheim"},
        ],
        rationale=[],
        opportunity_score=0,
    )
    db_session.add_all(
        [
            researcher,
            cluster,
            OpenSeminarWindow(
                starts_at=datetime(2026, 5, 6, 16, 15, tzinfo=ZoneInfo("Europe/Zurich")),
                ends_at=datetime(2026, 5, 6, 17, 30, tzinfo=ZoneInfo("Europe/Zurich")),
                source="template",
                metadata_json={"label": "Tuesday Seminar"},
            ),
        ]
    )
    db_session.commit()

    review_service = FactReviewService(db_session)
    for candidate in researcher.fact_candidates:
        review_service.approve(candidate)
    Scorer(db_session).score_cluster(cluster, researcher)
    db_session.commit()

    response = client.post("/api/outreach-drafts", json={"researcher_id": researcher.id, "trip_cluster_id": cluster.id})
    researcher_facts = db_session.scalars(select(ResearcherFact).where(ResearcherFact.researcher_id == researcher.id)).all()

    assert response.status_code == 200
    draft_payload = response.json()
    assert "Biographic hook" not in draft_payload["body"]
    assert draft_payload["metadata_json"]["template_key"] == "kof_invitation"
    assert any(item["label"] == "Biographic hook" for item in draft_payload["metadata_json"]["send_brief"])
    assert {fact.fact_type for fact in researcher_facts} == {"phd_institution", "nationality"}


def test_seed_demo_endpoint_creates_reviewable_pilot_data(client, monkeypatch) -> None:
    monkeypatch.setenv("ROADSHOW_ENABLE_DEMO_TOOLS", "true")
    response = client.post("/api/jobs/seed-demo")
    assert response.status_code == 200
    assert response.json()["processed_count"] == 2

    researchers_response = client.get("/api/researchers")
    review_response = client.get("/api/review/facts")
    catch_response = client.get("/api/dashboard/daily-catch")

    assert researchers_response.status_code == 200
    assert review_response.status_code == 200
    assert catch_response.status_code == 200
    assert len(researchers_response.json()) >= 2
    assert any(item["researcher_name"] == "Prof. Luca Pending" for item in review_response.json())
    assert catch_response.json()["top_clusters"]
