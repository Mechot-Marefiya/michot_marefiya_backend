import json
from uuid import uuid4

# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01
import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from apps.account.models import HotelProfile
from apps.core.models import CurrencyRate
from apps.listing.models import (
    AddonOffering,
    Booking,
    BookingItem,
    CarAvailability,
    CarListing,
    CarRental,
    CarRentalItem,
    EventSpaceAvailability,
    EventSpaceListing,
    EventSpaceBooking,
    EventSpaceBookingItem,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseInventory,
    GuestHouseProfile,
    GuestHouseRoom,
    RoomListing,
    Season,
    SeasonalRate,
    StayAvailability,
    TermsAndConditions,
)
from apps.account.models import User

pytestmark = pytest.mark.django_db


def _listing_address_payload():
    return {
        "street_line1": "Wollo Sefer",
        "country": "Ethiopia",
        "city": "Addis Ababa",
        "sub_city": "Bole",
        "state": "Addis Ababa",
        "postal_code": "1000",
        "latitude": "9.012345",
        "longitude": "38.765432",
    }


def _create_stay_availability(room, start_date, end_date, available_rooms=None):
    available_rooms = available_rooms or room.total_units
    for offset in range((end_date - start_date).days):
        StayAvailability.objects.create(
            hotel=room.hotel,
            room=room,
            date=start_date + timedelta(days=offset),
            available_rooms=available_rooms,
        )


def _create_car_availability(car_listing, start_date, end_date, available_units=None):
    available_units = available_units or car_listing.quantity
    for offset in range((end_date - start_date).days):
        CarAvailability.objects.create(
            car_listing=car_listing,
            date=start_date + timedelta(days=offset),
            available_units=available_units,
        )


def _create_guesthouse_inventory(room, start_date, end_date, available_rooms=None):
    available_rooms = available_rooms or room.total_units
    for offset in range((end_date - start_date).days):
        GuestHouseInventory.objects.create(
            guest_house_room=room,
            date=start_date + timedelta(days=offset),
            available_rooms=available_rooms,
            price=room.base_price,
        )


def _create_eventspace_availability(space, start_date, end_date, available_units=None):
    available_units = available_units or space.total_units
    for offset in range((end_date - start_date).days):
        EventSpaceAvailability.objects.create(
            space_listing=space,
            date=start_date + timedelta(days=offset),
            available_eventspace=available_units,
            price=space.base_price,
        )


def _create_terms(content_object, version="1"):
    return TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(content_object),
        object_id=content_object.id,
        version=version,
        title=f"{content_object.__class__.__name__} Terms",
        content="Terms content",
        effective_date=date.today(),
        is_active=True,
    )


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


def test_get_room_detail_includes_conversion_when_display_currency_requested(api_client, room):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("100.000000"), date=date.today())

    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/", {"display_currency": "USD"})

    assert response.status_code == 200
    data = response.json()
    assert data["conversion"]["from"] == room.currency
    assert data["conversion"]["to"] == "USD"
    assert "rate" in data["conversion"]
    assert "total" in data["conversion"]
    assert "calculated_at" in data["conversion"]


def test_get_room_list_includes_conversion_when_display_currency_requested(api_client, room):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("100.000000"), date=date.today())

    response = api_client.get("/api/v1/listing/rooms/", {"display_currency": "USD"})

    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["id"] == str(room.id)
    assert data["results"][0]["conversion"]["from"] == room.currency
    assert data["results"][0]["conversion"]["to"] == "USD"


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
    matrix_date = date(2026, 6, 10)
    StayAvailability.objects.create(hotel=hotel, room=room, date=matrix_date, available_rooms=2)

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
    assert data[0]["room_id"] == str(room.id)
    assert data[0]["availability"][0]["date"] == matrix_date.isoformat()
    assert data[0]["availability"][0]["available"] == 2
    assert data[0]["availability"][0]["status"] == "partial"


def test_get_room_availability_matrix_invalid_payload(company_client):
    response = company_client.get(
        "/api/v1/listing/rooms/availability-matrix/",
        {"workspace": str(uuid4()), "start_date": "bad-date", "end_date": "2026-06-12"},
    )

    assert response.status_code == 400


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


def test_post_guesthouse_create_unauthenticated(api_client, image_file, company):
    response = api_client.post(
        "/api/v1/listing/guest-houses/",
        {
            "title": "Guest House Draft",
            "description": "Draft guest house",
            "company": str(company.id),
            "address": json.dumps(_listing_address_payload()),
            "amenities": json.dumps([]),
            "images": [image_file],
        },
        format="multipart",
    )

    assert response.status_code == 401


def test_post_guesthouse_create_success(company_client, company, image_file):
    response = company_client.post(
        "/api/v1/listing/guest-houses/",
        {
            "title": "Guest House Draft",
            "description": "Draft guest house",
            "company": str(company.id),
            "address": json.dumps(_listing_address_payload()),
            "amenities": json.dumps([]),
            "images": [image_file],
        },
        format="multipart",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Guest House Draft"


def test_patch_guesthouse_success(company_client, guest_house):
    response = company_client.patch(
        f"/api/v1/listing/guest-houses/{guest_house.id}/",
        {"title": "Updated Guest House"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Guest House"


def test_patch_guesthouse_forbidden_for_non_owner(auth_client, guest_house):
    response = auth_client.patch(
        f"/api/v1/listing/guest-houses/{guest_house.id}/",
        {"title": "Updated Guest House"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_guesthouse_success(company_client, guest_house):
    response = company_client.delete(f"/api/v1/listing/guest-houses/{guest_house.id}/")

    assert response.status_code == 204


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


def test_post_guesthouse_room_create_unauthenticated(api_client, guest_house):
    response = api_client.post(
        "/api/v1/listing/guest-house-rooms/",
        {
            "guest_house_id": str(guest_house.id),
            "title": "Room Draft",
            "base_price": "900.00",
            "currency": "ETB",
            "number_of_guests": 2,
            "total_units": 2,
            "bed_type": "twin",
            "room_size_sqm": 18,
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_guesthouse_room_create_success(company_client, guest_house):
    response = company_client.post(
        "/api/v1/listing/guest-house-rooms/",
        {
            "guest_house_id": str(guest_house.id),
            "title": "Room Draft",
            "base_price": "900.00",
            "currency": "ETB",
            "number_of_guests": 2,
            "total_units": 2,
            "bed_type": "twin",
            "room_size_sqm": 18,
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Room Draft"


def test_patch_guesthouse_room_success(company_client, guest_house_room):
    response = company_client.patch(
        f"/api/v1/listing/guest-house-rooms/{guest_house_room.id}/",
        {"title": "Updated Guest House Room"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Guest House Room"


def test_delete_guesthouse_room_success(company_client, guest_house_room):
    response = company_client.delete(f"/api/v1/listing/guest-house-rooms/{guest_house_room.id}/")

    assert response.status_code == 204


def test_get_guesthouse_room_availability_matrix_owner_only(company_client, guest_house, guest_house_room):
    matrix_date = date(2026, 6, 10)
    GuestHouseInventory.objects.create(
        guest_house_room=guest_house_room,
        date=matrix_date,
        available_rooms=1,
        price=guest_house_room.base_price,
    )

    response = company_client.get(
        "/api/v1/listing/guest-house-rooms/availability-matrix/",
        {
            "workspace": str(guest_house.id),
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["room_id"] == str(guest_house_room.id)
    assert data[0]["availability"][0]["date"] == matrix_date.isoformat()
    assert data[0]["availability"][0]["available"] == 1
    assert data[0]["availability"][0]["status"] == "partial"


def test_get_guesthouse_room_availability_matrix_missing_payload(company_client):
    response = company_client.get("/api/v1/listing/guest-house-rooms/availability-matrix/")

    assert response.status_code == 400


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


def test_patch_car_listing_success(company_client, car_listing):
    response = company_client.patch(
        f"/api/v1/listing/cars/{car_listing.id}/",
        {"title": "Updated Car Title"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Car Title"


def test_patch_car_listing_forbidden_for_non_owner(auth_client, car_listing):
    response = auth_client.patch(
        f"/api/v1/listing/cars/{car_listing.id}/",
        {"title": "Updated Car Title"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_car_listing_success(company_client, car_listing):
    response = company_client.delete(f"/api/v1/listing/cars/{car_listing.id}/")

    assert response.status_code == 204


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


def test_get_room_booking_lookup_public_contract(api_client, booking):
    response = api_client.get(
        "/api/v1/listing/bookings/lookup/",
        {"reference": booking.booking_reference, "email": booking.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == booking.booking_reference


def test_get_room_booking_lookup_invalid_payload(api_client):
    response = api_client.get("/api/v1/listing/bookings/lookup/")

    assert response.status_code == 400


def test_room_booking_partial_cancel_success(api_client, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=2),
        check_out_date=date.today() + timedelta(days=4),
        total_price=Decimal("4000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000111",
        special_requests="No peanuts",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    booking_item = BookingItem.objects.create(
        booking=booking,
        room=room,
        units_booked=2,
        price_per_unit=Decimal("1000.00"),
    )
    _create_stay_availability(room, booking.check_in_date, booking.check_out_date)

    api_client.force_authenticate(user=user)
    response = api_client.post(
        f"/api/v1/listing/bookings/{booking.id}/partial-cancel/",
        {"item_id": str(booking_item.id), "units_to_cancel": 1},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    booking_item.refresh_from_db()
    assert booking.status == Booking.BookingStatus.PENDING
    assert booking_item.units_booked == 1


def test_room_booking_workspace_bookings_success(front_desk_client, front_desk_user, room):
    booking = Booking.objects.create(
        user=front_desk_user,
        check_in_date=date.today() + timedelta(days=2),
        check_out_date=date.today() + timedelta(days=4),
        total_price=Decimal("2000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Front",
        guest_last_name="Desk",
        guest_email=front_desk_user.email,
        guest_phone="0911000112",
        special_requests="Window seat",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    BookingItem.objects.create(
        booking=booking,
        room=room,
        units_booked=1,
        price_per_unit=Decimal("1000.00"),
    )
    _create_stay_availability(room, booking.check_in_date, booking.check_out_date)

    response = front_desk_client.get("/api/v1/listing/bookings/workspace-bookings/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["booking_reference"] == booking.booking_reference


def test_room_booking_patch_not_allowed(api_client, booking):
    api_client.force_authenticate(user=booking.user)
    response = api_client.patch(
        f"/api/v1/listing/bookings/{booking.id}/",
        {"status": Booking.BookingStatus.CANCELLED},
        format="json",
    )

    assert response.status_code == 405


def test_room_booking_delete_not_allowed(api_client, booking):
    api_client.force_authenticate(user=booking.user)
    response = api_client.delete(f"/api/v1/listing/bookings/{booking.id}/")

    assert response.status_code == 405


def test_room_walk_in_booking_success(front_desk_client, room):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=2)

    response = front_desk_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Walk",
            "guest_last_name": "In",
            "guest_email": "walkin-hotel@example.com",
            "guest_phone": "0911000222",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == Booking.BookingStatus.WALK_IN
    assert data["booking_reference"]

    availability = StayAvailability.objects.get(room=room, date=check_in)
    assert availability.available_rooms == 1


def test_room_walk_in_booking_forbidden_for_non_staff(auth_client, room):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=2)

    response = auth_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Denied",
            "guest_last_name": "Guest",
            "guest_email": "denied-hotel@example.com",
            "guest_phone": "0911000333",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 403


def test_room_walk_in_booking_invalid_payload(front_desk_client, room):
    check_in = date.today() + timedelta(days=5)
    _create_terms(room.hotel)

    response = front_desk_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_in.isoformat(),
            "guest_first_name": "Invalid",
            "guest_last_name": "Range",
            "guest_email": "invalid-hotel@example.com",
            "guest_phone": "0911000444",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "check_out_date" in response.json()


def test_room_walk_in_booking_inventory_conflict(front_desk_client, room):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=1)

    response = front_desk_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Inventory",
            "guest_last_name": "Conflict",
            "guest_email": "inventory-hotel@example.com",
            "guest_phone": "0911000555",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 2}],
        },
        format="json",
    )

    assert response.status_code == 409


def test_get_guesthouse_booking_lookup_public_contract(api_client, guesthouse_booking):
    response = api_client.get(
        "/api/v1/listing/guesthouse-bookings/lookup/",
        {"reference": guesthouse_booking.booking_reference, "email": guesthouse_booking.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == guesthouse_booking.booking_reference


def test_guesthouse_booking_workspace_bookings_success(api_client, guest_house, guest_house_room, django_user_model):
    workspace_user = django_user_model.objects.create_user(
        email="guesthouse-workspace@example.com",
        password="password123",
        first_name="Guesthouse",
        last_name="Workspace",
    )
    workspace_user.workspace = guest_house
    workspace_user.save()

    booking = GuestHouseBooking.objects.create(
        renter=workspace_user,
        start_date=date.today() + timedelta(days=3),
        end_date=date.today() + timedelta(days=5),
        total_price=Decimal("1600.00"),
        currency="ETB",
        status=GuestHouseBooking.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=workspace_user.email,
        guest_phone="0911000114",
        special_requests="Late check-in",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    GuestHouseBookingItem.objects.create(
        booking=booking,
        room=guest_house_room,
        units_booked=2,
        price_per_unit=Decimal("800.00"),
    )

    api_client.force_authenticate(user=workspace_user)
    response = api_client.get("/api/v1/listing/guesthouse-bookings/workspace-bookings/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1


def test_guesthouse_walk_in_booking_success(company_client, guest_house_room):
    start_date = date.today() + timedelta(days=6)
    end_date = start_date + timedelta(days=2)
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=2)

    response = company_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Guest",
            "guest_last_name": "House",
            "guest_email": "walkin-guesthouse@example.com",
            "guest_phone": "0911000666",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == GuestHouseBooking.RentStatus.WALK_IN
    assert data["booking_reference"]

    inventory = GuestHouseInventory.objects.get(guest_house_room=guest_house_room, date=start_date)
    assert inventory.available_rooms == 1


def test_guesthouse_walk_in_booking_forbidden_for_non_staff(auth_client, guest_house_room):
    start_date = date.today() + timedelta(days=6)
    end_date = start_date + timedelta(days=2)
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=2)

    response = auth_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Denied",
            "guest_last_name": "Guesthouse",
            "guest_email": "denied-guesthouse@example.com",
            "guest_phone": "0911000777",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 403


def test_guesthouse_walk_in_booking_invalid_payload(company_client, guest_house_room):
    start_date = date.today() + timedelta(days=6)
    _create_terms(guest_house_room.guest_house)

    response = company_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": start_date.isoformat(),
            "guest_first_name": "Invalid",
            "guest_last_name": "Guesthouse",
            "guest_email": "invalid-guesthouse@example.com",
            "guest_phone": "0911000888",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400


def test_guesthouse_walk_in_booking_inventory_conflict(company_client, guest_house_room):
    start_date = date.today() + timedelta(days=6)
    end_date = start_date + timedelta(days=2)
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=1)

    response = company_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Inventory",
            "guest_last_name": "Guesthouse",
            "guest_email": "inventory-guesthouse@example.com",
            "guest_phone": "0911000999",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 2}],
        },
        format="json",
    )

    assert response.status_code == 409


def test_get_eventspace_booking_lookup_public_contract(api_client, eventspace_booking):
    response = api_client.get(
        "/api/v1/listing/bookings-eventspaces/lookup/",
        {"reference": eventspace_booking.booking_reference, "email": eventspace_booking.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == eventspace_booking.booking_reference


def test_car_rentals_my_rentals_success(api_client, user, car_listing):
    rental = CarRental.objects.create(
        renter=user,
        start_date=date.today() + timedelta(days=4),
        end_date=date.today() + timedelta(days=6),
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000112",
        special_requests="Need driver",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )

    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1/listing/car-rentals/my_rentals/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["booking_reference"] == rental.booking_reference


def test_car_rental_confirm_and_cancel_success(api_client, user, car_listing):
    rental = CarRental.objects.create(
        renter=user,
        start_date=date.today() + timedelta(days=4),
        end_date=date.today() + timedelta(days=6),
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000112",
        special_requests="Need driver",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )
    _create_car_availability(car_listing, rental.start_date, rental.end_date)

    api_client.force_authenticate(user=user)
    confirm_response = api_client.post(f"/api/v1/listing/car-rentals/{rental.id}/confirm/")
    assert confirm_response.status_code == 200

    rental.refresh_from_db()
    assert rental.status == CarRental.RentStatus.CONFIRMED

    cancel_response = api_client.post(f"/api/v1/listing/car-rentals/{rental.id}/cancel/")
    assert cancel_response.status_code == 200

    rental.refresh_from_db()
    assert rental.status == CarRental.RentStatus.CANCELLED


def test_get_eventspace_list_public_contract(api_client, event_space):
    response = api_client.get("/api/v1/listing/event-spaces/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(event_space.id)


def test_get_eventspace_detail_public_contract(api_client, event_space):
    response = api_client.get(f"/api/v1/listing/event-spaces/{event_space.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(event_space.id)
    assert data["title"] == event_space.title
    assert "base_price" in data


def test_post_eventspace_create_unauthenticated(api_client, hotel):
    response = api_client.post(
        "/api/v1/listing/event-spaces/",
        {
            "title": "Event Space Draft",
            "company_id": str(hotel.company.id),
            "description": "Event space draft",
            "base_price": "5000.00",
            "currency": "ETB",
            "number_of_guests": 100,
            "total_units": 1,
            "space_type": "conference_hall",
            "floor_area_sqm": 120,
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_eventspace_create_success(company_client, hotel):
    response = company_client.post(
        "/api/v1/listing/event-spaces/",
        {
            "title": "Event Space Draft",
            "company_id": str(hotel.company.id),
            "description": "Event space draft",
            "base_price": "5000.00",
            "currency": "ETB",
            "number_of_guests": 100,
            "total_units": 1,
            "space_type": "conference_hall",
            "floor_area_sqm": 120,
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Event Space Draft"


def test_patch_eventspace_success(company_client, event_space):
    response = company_client.patch(
        f"/api/v1/listing/event-spaces/{event_space.id}/",
        {"title": "Updated Event Space"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Event Space"


def test_patch_eventspace_forbidden_for_non_owner(auth_client, event_space):
    response = auth_client.patch(
        f"/api/v1/listing/event-spaces/{event_space.id}/",
        {"title": "Updated Event Space"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_eventspace_success(company_client, event_space):
    response = company_client.delete(f"/api/v1/listing/event-spaces/{event_space.id}/")

    assert response.status_code == 204


def test_eventspace_walk_in_booking_success(front_desk_client, event_space):
    check_in = date.today() + timedelta(days=7)
    check_out = check_in + timedelta(days=1)
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)

    response = front_desk_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Event",
            "guest_last_name": "Walkin",
            "guest_email": "walkin-eventspace@example.com",
            "guest_phone": "0911001111",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == EventSpaceBooking.BookingStatus.WALK_IN
    assert data["booking_reference"]

    availability = EventSpaceAvailability.objects.get(space_listing=event_space, date=check_in)
    assert availability.available_eventspace == 0


def test_eventspace_walk_in_booking_forbidden_for_non_staff(auth_client, event_space):
    check_in = date.today() + timedelta(days=7)
    check_out = check_in + timedelta(days=1)
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)

    response = auth_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Denied",
            "guest_last_name": "Event",
            "guest_email": "denied-eventspace@example.com",
            "guest_phone": "0911001222",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 403


def test_eventspace_walk_in_booking_invalid_payload(front_desk_client, event_space):
    check_in = date.today() + timedelta(days=7)
    _create_terms(event_space.hotel)

    response = front_desk_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_in.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Invalid",
            "guest_last_name": "Event",
            "guest_email": "invalid-eventspace@example.com",
            "guest_phone": "0911001333",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "check_out_date" in response.json()


def test_eventspace_walk_in_booking_inventory_conflict(front_desk_client, event_space):
    check_in = date.today() + timedelta(days=7)
    check_out = check_in + timedelta(days=1)
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)

    response = front_desk_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Inventory",
            "guest_last_name": "Event",
            "guest_email": "inventory-eventspace@example.com",
            "guest_phone": "0911001444",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 2}],
        },
        format="json",
    )

    assert response.status_code == 409


def test_get_property_list_public_contract(api_client, property_listing):
    response = api_client.get("/api/v1/listing/properties/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(property_listing.id)


def test_get_property_detail_public_contract(api_client, property_listing):
    response = api_client.get(f"/api/v1/listing/properties/{property_listing.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(property_listing.id)
    assert data["title"] == property_listing.title
    assert "property_type" in data


def test_patch_property_success(company_client, property_listing):
    response = company_client.patch(
        f"/api/v1/listing/properties/{property_listing.id}/",
        {"title": "Updated Property"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Property"


def test_patch_property_forbidden_for_non_owner(auth_client, property_listing):
    response = auth_client.patch(
        f"/api/v1/listing/properties/{property_listing.id}/",
        {"title": "Updated Property"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_property_success(company_client, property_listing):
    response = company_client.delete(f"/api/v1/listing/properties/{property_listing.id}/")

    assert response.status_code == 204


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


def test_get_terms_company_public_contract(api_client, company):
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
    assert data["id"] == str(terms.id)
    assert data["title"] == "Company Terms"


def test_get_terms_company_not_found(api_client, company):
    response = api_client.get(f"/api/v1/listing/terms/company/{company.id}/")

    assert response.status_code == 404
    assert "No terms and conditions available for this company." in response.json()["detail"]


def test_get_terms_hotel_not_found(api_client, hotel):
    response = api_client.get(f"/api/v1/listing/terms/hotel/{hotel.id}/")

    assert response.status_code == 404
    assert "No terms and conditions available for this hotel." in response.json()["detail"]


def test_get_terms_guesthouse_not_found(api_client, guest_house):
    response = api_client.get(f"/api/v1/listing/terms/guesthouse/{guest_house.id}/")

    assert response.status_code == 404
    assert "No terms and conditions available for this guest house." in response.json()["detail"]


def test_get_addons_public_contract(api_client, addon):
    response = api_client.get("/api/v1/listing/addon-offerings/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(addon.id)


def test_get_addon_detail_public_contract(api_client, addon):
    response = api_client.get(f"/api/v1/listing/addon-offerings/{addon.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(addon.id)
    assert data["name"] == addon.name
    assert "price_per_unit" in data


def test_post_addon_create_unauthenticated(api_client, hotel):
    response = api_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Breakfast Tray",
            "description": "Breakfast service",
            "category": "meal",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_addon_create_success(company_client, hotel):
    response = company_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Breakfast Tray",
            "description": "Breakfast service",
            "category": "meal",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Breakfast Tray"
    assert data["hotel"] == str(hotel.id)


def test_post_addon_create_forbidden_for_other_owner(auth_client, hotel):
    response = auth_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Breakfast Tray",
            "description": "Breakfast service",
            "category": "meal",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 403


def test_post_addon_create_invalid_payload(company_client, hotel):
    response = company_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Inventory Addon",
            "description": "Tracked inventory service",
            "category": "service",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "requires_inventory": True,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "daily_capacity" in response.json()


def test_patch_addon_success(company_client, addon, hotel):
    addon.hotel = hotel
    addon.save(update_fields=["hotel"])

    response = company_client.patch(
        f"/api/v1/listing/addon-offerings/{addon.id}/",
        {"price_per_unit": "300.00", "description": "Updated description"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["price_per_unit"] == "300.00"
    assert data["description"] == "Updated description"


def test_patch_addon_forbidden_for_non_owner(auth_client, addon):
    response = auth_client.patch(
        f"/api/v1/listing/addon-offerings/{addon.id}/",
        {"price_per_unit": "300.00"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_addon_success(company_client, addon, hotel):
    addon.hotel = hotel
    addon.save(update_fields=["hotel"])

    response = company_client.delete(f"/api/v1/listing/addon-offerings/{addon.id}/")

    assert response.status_code == 204


def test_get_addon_not_found(api_client):
    response = api_client.get(f"/api/v1/listing/addon-offerings/{uuid4()}/")

    assert response.status_code == 404


def test_get_season_list_owner_contract(company_client, season):
    response = company_client.get("/api/v1/listing/seasons/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(season.id)


def test_get_season_detail_owner_contract(company_client, season):
    response = company_client.get(f"/api/v1/listing/seasons/{season.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(season.id)
    assert data["name"] == season.name


def test_post_season_create_unauthenticated(api_client):
    response = api_client.post(
        "/api/v1/listing/seasons/",
        {
            "name": "Holiday Window",
            "start_date": "2026-12-20",
            "end_date": "2026-12-27",
            "recurring": False,
            "active": True,
            "notes": "Peak dates",
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_season_create_success(company_client, company):
    response = company_client.post(
        "/api/v1/listing/seasons/",
        {
            "name": "Holiday Window",
            "start_date": "2026-12-20",
            "end_date": "2026-12-27",
            "recurring": False,
            "active": True,
            "notes": "Peak dates",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Holiday Window"
    assert data["company"] == str(company.id)


def test_post_season_invalid_dates(company_client):
    response = company_client.post(
        "/api/v1/listing/seasons/",
        {
            "name": "Broken Window",
            "start_date": "2026-12-27",
            "end_date": "2026-12-20",
            "recurring": False,
            "active": True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "end_date" in response.json()


def test_patch_season_success(company_client, season):
    response = company_client.patch(
        f"/api/v1/listing/seasons/{season.id}/",
        {"notes": "Updated seasonal notes"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["notes"] == "Updated seasonal notes"


def test_patch_season_non_owner_hidden(auth_client, season):
    response = auth_client.patch(
        f"/api/v1/listing/seasons/{season.id}/",
        {"notes": "Should not work"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_season_success(company_client, season):
    response = company_client.delete(f"/api/v1/listing/seasons/{season.id}/")

    assert response.status_code == 204


def test_get_season_not_found(company_client):
    response = company_client.get(f"/api/v1/listing/seasons/{uuid4()}/")

    assert response.status_code == 404


def test_get_seasonal_rate_list_owner_contract(company_client, seasonal_rate):
    response = company_client.get("/api/v1/listing/seasonal-rates/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(seasonal_rate.id)


def test_get_seasonal_rate_detail_owner_contract(company_client, seasonal_rate):
    response = company_client.get(f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(seasonal_rate.id)
    assert data["season"] == str(seasonal_rate.season.id)


def test_post_seasonal_rate_create_unauthenticated(api_client, season, room):
    response = api_client.post(
        "/api/v1/listing/seasonal-rates/",
        {
            "season": str(season.id),
            "room": str(room.id),
            "price_override": "1500.00",
            "priority": 3,
            "active": True,
            "days_of_week": [],
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_seasonal_rate_create_success(company_client, season, room, company):
    response = company_client.post(
        "/api/v1/listing/seasonal-rates/",
        {
            "season": str(season.id),
            "room": str(room.id),
            "price_override": "1500.00",
            "priority": 3,
            "active": True,
            "days_of_week": [],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["season"] == str(season.id)
    assert data["room"] == str(room.id)
    assert data["hotel"] == str(room.hotel.id)
    assert data["company"] == str(company.id)


def test_post_seasonal_rate_invalid_payload(company_client, season, room):
    response = company_client.post(
        "/api/v1/listing/seasonal-rates/",
        {
            "season": str(season.id),
            "room": str(room.id),
            "priority": 3,
            "active": True,
            "days_of_week": [],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "Either a Multiplier or a Price Override must be set." in str(response.json())


def test_patch_seasonal_rate_success(company_client, seasonal_rate):
    response = company_client.patch(
        f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/",
        {"priority": 9, "active": False},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["priority"] == 9
    assert data["active"] is False


def test_patch_seasonal_rate_non_owner_hidden(auth_client, seasonal_rate):
    response = auth_client.patch(
        f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/",
        {"priority": 9},
        format="json",
    )

    assert response.status_code == 403


def test_delete_seasonal_rate_success(company_client, seasonal_rate):
    response = company_client.delete(f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/")

    assert response.status_code == 204


def test_get_seasonal_rate_not_found(company_client):
    response = company_client.get(f"/api/v1/listing/seasonal-rates/{uuid4()}/")

    assert response.status_code == 404


def test_put_stay_availability_update_success(company_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = company_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["available_rooms"] == 0
    availability.refresh_from_db()
    assert availability.available_rooms == 0


def test_put_stay_availability_update_unauthenticated(api_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = api_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 401


def test_put_stay_availability_update_forbidden(auth_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = auth_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 403


def test_put_stay_availability_update_invalid_payload(company_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = company_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": -1},
        format="json",
    )

    assert response.status_code == 400


def test_put_stay_availability_update_not_found(company_client):
    response = company_client.put(
        f"/api/v1/listing/stays/availability/{uuid4()}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 404


def test_patch_car_availability_update_success(company_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 200
    availability.refresh_from_db()
    assert availability.available_units == 0


def test_patch_car_availability_update_accepts_available_units(company_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"available_units": 2},
        format="json",
    )

    assert response.status_code == 200
    availability.refresh_from_db()
    assert availability.available_units == 2


def test_patch_car_availability_update_unauthenticated(api_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = api_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 401


def test_patch_car_availability_update_forbidden(auth_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = auth_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 403


def test_patch_car_availability_update_invalid_payload(company_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": -1},
        format="json",
    )

    assert response.status_code == 400


def test_patch_car_availability_update_not_found(company_client):
    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{uuid4()}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 404


def test_get_inventory_grid_owner_only(company_client, hotel):
    response = company_client.get(
        "/api/v1/listing/inventory/grid/",
        {"property_id": str(hotel.id), "property_type": "hotel", "days": 7},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["property_id"] == str(hotel.id)
    assert data["property_type"] == "hotel"
    assert "units" in data


def test_get_inventory_grid_unauthenticated(api_client, hotel):
    response = api_client.get(
        "/api/v1/listing/inventory/grid/",
        {"property_id": str(hotel.id), "property_type": "hotel", "days": 7},
    )

    assert response.status_code == 401


def test_get_inventory_grid_forbidden(auth_client, hotel):
    response = auth_client.get(
        "/api/v1/listing/inventory/grid/",
        {"property_id": str(hotel.id), "property_type": "hotel", "days": 7},
    )

    assert response.status_code == 403


def test_get_inventory_grid_invalid_payload(company_client):
    response = company_client.get("/api/v1/listing/inventory/grid/")

    assert response.status_code == 400
