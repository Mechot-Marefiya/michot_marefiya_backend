import pytest
from decimal import Decimal
from unittest.mock import patch

from apps.listing.models import CarListing, CarSaleListing, PropertySaleListing

pytestmark = pytest.mark.django_db


def _set_geo(listing, lat, lng, formatted_address="Test address", place_id="test-place-id"):
    listing.latitude = Decimal(str(lat))
    listing.longitude = Decimal(str(lng))
    listing.formatted_address = formatted_address
    listing.place_id = place_id
    listing.save(update_fields=["latitude", "longitude", "formatted_address", "place_id", "updated_at"])


def _create_car_sale(company, *, title, lat, lng, suffix):
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
        latitude=Decimal(str(lat)),
        longitude=Decimal(str(lng)),
        formatted_address=f"{title} address",
        place_id=f"{title.lower().replace(' ', '-')}-place",
    )


def _create_property_sale(company, *, title, lat, lng, suffix):
    from apps.core.models import Address

    return PropertySaleListing.objects.create(
        company=company,
        address=Address.objects.create(
            street_line1=f"{title} Street",
            city="Addis Ababa",
            state="Addis Ababa",
            country="Ethiopia",
        ),
        property_type=PropertySaleListing.PropertyTypeChoices.HOUSE,
        bedrooms=3,
        bathrooms=2,
        square_meters=Decimal("180.00"),
        land_size_square_meters=Decimal("240.00"),
        is_furnished=True,
        title=title,
        description=f"{title} description",
        base_price=Decimal("4500000.00") + Decimal(str(suffix)),
        currency="ETB",
        seller_contact_name="Seller",
        seller_phone="0911000000",
        seller_email="seller@example.com",
        reveal_fee=Decimal("150.00"),
        is_active=True,
        latitude=Decimal(str(lat)),
        longitude=Decimal(str(lng)),
        formatted_address=f"{title} address",
        place_id=f"{title.lower().replace(' ', '-')}-place",
    )


def test_nearby_returns_listings_with_distance_and_filtering(
    api_client,
    hotel,
    guest_house,
    property_listing,
    event_space,
    car_listing,
    company,
):
    _set_geo(hotel, 9.0000, 38.0000, "Hotel address", "hotel-place")
    _set_geo(guest_house, 9.0010, 38.0010, "Guesthouse address", "guesthouse-place")
    _set_geo(property_listing, 9.0020, 38.0020, "Property address", "property-place")
    _set_geo(event_space, 9.0030, 38.0030, "Event space address", "event-space-place")
    _set_geo(car_listing, 9.0040, 38.0040, "Car rental address", "car-rental-place")
    _create_property_sale(company, title="Sale House", lat=9.0050, lng=38.0050, suffix=12)
    far_sale = _create_car_sale(company, title="Far Sale", lat=9.0500, lng=38.0500, suffix=99)

    response = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "1", "listing_type": "all"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert data["results"]
    ids = {item["id"] for item in data["results"]}
    assert str(far_sale.id) not in ids
    listing_types = {item["listing_type"] for item in data["results"]}
    assert {
        "hotel",
        "guesthouse",
        "event_space",
        "property_rental",
        "property_sales",
        "car_rental",
    } <= listing_types
    for item in data["results"]:
        assert "distance_km" in item
        assert "formatted_address" in item
        assert "latitude" in item
        assert "longitude" in item


@pytest.mark.parametrize(
    ("listing_type", "fixture_name"),
    [
        ("event_space", "event_space"),
        ("property_rental", "property_listing"),
        ("car_rental", "car_listing"),
    ],
)
def test_nearby_supports_rental_listing_type_filters(api_client, request, listing_type, fixture_name):
    listing = request.getfixturevalue(fixture_name)
    _set_geo(listing, 9.0000, 38.0000, f"{listing_type} address", f"{listing_type}-place")

    response = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "2", "listing_type": listing_type},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    assert all(item["listing_type"] == listing_type for item in results)


def test_nearby_supports_property_sales_filter(api_client, company):
    listing = _create_property_sale(company, title="Nearby Sale House", lat=9.0000, lng=38.0000, suffix=33)

    response = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "2", "listing_type": "property_sales"},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["id"] for item in results] == [str(listing.id)]
    assert all(item["listing_type"] == "property_sales" for item in results)


def test_nearby_excludes_listings_beyond_radius(api_client, hotel, company):
    _set_geo(hotel, 9.0000, 38.0000, "Hotel address", "hotel-place")
    far_sale = _create_car_sale(company, title="Far Sale", lat=9.5000, lng=38.5000, suffix=10)

    response = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "1"},
    )

    assert response.status_code == 200
    data = response.json()["results"]
    ids = {item["id"] for item in data}
    assert data
    assert str(far_sale.id) not in ids


def test_nearby_respects_listing_type_filter(api_client, hotel, guest_house):
    _set_geo(hotel, 9.0000, 38.0000, "Hotel address", "hotel-place")
    _set_geo(guest_house, 9.0010, 38.0010, "Guesthouse address", "guesthouse-place")

    response = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "2", "listing_type": "hotel"},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    assert all(item["listing_type"] == "hotel" for item in results)
    assert all("distance_km" in item for item in results)


def test_nearby_returns_empty_list_when_no_matches(api_client):
    response = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.5000", "lng": "38.5000", "radius_km": "1"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["results"] == []


def test_nearby_validates_required_coordinates_and_radius(api_client):
    missing_lat = api_client.get("/api/v1/listing/nearby/", {"lng": "38.0000"})
    missing_lng = api_client.get("/api/v1/listing/nearby/", {"lat": "9.0000"})
    too_large = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "101"},
    )

    assert missing_lat.status_code == 400
    assert missing_lng.status_code == 400
    assert too_large.status_code == 400


def test_within_bounds_returns_listings_inside_viewport(api_client, hotel, property_listing, company):
    _set_geo(hotel, 9.0000, 38.0000, "Hotel address", "hotel-place")
    _set_geo(property_listing, 9.0200, 38.0200, "Property address", "property-place")
    outside = _create_car_sale(company, title="Outside Sale", lat=9.5000, lng=38.5000, suffix=11)

    response = api_client.get(
        "/api/v1/listing/within-bounds/",
        {"north": "9.0500", "south": "8.9500", "east": "38.0500", "west": "37.9500"},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    ids = {item["id"] for item in results}
    assert results
    assert str(outside.id) not in ids
    assert all("latitude" in item and "longitude" in item for item in results)


def test_map_pins_are_lightweight_and_capped_at_200(api_client, company):
    listings = [
        CarSaleListing(
            company=company,
            brand=CarListing.CarBrandChoices.TOYOTA,
            model=f"Model {idx}",
            year=2022,
            mileage=10000 + idx,
            fuel_type=CarListing.FuelTypeChoices.PETROL,
            transmission=CarListing.TransmissionChoices.AUTOMATIC,
            condition=CarListing.ConditionChoices.USED,
            car_class=CarListing.CarClassChoices.NORMAL,
            title=f"Pin Car {idx}",
            description="Pin description",
            base_price=Decimal("30000.00"),
            currency="ETB",
            seller_contact_name="Seller",
            seller_phone="0911000000",
            seller_email="seller@example.com",
            reveal_fee=Decimal("100.00"),
            is_active=True,
            latitude=Decimal("9.0000"),
            longitude=Decimal("38.0000"),
            formatted_address="Pin address",
            place_id=f"pin-place-{idx}",
        )
        for idx in range(205)
    ]
    CarSaleListing.objects.bulk_create(listings)

    response = api_client.get(
        "/api/v1/listing/map-pins/",
        {"lat": "9.0000", "lng": "38.0000", "radius_km": "2", "listing_type": "car_sales"},
    )

    assert response.status_code == 200
    pins = response.json()
    assert len(pins) == 200
    pin = pins[0]
    assert set(pin.keys()) <= {"id", "listing_type", "latitude", "longitude", "title", "price_preview", "thumbnail_url", "rating"}
    assert "distance_km" not in pin
    assert "formatted_address" not in pin


def test_feed_returns_proximity_when_user_location_is_available(auth_client, user, hotel):
    _set_geo(hotel, 9.0000, 38.0000, "Hotel address", "hotel-place")
    user.location_permission_granted = True
    user.last_known_lat = Decimal("9.0000")
    user.last_known_lng = Decimal("38.0000")
    user.save(update_fields=["location_permission_granted", "last_known_lat", "last_known_lng", "updated_at"])

    response = auth_client.get("/api/v1/listing/feed/")

    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    assert "distance_km" in data["results"][0]


def test_feed_returns_standard_listings_for_anonymous_users(api_client, hotel):
    _set_geo(hotel, 9.0000, 38.0000, "Hotel address", "hotel-place")

    response = api_client.get("/api/v1/listing/feed/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    if data["results"]:
        assert "distance_km" not in data["results"][0]


@patch("apps.listing.views.cache.get", side_effect=[None, {"count": 1, "total_pages": 1, "current_page": 1, "page_size": 10, "next": None, "previous": None, "results": []}])
@patch("apps.listing.views.cache.set", return_value=None)
def test_nearby_uses_cache_and_rounded_coordinates(mock_cache_set, mock_cache_get, api_client, hotel):
    _set_geo(hotel, 9.1234, 38.5678, "Hotel address", "hotel-place")

    first = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.1234", "lng": "38.5678", "radius_km": "1"},
    )

    assert first.status_code == 200
    assert mock_cache_set.call_count == 1
    first_key = mock_cache_set.call_args_list[0].args[0]

    mock_cache_get.side_effect = [None, {"count": 1, "total_pages": 1, "current_page": 1, "page_size": 10, "next": None, "previous": None, "results": []}]
    second = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.1236", "lng": "38.5678", "radius_km": "1"},
    )

    assert second.status_code == 200
    assert mock_cache_set.call_count == 2
    second_key = mock_cache_set.call_args_list[1].args[0]
    assert first_key != second_key
