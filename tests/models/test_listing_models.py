# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: no
# Last updated: 2026-06-01

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from apps.account.models import HotelProfile
from apps.listing.models import (
    AddonOffering,
    Booking,
    BookingItem,
    CarListing,
    CarRental,
    CarRentalItem,
    EventSpaceListing,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseInventory,
    GuestHouseProfile,
    GuestHouseRoom,
    RoomListing,
    SeasonalRate,
    TermsAndConditions,
)

pytestmark = pytest.mark.django_db


def test_car_listing_str_representation(car_listing):
    assert str(car_listing) == f"{car_listing.brand}::{car_listing.model}"


def test_car_listing_owner_constraint_validation(company, individual_owner, address):
    car = CarListing(
        company=company,
        individual_owner=individual_owner,
        brand=CarListing.CarBrandChoices.TOYOTA,
        model="Corolla",
        year=2024,
        mileage=10,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        listing_type=CarListing.ListingTypeChoices.RENT,
        car_class=CarListing.CarClassChoices.NORMAL,
        condition=CarListing.ConditionChoices.USED,
        title="Car",
        description="Car",
        base_price=Decimal("1000.00"),
        currency="ETB",
        quantity=1,
        seats=4,
    )

    with pytest.raises(ValidationError):
        car.full_clean()


def test_car_rental_str_representation(car_rental):
    assert str(car_rental).startswith("Rental by")


def test_car_rental_item_str_representation(car_rental, car_listing):
    item = CarRentalItem.objects.create(car_rental=car_rental, car_listing=car_listing, units_rent=1, price_per_unit=Decimal("1500.00"))
    assert str(item).startswith("Car ")


def test_guesthouse_profile_str_representation(guest_house):
    assert str(guest_house) == f"{guest_house.title} ({guest_house.address.city})"


def test_guesthouse_room_str_representation(guest_house_room):
    assert str(guest_house_room) == f"{guest_house_room.title} at {guest_house_room.guest_house.title}"


def test_guesthouse_room_signal_creates_inventory_and_syncs_base_price(guest_house, django_capture_on_commit_callbacks):
    guest_house.base_price = Decimal("2000.00")
    guest_house.save(update_fields=["base_price"])

    with django_capture_on_commit_callbacks(execute=True):
        room = GuestHouseRoom.objects.create(
            guest_house=guest_house,
            title="Standard",
            description="Standard room",
            base_price=Decimal("1200.00"),
            currency="ETB",
            number_of_guests=2,
            total_units=2,
            bed_type="single",
            room_size_sqm=18,
        )

    guest_house.refresh_from_db()
    assert guest_house.base_price == Decimal("1200.00")
    assert GuestHouseInventory.objects.filter(guest_house_room=room).exists()


def test_booking_str_representation(booking):
    assert str(booking).startswith("Booking")


def test_booking_item_str_representation(booking, room):
    item = BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("1000.00"))
    assert str(item).startswith("Room ")


def test_event_space_listing_str_representation(event_space):
    assert str(event_space) == event_space.title


def test_guesthouse_booking_str_representation(guesthouse_booking):
    assert str(guesthouse_booking).startswith("Booking #")


def test_guesthouse_booking_item_str_representation(guesthouse_booking, guest_house_room):
    item = GuestHouseBookingItem.objects.create(
        booking=guesthouse_booking,
        room=guest_house_room,
        units_booked=1,
        price_per_unit=Decimal("800.00"),
    )
    assert str(item).startswith("GH Room") or str(item).startswith("Room")


def test_addon_offering_clean_validation(hotel):
    addon = AddonOffering(
        hotel=hotel,
        name="Breakfast",
        description="Breakfast",
        category="meal",
        price_per_unit=Decimal("0.00"),
        currency="ETB",
        pricing_type="per_booking",
        is_active=True,
        max_quantity_per_booking=1,
        requires_inventory=False,
        daily_capacity=1,
        icon="plus",
        display_order=1,
    )

    with pytest.raises(ValidationError):
        addon.full_clean()


def test_seasonal_rate_days_of_week_validation(season):
    rate = SeasonalRate(
        season=season,
        price_override=Decimal("1200.00"),
        multiplier=Decimal("1.20"),
        priority=1,
        active=True,
        days_of_week=[7],
    )

    with pytest.raises(ValidationError):
        rate.full_clean()


def test_terms_and_conditions_save_deactivates_previous(hotel):
    first = TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        version=1,
        title="Terms 1",
        content="One",
        effective_date=date.today(),
        is_active=True,
    )
    second = TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        version=2,
        title="Terms 2",
        content="Two",
        effective_date=date.today() + timedelta(days=1),
        is_active=True,
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.is_active is False
    assert second.is_active is True
