from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, Role
from apps.core.models import Address
from apps.listing.models import EventSpaceBooking, EventSpaceBookingItem, EventSpaceListing


pytestmark = pytest.mark.django_db


def create_address(label: str) -> Address:
    return Address.objects.create(
        street_line1=f"{label} Street",
        city="Addis Ababa",
        sub_city=label,
        country="Ethiopia",
    )


def create_company_user(django_user_model, *, suffix: str, attach_company: bool = True):
    company_role = Role.objects.get_or_create(name="Company", code=RoleCode.COMPANY.value)[0]
    user = django_user_model.objects.create_user(
        email=f"company-{suffix}@example.com",
        password="pass1234",
        phone=f"+2519111{suffix}",
        role=company_role,
    )

    company = None
    if attach_company:
        company = CompanyProfile.objects.create(
            user=user,
            name=f"Company {suffix}",
            phone=f"+2519222{suffix}",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=create_address(f"Company {suffix}"),
            status=CompanyProfile.StatusChoice.APPROVED,
        )
        user.company = company
        user.save(update_fields=["company"])

    client = APIClient()
    client.force_authenticate(user=user)
    return client, user, company


def create_guest_user(django_user_model, *, suffix: str):
    user_role = Role.objects.get_or_create(name="User", code=RoleCode.USER.value)[0]
    return django_user_model.objects.create_user(
        email=f"guest-{suffix}@example.com",
        password="pass1234",
        phone=f"+2519333{suffix}",
        role=user_role,
    )


def create_hotel(company: CompanyProfile, *, label: str) -> HotelProfile:
    return HotelProfile.objects.create(
        company=company,
        name=f"{label} Hotel",
        stars=4,
        address=create_address(f"{label} Hotel"),
        is_active=True,
    )


def create_event_space(hotel: HotelProfile, *, label: str) -> EventSpaceListing:
    return EventSpaceListing.objects.create(
        hotel=hotel,
        address=create_address(f"{label} Event Space"),
        title=f"{label} Hall",
        description=f"{label} hall",
        base_price=Decimal("5000.00"),
        currency="ETB",
        total_units=1,
        number_of_guests=100,
        space_type=EventSpaceListing.SpaceType.CONFERENCE_HALL,
        is_active=True,
    )


def create_booking(*, user, event_space: EventSpaceListing, guest_suffix: str) -> EventSpaceBooking:
    booking = EventSpaceBooking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=1),
        check_out_date=date.today() + timedelta(days=2),
        total_price=Decimal("5250.00"),
        currency="ETB",
        status=EventSpaceBooking.BookingStatus.CONFIRMED,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=f"booking-{guest_suffix}@example.com",
        guest_phone=f"0911{guest_suffix}",
        terms_accepted=True,
        terms_version="1.0",
        terms_content_snapshot="Terms",
    )
    EventSpaceBookingItem.objects.create(
        booking=booking,
        event_space=event_space,
        units_booked=1,
        price_per_unit=Decimal("5000.00"),
    )
    return booking


def test_event_space_host_mode_lists_single_hotel_company_inventory(django_user_model):
    client, _owner, company = create_company_user(django_user_model, suffix="0001")
    guest_user = create_guest_user(django_user_model, suffix="1001")
    hotel = create_hotel(company, label="Solo")
    event_space = create_event_space(hotel, label="Solo")
    booking = create_booking(user=guest_user, event_space=event_space, guest_suffix="7001")

    response = client.get(reverse("bookings-eventspaces-list"), {"mode": "host"})

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert {item["id"] for item in response.data["results"]} == {str(booking.id)}


def test_event_space_host_mode_aggregates_across_all_company_hotels(django_user_model):
    client, _owner, company = create_company_user(django_user_model, suffix="0002")
    guest_user = create_guest_user(django_user_model, suffix="1002")
    first_hotel = create_hotel(company, label="North")
    second_hotel = create_hotel(company, label="South")
    first_booking = create_booking(
        user=guest_user,
        event_space=create_event_space(first_hotel, label="North"),
        guest_suffix="7002",
    )
    second_booking = create_booking(
        user=guest_user,
        event_space=create_event_space(second_hotel, label="South"),
        guest_suffix="7003",
    )

    response = client.get(reverse("bookings-eventspaces-list"), {"mode": "host"})

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2
    assert {item["id"] for item in response.data["results"]} == {
        str(first_booking.id),
        str(second_booking.id),
    }


def test_event_space_host_mode_can_filter_to_explicit_hotel(django_user_model):
    client, _owner, company = create_company_user(django_user_model, suffix="0003")
    guest_user = create_guest_user(django_user_model, suffix="1003")
    first_hotel = create_hotel(company, label="East")
    second_hotel = create_hotel(company, label="West")
    first_booking = create_booking(
        user=guest_user,
        event_space=create_event_space(first_hotel, label="East"),
        guest_suffix="7004",
    )
    create_booking(
        user=guest_user,
        event_space=create_event_space(second_hotel, label="West"),
        guest_suffix="7005",
    )

    response = client.get(
        reverse("bookings-eventspaces-list"),
        {"mode": "host", "hotel_id": str(first_hotel.id)},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(first_booking.id)


def test_event_space_host_mode_rejects_foreign_hotel_filter(django_user_model):
    client, _owner, company = create_company_user(django_user_model, suffix="0004")
    outsider_client, _outsider_owner, outsider_company = create_company_user(
        django_user_model, suffix="0005"
    )
    foreign_hotel = create_hotel(outsider_company, label="Foreign")
    create_booking(
        user=create_guest_user(django_user_model, suffix="1004"),
        event_space=create_event_space(create_hotel(company, label="Local"), label="Local"),
        guest_suffix="7006",
    )

    response = client.get(
        reverse("bookings-eventspaces-list"),
        {"mode": "host", "hotel": str(foreign_hotel.id)},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "selected hotel" in str(response.data["detail"]).lower()

    outsider_response = outsider_client.get(
        reverse("bookings-eventspaces-list"),
        {"mode": "host", "hotel_id": str(foreign_hotel.id)},
    )
    assert outsider_response.status_code == status.HTTP_200_OK


def test_event_space_booking_detail_cannot_escape_company_inventory(django_user_model):
    client, _owner, company = create_company_user(django_user_model, suffix="0006")
    outsider_client, _outsider_owner, outsider_company = create_company_user(
        django_user_model, suffix="0007"
    )
    guest_user = create_guest_user(django_user_model, suffix="1005")

    owned_booking = create_booking(
        user=guest_user,
        event_space=create_event_space(create_hotel(company, label="Owned"), label="Owned"),
        guest_suffix="7007",
    )
    foreign_booking = create_booking(
        user=guest_user,
        event_space=create_event_space(create_hotel(outsider_company, label="Foreign"), label="Foreign"),
        guest_suffix="7008",
    )

    owned_response = client.get(reverse("bookings-eventspaces-detail", args=[owned_booking.id]))
    assert owned_response.status_code == status.HTTP_200_OK

    foreign_response = client.get(reverse("bookings-eventspaces-detail", args=[foreign_booking.id]))
    assert foreign_response.status_code == status.HTTP_404_NOT_FOUND

    outsider_foreign_response = outsider_client.get(
        reverse("bookings-eventspaces-detail", args=[foreign_booking.id])
    )
    assert outsider_foreign_response.status_code == status.HTTP_200_OK


def test_event_space_host_mode_without_company_scope_returns_400(django_user_model):
    client, _owner, _company = create_company_user(
        django_user_model, suffix="0008", attach_company=False
    )

    response = client.get(reverse("bookings-eventspaces-list"), {"mode": "host"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "host scope" in str(response.data["detail"]).lower()
