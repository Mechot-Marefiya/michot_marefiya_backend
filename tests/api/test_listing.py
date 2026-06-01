# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from apps.account.models import HotelProfile
from apps.listing.models import (
    AddonOffering,
    CarAvailability,
    CarListing,
    CarRental,
    CarRentalItem,
    EventSpaceListing,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseProfile,
    GuestHouseRoom,
    RoomListing,
    StayAvailability,
    TermsAndConditions,
)

pytestmark = pytest.mark.django_db


def test_get_room_list_public_contract(api_client, room):
    response = api_client.get("/api/v1/listing/rooms/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(room.id)
    assert data["results"][0]["title"] == room.title


def test_get_room_detail_public_contract(api_client, room):
    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(room.id)
    assert data["title"] == room.title
    assert "base_price" in data
    assert "currency" in data


def test_get_room_price_preview_public_contract(api_client, room):
    response = api_client.get(
        f"/api/v1/listing/rooms/{room.id}/price-preview/",
        {"check_in": "2026-06-10", "check_out": "2026-06-12"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "lines" in data
    assert "total" in data
    assert "has_discount" in data
    assert "warning" in data


def test_get_room_price_preview_invalid_payload(api_client, room):
    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/price-preview/")

    assert response.status_code == 400


def test_get_room_availability_matrix_owner_only(company_client, hotel, room):
    StayAvailability.objects.create(hotel=hotel, room=room, date=date.today() + timedelta(days=1), available_rooms=2)

    response = company_client.get(
        "/api/v1/listing/rooms/availability-matrix/",
        {
            "workspace": str(hotel.id),
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_guesthouse_list_public_contract(api_client, guest_house):
    response = api_client.get("/api/v1/listing/guest-houses/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(guest_house.id)


def test_get_guesthouse_detail_public_contract(api_client, guest_house):
    response = api_client.get(f"/api/v1/listing/guest-houses/{guest_house.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(guest_house.id)
    assert data["title"] == guest_house.title
    assert "rooms" in data


def test_get_guesthouse_check_availability_public_contract(api_client, guest_house):
    response = api_client.get(
        "/api/v1/listing/guest-houses/check-availability/",
        {
            "check_in": "2026-06-10",
            "check_out": "2026-06-12",
            "guesthouse_id": str(guest_house.id),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data


def test_get_guesthouse_room_list_public_contract(api_client, guest_house_room):
    response = api_client.get("/api/v1/listing/guest-house-rooms/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(guest_house_room.id)


def test_get_guesthouse_room_detail_public_contract(api_client, guest_house_room):
    response = api_client.get(f"/api/v1/listing/guest-house-rooms/{guest_house_room.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(guest_house_room.id)
    assert data["title"] == guest_house_room.title


def test_get_guesthouse_room_availability_matrix_owner_only(company_client, guest_house, guest_house_room):
    response = company_client.get(
        "/api/v1/listing/guest-house-rooms/availability-matrix/",
        {
            "workspace": str(guest_house.id),
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_car_list_public_contract(api_client, car_listing):
    response = api_client.get("/api/v1/listing/cars/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(car_listing.id)


def test_get_car_detail_public_contract(api_client, car_listing):
    response = api_client.get(f"/api/v1/listing/cars/{car_listing.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(car_listing.id)
    assert data["brand"] == car_listing.brand
    assert data["model"] == car_listing.model


def test_post_car_check_availability_success(api_client, car_listing):
    CarAvailability.objects.create(car_listing=car_listing, date=date(2026, 6, 10), available_units=1)
    CarAvailability.objects.create(car_listing=car_listing, date=date(2026, 6, 11), available_units=1)

    response = api_client.post(
        f"/api/v1/listing/cars/{car_listing.id}/check_availability/",
        {"quantity": 1, "start_date": "2026-06-10", "end_date": "2026-06-12"},
        format="json",
    )

    assert response.status_code == 200
    assert response.content in {b"", b"null"}


def test_get_car_available_for_rent_public_contract(api_client, car_listing):
    CarAvailability.objects.create(car_listing=car_listing, date=date.today() + timedelta(days=1), available_units=1)

    response = api_client.get(
        "/api/v1/listing/cars/available_for_rent/",
        {
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
            "brand": car_listing.brand,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data


def test_get_car_lookup_public_contract(api_client, car_rental):
    response = api_client.get(
        "/api/v1/listing/car-rentals/lookup/",
        {"reference": car_rental.booking_reference, "email": car_rental.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == car_rental.booking_reference


def test_get_eventspace_list_public_contract(api_client, event_space):
    response = api_client.get("/api/v1/listing/event-spaces/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(event_space.id)


def test_get_terms_list_public_contract(api_client, hotel):
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
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["title"] == "Hotel Terms"


def test_get_terms_detail_public_contract(api_client, hotel):
    terms = TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        version=1,
        title="Hotel Terms",
        content="Hotel terms content",
        effective_date=date.today(),
        is_active=True,
    )

    response = api_client.get(f"/api/v1/listing/terms/{terms.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(terms.id)
    assert data["title"] == "Hotel Terms"


def test_get_addons_public_contract(api_client, addon):
    response = api_client.get("/api/v1/listing/addon-offerings/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(addon.id)


def test_get_inventory_grid_owner_only(company_client, hotel):
    response = company_client.get(
        "/api/v1/listing/inventory/grid/",
        {"property_id": str(hotel.id), "property_type": "hotel", "days": 7},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), dict)


def test_get_inventory_grid_invalid_payload(company_client):
    response = company_client.get("/api/v1/listing/inventory/grid/")

    assert response.status_code == 400
