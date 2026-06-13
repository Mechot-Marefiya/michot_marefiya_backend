from decimal import Decimal

import pytest
import requests
from django.core.cache import cache
from django.test import override_settings

from services.maps import (
    GeocodingError,
    _hash_address,
    autocomplete_address,
    build_map_pin,
    calculate_distance_km,
    find_listings_near,
    geocode_address,
    get_bounding_box,
    get_place_detail,
    reverse_geocode,
)


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class DummyListing:
    def __init__(self, id, title, latitude, longitude):
        self.id = id
        self.title = title
        self.latitude = latitude
        self.longitude = longitude


class DummyQuerySet:
    def __init__(self, items):
        self._items = list(items)

    def filter(self, **kwargs):
        items = self._items
        for key, value in kwargs.items():
            field, lookup = key.split("__", 1)
            if lookup == "gte":
                items = [item for item in items if getattr(item, field) >= value]
            elif lookup == "lte":
                items = [item for item in items if getattr(item, field) <= value]
            else:
                raise AssertionError(f"Unexpected lookup: {lookup}")
        return DummyQuerySet(items)

    def __iter__(self):
        return iter(self._items)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_hash_address_normalizes_input():
    assert _hash_address("  Addis Ababa") == _hash_address("addis ababa  ")


@override_settings(GOOGLE_MAPS_API_KEY="test-key", GEOCODING_CACHE_TTL=3600)
def test_geocode_address_returns_correct_structure(monkeypatch):
    payload = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "Bole, Addis Ababa, Ethiopia",
                "place_id": "place-123",
                "geometry": {"location": {"lat": 9.03, "lng": 38.75}},
                "address_components": [
                    {"long_name": "Addis Ababa", "types": ["locality"]},
                    {"long_name": "Addis Ababa", "types": ["administrative_area_level_1"]},
                    {"long_name": "Ethiopia", "types": ["country"]},
                    {"long_name": "1000", "types": ["postal_code"]},
                ],
            }
        ],
    }
    monkeypatch.setattr("services.maps.requests.get", lambda *a, **k: DummyResponse(payload))

    result = geocode_address("Bole, Addis Ababa")

    assert result["lat"] == Decimal("9.03")
    assert result["lng"] == Decimal("38.75")
    assert result["formatted_address"] == "Bole, Addis Ababa, Ethiopia"
    assert result["place_id"] == "place-123"
    assert result["components"] == {
        "city": "Addis Ababa",
        "region": "Addis Ababa",
        "country": "Ethiopia",
        "postcode": "1000",
    }


@override_settings(GOOGLE_MAPS_API_KEY="test-key")
def test_geocode_address_raises_on_empty_results(monkeypatch):
    monkeypatch.setattr(
        "services.maps.requests.get",
        lambda *a, **k: DummyResponse({"status": "ZERO_RESULTS", "results": []}),
    )

    with pytest.raises(GeocodingError):
        geocode_address("Unknown place")


@override_settings(GOOGLE_MAPS_API_KEY="test-key")
def test_geocode_address_raises_on_network_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr("services.maps.requests.get", boom)

    with pytest.raises(GeocodingError):
        geocode_address("Bole, Addis Ababa")


@override_settings(GOOGLE_MAPS_API_KEY="test-key", GEOCODING_CACHE_TTL=3600)
def test_geocode_address_returns_cached_value_on_second_call(monkeypatch):
    payload = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "Bole, Addis Ababa, Ethiopia",
                "place_id": "place-123",
                "geometry": {"location": {"lat": 9.03, "lng": 38.75}},
                "address_components": [],
            }
        ],
    }
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return DummyResponse(payload)

    monkeypatch.setattr("services.maps.requests.get", fake_get)

    first = geocode_address("Bole, Addis Ababa")
    second = geocode_address("Bole, Addis Ababa")

    assert first == second
    assert calls["count"] == 1


@override_settings(GOOGLE_MAPS_API_KEY="test-key", GEOCODING_CACHE_TTL=3600)
def test_reverse_geocode_returns_formatted_address(monkeypatch):
    payload = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "Bole, Addis Ababa, Ethiopia",
                "address_components": [
                    {"long_name": "Bole", "types": ["locality"]},
                    {"long_name": "Addis Ababa", "types": ["administrative_area_level_1"]},
                ],
            }
        ],
    }
    monkeypatch.setattr("services.maps.requests.get", lambda *a, **k: DummyResponse(payload))

    result = reverse_geocode(Decimal("9.03"), Decimal("38.75"))

    assert result["formatted_address"] == "Bole, Addis Ababa, Ethiopia"
    assert result["components"]["city"] == "Bole"


@override_settings(GOOGLE_MAPS_API_KEY="test-key")
def test_autocomplete_address_returns_suggestions_list(monkeypatch):
    payload = {
        "predictions": [
            {
                "place_id": "place-1",
                "description": "Bole, Addis Ababa, Ethiopia",
                "structured_formatting": {
                    "main_text": "Bole",
                    "secondary_text": "Addis Ababa, Ethiopia",
                },
            }
        ]
    }
    monkeypatch.setattr("services.maps.requests.get", lambda *a, **k: DummyResponse(payload))

    result = autocomplete_address("Bol", "session-1")

    assert result == [
        {
            "place_id": "place-1",
            "description": "Bole, Addis Ababa, Ethiopia",
            "main_text": "Bole",
            "secondary_text": "Addis Ababa, Ethiopia",
        }
    ]


@override_settings(GOOGLE_MAPS_API_KEY="test-key")
def test_autocomplete_address_returns_empty_list_on_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr("services.maps.requests.get", boom)

    assert autocomplete_address("Bol", "session-1") == []


@override_settings(GOOGLE_MAPS_API_KEY="test-key", GEOCODING_CACHE_TTL=3600)
def test_get_place_detail_returns_lat_lng_address(monkeypatch):
    payload = {
        "status": "OK",
        "result": {
            "place_id": "place-555",
            "formatted_address": "Bole, Addis Ababa, Ethiopia",
            "geometry": {"location": {"lat": 9.03, "lng": 38.75}},
            "address_components": [
                {"long_name": "Bole", "types": ["locality"]},
                {"long_name": "Ethiopia", "types": ["country"]},
            ],
        },
    }
    monkeypatch.setattr("services.maps.requests.get", lambda *a, **k: DummyResponse(payload))

    result = get_place_detail("place-555", "session-1")

    assert result["lat"] == Decimal("9.03")
    assert result["lng"] == Decimal("38.75")
    assert result["formatted_address"] == "Bole, Addis Ababa, Ethiopia"
    assert result["place_id"] == "place-555"


@override_settings(GOOGLE_MAPS_API_KEY="test-key")
def test_get_place_detail_raises_on_failure(monkeypatch):
    monkeypatch.setattr(
        "services.maps.requests.get",
        lambda *a, **k: DummyResponse({"status": "ZERO_RESULTS", "result": None}),
    )

    with pytest.raises(GeocodingError):
        get_place_detail("place-555", "session-1")


def test_calculate_distance_km_known_coordinates():
    distance = calculate_distance_km(9.0333, 38.7465, 8.9779, 38.7993)
    assert 8.0 <= distance <= 9.5


def test_get_bounding_box_returns_correct_delta_values():
    result = get_bounding_box(9.0333, 38.7465, 10)
    assert result["lat_min"] == pytest.approx(8.943209, rel=1e-6)
    assert result["lat_max"] == pytest.approx(9.123391, rel=1e-6)
    assert result["lng_min"] == pytest.approx(38.655279, rel=1e-6)
    assert result["lng_max"] == pytest.approx(38.837721, rel=1e-6)


def test_find_listings_near_returns_listings_ordered_by_distance():
    listings = DummyQuerySet(
        [
            DummyListing("1", "Far", 9.10, 38.80),
            DummyListing("2", "Near", 9.03, 38.75),
            DummyListing("3", "Mid", 9.05, 38.77),
        ]
    )

    result = find_listings_near(9.0333, 38.7465, 15, listings)

    assert [item["title"] for item in result] == ["Near", "Mid", "Far"]
    assert result[0]["distance_km"] <= result[1]["distance_km"] <= result[2]["distance_km"]


def test_find_listings_near_excludes_listings_beyond_radius():
    listings = DummyQuerySet(
        [
            DummyListing("1", "Close", 9.03, 38.75),
            DummyListing("2", "Too Far", 10.0, 39.5),
        ]
    )

    result = find_listings_near(9.0333, 38.7465, 5, listings)

    assert [item["title"] for item in result] == ["Close"]


def test_find_listings_near_returns_empty_list_when_none_found():
    listings = DummyQuerySet([DummyListing("1", "Too Far", 10.5, 40.0)])

    result = find_listings_near(9.0333, 38.7465, 2, listings)

    assert result == []


def test_build_map_pin_returns_lightweight_pin():
    pin = build_map_pin(
        {
            "id": "listing-1",
            "title": "Bole Apartment",
            "latitude": Decimal("9.03"),
            "longitude": Decimal("38.75"),
            "price_preview": "1200.00",
            "thumbnail_url": "https://example.com/image.jpg",
            "rating": 4.8,
        },
        "property",
    )

    assert pin == {
        "id": "listing-1",
        "listing_type": "property",
        "latitude": Decimal("9.03"),
        "longitude": Decimal("38.75"),
        "title": "Bole Apartment",
        "price_preview": "1200.00",
        "thumbnail_url": "https://example.com/image.jpg",
        "rating": 4.8,
    }
