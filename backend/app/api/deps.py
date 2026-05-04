from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.models.entities import Tenant, User, UserSession
from app.services.tenancy import SESSION_COOKIE_NAME, ensure_default_tenant, get_session_tenant, resolve_auth_session


def session_dep(request: Request) -> Generator[Session, None, None]:
    for session in get_session():
        auth_session: UserSession | None = None
        token = request.headers.get("x-roadshow-session") or request.cookies.get(SESSION_COOKIE_NAME)
        auth_session = resolve_auth_session(session, token)
        tenant_header = request.headers.get("x-roadshow-tenant-id")
        if auth_session and tenant_header:
            matching = [
                membership
                for membership in auth_session.user.memberships
                if membership.tenant_id == tenant_header and membership.status == "active"
            ]
            if matching:
                session.info["tenant_id"] = tenant_header
        if not auth_session:
            is_protected_api = request.url.path.startswith(settings.api_prefix) and not settings.is_public_api_path(
                request.url.path
            )
            if settings.is_production and is_protected_api:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Roadshow login required.")
            tenant = ensure_default_tenant(session)
            session.info.setdefault("tenant_id", tenant.id)
        yield session


def current_tenant_dep(session: Session = Depends(session_dep)) -> Tenant:
    return get_session_tenant(session)


def current_user_dep(session: Session = Depends(session_dep)) -> User:
    user_id = session.info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Roadshow login required.")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Roadshow login required.")
    return user
