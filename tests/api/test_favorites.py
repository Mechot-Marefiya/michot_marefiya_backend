# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01


def test_get_favorites_unauthenticated(api_client):
    response = api_client.get("/api/v1/favorites/")

    assert response.status_code == 401


def test_get_favorites_list_success(auth_client, favorite):
    response = auth_client.get("/api/v1/favorites/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(favorite.id)


def test_post_favorite_create_success(auth_client, hotel):
    response = auth_client.post(
        "/api/v1/favorites/",
        {"content_type": "account.hotelprofile", "object_id": str(hotel.id)},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["object_id"] == str(hotel.id)
    assert "content_type_display" in data
    assert "object" in data


def test_post_favorite_toggle_creates_and_removes(auth_client, hotel):
    create_response = auth_client.post(
        "/api/v1/favorites/toggle/",
        {"content_type": "account.hotelprofile", "object_id": str(hotel.id)},
        format="json",
    )
    assert create_response.status_code == 201

    remove_response = auth_client.post(
        "/api/v1/favorites/toggle/",
        {"content_type": "account.hotelprofile", "object_id": str(hotel.id)},
        format="json",
    )

    assert remove_response.status_code == 200
    assert remove_response.json()["detail"] == "removed"


def test_post_favorite_toggle_invalid_payload(auth_client):
    response = auth_client.post("/api/v1/favorites/toggle/", {}, format="json")

    assert response.status_code == 400
