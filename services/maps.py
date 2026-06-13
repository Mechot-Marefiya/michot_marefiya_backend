"""Shared Google Maps helpers used across listing discovery flows."""

from __future__ import annotations

import hashlib
import logging
import math
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class GeocodingError(Exception):
    """Raised when a Google Maps lookup cannot be completed."""


def _hash_address(address: str) -> str:
    normalized = (address or "").strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _to_decimal(value) -> Decimal:
    return Decimal(str(value))


def _api_key() -> str:
    return getattr(settings, "GOOGLE_MAPS_API_KEY", "").strip()


def _cache_get(key: str):
    return cache.get(key)


def _cache_set(key: str, value, ttl: int) -> None:
    cache.set(key, value, timeout=ttl)


def _safe_components(address_components) -> dict:
    lookup = {}
    for component in address_components or []:
        types = component.get("types", [])
        for type_name in types:
            lookup.setdefault(type_name, component)

    city_component = (
        lookup.get("locality")
        or lookup.get("postal_town")
        or lookup.get("administrative_area_level_2")
        or lookup.get("sublocality")
    )
    region_component = lookup.get("administrative_area_level_1")
    country_component = lookup.get("country")
    postcode_component = lookup.get("postal_code")

    return {
        "city": city_component.get("long_name") if city_component else None,
        "region": region_component.get("long_name") if region_component else None,
        "country": country_component.get("long_name") if country_component else None,
        "postcode": postcode_component.get("long_name") if postcode_component else None,
    }


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
        response = requests.get(
            settings.GOOGLE_MAPS_GEOCODING_URL,
            params={"address": address, "key": _api_key()},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "OK" or not payload.get("results"):
            raise ValueError(payload.get("status", "NO_RESULTS"))

        result = payload["results"][0]
        location = result["geometry"]["location"]
        parsed = {
            "lat": _to_decimal(location["lat"]),
            "lng": _to_decimal(location["lng"]),
            "formatted_address": result.get("formatted_address", ""),
            "place_id": result.get("place_id", ""),
            "components": _safe_components(result.get("address_components")),
        }
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
        response = requests.get(
            settings.GOOGLE_MAPS_GEOCODING_URL,
            params={"latlng": f"{lat},{lng}", "key": _api_key()},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "OK" or not payload.get("results"):
            raise ValueError(payload.get("status", "NO_RESULTS"))

        result = payload["results"][0]
        parsed = {
            "formatted_address": result.get("formatted_address", ""),
            "components": _safe_components(result.get("address_components")),
        }
        _cache_set(cache_key, parsed, getattr(settings, "GEOCODING_CACHE_TTL", 86400))
        return parsed
    except Exception as exc:  # pragma: no cover - exercised through tests
        _raise_geocoding_error("Unable to reverse geocode coordinates.", exc)


def autocomplete_address(input_text: str, session_token: str) -> list:
    if not input_text or not input_text.strip():
        return []

    try:
        response = requests.get(
            settings.GOOGLE_MAPS_PLACES_AUTOCOMPLETE_URL,
            params={
                "input": input_text,
                "sessiontoken": session_token,
                "key": _api_key(),
            },
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        predictions = payload.get("predictions") or []
        suggestions = []
        for item in predictions:
            structured = item.get("structured_formatting") or {}
            suggestions.append(
                {
                    "place_id": item.get("place_id", ""),
                    "description": item.get("description", ""),
                    "main_text": structured.get("main_text", ""),
                    "secondary_text": structured.get("secondary_text", ""),
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
        response = requests.get(
            settings.GOOGLE_MAPS_PLACE_DETAIL_URL,
            params={
                "place_id": place_id,
                "fields": "geometry,formatted_address,address_components,place_id",
                "sessiontoken": session_token,
                "key": _api_key(),
            },
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "OK" or not payload.get("result"):
            raise ValueError(payload.get("status", "NO_RESULTS"))

        result = payload["result"]
        location = result["geometry"]["location"]
        parsed = {
            "lat": _to_decimal(location["lat"]),
            "lng": _to_decimal(location["lng"]),
            "formatted_address": result.get("formatted_address", ""),
            "place_id": result.get("place_id", place_id),
            "components": _safe_components(result.get("address_components")),
        }
        _cache_set(cache_key, parsed, getattr(settings, "GEOCODING_CACHE_TTL", 86400))
        return parsed
    except Exception as exc:  # pragma: no cover - exercised through tests
        _raise_geocoding_error("Unable to fetch Google place details.", exc)


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
