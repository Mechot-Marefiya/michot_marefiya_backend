# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

pytestmark = pytest.mark.django_db

def test_post_token_obtain_success(api_client, user):
    response = api_client.post(
        "/api/v1/auth/token/",
        {"email": user.email, "password": "pass1234"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["access"], str)
    assert isinstance(data["refresh"], str)
    assert data["role"] == user.role.code


def test_post_token_obtain_invalid_credentials(api_client):
    response = api_client.post(
        "/api/v1/auth/token/",
        {"email": "missing@example.com", "password": "wrong"},
        format="json",
    )

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_post_token_refresh_success(api_client, user):
    refresh = str(RefreshToken.for_user(user))
    response = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": refresh},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["access"], str)


def test_post_token_refresh_invalid_payload(api_client):
    response = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": "invalid"},
        format="json",
    )

    assert response.status_code in {400, 401}
    assert isinstance(response.json(), dict)


def test_post_logout_success(api_client, user):
    refresh = str(RefreshToken.for_user(user))
    response = api_client.post("/api/v1/auth/logout/", {"refresh": refresh}, format="json")

    assert response.status_code == 200
    assert response.content == b""


def test_post_logout_invalid_payload(api_client):
    response = api_client.post("/api/v1/auth/logout/", {}, format="json")

    assert response.status_code == 400


def test_get_me_unauthenticated(api_client):
    response = api_client.get("/api/v1/auth/me/")

    assert response.status_code == 401


def test_get_me_success(auth_client, user):
    response = auth_client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user.email
    assert "id" in data
    assert "role" in data
    assert "workspace" in data
