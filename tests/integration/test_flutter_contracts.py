# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.utils import timezone

from apps.account.enums import RoleCode
from apps.account.models import HotelProfile
from apps.account.models import OtpChallenge, OwnerComplianceAgreement, Role
from apps.core.models import Address, CurrencyRate
from apps.listing.models import (
    Booking,
    BookingItem,
    CarAvailability,
    CarListing,
    CarSaleListing,
    ContactRevealRequest,
    PropertyContactRevealRequest,
    PropertyListing,
    PropertyRentalAvailability,
    PropertyRentalBooking,
    PropertySaleListing,
    TermsAndConditions,
)
from apps.payment.models import PaymentTransaction
from apps.promotions.models import PromotionCampaign, PromotionPlacement

pytestmark = pytest.mark.django_db


def _assert_verification_fields(payload):
    assert "is_verified" in payload
    assert "verified_at" in payload
    assert "verified_by" in payload
    assert "verification_note" in payload


def _make_discovery_visible(listing, *, lat="9.000000", lng="38.000000", address="Discovery address"):
    listing.latitude = Decimal(lat)
    listing.longitude = Decimal(lng)
    listing.formatted_address = address
    listing.place_id = f"flutter-discovery-{listing.id}"
    if hasattr(listing, "is_active"):
        listing.is_active = True
    listing.save(update_fields=["latitude", "longitude", "formatted_address", "place_id", "is_active", "updated_at"])
    return listing


def test_flutter_contract_auth_me(auth_client, user):
    response = auth_client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    data = response.json()
    for key in ["id", "email", "first_name", "last_name", "phone", "is_active", "role", "workspace"]:
        assert key in data


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_flutter_contract_auth_otp_request(mock_send_sms, mock_generate_code, api_client, user):
    response = api_client.post(
        "/api/v1/auth/otp/request/",
        {"phone": user.phone},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["success", "challenge_id", "challenge_token", "purpose", "expires_at", "cooldown_seconds", "phone"]:
        assert key in data


def test_flutter_contract_auth_otp_verify(api_client, user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
    )

    response = api_client.post(
        "/api/v1/auth/otp/verify/",
        {"challenge_id": str(challenge.id), "code": "123456"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["success", "purpose", "user", "access", "refresh", "role"]:
        assert key in data
    for key in ["id", "email", "first_name", "last_name", "phone", "is_active", "role", "workspace"]:
        assert key in data["user"]


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_flutter_contract_phone_first_signup(mock_send_sms, mock_generate_code, api_client):
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)

    response = api_client.post(
        "/api/v1/account/users/",
        {
            "email": "flutter-signup@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "first_name": "Flutter",
            "last_name": "Signup",
            "phone": "0911000201",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    for key in [
        "id",
        "email",
        "first_name",
        "last_name",
        "phone",
        "phone_verified",
        "phone_verified_at",
        "is_active",
        "role",
        "workspace",
        "verification_required",
        "phone_verification_required",
        "otp_challenge_id",
        "otp_expires_at",
        "otp_purpose",
    ]:
        assert key in data
    assert data["verification_required"] == "phone"
    assert data["phone_verification_required"] is True
    assert data["otp_purpose"] == "signup"


def test_flutter_contract_convert_guest_bookings(auth_client, user):
    user.phone = "0911444333"
    user.save(update_fields=["phone", "updated_at"])
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at", "updated_at"])

    response = auth_client.post(
        "/api/v1/account/users/me/convert-guest-bookings/",
        {},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in [
        "success",
        "phone",
        "verified_via",
        "linked_counts",
        "already_linked_counts",
        "linked_total",
        "already_linked_total",
    ]:
        assert key in data


def test_flutter_contract_core_currency_convert(api_client):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"), date=date.today())
    response = api_client.post(
        "/api/v1/core/currency/convert/",
        {"base": "USD", "target": "ETB", "amount": "10", "date": date.today().isoformat()},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["status", "input_amount", "base", "target", "converted_amount", "rate_date", "rate_used"]:
        assert key in data


def test_flutter_contract_core_currencies_list(api_client):
    response = api_client.get("/api/v1/core/currencies/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data
    for key in ["code", "name"]:
        assert key in data[0]


def test_flutter_contract_core_currency_rates(api_client):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"), date=date.today())
    response = api_client.get("/api/v1/core/currencies/rates/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "ETB" in data
    assert "USD" in data


def test_flutter_contract_account_hotels(api_client, hotel):
    response = api_client.get("/api/v1/account/hotels/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data and "results" in data
    assert isinstance(data["results"], list)
    _assert_verification_fields(data["results"][0])


def test_flutter_contract_individual_owner_agreement(individual_owner_client, individual_owner):
    OwnerComplianceAgreement.objects.create(
        owner=individual_owner,
        agreement_version="v1",
        status=OwnerComplianceAgreement.Status.SIGNED,
        signed_at=timezone.now(),
    )

    detail_response = individual_owner_client.get(
        f"/api/v1/account/individual-owners/{individual_owner.id}/agreement/"
    )
    profile_response = individual_owner_client.get("/api/v1/account/profile/agreement/")

    assert detail_response.status_code == 200
    detail_data = detail_response.json()
    assert set(detail_data.keys()) == {"status", "signed_at", "agreement_version"}

    assert profile_response.status_code == 200
    profile_data = profile_response.json()
    assert set(profile_data.keys()) == {"status", "signed_at", "agreement_version"}


def test_flutter_contract_listing_verification_fields(
    api_client,
    guest_house,
    car_listing,
    property_listing,
    event_space,
):
    endpoints = [
        f"/api/v1/listing/guest-houses/{guest_house.id}/",
        f"/api/v1/listing/cars/{car_listing.id}/",
        f"/api/v1/listing/properties/{property_listing.id}/",
        f"/api/v1/listing/event-spaces/{event_space.id}/",
    ]

    for endpoint in endpoints:
        response = api_client.get(endpoint)
        assert response.status_code == 200
        _assert_verification_fields(response.json())


def test_flutter_contract_listing_room_detail(api_client, room):
    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/")

    assert response.status_code == 200
    data = response.json()
    for key in ["id", "title", "description", "base_price", "currency"]:
        assert key in data
    _assert_verification_fields(data)


def test_flutter_contract_car_sales_connector(auth_client, user, company):
    listing = CarSaleListing.objects.create(
        company=company,
        title="Flutter Sale Car",
        description="Sale listing for contract test",
        base_price=Decimal("950000.00"),
        currency="ETB",
        brand=CarListing.CarBrandChoices.TOYOTA,
        model="Yaris",
        year=2019,
        mileage=50000,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        condition=CarListing.ConditionChoices.USED,
        car_class=CarListing.CarClassChoices.NORMAL,
        seats=5,
        seller_contact_name="Flutter Seller",
        seller_phone="0911999888",
        seller_email="flutter-seller@example.com",
        reveal_fee=Decimal("100.00"),
        is_active=True,
    )

    response = auth_client.get(f"/api/v1/listing/car-sales/{listing.id}/")
    assert response.status_code == 200
    data = response.json()
    for key in [
        "id",
        "title",
        "description",
        "base_price",
        "currency",
        "brand",
        "model",
        "year",
        "mileage",
        "reveal_fee",
        "reveal_state",
        "is_verified",
        "verified_at",
        "verified_by",
        "verification_note",
    ]:
        assert key in data
    assert "seller_phone" not in data
    assert "seller_email" not in data

    reveal_request = ContactRevealRequest.objects.create(
        listing=listing,
        buyer=user,
        amount=listing.reveal_fee,
        currency=listing.currency,
        status=ContactRevealRequest.RevealStatus.PAID_REVEALED,
        tx_ref="contract-contact-1",
        expires_at=timezone.now() + timezone.timedelta(minutes=30),
        unlocked_at=timezone.now(),
        contact_snapshot={
            "seller_contact_name": listing.seller_contact_name,
            "seller_phone": listing.seller_phone,
            "seller_email": listing.seller_email,
            "off_platform_notice": "The sale closes off-platform.",
        },
    )

    response = auth_client.get(f"/api/v1/listing/car-sales/{listing.id}/contact/")
    assert response.status_code == 200
    contact = response.json()
    for key in [
        "listing_id",
        "request_id",
        "status",
        "seller_contact_name",
        "seller_phone",
        "seller_email",
        "off_platform_notice",
    ]:
        assert key in contact
    assert contact["request_id"] == str(reveal_request.id)


def test_flutter_contract_property_sales_connector(auth_client, user, company):
    address = Address.objects.create(
        street_line1="Bole Road",
        country="Ethiopia",
        city="Addis Ababa",
        sub_city="Bole",
        state="Addis Ababa",
        postal_code="1000",
        latitude="9.010000",
        longitude="38.760000",
    )
    listing = PropertySaleListing.objects.create(
        company=company,
        address=address,
        title="Flutter Sale Property",
        description="Property sale listing for contract test",
        base_price=Decimal("4500000.00"),
        currency="ETB",
        property_type=PropertySaleListing.PropertyTypeChoices.VILLA,
        bedrooms=4,
        bathrooms=3,
        square_meters=Decimal("240.00"),
        land_size_square_meters=Decimal("320.00"),
        is_furnished=True,
        seller_contact_name="Flutter Property Seller",
        seller_phone="0911888777",
        seller_email="flutter-property-seller@example.com",
        reveal_fee=Decimal("150.00"),
        is_active=True,
    )

    response = auth_client.get(f"/api/v1/listing/property-sales/{listing.id}/")
    assert response.status_code == 200
    data = response.json()
    for key in [
        "id",
        "title",
        "description",
        "base_price",
        "currency",
        "address",
        "latitude",
        "longitude",
        "formatted_address",
        "place_id",
        "property_type",
        "bedrooms",
        "bathrooms",
        "square_meters",
        "reveal_fee",
        "reveal_state",
        "is_verified",
        "verified_at",
        "verified_by",
        "verification_note",
    ]:
        assert key in data
    assert "seller_phone" not in data
    assert "seller_email" not in data

    reveal_request = PropertyContactRevealRequest.objects.create(
        listing=listing,
        buyer=user,
        amount=listing.reveal_fee,
        currency=listing.currency,
        status=PropertyContactRevealRequest.RevealStatus.PAID_REVEALED,
        tx_ref="property-contract-contact-1",
        expires_at=timezone.now() + timezone.timedelta(minutes=30),
        unlocked_at=timezone.now(),
        contact_snapshot={
            "seller_contact_name": listing.seller_contact_name,
            "seller_phone": listing.seller_phone,
            "seller_email": listing.seller_email,
            "off_platform_notice": "The sale closes off-platform.",
        },
    )

    response = auth_client.post(f"/api/v1/listing/property-sales/{listing.id}/request-contact/", {}, format="json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["contact_unlocked"] is True
    assert payload["reveal_request"]["id"] == str(reveal_request.id)
    for key in ["seller_contact_name", "seller_phone", "seller_email", "off_platform_notice"]:
        assert key in payload["contact"]


def test_flutter_contract_listing_nearby(api_client, hotel):
    hotel.latitude = Decimal("9.000000")
    hotel.longitude = Decimal("38.000000")
    hotel.formatted_address = "Nearby hotel address"
    hotel.place_id = "nearby-hotel-place"
    hotel.save(update_fields=["latitude", "longitude", "formatted_address", "place_id", "updated_at"])

    response = api_client.get(
        "/api/v1/listing/nearby/",
        {"lat": "9.000000", "lng": "38.000000", "radius_km": "1", "listing_type": "hotel"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    item = data["results"][0]
    for key in ["id", "listing_type", "title", "latitude", "longitude", "formatted_address", "price_preview", "currency", "distance_km"]:
        assert key in item


def test_flutter_contract_listing_map_pins(api_client, hotel):
    hotel.latitude = Decimal("9.000000")
    hotel.longitude = Decimal("38.000000")
    hotel.formatted_address = "Map pin hotel address"
    hotel.place_id = "map-pin-hotel-place"
    hotel.save(update_fields=["latitude", "longitude", "formatted_address", "place_id", "updated_at"])

    response = api_client.get(
        "/api/v1/listing/map-pins/",
        {"lat": "9.000000", "lng": "38.000000", "radius_km": "1", "listing_type": "hotel"},
    )

    assert response.status_code == 200
    pins = response.json()
    assert pins
    pin = pins[0]
    for key in ["id", "listing_type", "latitude", "longitude", "title", "price_preview", "thumbnail_url", "rating"]:
        assert key in pin
    assert "distance_km" not in pin
    assert "formatted_address" not in pin


def test_flutter_contract_listing_feed_proximity(auth_client, user, hotel):
    hotel.latitude = Decimal("9.000000")
    hotel.longitude = Decimal("38.000000")
    hotel.formatted_address = "Feed hotel address"
    hotel.place_id = "feed-hotel-place"
    hotel.save(update_fields=["latitude", "longitude", "formatted_address", "place_id", "updated_at"])

    user.location_permission_granted = True
    user.last_known_lat = Decimal("9.000000")
    user.last_known_lng = Decimal("38.000000")
    user.save(update_fields=["location_permission_granted", "last_known_lat", "last_known_lng", "updated_at"])

    response = auth_client.get("/api/v1/listing/feed/")

    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    assert "distance_km" in data["results"][0]


def test_flutter_contract_discovery_shapes_all_listing_types(
    auth_client,
    api_client,
    user,
    company,
    hotel,
    guest_house,
    car_listing,
    property_listing,
    event_space,
):
    cache.clear()
    car_listing.listing_type = CarListing.ListingTypeChoices.RENT
    car_listing.save(update_fields=["listing_type", "updated_at"])

    car_sale = CarSaleListing.objects.create(
        company=company,
        title="Flutter Car Sale",
        description="Contract car sale listing",
        base_price=Decimal("900000.00"),
        currency="ETB",
        brand=CarListing.CarBrandChoices.TOYOTA,
        model="Yaris",
        year=2020,
        mileage=45000,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        condition=CarListing.ConditionChoices.USED,
        car_class=CarListing.CarClassChoices.NORMAL,
        seats=5,
        seller_contact_name="Car Seller",
        seller_phone="0911777000",
        seller_email="carsale@example.com",
        reveal_fee=Decimal("100.00"),
        is_active=True,
    )
    property_sale = PropertySaleListing.objects.create(
        company=company,
        address=Address.objects.create(
            street_line1="Bole Atlas",
            country="Ethiopia",
            city="Addis Ababa",
            sub_city="Bole",
            state="Addis Ababa",
            postal_code="1000",
        ),
        title="Flutter House Sale",
        description="Contract property sale listing",
        base_price=Decimal("5500000.00"),
        currency="ETB",
        property_type=PropertySaleListing.PropertyTypeChoices.VILLA,
        bedrooms=4,
        bathrooms=3,
        square_meters=Decimal("240.00"),
        land_size_square_meters=Decimal("300.00"),
        is_furnished=True,
        seller_contact_name="Property Seller",
        seller_phone="0911888000",
        seller_email="propertysale@example.com",
        reveal_fee=Decimal("150.00"),
        is_active=True,
    )

    visible_listings = {
        "hotel": _make_discovery_visible(hotel, address="Hotel contract address"),
        "guesthouse": _make_discovery_visible(guest_house, address="Guest house contract address"),
        "car_rental": _make_discovery_visible(car_listing, address="Car rental contract address"),
        "car_sales": _make_discovery_visible(car_sale, address="Car sale contract address"),
        "property_rental": _make_discovery_visible(property_listing, address="House rent contract address"),
        "property_sales": _make_discovery_visible(property_sale, address="House sale contract address"),
        "event_space": _make_discovery_visible(event_space, address="Event space contract address"),
    }

    user.location_permission_granted = True
    user.last_known_lat = Decimal("9.000000")
    user.last_known_lng = Decimal("38.000000")
    user.save(update_fields=["location_permission_granted", "last_known_lat", "last_known_lng", "updated_at"])

    for listing_type, listing in visible_listings.items():
        nearby_response = api_client.get(
            "/api/v1/listing/nearby/",
            {"lat": "9.000000", "lng": "38.000000", "radius_km": "2", "listing_type": listing_type},
        )
        assert nearby_response.status_code == 200
        nearby_payload = nearby_response.json()
        assert nearby_payload["results"]
        nearby_item = next(
            item for item in nearby_payload["results"]
            if item["id"] == str(listing.id) and item["listing_type"] == listing_type
        )
        for key in ["id", "listing_type", "title", "latitude", "longitude", "formatted_address", "price_preview", "currency", "distance_km"]:
            assert key in nearby_item

        pins_response = api_client.get(
            "/api/v1/listing/map-pins/",
            {"lat": "9.000000", "lng": "38.000000", "radius_km": "2", "listing_type": listing_type},
        )
        assert pins_response.status_code == 200
        pins_payload = pins_response.json()
        assert pins_payload
        pin = next(
            item for item in pins_payload
            if item["id"] == str(listing.id) and item["listing_type"] == listing_type
        )
        for key in ["id", "listing_type", "latitude", "longitude", "title", "price_preview", "thumbnail_url", "rating"]:
            assert key in pin

        feed_response = auth_client.get("/api/v1/listing/feed/", {"listing_type": listing_type})
        assert feed_response.status_code == 200
        feed_payload = feed_response.json()
        assert feed_payload["results"]
        feed_item = next(
            item for item in feed_payload["results"]
            if item["id"] == str(listing.id) and item["listing_type"] == listing_type
        )
        for key in ["id", "listing_type", "title", "latitude", "longitude", "formatted_address", "price_preview", "currency", "distance_km"]:
            assert key in feed_item


def test_flutter_contract_listing_search_with_map_context(api_client, property_listing):
    property_listing.title = "Flutter Search Listing"
    property_listing.latitude = Decimal("9.000000")
    property_listing.longitude = Decimal("38.000000")
    property_listing.formatted_address = "Search listing address"
    property_listing.place_id = "flutter-search-place"
    property_listing.save(update_fields=["title", "latitude", "longitude", "formatted_address", "place_id", "updated_at"])

    response = api_client.get(
        "/api/v1/listing/search/",
        {
            "q": "Flutter Search",
            "lat": "9.000000",
            "lng": "38.000000",
            "radius_km": "2",
            "listing_type": "property_rental",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    assert "search_center" in data
    for key in ["id", "listing_type", "title", "latitude", "longitude", "formatted_address", "distance_km"]:
        assert key in data["results"][0]


def test_flutter_contract_listing_search_suggestions(api_client, property_listing):
    property_listing.title = "Suggestion Listing"
    property_listing.latitude = Decimal("9.000000")
    property_listing.longitude = Decimal("38.000000")
    property_listing.formatted_address = "Suggestion listing address"
    property_listing.place_id = "flutter-suggestion-place"
    property_listing.save(update_fields=["title", "latitude", "longitude", "formatted_address", "place_id", "updated_at"])

    response = api_client.get(
        "/api/v1/listing/search/suggestions/",
        {"q": "Suggestion", "listing_type": "property_rental"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload
    for key in ["id", "listing_type", "title", "formatted_address", "price_preview", "distance_km", "latitude", "longitude"]:
        assert key in payload[0]


def test_flutter_contract_maps_autocomplete(auth_client):
    with patch(
        "apps.listing.maps_views.autocomplete_address",
        return_value=[
            {
                "place_id": "place-123",
                "description": "Bole Road, Addis Ababa, Ethiopia",
                "main_text": "Bole Road",
                "secondary_text": "Addis Ababa, Ethiopia",
            }
        ],
    ):
        response = auth_client.get(
            "/api/v1/maps/autocomplete/",
            {"input": "Bole", "session_token": "session-123"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload
    for key in ["place_id", "description", "main_text", "secondary_text"]:
        assert key in payload[0]


def test_flutter_contract_maps_place_detail(auth_client):
    with patch(
        "apps.listing.maps_views.get_place_detail",
        return_value={
            "lat": Decimal("9.012345"),
            "lng": Decimal("38.765432"),
            "formatted_address": "Bole Road, Addis Ababa, Ethiopia",
            "place_id": "place-123",
            "components": {"city": "Addis Ababa", "country": "Ethiopia"},
        },
    ):
        response = auth_client.post(
            "/api/v1/maps/place-detail/",
            {"place_id": "place-123", "session_token": "session-123"},
            format="json",
        )

    assert response.status_code == 200
    payload = response.json()
    for key in ["lat", "lng", "formatted_address", "place_id", "components"]:
        assert key in payload


def test_flutter_contract_property_listing_create_with_place_id(company_client, company):
    with patch(
        "apps.listing.serializers.get_place_detail",
        return_value={
            "lat": Decimal("9.012345"),
            "lng": Decimal("38.765432"),
            "formatted_address": "Bole Road, Addis Ababa, Ethiopia",
            "place_id": "place-123",
            "components": {"city": "Addis Ababa", "country": "Ethiopia"},
        },
    ):
        response = company_client.post(
            "/api/v1/listing/properties/",
            {
                "title": "Flutter Property",
                "description": "Created from Flutter contract test",
                "images": [],
                "base_price": "3000.00",
                "currency": "ETB",
                "company": str(company.id),
                "address": {
                    "street_line1": "Bole Road",
                    "country": "Ethiopia",
                    "city": "Addis Ababa",
                    "sub_city": "Bole",
                    "state": "Addis Ababa",
                    "postal_code": "1000",
                },
                "property_type": PropertyListing.PropertyTypeChoices.APARTMENT,
                "bedrooms": 2,
                "bathrooms": 1,
                "square_meters": 80,
                "is_furnished": True,
                "place_id": "place-123",
                "session_token": "session-123",
            },
            format="json",
        )

    assert response.status_code == 201
    payload = response.json()
    for key in ["id", "latitude", "longitude", "formatted_address", "place_id"]:
        assert key in payload


def test_flutter_contract_account_location(auth_client):
    response = auth_client.post(
        "/api/v1/account/location/",
        {"lat": "9.012345", "lng": "38.765432", "permission_granted": True},
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    for key in ["lat", "lng", "location_updated_at", "location_permission_granted"]:
        assert key in payload


def test_flutter_contract_property_rental_booking(auth_client, property_listing):
    start_date = date.today() + timedelta(days=3)
    end_date = start_date + timedelta(days=2)
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(property_listing),
        object_id=property_listing.id,
        version="1",
        title="Property rental terms",
        content="Property rental terms content",
        effective_date=date.today(),
        is_active=True,
    )
    for offset in range((end_date - start_date).days):
        PropertyRentalAvailability.objects.update_or_create(
            property_listing=property_listing,
            date=start_date + timedelta(days=offset),
            defaults={"available_units": 1, "price": Decimal("3000.00")},
        )

    preview_response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/price-preview/",
        {
            "property_listing": str(property_listing.id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_phone": "0911777001",
        },
        format="json",
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    for key in ["nights", "items", "totals"]:
        assert key in preview

    create_response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        {
            "property_listing": str(property_listing.id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Flutter",
            "guest_last_name": "Rental",
            "guest_email": "flutter-property-rental@example.com",
            "guest_phone": "0911777001",
            "terms_accepted": True,
            "terms_version": "1",
        },
        format="json",
    )
    assert create_response.status_code == 201
    data = create_response.json()
    for key in [
        "id",
        "booking_reference",
        "property_listing",
        "start_date",
        "end_date",
        "total_price",
        "currency",
        "status",
        "terms_accepted",
        "terms_version",
        "terms_content_snapshot",
        "snapshot",
        "created_at",
    ]:
        assert key in data
    assert data["status"] == PropertyRentalBooking.RentStatus.PENDING

    detail_response = auth_client.get(f"/api/v1/listing/property-rentals/bookings/{data['id']}/")
    assert detail_response.status_code == 200


def test_flutter_contract_car_rental_price_preview(api_client, car_listing):
    start_date = date.today() + timedelta(days=3)
    end_date = start_date + timedelta(days=2)
    for offset in range((end_date - start_date).days):
        CarAvailability.objects.update_or_create(
            car_listing=car_listing,
            date=start_date + timedelta(days=offset),
            defaults={"available_units": 1},
        )

    response = api_client.post(
        "/api/v1/listing/car-rentals/price-preview/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "items": [{"car_listing": str(car_listing.id), "units_rent": 1}],
            "guest_phone": "0911777222",
        },
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    for key in ["nights", "items", "totals"]:
        assert key in payload
    assert payload["items"]
    for key in ["id", "title", "units", "price_per_unit", "subtotal", "breakdown"]:
        assert key in payload["items"][0]


def test_flutter_contract_listing_terms(api_client, hotel):
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        version=1,
        title="Hotel Terms",
        content="Hotel terms content",
        effective_date=date.today(),
        is_active=True,
    )
    response = api_client.get("/api/v1/listing/terms/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)


def test_flutter_contract_listing_company_terms(api_client, company):
    terms = TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(company),
        object_id=company.id,
        version=1,
        title="Company Terms",
        content="Company terms content",
        effective_date=date.today(),
        is_active=True,
    )

    response = api_client.get(f"/api/v1/listing/terms/company/{company.id}/")

    assert response.status_code == 200
    data = response.json()
    for key in ["id", "version", "title", "content", "effective_date", "is_active"]:
        assert key in data
    assert data["id"] == str(terms.id)


def test_flutter_contract_payment_verify_public(api_client, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=7),
        check_out_date=date.today() + timedelta(days=9),
        total_price=Decimal("1000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email="guest@example.com",
        guest_phone="0911000000",
        special_requests="None",
        booking_reference="H-000777",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=None,
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("1000.00"))
    payment = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-contract-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    response = api_client.get(f"/api/v1/payment/verify-public/{payment.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert "chapa_verification" in data


def test_flutter_contract_admin_transaction_monitor(admin_client, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=7),
        check_out_date=date.today() + timedelta(days=9),
        total_price=Decimal("1000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email="guest@example.com",
        guest_phone="0911000000",
        special_requests="None",
        booking_reference="H-000778",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=None,
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("1000.00"))
    payment = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-contract-monitor-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        tax_amount=Decimal("15.00"),
        metadata={},
    )

    response = admin_client.get("/api/v1/payment/admin/transactions/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    result = data["results"][0]
    for key in [
        "id",
        "tx_ref",
        "status",
        "amount",
        "tax_amount",
        "grand_total",
        "payout_status",
        "dispute_status",
    ]:
        assert key in result
    assert result["id"] == str(payment.id)


def test_flutter_contract_favorites_list(auth_client, favorite):
    response = auth_client.get("/api/v1/favorites/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "snapshot" in data["results"][0]


def test_flutter_contract_guest_favorites_list(api_client, hotel):
    response = api_client.post(
        "/api/v1/favorites/guest/",
        {
            "guest_phone": "0911223344",
            "content_type": "account.hotelprofile",
            "object_id": str(hotel.id),
        },
        format="json",
    )
    assert response.status_code == 201

    response = api_client.get("/api/v1/favorites/guest/", {"guest_phone": "0911223344"})

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    for key in ["id", "guest_phone", "object_id", "content_type_display", "snapshot", "object", "created_at"]:
        assert key in data["results"][0]


def test_flutter_contract_notifications_list(auth_client, notification):
    response = auth_client.get("/api/v1/notifications/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    item = data["results"][0]
    for key in [
        "id",
        "notification_type",
        "notification_type_display",
        "title",
        "message",
        "action_url",
        "metadata",
        "is_read",
        "read_at",
        "priority",
        "priority_display",
        "created_at",
        "delivered_in_app",
        "delivered_email",
        "delivered_sms",
        "delivered_push",
        "email_sent_at",
        "sms_sent_at",
        "push_sent_at",
    ]:
        assert key in item


def test_flutter_contract_notification_preferences(auth_client, notification_preference):
    response = auth_client.get("/api/v1/notifications/preferences/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    for key in [
        "email_preferences",
        "in_app_preferences",
        "sms_preferences",
        "push_preferences",
        "email_enabled",
        "sms_enabled",
        "push_enabled",
    ]:
        assert key in data["data"]


def test_flutter_contract_analytics_overview(company_client):
    response = company_client.get("/api/v1/analytics/company/overview/")

    assert response.status_code == 200
    data = response.json()
    assert "total_revenue" in data
    assert "total_bookings" in data


def test_flutter_contract_analytics_frontdesk_stats(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["arrivals_today", "departures_today", "in_house_count", "availability_percent", "total_rooms", "occupied_rooms"]:
        assert key in data


def test_flutter_contract_analytics_frontdesk_availability(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/availability/",
        {
            "workspace_id": str(hotel.id),
            "workspace_type": "hotel",
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        for key in ["room_id", "room_name", "total_units", "availability"]:
            assert key in data[0]


def test_flutter_contract_public_promotions(api_client, user, car_listing):
    content_type = ContentType.objects.get_for_model(car_listing)
    campaign = PromotionCampaign.objects.create(
        name="Flutter Promo",
        advertiser=user,
        status=PromotionCampaign.Status.ACTIVE,
        starts_at=timezone.now() - timezone.timedelta(hours=1),
        ends_at=timezone.now() + timezone.timedelta(days=1),
    )
    PromotionPlacement.objects.create(
        campaign=campaign,
        slot_type=PromotionPlacement.SlotType.FEATURED_LISTING,
        content_type=content_type,
        object_id=car_listing.id,
        target_category="cars",
        is_active=True,
    )

    response = api_client.get("/api/v1/promotions/placements/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data
    placement = data[0]
    for key in ["id", "slot_type", "display_order", "promoted_listing", "promoted_category"]:
        assert key in placement
    assert "budget" not in placement
    listing = placement["promoted_listing"]
    for key in ["id", "title", "thumbnail", "category", "rating", "price_preview", "currency", "listing_type"]:
        assert key in listing
