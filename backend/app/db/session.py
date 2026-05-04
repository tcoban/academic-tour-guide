from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
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
        BusinessCaseResult,
        BusinessCaseRun,
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
        Tenant,
        TenantMembership,
        TenantOpportunity,
        TenantSettings,
        TenantSourceSubscription,
        TourAssemblyProposal,
        TourLeg,
        TourStop,
        TravelPriceCheck,
        TripCluster,
        User,
        UserSession,
        WishlistAlert,
        WishlistEntry,
        WishlistMatchGroup,
        WishlistMatchParticipant,
    )

    Base.metadata.create_all(bind=engine)
    _ensure_runtime_columns()


def _ensure_runtime_columns() -> None:
    """Small SQLite-safe bootstrap migration until Alembic becomes mandatory.

    Production Postgres migrations can be generated from the same models; this
    keeps existing local pilot databases usable during the SaaS refactor.
    """
    inspector = inspect(engine)
    table_columns = {
        "audit_events": "tenant_id",
        "business_case_runs": "tenant_id",
        "feedback_signals": "tenant_id",
        "host_calendar_events": "tenant_id",
        "open_seminar_windows": "tenant_id",
        "outreach_drafts": "tenant_id",
        "relationship_briefs": "tenant_id",
        "researcher_facts": "tenant_id",
        "seminar_slot_overrides": "tenant_id",
        "seminar_slot_templates": "tenant_id",
        "tour_assembly_proposals": "tenant_id",
        "tour_legs": "tenant_id",
        "travel_price_checks": "tenant_id",
        "wishlist_alerts": "tenant_id",
        "wishlist_entries": "tenant_id",
        "wishlist_match_participants": "tenant_id",
    }
    with engine.begin() as connection:
        for table_name, column_name in table_columns.items():
            if table_name not in inspector.get_table_names():
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            if column_name in existing:
                continue
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} VARCHAR(36)"))


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
