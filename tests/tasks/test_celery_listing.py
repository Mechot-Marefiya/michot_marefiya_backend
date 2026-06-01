# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest
from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from apps.listing.models import Booking, GuestHouseBooking
from apps.listing.tasks import auto_cancel_pending_booking, auto_cancel_pending_guesthouse_booking, cancel_all_expired_bookings
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


def test_cancel_all_expired_bookings_beat_schedule_registered():
    assert "cleanup-expired-bookings-every-5-minutes" in settings.CELERY_BEAT_SCHEDULE


def test_cancel_all_expired_bookings_triggers_child_tasks(monkeypatch, booking, guesthouse_booking):
    Booking.objects.filter(id=booking.id).update(created_at=timezone.now() - timedelta(minutes=30))
    GuestHouseBooking.objects.filter(id=guesthouse_booking.id).update(created_at=timezone.now() - timedelta(minutes=30))

    calls = {"booking": False, "guesthouse": False}

    class DummyTask:
        def __init__(self, key):
            self.key = key

        def delay(self, pk):
            calls[self.key] = True

    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_booking", DummyTask("booking"))
    monkeypatch.setattr("apps.listing.tasks.auto_cancel_pending_guesthouse_booking", DummyTask("guesthouse"))

    assert cancel_all_expired_bookings() is None
    assert calls["booking"] is True
    assert calls["guesthouse"] is True
