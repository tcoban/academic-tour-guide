from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets
import unicodedata

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    AuditEvent,
    BusinessCaseRun,
    FeedbackSignal,
    HostCalendarEvent,
    Institution,
    OpenSeminarWindow,
    OutreachDraft,
    RelationshipBrief,
    ResearcherFact,
    SeminarSlotOverride,
    SeminarSlotTemplate,
    Tenant,
    TenantMembership,
    TenantOpportunity,
    TenantSettings,
    TenantSourceSubscription,
    TourAssemblyProposal,
    TourLeg,
    TravelPriceCheck,
    User,
    UserSession,
    WishlistAlert,
    WishlistEntry,
    WishlistMatchParticipant,
)


DEFAULT_TENANT_NAME = "KOF Swiss Economic Institute"
DEFAULT_TENANT_SLUG = "kof"
SESSION_COOKIE_NAME = "roadshow_session"
SESSION_DAYS = 14
DEFAULT_RESEARCH_FOCUSES = [
    "business cycles",
    "macroeconomics",
    "labor markets",
    "innovation",
    "public economics",
    "international economics",
    "forecasting",
]
DEFAULT_SOURCE_SUBSCRIPTIONS = [
    "KOF",
    "Bocconi",
    "Mannheim",
    "Bonn",
    "BIS",
    "ECB",
    "LSE",
    "Oxford",
    "PSE",
    "LMU Munich",
    "EUI",
]


@dataclass(slots=True)
class AuthSession:
    token: str
    user: User
    tenant: Tenant
    expires_at: datetime


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in normalized)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)[:100] or "tenant"


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 240_000)
    return f"pbkdf2_sha256$240000${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt, expected = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations_raw),
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_default_tenant(session: Session) -> Tenant:
    institution = session.scalar(select(Institution).where(Institution.name == DEFAULT_TENANT_NAME))
    if not institution:
        institution = Institution(
            name=DEFAULT_TENANT_NAME,
            city="Zurich",
            country="Switzerland",
            latitude=47.3769,
            longitude=8.5417,
            metadata_json={"tenant": DEFAULT_TENANT_SLUG, "roadshow_role": "anchor_host"},
        )
        session.add(institution)
        session.flush()

    tenant = session.scalar(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    if not tenant:
        tenant = Tenant(
            name=DEFAULT_TENANT_NAME,
            slug=DEFAULT_TENANT_SLUG,
            status="active",
            host_institution_id=institution.id,
            city=institution.city,
            country=institution.country,
            latitude=institution.latitude,
            longitude=institution.longitude,
            timezone="Europe/Zurich",
            currency="CHF",
            anonymous_matching_opt_in=True,
            branding_json={"short_name": "KOF", "seminar_team": "KOF seminar team"},
        )
        session.add(tenant)
        session.flush()
    else:
        tenant.host_institution_id = tenant.host_institution_id or institution.id
        tenant.city = tenant.city or institution.city
        tenant.country = tenant.country or institution.country
        tenant.latitude = tenant.latitude if tenant.latitude is not None else institution.latitude
        tenant.longitude = tenant.longitude if tenant.longitude is not None else institution.longitude

    ensure_tenant_settings(session, tenant)
    ensure_source_subscriptions(session, tenant)
    backfill_default_tenant_scope(session, tenant)
    return tenant


def backfill_default_tenant_scope(session: Session, tenant: Tenant) -> None:
    tenant_scoped_models = [
        AuditEvent,
        BusinessCaseRun,
        FeedbackSignal,
        HostCalendarEvent,
        OpenSeminarWindow,
        OutreachDraft,
        RelationshipBrief,
        ResearcherFact,
        SeminarSlotOverride,
        SeminarSlotTemplate,
        TourAssemblyProposal,
        TourLeg,
        TravelPriceCheck,
        WishlistAlert,
        WishlistEntry,
        WishlistMatchParticipant,
    ]
    for model in tenant_scoped_models:
        session.execute(update(model).where(model.tenant_id.is_(None)).values(tenant_id=tenant.id))
    session.flush()


def ensure_tenant_settings(session: Session, tenant: Tenant) -> TenantSettings:
    settings = session.scalar(select(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
    if settings:
        return settings
    settings = TenantSettings(
        tenant_id=tenant.id,
        research_focuses=list(DEFAULT_RESEARCH_FOCUSES),
        hospitality_policy_json={
            "hotel_chf": 220,
            "dinner_chf": 90,
            "local_transport_chf": 30,
            "description": "Host city hospitality estimate for the seminar day.",
        },
        rail_policy_json={"travel_class": "first", "fare_policy": "full_fare"},
        outreach_defaults_json={
            "host_display_name": "KOF Swiss Economic Institute",
            "seminar_team": "KOF seminar team",
            "city": "Zurich",
        },
        source_subscriptions_json=list(DEFAULT_SOURCE_SUBSCRIPTIONS),
    )
    session.add(settings)
    session.flush()
    return settings


def ensure_source_subscriptions(session: Session, tenant: Tenant) -> None:
    existing = {
        subscription.source_name
        for subscription in session.scalars(
            select(TenantSourceSubscription).where(TenantSourceSubscription.tenant_id == tenant.id)
        ).all()
    }
    for source_name in DEFAULT_SOURCE_SUBSCRIPTIONS:
        if source_name in existing:
            continue
        session.add(TenantSourceSubscription(tenant_id=tenant.id, source_name=source_name, status="active"))
    session.flush()


def get_session_tenant(session: Session) -> Tenant:
    tenant_id = session.info.get("tenant_id")
    if tenant_id:
        tenant = session.get(Tenant, tenant_id)
        if tenant:
            return tenant
    tenant = ensure_default_tenant(session)
    session.info["tenant_id"] = tenant.id
    return tenant


def set_session_tenant(session: Session, tenant: Tenant) -> Tenant:
    session.info["tenant_id"] = tenant.id
    return tenant


def tenant_filter(model, session: Session):
    tenant = get_session_tenant(session)
    return tenant_scope(model, tenant)


def tenant_scope(model, tenant: Tenant):
    tenant_column = getattr(model, "tenant_id")
    if tenant.slug == DEFAULT_TENANT_SLUG:
        return or_(tenant_column == tenant.id, tenant_column.is_(None))
    return tenant_column == tenant.id


def register_user(
    session: Session,
    *,
    email: str,
    name: str,
    password: str,
    institution_name: str,
    city: str | None = None,
    country: str | None = None,
) -> AuthSession:
    email_normalized = email.strip().lower()
    if session.scalar(select(User).where(User.email == email_normalized)):
        raise ValueError("A Roadshow account already exists for this email.")

    institution = session.scalar(select(Institution).where(Institution.name == institution_name.strip()))
    if not institution:
        institution = Institution(
            name=institution_name.strip(),
            city=city,
            country=country,
            metadata_json={"created_from": "self_service_registration"},
        )
        session.add(institution)
        session.flush()

    tenant_slug = unique_tenant_slug(session, slugify(institution.name))
    tenant = Tenant(
        name=institution.name,
        slug=tenant_slug,
        status="active",
        host_institution_id=institution.id,
        city=city or institution.city,
        country=country or institution.country,
        latitude=institution.latitude,
        longitude=institution.longitude,
        timezone="Europe/Zurich",
        currency="CHF",
        anonymous_matching_opt_in=False,
        branding_json={"short_name": institution.name, "seminar_team": "seminar team"},
    )
    session.add(tenant)
    session.flush()
    ensure_tenant_settings(session, tenant)

    user = User(email=email_normalized, name=name.strip(), password_hash=password_hash(password))
    session.add(user)
    session.flush()
    session.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner", status="active"))
    session.flush()
    return create_auth_session(session, user, tenant)


def unique_tenant_slug(session: Session, base_slug: str) -> str:
    candidate = base_slug
    counter = 2
    while session.scalar(select(Tenant).where(Tenant.slug == candidate)):
        candidate = f"{base_slug}-{counter}"
        counter += 1
    return candidate


def authenticate_user(session: Session, email: str, password: str) -> AuthSession:
    user = session.scalar(
        select(User)
        .where(User.email == email.strip().lower(), User.status == "active")
        .options(selectinload(User.memberships).selectinload(TenantMembership.tenant))
    )
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password.")
    membership = next((item for item in user.memberships if item.status == "active" and item.tenant.status == "active"), None)
    if not membership:
        raise ValueError("This user does not have an active tenant membership.")
    return create_auth_session(session, user, membership.tenant)


def create_auth_session(session: Session, user: User, tenant: Tenant) -> AuthSession:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    user_session = UserSession(
        user_id=user.id,
        active_tenant_id=tenant.id,
        token_hash=hash_session_token(token),
        expires_at=expires_at,
    )
    session.add(user_session)
    session.flush()
    session.info["user_id"] = user.id
    session.info["tenant_id"] = tenant.id
    return AuthSession(token=token, user=user, tenant=tenant, expires_at=expires_at)


def resolve_auth_session(session: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    token_hash = hash_session_token(token)
    user_session = session.scalar(
        select(UserSession)
        .where(UserSession.token_hash == token_hash, UserSession.expires_at > datetime.now(UTC))
        .options(
            selectinload(UserSession.user).selectinload(User.memberships).selectinload(TenantMembership.tenant),
            selectinload(UserSession.active_tenant),
        )
    )
    if not user_session or user_session.user.status != "active" or user_session.active_tenant.status != "active":
        return None
    user_session.last_seen_at = datetime.now(UTC)
    session.info["user_id"] = user_session.user_id
    session.info["tenant_id"] = user_session.active_tenant_id
    return user_session


def revoke_auth_session(session: Session, token: str | None) -> bool:
    if not token:
        return False
    token_hash = hash_session_token(token)
    user_session = session.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if not user_session:
        return False
    session.delete(user_session)
    session.flush()
    return True


def switch_active_tenant(session: Session, user_session: UserSession, tenant_id: str) -> UserSession:
    membership = next(
        (
            item
            for item in user_session.user.memberships
            if item.tenant_id == tenant_id and item.status == "active" and item.tenant.status == "active"
        ),
        None,
    )
    if not membership:
        raise ValueError("The active user is not a member of that tenant.")
    user_session.active_tenant_id = tenant_id
    user_session.last_seen_at = datetime.now(UTC)
    session.info["tenant_id"] = tenant_id
    session.add(user_session)
    session.flush()
    return user_session
