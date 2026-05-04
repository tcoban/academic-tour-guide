from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.entities import Tenant, WishlistEntry
from app.services.tenancy import DEFAULT_TENANT_SLUG


def _register(client: TestClient, email: str, institution_name: str, city: str = "Zurich") -> tuple[str, dict]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "name": email.split("@")[0].replace(".", " ").title(),
            "password": "safe-password-123",
            "institution_name": institution_name,
            "city": city,
            "country": "Switzerland",
        },
    )
    assert response.status_code == 200, response.text
    return response.cookies["roadshow_session"], response.json()


def test_default_kof_tenant_is_seeded(db_session: Session) -> None:
    tenant = db_session.query(Tenant).filter(Tenant.slug == DEFAULT_TENANT_SLUG).one()

    assert tenant.name == "KOF Swiss Economic Institute"
    assert tenant.host_institution is not None
    assert tenant.host_institution.city == "Zurich"
    assert tenant.anonymous_matching_opt_in is True


def test_registration_login_and_me(client: TestClient) -> None:
    token, auth_payload = _register(client, "owner@example.edu", "Example Economics Institute")

    assert auth_payload["active_tenant"]["name"] == "Example Economics Institute"
    me_response = client.get("/api/me", headers={"x-roadshow-session": token})

    assert me_response.status_code == 200
    payload = me_response.json()
    assert payload["authenticated"] is True
    assert payload["email"] == "owner@example.edu"
    assert payload["memberships"][0]["role"] == "owner"


def test_wishlist_entries_are_tenant_isolated(client: TestClient) -> None:
    token_a, auth_a = _register(client, "owner.a@example.edu", "Tenant A Institute")
    token_b, auth_b = _register(client, "owner.b@example.edu", "Tenant B Institute")

    response_a = client.post(
        "/api/wishlist",
        headers={"x-roadshow-session": token_a},
        json={
            "institution_id": auth_a["active_tenant"]["host_institution_id"],
            "speaker_name": "Daron Acemoglu",
            "priority": 95,
            "status": "active",
        },
    )
    response_b = client.post(
        "/api/wishlist",
        headers={"x-roadshow-session": token_b},
        json={
            "institution_id": auth_b["active_tenant"]["host_institution_id"],
            "speaker_name": "Rahul Deb",
            "priority": 90,
            "status": "active",
        },
    )

    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text
    list_a = client.get("/api/wishlist", headers={"x-roadshow-session": token_a}).json()
    list_b = client.get("/api/wishlist", headers={"x-roadshow-session": token_b}).json()

    assert [entry["speaker_name"] for entry in list_a] == ["Daron Acemoglu"]
    assert [entry["speaker_name"] for entry in list_b] == ["Rahul Deb"]


def test_anonymous_matching_requires_opt_in(client: TestClient, db_session: Session) -> None:
    token_a, auth_a = _register(client, "match.a@example.edu", "Match A Institute")
    token_b, auth_b = _register(client, "match.b@example.edu", "Match B Institute")

    for token in (token_a, token_b):
        response = client.patch(
            "/api/tenants/current",
            headers={"x-roadshow-session": token},
            json={"anonymous_matching_opt_in": True},
        )
        assert response.status_code == 200, response.text

    for token, auth_payload in ((token_a, auth_a), (token_b, auth_b)):
        response = client.post(
            "/api/wishlist",
            headers={"x-roadshow-session": token},
            json={
                "institution_id": auth_payload["active_tenant"]["host_institution_id"],
                "speaker_name": "Mirko Wiederholt",
                "priority": 80,
                "status": "active",
            },
        )
        assert response.status_code == 200, response.text

    match_response = client.post("/api/wishlist-matches/refresh", headers={"x-roadshow-session": token_a})
    assert match_response.status_code == 200, match_response.text
    groups = match_response.json()
    assert len(groups) == 1
    assert groups[0]["participant_count"] == 2
    assert all("institution_id" not in participant for participant in groups[0]["participants"])

    client.patch(
        "/api/tenants/current",
        headers={"x-roadshow-session": token_b},
        json={"anonymous_matching_opt_in": False},
    )
    client.post("/api/wishlist-matches/refresh", headers={"x-roadshow-session": token_a})
    visible_to_b = client.get("/api/wishlist-matches", headers={"x-roadshow-session": token_b}).json()

    assert visible_to_b == []
    assert db_session.query(WishlistEntry).count() == 2
