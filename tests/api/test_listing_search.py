from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.listing.models import CarListing, CarSaleListing
from tests.conftest import HotelProfileFactory, PropertyListingFactory


pytestmark = pytest.mark.django_db


def _set_geo(listing, lat, lng, formatted_address="Test address", place_id="test-place-id"):
    listing.latitude = Decimal(str(lat))
    listing.longitude = Decimal(str(lng))
    listing.formatted_address = formatted_address
    listing.place_id = place_id
    listing.save(update_fields=["latitude", "longitude", "formatted_address", "place_id", "updated_at"])


def _create_car_sale(company, *, title, lat=None, lng=None, suffix=1):
    return CarSaleListing.objects.create(
        company=company,
        brand=CarListing.CarBrandChoices.TOYOTA,
        model=f"Model {suffix}",
        year=2022,
        mileage=12000 + suffix,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        condition=CarListing.ConditionChoices.USED,
        car_class=CarListing.CarClassChoices.NORMAL,
        title=title,
        description=f"{title} description",
        base_price=Decimal("25000.00") + Decimal(str(suffix)),
        currency="ETB",
        seller_contact_name="Seller",
        seller_phone="0911000000",
        seller_email="seller@example.com",
        reveal_fee=Decimal("150.00"),
        is_active=True,
        latitude=Decimal(str(lat)) if lat is not None else None,
        longitude=Decimal(str(lng)) if lng is not None else None,
        formatted_address=f"{title} address" if lat is not None and lng is not None else None,
        place_id=f"{title.lower().replace(' ', '-')}-place" if lat is not None and lng is not None else None,
    )


def test_listing_search_keyword_only_preserves_results_without_coordinates(api_client, company):
    with_geo = PropertyListingFactory(company=company, title="Addis Loft")
    no_geo = PropertyListingFactory(company=company, title="Addis Budget")
    _set_geo(with_geo, 9.01, 38.75, "Bole, Addis Ababa, Ethiopia", "geo-place")
    no_geo.latitude = None
    no_geo.longitude = None
    no_geo.formatted_address = None
    no_geo.place_id = None
    no_geo.save(update_fields=["latitude", "longitude", "formatted_address", "place_id", "updated_at"])

    response = api_client.get("/api/v1/listing/search/", {"q": "Addis", "listing_type": "property_rental"})

    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["results"]}
    assert str(with_geo.id) in ids
    assert str(no_geo.id) in ids
    for item in data["results"]:
        assert "distance_km" in item
        assert item["distance_km"] is None
    assert "search_center" not in data
    assert "applied_radius_km" not in data


def test_listing_search_no_params_matches_feed(api_client, hotel):
    _set_geo(hotel, 9.0, 38.0, "Feed Hotel address", "feed-place")

    search_response = api_client.get("/api/v1/listing/search/")
    feed_response = api_client.get("/api/v1/listing/feed/")

    assert search_response.status_code == 200
    assert feed_response.status_code == 200
    assert search_response.json()["count"] == feed_response.json()["count"]
    assert [item["id"] for item in search_response.json()["results"]] == [
        item["id"] for item in feed_response.json()["results"]
    ]


def test_listing_search_location_only_orders_by_distance(api_client, company):
    near = PropertyListingFactory(company=company, title="Nearby Listing")
    far = PropertyListingFactory(company=company, title="Far Listing")
    _set_geo(near, 9.0000, 38.0000, "Near address", "near-place")
    _set_geo(far, 9.0200, 38.0200, "Far address", "far-place")

    response = api_client.get(
        "/api/v1/listing/search/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "5", "listing_type": "property_rental"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    assert data["results"][0]["id"] == str(near.id)
    assert data["results"][0]["distance_km"] <= data["results"][1]["distance_km"]
    assert data["search_center"] == {"lat": 9.0, "lng": 38.0}
    assert data["applied_radius_km"] == 5.0


def test_listing_search_keyword_plus_location_filters_and_excludes_missing_coordinates(api_client, company):
    match = PropertyListingFactory(company=company, title="Bole Apartment")
    no_geo = PropertyListingFactory(company=company, title="Bole Hidden")
    far = PropertyListingFactory(company=company, title="Bole Far")
    _set_geo(match, 9.0000, 38.0000, "Bole, Addis Ababa", "match-place")
    _set_geo(far, 9.5000, 38.5000, "Far, Addis Ababa", "far-place")
    no_geo.latitude = None
    no_geo.longitude = None
    no_geo.save(update_fields=["latitude", "longitude", "updated_at"])

    response = api_client.get(
        "/api/v1/listing/search/",
        {
            "q": "Bole",
            "lat": "9.0000",
            "lng": "38.0000",
            "radius_km": "2",
            "listing_type": "property_rental",
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["id"] == str(match.id)
    assert results[0]["distance_km"] is not None


def test_listing_search_validates_radius_and_coordinate_pairs(api_client):
    radius_response = api_client.get(
        "/api/v1/listing/search/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "101"},
    )
    lat_only_response = api_client.get("/api/v1/listing/search/", {"lat": "9.0000"})
    lng_only_response = api_client.get("/api/v1/listing/search/", {"lng": "38.0000"})

    assert radius_response.status_code == 400
    assert lat_only_response.status_code == 400
    assert lng_only_response.status_code == 400


def test_listing_search_sort_options(api_client, company):
    cheap = PropertyListingFactory(company=company, title="Sort Cheap", base_price=Decimal("1000.00"))
    pricey = PropertyListingFactory(company=company, title="Sort Pricey", base_price=Decimal("5000.00"))
    _set_geo(cheap, 9.0000, 38.0000, "Cheap address", "cheap-place")
    _set_geo(pricey, 9.0010, 38.0010, "Pricey address", "pricey-place")

    low_star = HotelProfileFactory(company=company, name="Low Star Hotel", stars=2)
    high_star = HotelProfileFactory(company=company, name="High Star Hotel", stars=5)
    _set_geo(low_star, 9.0000, 38.0000, "Low star address", "low-star-place")
    _set_geo(high_star, 9.0020, 38.0020, "High star address", "high-star-place")

    price_response = api_client.get(
        "/api/v1/listing/search/",
        {"q": "Sort", "sort_by": "price", "listing_type": "property_rental"},
    )
    rating_response = api_client.get(
        "/api/v1/listing/search/",
        {"q": "Hotel", "sort_by": "rating", "listing_type": "hotel"},
    )
    newest_response = api_client.get(
        "/api/v1/listing/search/",
        {"q": "Sort", "sort_by": "newest", "listing_type": "property_rental"},
    )

    assert price_response.status_code == 200
    assert rating_response.status_code == 200
    assert newest_response.status_code == 200
    assert price_response.json()["results"][0]["id"] == str(cheap.id)
    assert rating_response.json()["results"][0]["id"] == str(high_star.id)
    assert newest_response.json()["results"][0]["id"] == str(pricey.id)


def test_listing_search_suggestions_include_distance_and_respect_limit(api_client, company):
    first = PropertyListingFactory(company=company, title="Atlas One")
    second = PropertyListingFactory(company=company, title="Atlas Two")
    third = PropertyListingFactory(company=company, title="Atlas Three")
    _set_geo(first, 9.0000, 38.0000, "Atlas One address", "atlas-one-place")
    _set_geo(second, 9.0010, 38.0010, "Atlas Two address", "atlas-two-place")
    _set_geo(third, 9.0020, 38.0020, "Atlas Three address", "atlas-three-place")

    response = api_client.get(
        "/api/v1/listing/search/suggestions/",
        {"q": "Atlas", "lat": "9.0000", "lng": "38.0000", "limit": 2, "listing_type": "property_rental"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert all(item["distance_km"] is not None for item in payload)
    assert all("latitude" in item and "longitude" in item for item in payload)


def test_listing_search_suggestions_return_null_distance_without_location(api_client, company):
    listing = PropertyListingFactory(company=company, title="Mercato Home")
    response = api_client.get(
        "/api/v1/listing/search/suggestions/",
        {"q": "Mercato", "listing_type": "property_rental"},
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(listing.id)
    assert response.json()[0]["distance_km"] is None


def test_listing_search_suggestions_validate_short_queries(api_client):
    response = api_client.get("/api/v1/listing/search/suggestions/", {"q": "A"})
    assert response.status_code == 400


@patch("apps.listing.views.cache.set", return_value=None)
@patch(
    "apps.listing.views.cache.get",
    side_effect=[
        None,
        [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "listing_type": "property_rental",
                "title": "Cached Search",
                "formatted_address": "Cached address",
                "thumbnail_url": None,
                "rating": None,
                "price_preview": "1000.00",
                "distance_km": None,
                "latitude": None,
                "longitude": None,
            }
        ],
    ],
)
def test_listing_search_suggestions_use_cache(mock_cache_get, mock_cache_set, api_client, company):
    listing = PropertyListingFactory(company=company, title="Cached Search")
    _set_geo(listing, 9.0000, 38.0000, "Cached address", "cached-place")

    first = api_client.get(
        "/api/v1/listing/search/suggestions/",
        {"q": "Cached", "listing_type": "property_rental"},
    )
    second = api_client.get(
        "/api/v1/listing/search/suggestions/",
        {"q": "Cached", "listing_type": "property_rental"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert mock_cache_set.call_count == 1
