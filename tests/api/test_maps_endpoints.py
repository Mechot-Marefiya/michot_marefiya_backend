from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.listing.models import CarListing, PropertyListing

pytestmark = pytest.mark.django_db


def _address_payload(street="Bole Road"):
    return {
        "street_line1": street,
        "country": "Ethiopia",
        "city": "Addis Ababa",
        "sub_city": "Bole",
        "state": "Addis Ababa",
        "postal_code": "1000",
    }


class _MockResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_get_maps_autocomplete_returns_suggestions(auth_client, settings, monkeypatch):
    monkeypatch.setattr(
        "apps.listing.maps_views.autocomplete_address",
        lambda input_text, session_token: [
            {
                "place_id": "place-123",
                "description": "Bole Road, Addis Ababa, Ethiopia",
                "main_text": "Bole Road",
                "secondary_text": "Addis Ababa, Ethiopia",
            }
        ],
    )

    response = auth_client.get(
        "/api/v1/maps/autocomplete/",
        {"input": "Bole", "session_token": "session-123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["place_id"] == "place-123"
    assert "description" in payload[0]
    assert settings.GOOGLE_MAPS_API_KEY not in response.content.decode()


def test_get_maps_autocomplete_requires_auth(api_client):
    response = api_client.get(
        "/api/v1/maps/autocomplete/",
        {"input": "Bole", "session_token": "session-123"},
    )

    assert response.status_code == 401


def test_get_maps_autocomplete_missing_input_returns_400(auth_client):
    response = auth_client.get("/api/v1/maps/autocomplete/", {"session_token": "session-123"})

    assert response.status_code == 400
    assert "input" in response.json()


def test_get_maps_autocomplete_returns_empty_list_on_failure(auth_client, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("upstream failed")

    monkeypatch.setattr("apps.listing.maps_views.autocomplete_address", _boom)

    response = auth_client.get(
        "/api/v1/maps/autocomplete/",
        {"input": "Bole", "session_token": "session-123"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_post_maps_place_detail_returns_payload_and_uses_cache(auth_client, settings, monkeypatch):
    cache.clear()
    calls = {"count": 0}

    def _fake_get(url, params=None, timeout=5):
        calls["count"] += 1
        return _MockResponse(
            {
                "status": "OK",
                "result": {
                    "place_id": "place-123",
                    "formatted_address": "Bole Road, Addis Ababa, Ethiopia",
                    "geometry": {"location": {"lat": 9.012345, "lng": 38.765432}},
                    "address_components": [
                        {"long_name": "Addis Ababa", "types": ["locality"]},
                        {"long_name": "Addis Ababa", "types": ["administrative_area_level_1"]},
                        {"long_name": "Ethiopia", "types": ["country"]},
                        {"long_name": "1000", "types": ["postal_code"]},
                    ],
                },
            }
        )

    monkeypatch.setattr("services.maps.requests.get", _fake_get)

    payload = {"place_id": "place-123", "session_token": "session-123"}
    first = auth_client.post("/api/v1/maps/place-detail/", payload, format="json")
    second = auth_client.post("/api/v1/maps/place-detail/", payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    data = first.json()
    assert data["place_id"] == "place-123"
    assert data["formatted_address"] == "Bole Road, Addis Ababa, Ethiopia"
    assert Decimal(data["lat"]) == Decimal("9.012345")
    assert Decimal(data["lng"]) == Decimal("38.765432")
    assert settings.GOOGLE_MAPS_API_KEY not in first.content.decode()


def test_post_maps_place_detail_requires_auth(api_client):
    response = api_client.post(
        "/api/v1/maps/place-detail/",
        {"place_id": "place-123", "session_token": "session-123"},
        format="json",
    )

    assert response.status_code == 401


def test_post_maps_place_detail_missing_place_id_returns_400(auth_client):
    response = auth_client.post(
        "/api/v1/maps/place-detail/",
        {"session_token": "session-123"},
        format="json",
    )

    assert response.status_code == 400
    assert "place_id" in response.json()


def test_get_maps_reverse_geocode_returns_payload(auth_client, settings, monkeypatch):
    cache.clear()

    def _fake_get(url, params=None, timeout=5):
        return _MockResponse(
            {
                "status": "OK",
                "results": [
                    {
                        "formatted_address": "Bole Road, Addis Ababa, Ethiopia",
                        "address_components": [
                            {"long_name": "Addis Ababa", "types": ["locality"]},
                            {"long_name": "Addis Ababa", "types": ["administrative_area_level_1"]},
                            {"long_name": "Ethiopia", "types": ["country"]},
                            {"long_name": "1000", "types": ["postal_code"]},
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr("services.maps.requests.get", _fake_get)

    response = auth_client.get(
        "/api/v1/maps/reverse-geocode/",
        {"lat": "9.012345", "lng": "38.765432"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["formatted_address"] == "Bole Road, Addis Ababa, Ethiopia"
    assert data["components"]["country"] == "Ethiopia"
    assert settings.GOOGLE_MAPS_API_KEY not in response.content.decode()


def test_get_maps_reverse_geocode_requires_auth(api_client):
    response = api_client.get(
        "/api/v1/maps/reverse-geocode/",
        {"lat": "9.012345", "lng": "38.765432"},
    )

    assert response.status_code == 401


def test_get_maps_reverse_geocode_missing_lat_returns_400(auth_client):
    response = auth_client.get("/api/v1/maps/reverse-geocode/", {"lng": "38.765432"})

    assert response.status_code == 400
    assert "lat" in response.json()


def test_create_property_listing_with_place_id_populates_coordinates(company_client, company, monkeypatch):
    monkeypatch.setattr(
        "apps.listing.serializers.get_place_detail",
        lambda place_id, session_token: {
            "lat": Decimal("9.012345"),
            "lng": Decimal("38.765432"),
            "formatted_address": "Bole Road, Addis Ababa, Ethiopia",
            "place_id": place_id,
            "components": {"city": "Addis Ababa", "country": "Ethiopia"},
        },
    )

    response = company_client.post(
        "/api/v1/listing/properties/",
        {
            "title": "Mapped Property",
            "description": "Created with place detail",
            "images": [],
            "base_price": "3000.00",
            "currency": "ETB",
            "company": str(company.id),
            "address": _address_payload(),
            "property_type": "apartment",
            "bedrooms": 2,
            "bathrooms": 1,
            "square_meters": 80,
            "is_furnished": True,
            "place_id": "place-123",
            "session_token": "session-123",
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    listing = PropertyListing.objects.get(id=response.json()["id"])
    assert listing.latitude == Decimal("9.012345")
    assert listing.longitude == Decimal("38.765432")
    assert listing.formatted_address == "Bole Road, Addis Ababa, Ethiopia"
    assert listing.place_id == "place-123"


def test_create_property_listing_with_text_address_only_dispatches_geocode_task(
    company_client,
    company,
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = company_client.post(
            "/api/v1/listing/properties/",
            {
                "title": "Address Only Property",
                "description": "Created without place detail",
                "images": [],
                "base_price": "3000.00",
                "currency": "ETB",
                "company": str(company.id),
                "address": _address_payload("Mexico Square"),
                "property_type": "apartment",
                "bedrooms": 2,
                "bathrooms": 1,
                "square_meters": 80,
                "is_furnished": True,
            },
            format="json",
        )

    assert response.status_code == 201, response.json()
    listing_id = response.json()["id"]
    assert len(calls) == 1
    assert str(calls[0][0]) == listing_id
    assert calls[0][1] == "listing.propertylisting"


def test_create_car_listing_without_place_or_address_stays_backward_compatible(company_client, company):
    response = company_client.post(
        "/api/v1/listing/cars/",
        {
            "title": "Car Draft",
            "description": "Still valid without place metadata",
            "base_price": "1500.00",
            "currency": "ETB",
            "company": str(company.id),
            "brand": CarListing.CarBrandChoices.TOYOTA,
            "model": "Camry",
            "year": 2024,
            "mileage": 1000,
            "fuel_type": CarListing.FuelTypeChoices.PETROL,
            "transmission": CarListing.TransmissionChoices.AUTOMATIC,
            "condition": CarListing.ConditionChoices.USED,
            "seats": 4,
            "listing_type": CarListing.ListingTypeChoices.RENT,
            "rental_mode": CarListing.RentalModeChoices.WITHOUT_DRIVER,
            "car_class": CarListing.CarClassChoices.NORMAL,
            "quantity": 1,
            "requires_code_3": True,
            "requires_business_license": True,
            "pre_rental_requirements": "Bring original IDs.",
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    listing = CarListing.objects.get(id=response.json()["id"])
    assert listing.latitude is None
    assert listing.longitude is None
    assert response.json()["latitude"] is None
    assert response.json()["longitude"] is None


def test_update_property_listing_with_place_id_updates_coordinates(company_client, property_listing, monkeypatch):
    monkeypatch.setattr(
        "apps.listing.serializers.get_place_detail",
        lambda place_id, session_token: {
            "lat": Decimal("8.998877"),
            "lng": Decimal("38.554433"),
            "formatted_address": "Kazanchis, Addis Ababa, Ethiopia",
            "place_id": place_id,
            "components": {"city": "Addis Ababa", "country": "Ethiopia"},
        },
    )

    response = company_client.patch(
        f"/api/v1/listing/properties/{property_listing.id}/",
        {"place_id": "place-999", "session_token": "session-999"},
        format="json",
    )

    assert response.status_code == 200, response.json()
    property_listing.refresh_from_db()
    assert property_listing.latitude == Decimal("8.998877")
    assert property_listing.longitude == Decimal("38.554433")
    assert property_listing.place_id == "place-999"


def test_post_account_location_stores_user_coordinates(auth_client, user):
    response = auth_client.post(
        "/api/v1/account/location/",
        {"lat": "9.012345", "lng": "38.765432", "permission_granted": True},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.last_known_lat == Decimal("9.012345")
    assert user.last_known_lng == Decimal("38.765432")
    assert user.location_permission_granted is True
    assert response.json()["location_permission_granted"] is True
    assert response.json()["location_updated_at"]


def test_post_account_location_requires_auth(api_client):
    response = api_client.post(
        "/api/v1/account/location/",
        {"lat": "9.012345", "lng": "38.765432", "permission_granted": True},
        format="json",
    )

    assert response.status_code == 401


def test_post_account_location_missing_lat_returns_400(auth_client):
    response = auth_client.post(
        "/api/v1/account/location/",
        {"lng": "38.765432", "permission_granted": True},
        format="json",
    )

    assert response.status_code == 400
    assert "lat" in response.json()
