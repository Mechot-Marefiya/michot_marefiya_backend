from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.account.enums import RoleCode
from apps.account.models import IndividualOwnerProfile, Role, User
from apps.core.models import Address
from apps.listing.models import (
    CarListing,
    CarRental,
    CarRentalItem,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseProfile,
    GuestHouseRoom,
)
from apps.payment.models import PaymentTransaction


pytestmark = pytest.mark.django_db


def create_address(street_line1):
    return Address.objects.create(
        street_line1=street_line1,
        city="Addis Ababa",
        country="Ethiopia",
    )


def create_role(code):
    return Role.objects.get_or_create(name=code.replace("_", " ").title(), code=code)[0]


def create_owner_login(*, email="owner@example.com", phone="+251911111111", role_code=RoleCode.USER.value):
    role = create_role(role_code)
    owner = IndividualOwnerProfile.objects.create(
        first_name="Owner",
        last_name="Person",
        phone=phone,
        address=create_address(f"{email} address"),
    )
    user = User.objects.create_user(
        email=email,
        password="pass1234",
        phone=phone,
        role=role,
        first_name="Owner",
        last_name="Person",
    )
    user.individual_owner = owner
    user.save(update_fields=["individual_owner"])
    return user, owner


def create_authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def create_guesthouse_for_owner(owner, *, title="Owner Guest House"):
    return GuestHouseProfile.objects.create(
        individual_owner=owner,
        title=title,
        base_price=Decimal("1500.00"),
        currency="ETB",
        address=create_address(f"{title} address"),
        phone="+251922222222",
        is_active=True,
    )


def create_room(guest_house, *, title="Room 1"):
    return GuestHouseRoom.objects.create(
        guest_house=guest_house,
        title=title,
        base_price=Decimal("750.00"),
        total_units=3,
        bed_type=GuestHouseRoom.BedType.DOUBLE,
    )


def create_rental_car(owner, *, model="Corolla"):
    return CarListing.objects.create(
        title=f"Toyota {model}",
        individual_owner=owner,
        brand=CarListing.CarBrandChoices.TOYOTA,
        model=model,
        year=2024,
        mileage=1200,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        base_price=Decimal("2500.00"),
        currency="ETB",
        listing_type=CarListing.ListingTypeChoices.RENT,
        rental_mode=CarListing.RentalModeChoices.WITH_DRIVER,
        car_class=CarListing.CarClassChoices.NORMAL,
        condition=CarListing.ConditionChoices.NEW,
        quantity=2,
        seats=5,
        is_active=True,
    )


def test_auth_me_reports_effective_individual_owner_role_for_linked_owner():
    user, owner = create_owner_login(role_code=RoleCode.USER.value)
    client = create_authenticated_client(user)

    response = client.get(reverse("auth_me"))

    assert response.status_code == 200
    assert response.data["role"]["code"] == RoleCode.INDIVIDUAL_OWNER.value
    assert response.data["individual_owner"] == {
        "id": str(owner.id),
        "name": "Owner Person",
    }


def test_individual_owner_can_access_payment_owner_endpoints():
    user, owner = create_owner_login(email="ledger-owner@example.com", phone="+251911111112")
    client = create_authenticated_client(user)

    PaymentTransaction.objects.create(
        tx_ref="OWNER-TX-1",
        amount=Decimal("3000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        payout_status=PaymentTransaction.PayoutStatus.PENDING,
        vendor_individual=owner,
        vendor_payout_amount=Decimal("2700.00"),
        commission_amount=Decimal("300.00"),
    )

    _other_user, other_owner = create_owner_login(
        email="other-owner@example.com",
        phone="+251911111113",
    )
    PaymentTransaction.objects.create(
        tx_ref="OWNER-TX-2",
        amount=Decimal("4000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        payout_status=PaymentTransaction.PayoutStatus.PENDING,
        vendor_individual=other_owner,
        vendor_payout_amount=Decimal("3600.00"),
        commission_amount=Decimal("400.00"),
    )

    subaccount_response = client.get(reverse("chapa-subaccount-me"))
    assert subaccount_response.status_code == 200
    assert subaccount_response.data["owner_type"] == "individual_owner"
    assert str(subaccount_response.data["owner_id"]) == str(owner.id)

    ledger_response = client.get(reverse("owner-ledger-list"), {"scope": "owner"})
    assert ledger_response.status_code == 200
    assert [item["tx_ref"] for item in ledger_response.data["results"]] == ["OWNER-TX-1"]


def test_individual_owner_can_load_host_guesthouse_and_car_rental_lists():
    user, owner = create_owner_login(email="host-owner@example.com", phone="+251911111114")
    client = create_authenticated_client(user)

    guest_house = create_guesthouse_for_owner(owner)
    room = create_room(guest_house)
    renter = User.objects.create_user(
        email="guest@example.com",
        password="pass1234",
        phone="+251933333333",
    )
    guesthouse_booking = GuestHouseBooking.objects.create(
        renter=renter,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 3),
        total_price=Decimal("1500.00"),
        status=GuestHouseBooking.RentStatus.PENDING,
    )
    GuestHouseBookingItem.objects.create(
        booking=guesthouse_booking,
        room=room,
        units_booked=1,
        price_per_unit=Decimal("750.00"),
    )

    car = create_rental_car(owner)
    car_rental = CarRental.objects.create(
        renter=renter,
        start_date=date(2026, 7, 5),
        end_date=date(2026, 7, 6),
        total_price=Decimal("2500.00"),
        status=CarRental.RentStatus.PENDING,
    )
    CarRentalItem.objects.create(
        car_rental=car_rental,
        car_listing=car,
        units_rent=1,
        price_per_unit=Decimal("2500.00"),
    )

    guesthouse_response = client.get(reverse("guesthouse-bookings-list"), {"mode": "host"})
    assert guesthouse_response.status_code == 200
    assert guesthouse_response.data["count"] == 1

    car_rental_response = client.get(reverse("carrental-list"), {"mode": "host"})
    assert car_rental_response.status_code == 200
    assert car_rental_response.data["count"] == 1


def test_individual_owner_can_update_owned_car_listing_with_stale_user_role():
    user, owner = create_owner_login(email="edit-owner@example.com", phone="+251911111115")
    client = create_authenticated_client(user)
    car = create_rental_car(owner, model="Yaris")

    response = client.patch(
        reverse("cars-detail", args=[car.id]),
        {"title": "Updated Owner Car"},
        format="json",
    )

    assert response.status_code == 200
    car.refresh_from_db()
    assert car.title == "Updated Owner Car"


def test_individual_owner_cannot_update_foreign_car_listing():
    user, _owner = create_owner_login(email="owner-a@example.com", phone="+251911111116")
    _other_user, other_owner = create_owner_login(
        email="owner-b@example.com",
        phone="+251911111117",
    )
    client = create_authenticated_client(user)
    car = create_rental_car(other_owner, model="Hilux")

    response = client.patch(
        reverse("cars-detail", args=[car.id]),
        {"title": "Illegal Update"},
        format="json",
    )

    assert response.status_code == 403
