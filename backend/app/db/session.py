from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


engine = create_engine(settings.database_url, future=True, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    from app.models.entities import (  # noqa: F401
        AuditEvent,
        FactCandidate,
        FeedbackSignal,
        HostCalendarEvent,
        Institution,
        InstitutionProfile,
        OpenSeminarWindow,
        OutreachDraft,
        RelationshipBrief,
        Researcher,
        ResearcherFact,
        ResearcherIdentity,
        SeminarSlotOverride,
        SeminarSlotTemplate,
        SpeakerProfile,
        SourceHealthCheck,
        SourceDocument,
        TalkEvent,
        TourLeg,
        TourStop,
        TripCluster,
        WishlistAlert,
        WishlistEntry,
    )

    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
