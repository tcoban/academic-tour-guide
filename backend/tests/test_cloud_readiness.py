from __future__ import annotations

from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import _auth_response
from app.core.config import settings
from app.main import app
from app.services.tenancy import register_user


def test_production_validation_requires_database_cors_and_api_gate(monkeypatch) -> None:
    monkeypatch.setenv("ROADSHOW_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ROADSHOW_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("ROADSHOW_API_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("ROADSHOW_CLOUD_IAP_ENABLED", "false")
    monkeypatch.setenv("ROADSHOW_SESSION_COOKIE_SECURE", "false")

    errors = settings.production_validation_errors()

    assert any("DATABASE_URL" in error for error in errors)
    assert any("ROADSHOW_CORS_ORIGINS" in error for error in errors)
    assert any("ROADSHOW_API_ACCESS_TOKEN" in error for error in errors)
    assert any("ROADSHOW_SESSION_COOKIE_SECURE" in error for error in errors)


def test_production_validation_accepts_postgres_token_and_secure_cookie(monkeypatch) -> None:
    monkeypatch.setenv("ROADSHOW_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://roadshow:secret@127.0.0.1:5432/roadshow")
    monkeypatch.setenv("ROADSHOW_CORS_ORIGINS", "https://roadshow-frontend.example")
    monkeypatch.setenv("ROADSHOW_API_ACCESS_TOKEN", "edge-token")
    monkeypatch.setenv("ROADSHOW_CLOUD_IAP_ENABLED", "false")
    monkeypatch.setenv("ROADSHOW_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("ROADSHOW_ENABLE_DEMO_TOOLS", "false")

    assert settings.production_validation_errors() == []


def test_production_validation_accepts_cloud_iap_without_api_token(monkeypatch) -> None:
    monkeypatch.setenv("ROADSHOW_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://roadshow:secret@127.0.0.1:5432/roadshow")
    monkeypatch.setenv("ROADSHOW_CORS_ORIGINS", "https://roadshow-frontend.example")
    monkeypatch.delenv("ROADSHOW_API_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ATG_API_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("ROADSHOW_CLOUD_IAP_ENABLED", "true")
    monkeypatch.setenv("ROADSHOW_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("ROADSHOW_ENABLE_DEMO_TOOLS", "false")

    assert settings.production_validation_errors() == []


def test_production_auth_cookie_is_secure(monkeypatch, db_session: Session) -> None:
    monkeypatch.setenv("ROADSHOW_ENV", "production")
    auth_session = register_user(
        db_session,
        email="cloud-cookie@example.edu",
        name="Cloud Cookie",
        password="safe-password-123",
        institution_name="Cloud Readiness Institute",
        city="Zurich",
        country="Switzerland",
    )

    response = Response()
    _auth_response(response, auth_session)

    assert "secure" in response.headers["set-cookie"].lower()


def test_production_protected_api_requires_session_when_using_iap(monkeypatch) -> None:
    monkeypatch.setenv("ROADSHOW_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://roadshow:secret@127.0.0.1:5432/roadshow")
    monkeypatch.setenv("ROADSHOW_CORS_ORIGINS", "https://roadshow-frontend.example")
    monkeypatch.delenv("ROADSHOW_API_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ATG_API_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("ROADSHOW_CLOUD_IAP_ENABLED", "true")
    monkeypatch.setenv("ROADSHOW_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("ROADSHOW_ENABLE_DEMO_TOOLS", "false")

    with TestClient(app) as client:
        response = client.get("/api/operator/cockpit")

    assert response.status_code == 401
    assert response.json()["detail"] == "Roadshow login required."
