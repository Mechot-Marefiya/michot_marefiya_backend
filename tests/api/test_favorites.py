# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01

from apps.favorites.models import Favorite, GuestFavorite
from django.contrib.contenttypes.models import ContentType
from tests.conftest import HotelProfileFactory


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
    assert "snapshot" in data["results"][0]
    assert "object" in data["results"][0]


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
    assert "snapshot" in data
    assert data["snapshot"]["id"] == str(hotel.id)
    assert data["snapshot"]["type"] == "account.hotelprofile"


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


def test_post_guest_favorite_create_success(api_client, hotel):
    response = api_client.post(
        "/api/v1/favorites/guest/",
        {
            "guest_phone": "+251911223344",
            "content_type": "account.hotelprofile",
            "object_id": str(hotel.id),
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["guest_phone"] == "0911223344"
    assert data["object_id"] == str(hotel.id)
    assert data["snapshot"]["id"] == str(hotel.id)
    assert GuestFavorite.objects.filter(guest_phone="0911223344", object_id=str(hotel.id)).exists()


def test_get_guest_favorites_list_success(api_client, hotel):
    ct = ContentType.objects.get_for_model(hotel.__class__)
    GuestFavorite.objects.create(
        guest_phone="0911223344",
        content_type=ct,
        object_id=str(hotel.id),
        snapshot={"id": str(hotel.id), "type": "account.hotelprofile"},
    )

    response = api_client.get("/api/v1/favorites/guest/", {"guest_phone": "0911223344"})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["guest_phone"] == "0911223344"
    assert data["results"][0]["snapshot"]["id"] == str(hotel.id)


def test_post_guest_favorite_toggle_creates_and_removes(api_client, hotel):
    create_response = api_client.post(
        "/api/v1/favorites/guest/toggle/",
        {
            "guest_phone": "0911223344",
            "content_type": "account.hotelprofile",
            "object_id": str(hotel.id),
        },
        format="json",
    )
    assert create_response.status_code == 201

    remove_response = api_client.post(
        "/api/v1/favorites/guest/toggle/",
        {
            "guest_phone": "0911223344",
            "content_type": "account.hotelprofile",
            "object_id": str(hotel.id),
        },
        format="json",
    )

    assert remove_response.status_code == 200
    assert remove_response.json()["detail"] == "removed"


def test_get_favorite_detail_success(auth_client, favorite):
    response = auth_client.get(f"/api/v1/favorites/{favorite.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(favorite.id)
    assert data["object_id"] == str(favorite.object_id)
    assert "snapshot" in data
    assert data["snapshot"] == data["object"]


def test_get_favorite_detail_unauthenticated(api_client, favorite):
    response = api_client.get(f"/api/v1/favorites/{favorite.id}/")

    assert response.status_code == 401


def test_get_favorite_detail_not_found(auth_client):
    response = auth_client.get("/api/v1/favorites/11111111-1111-1111-1111-111111111111/")

    assert response.status_code == 404


def test_patch_favorite_updates_snapshot(auth_client, favorite, hotel):
    other_hotel = HotelProfileFactory(company=hotel.company)

    response = auth_client.patch(
        f"/api/v1/favorites/{favorite.id}/",
        {"content_type": "account.hotelprofile", "object_id": str(other_hotel.id)},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["object_id"] == str(other_hotel.id)
    assert data["snapshot"]["id"] == str(other_hotel.id)
    assert data["snapshot"]["type"] == "account.hotelprofile"
    favorite.refresh_from_db()
    assert favorite.snapshot["id"] == str(other_hotel.id)


def test_patch_favorite_invalid_payload(auth_client, favorite):
    response = auth_client.patch(
        f"/api/v1/favorites/{favorite.id}/",
        {"content_type": "invalid-model", "object_id": str(favorite.object_id)},
        format="json",
    )

    assert response.status_code == 400
    assert "content_type" in response.json()


def test_patch_favorite_other_users_object_not_found(auth_client, company_user, hotel):
    ct = ContentType.objects.get_for_model(hotel.__class__)
    other_favorite = Favorite.objects.create(
        user=company_user,
        content_type=ct,
        object_id=str(hotel.id),
    )
    response = auth_client.patch(
        f"/api/v1/favorites/{other_favorite.id}/",
        {"content_type": "account.hotelprofile", "object_id": str(hotel.id)},
        format="json",
    )

    assert response.status_code == 404


def test_delete_favorite_success(auth_client, favorite):
    response = auth_client.delete(f"/api/v1/favorites/{favorite.id}/")

    assert response.status_code == 204
    assert not Favorite.objects.filter(id=favorite.id).exists()


def test_delete_favorite_unauthenticated(api_client, favorite):
    response = api_client.delete(f"/api/v1/favorites/{favorite.id}/")

    assert response.status_code == 401
