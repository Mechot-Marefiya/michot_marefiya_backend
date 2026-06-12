# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest
from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from apps.listing.models import Booking, GuestHouseBooking, PropertyRentalAvailability, PropertyRentalBooking
from apps.listing.tasks import (
    auto_cancel_pending_booking,
    auto_cancel_pending_guesthouse_booking,
    auto_cancel_pending_property_rental_booking,
    cancel_all_expired_bookings,
)
from django.conf import settings

pytestmark = pytest.mark.django_db


def test_auto_cancel_pending_booking_executes_successfully(monkeypatch, booking):
    called = {"value": False}

    def fake_cancel(obj):
        called["value"] = True
        obj.status = Booking.BookingStatus.CANCELLED
        obj.save(update_fields=["status"])

    monkeypatch.setattr("apps.listing.tasks.BookingService.cancel_booking", fake_cancel)

    assert auto_cancel_pending_booking(booking.id) is None
    assert called["value"] is True


def test_auto_cancel_pending_booking_handles_missing_object_gracefully():
    assert auto_cancel_pending_booking(uuid4()) is None


def test_auto_cancel_pending_guesthouse_booking_executes_successfully(monkeypatch, guesthouse_booking):
    called = {"value": False}

    def fake_cancel(obj):
        called["value"] = True
        obj.status = GuestHouseBooking.RentStatus.CANCELLED
        obj.save(update_fields=["status"])

    monkeypatch.setattr("apps.listing.tasks.GuestHouseBookingService.cancel_booking", fake_cancel)

    assert auto_cancel_pending_guesthouse_booking(guesthouse_booking.id) is None
    assert called["value"] is True


def test_auto_cancel_pending_guesthouse_booking_handles_missing_object_gracefully():
    assert auto_cancel_pending_guesthouse_booking(uuid4()) is None


def test_auto_cancel_pending_property_rental_booking_executes_successfully(monkeypatch, property_listing):
    booking = PropertyRentalBooking.objects.create(
        property_listing=property_listing,
        start_date=timezone.localdate() + timedelta(days=5),
        end_date=timezone.localdate() + timedelta(days=7),
        total_price="6000.00",
        currency="ETB",
        status=PropertyRentalBooking.RentStatus.PENDING,
        guest_first_name="Property",
        guest_last_name="Rental",
        guest_email="property-rental-task@example.com",
        guest_phone="0911555701",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    called = {"value": False}

    def fake_cancel(obj):
        called["value"] = True
        obj.status = PropertyRentalBooking.RentStatus.CANCELLED
        obj.save(update_fields=["status"])

    monkeypatch.setattr("apps.listing.tasks.PropertyRentalBookingService.cancel_booking", fake_cancel)

    assert auto_cancel_pending_property_rental_booking(booking.id) is None
    assert called["value"] is True


def test_auto_cancel_pending_property_rental_booking_handles_missing_object_gracefully():
    assert auto_cancel_pending_property_rental_booking(uuid4()) is None


def test_auto_cancel_pending_property_rental_booking_releases_availability(property_listing):
    start_date = timezone.localdate() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    booking = PropertyRentalBooking.objects.create(
        property_listing=property_listing,
        start_date=start_date,
        end_date=end_date,
        total_price="6000.00",
        currency="ETB",
        status=PropertyRentalBooking.RentStatus.PENDING,
        guest_first_name="Property",
        guest_last_name="Release",
        guest_email="property-rental-release@example.com",
        guest_phone="0911555705",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    for offset in range((end_date - start_date).days):
        PropertyRentalAvailability.objects.update_or_create(
            property_listing=property_listing,
            date=start_date + timedelta(days=offset),
            defaults={"available_units": 0},
        )

    assert auto_cancel_pending_property_rental_booking(booking.id) is None

    booking.refresh_from_db()
    assert booking.status == PropertyRentalBooking.RentStatus.CANCELLED
    assert list(
        PropertyRentalAvailability.objects.filter(property_listing=property_listing)
        .order_by("date")
        .values_list("available_units", flat=True)
    ) == [1, 1]


def test_property_rental_booking_signal_schedules_auto_cancel(django_capture_on_commit_callbacks, monkeypatch, property_listing):
    calls = []
    monkeypatch.setattr(
        "apps.listing.signals.auto_cancel_pending_property_rental_booking.apply_async",
        lambda args, countdown: calls.append({"args": args, "countdown": countdown}),
    )

    with django_capture_on_commit_callbacks(execute=True):
        booking = PropertyRentalBooking.objects.create(
            property_listing=property_listing,
            start_date=timezone.localdate() + timedelta(days=5),
            end_date=timezone.localdate() + timedelta(days=7),
            total_price="6000.00",
            currency="ETB",
            status=PropertyRentalBooking.RentStatus.PENDING,
            guest_first_name="Property",
            guest_last_name="Signal",
            guest_email="property-rental-signal@example.com",
            guest_phone="0911555706",
            terms_accepted=True,
            terms_version="1",
            terms_accepted_at=timezone.now(),
            terms_content_snapshot="Terms",
        )

    assert calls == [{"args": [booking.id], "countdown": 60 * getattr(settings, "BOOKING_PENDING_TIMEOUT_MINUTES", 15)}]


def test_cancel_all_expired_bookings_beat_schedule_registered():
    schedule = settings.CELERY_BEAT_SCHEDULE["cleanup-expired-bookings-every-5-minutes"]

    assert schedule["task"] == "apps.listing.tasks.cancel_all_expired_bookings"
    assert schedule["schedule"] == 60.0 * 5
    assert schedule["args"] == ()


def test_cancel_all_expired_bookings_triggers_child_tasks(monkeypatch, booking, guesthouse_booking, property_listing):
    property_booking = PropertyRentalBooking.objects.create(
        property_listing=property_listing,
        start_date=timezone.localdate() + timedelta(days=5),
        end_date=timezone.localdate() + timedelta(days=7),
        total_price="6000.00",
        currency="ETB",
        status=PropertyRentalBooking.RentStatus.PENDING,
        guest_first_name="Property",
        guest_last_name="Rental",
        guest_email="property-rental-expired@example.com",
        guest_phone="0911555702",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    Booking.objects.filter(id=booking.id).update(created_at=timezone.now() - timedelta(minutes=30))
    GuestHouseBooking.objects.filter(id=guesthouse_booking.id).update(created_at=timezone.now() - timedelta(minutes=30))
    PropertyRentalBooking.objects.filter(id=property_booking.id).update(created_at=timezone.now() - timedelta(minutes=30))

    calls = {"booking": False, "guesthouse": False, "property": False}

    class DummyTask:
        def __init__(self, key):
            self.key = key

        def delay(self, pk):
            calls[self.key] = True

    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_booking", DummyTask("booking"))
    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_guesthouse_booking", DummyTask("guesthouse"))
    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_property_rental_booking", DummyTask("property"))

    assert cancel_all_expired_bookings() is None
    assert calls["booking"] is True
    assert calls["guesthouse"] is True
    assert calls["property"] is True


def test_cancel_all_expired_bookings_dispatches_only_expired_pending(monkeypatch, booking, guesthouse_booking, property_listing):
    fresh_booking = Booking.objects.create(
        user=booking.user,
        check_in_date=booking.check_in_date,
        check_out_date=booking.check_out_date,
        total_price=booking.total_price,
        currency=booking.currency,
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Fresh",
        guest_last_name="Booking",
        guest_email="fresh@example.com",
        guest_phone="0911000999",
        booking_reference="H-FRESH",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    confirmed_booking = Booking.objects.create(
        user=booking.user,
        check_in_date=booking.check_in_date,
        check_out_date=booking.check_out_date,
        total_price=booking.total_price,
        currency=booking.currency,
        status=Booking.BookingStatus.CONFIRMED,
        guest_first_name="Confirmed",
        guest_last_name="Booking",
        guest_email="confirmed@example.com",
        guest_phone="0911000888",
        booking_reference="H-CONFIRMED",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )

    Booking.objects.filter(id=booking.id).update(created_at=timezone.now() - timedelta(minutes=30))
    Booking.objects.filter(id=fresh_booking.id).update(created_at=timezone.now())
    Booking.objects.filter(id=confirmed_booking.id).update(created_at=timezone.now() - timedelta(minutes=30))
    GuestHouseBooking.objects.filter(id=guesthouse_booking.id).update(created_at=timezone.now() - timedelta(minutes=30))
    property_booking = PropertyRentalBooking.objects.create(
        property_listing=property_listing,
        start_date=timezone.localdate() + timedelta(days=5),
        end_date=timezone.localdate() + timedelta(days=7),
        total_price="6000.00",
        currency="ETB",
        status=PropertyRentalBooking.RentStatus.PENDING,
        guest_first_name="Property",
        guest_last_name="Expired",
        guest_email="property-rental-dispatch@example.com",
        guest_phone="0911555703",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    fresh_property_booking = PropertyRentalBooking.objects.create(
        property_listing=property_listing,
        start_date=timezone.localdate() + timedelta(days=8),
        end_date=timezone.localdate() + timedelta(days=10),
        total_price="6000.00",
        currency="ETB",
        status=PropertyRentalBooking.RentStatus.PENDING,
        guest_first_name="Property",
        guest_last_name="Fresh",
        guest_email="property-rental-fresh@example.com",
        guest_phone="0911555704",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    PropertyRentalBooking.objects.filter(id=property_booking.id).update(created_at=timezone.now() - timedelta(minutes=30))
    PropertyRentalBooking.objects.filter(id=fresh_property_booking.id).update(created_at=timezone.now())

    dispatched = {"booking": [], "guesthouse": [], "property": []}

    class DummyTask:
        def __init__(self, key):
            self.key = key

        def delay(self, pk):
            dispatched[self.key].append(pk)

    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_booking", DummyTask("booking"))
    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_guesthouse_booking", DummyTask("guesthouse"))
    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_property_rental_booking", DummyTask("property"))

    assert cancel_all_expired_bookings() is None
    assert dispatched["booking"] == [booking.id]
    assert dispatched["guesthouse"] == [guesthouse_booking.id]
    assert dispatched["property"] == [property_booking.id]
