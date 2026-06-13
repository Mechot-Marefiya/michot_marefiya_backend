"""Shared Geoapify helpers used across listing discovery flows."""

from __future__ import annotations

import hashlib
import logging
import math
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class GeocodingError(Exception):
    """Raised when a map provider lookup cannot be completed."""


def _hash_address(address: str) -> str:
    normalized = (address or "").strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _to_decimal(value) -> Decimal:
    return Decimal(str(value))


def _api_key() -> str:
    return getattr(settings, "GEOAPIFY_API_KEY", "").strip()


def _cache_get(key: str):
    return cache.get(key)


def _cache_set(key: str, value, ttl: int) -> None:
    cache.set(key, value, timeout=ttl)


def _safe_components(properties: dict | None) -> dict:
    properties = properties or {}
    return {
        "city": (
            properties.get("city")
            or properties.get("town")
            or properties.get("village")
            or properties.get("municipality")
            or properties.get("suburb")
            or properties.get("county")
        ),
        "region": properties.get("state") or properties.get("region"),
        "country": properties.get("country"),
        "postcode": properties.get("postcode"),
    }


def _provider_params(extra: dict) -> dict:
    api_key = _api_key()
    if not api_key:
        raise GeocodingError("Geoapify API key is not configured.")
    return {**extra, "apiKey": api_key}


def _request_json(url: str, params: dict) -> dict:
    response = requests.get(url, params=_provider_params(params), timeout=5)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("INVALID_RESPONSE")
    return payload


def _feature_to_result(feature: dict) -> dict:
    properties = dict(feature.get("properties") or {})
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if len(coordinates) >= 2:
        properties.setdefault("lon", coordinates[0])
        properties.setdefault("lat", coordinates[1])
    return properties


def _results_from_payload(payload: dict) -> list[dict]:
    if payload.get("results"):
        return list(payload["results"])
    if payload.get("features"):
        return [_feature_to_result(feature) for feature in payload["features"]]
    return []


def _format_address(result: dict) -> str:
    return (
        result.get("formatted")
        or result.get("formatted_address")
        or ", ".join(
            part
            for part in [result.get("address_line1"), result.get("address_line2")]
            if part
        )
    )


def _normalize_place(result: dict, fallback_place_id: str = "") -> dict:
    lat = result.get("lat")
    lng = result.get("lon", result.get("lng"))
    if lat is None or lng is None:
        raise ValueError("MISSING_COORDINATES")

    place_id = result.get("place_id") or result.get("id") or fallback_place_id
    return {
        "lat": _to_decimal(lat),
        "lng": _to_decimal(lng),
        "formatted_address": _format_address(result),
        "place_id": place_id,
        "components": _safe_components(result),
    }


def _first_result(payload: dict) -> dict:
    results = _results_from_payload(payload)
    if not results:
        raise ValueError("NO_RESULTS")
    return results[0]


def _raise_geocoding_error(message: str, exc: Exception | None = None) -> None:
    if exc is not None:
        logger.error("%s: %s", message, exc, exc_info=True)
        raise GeocodingError(message) from exc
    logger.error(message)
    raise GeocodingError(message)


def geocode_address(address: str) -> dict:
    if not address or not address.strip():
        raise GeocodingError("Address is required.")

    cache_key = f"maps:geocode:{_hash_address(address)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = _request_json(
            settings.GEOAPIFY_GEOCODING_URL,
            {"text": address, "format": "json", "limit": 1},
        )
        parsed = _normalize_place(_first_result(payload))
        _cache_set(cache_key, parsed, getattr(settings, "GEOCODING_CACHE_TTL", 86400))
        return parsed
    except Exception as exc:  # pragma: no cover - exercised through tests
        _raise_geocoding_error("Unable to geocode address.", exc)


def reverse_geocode(lat: Decimal, lng: Decimal) -> dict:
    cache_key = f"maps:reverse:{round(_to_decimal(lat), 3)}:{round(_to_decimal(lng), 3)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = _request_json(
            settings.GEOAPIFY_REVERSE_GEOCODING_URL,
            {"lat": lat, "lon": lng, "format": "json", "limit": 1},
        )
        result = _first_result(payload)
        parsed = {
            "formatted_address": _format_address(result),
            "components": _safe_components(result),
        }
        _cache_set(cache_key, parsed, getattr(settings, "GEOCODING_CACHE_TTL", 86400))
        return parsed
    except Exception as exc:  # pragma: no cover - exercised through tests
        _raise_geocoding_error("Unable to reverse geocode coordinates.", exc)


def autocomplete_address(input_text: str, session_token: str) -> list:
    if not input_text or not input_text.strip():
        return []

    try:
        payload = _request_json(
            settings.GEOAPIFY_AUTOCOMPLETE_URL,
            {"text": input_text, "format": "json", "limit": 5},
        )
        suggestions = []
        for item in _results_from_payload(payload):
            formatted = _format_address(item)
            main_text = item.get("address_line1") or item.get("name") or formatted.split(",", 1)[0]
            secondary_text = item.get("address_line2") or (
                formatted.split(",", 1)[1].strip() if "," in formatted else ""
            )
            suggestions.append(
                {
                    "place_id": item.get("place_id", ""),
                    "description": formatted,
                    "main_text": main_text,
                    "secondary_text": secondary_text,
                }
            )
        return suggestions
    except Exception as exc:
        logger.error("Autocomplete lookup failed: %s", exc, exc_info=True)
        return []


def get_place_detail(place_id: str, session_token: str) -> dict:
    if not place_id:
        raise GeocodingError("Place ID is required.")

    cache_key = f"maps:place:{place_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = _request_json(
            settings.GEOAPIFY_PLACE_DETAIL_URL,
            {"id": place_id, "features": "details"},
        )
        parsed = _normalize_place(_first_result(payload), fallback_place_id=place_id)
        _cache_set(cache_key, parsed, getattr(settings, "GEOCODING_CACHE_TTL", 86400))
        return parsed
    except Exception as exc:  # pragma: no cover - exercised through tests
        _raise_geocoding_error("Unable to fetch place details.", exc)


def calculate_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_km = 6371.0
    lat1_rad = math.radians(float(lat1))
    lat2_rad = math.radians(float(lat2))
    delta_lat = math.radians(float(lat2) - float(lat1))
    delta_lng = math.radians(float(lng2) - float(lng1))

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


def get_bounding_box(lat: float, lng: float, radius_km: float) -> dict:
    lat_delta = float(radius_km) / 111.0
    lat_rad = math.radians(float(lat))
    cos_lat = math.cos(lat_rad)
    if abs(cos_lat) < 1e-9:
        lng_delta = 180.0
    else:
        lng_delta = float(radius_km) / (111.0 * cos_lat)

    return {
        "lat_min": float(lat) - lat_delta,
        "lat_max": float(lat) + lat_delta,
        "lng_min": float(lng) - lng_delta,
        "lng_max": float(lng) + lng_delta,
    }


def _listing_value(listing, attr: str):
    if isinstance(listing, dict):
        return listing.get(attr)
    return getattr(listing, attr, None)


def find_listings_near(lat: float, lng: float, radius_km: float, queryset) -> list:
    bounds = get_bounding_box(lat, lng, radius_km)
    filtered_queryset = queryset.filter(
        latitude__gte=bounds["lat_min"],
        latitude__lte=bounds["lat_max"],
        longitude__gte=bounds["lng_min"],
        longitude__lte=bounds["lng_max"],
    )

    nearby = []
    for listing in filtered_queryset:
        listing_lat = _listing_value(listing, "latitude")
        listing_lng = _listing_value(listing, "longitude")
        if listing_lat is None or listing_lng is None:
            continue

        distance_km = calculate_distance_km(lat, lng, listing_lat, listing_lng)
        if distance_km <= float(radius_km):
            nearby.append(
                {
                    "id": str(_listing_value(listing, "id") or ""),
                    "title": _listing_value(listing, "title") or _listing_value(listing, "name") or "",
                    "latitude": listing_lat,
                    "longitude": listing_lng,
                    "distance_km": distance_km,
                }
            )

    nearby.sort(key=lambda item: item["distance_km"])
    return nearby


def build_map_pin(listing_dict: dict, listing_type: str) -> dict:
    def pick(*keys, default=None):
        for key in keys:
            value = listing_dict.get(key)
            if value is not None:
                return value
        return default

    title = pick("title", "name")
    if not title and pick("brand") and pick("model"):
        title = f"{pick('brand')} {pick('model')}"

    price_preview = pick("price_preview", "base_price", "reveal_fee")
    thumbnail_url = pick("thumbnail_url", "thumbnail", "image_url", "image")
    rating = pick("rating")

    return {
        "id": pick("id"),
        "listing_type": listing_type,
        "latitude": pick("latitude"),
        "longitude": pick("longitude"),
        "title": title,
        "price_preview": price_preview,
        "thumbnail_url": thumbnail_url,
        "rating": rating,
    }
