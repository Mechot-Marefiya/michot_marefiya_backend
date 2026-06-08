# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest
from decimal import Decimal

from apps.analytics.models import AnalyticsDirtyDate, CompanyDailyMetrics, ListingDailyMetrics
from apps.listing.models import Booking, BookingItem

pytestmark = pytest.mark.django_db


def test_company_daily_metrics_unique_constraint(company):
    CompanyDailyMetrics.objects.create(
        company_id=company.id,
        date="2026-06-01",
        revenue=Decimal("100.00"),
        bookings_count=1,
        confirmed_count=1,
        cancelled_count=0,
        avg_booking_value=Decimal("100.00"),
    )

    with pytest.raises(Exception):
        CompanyDailyMetrics.objects.create(
            company_id=company.id,
            date="2026-06-01",
            revenue=Decimal("100.00"),
            bookings_count=1,
            confirmed_count=1,
            cancelled_count=0,
            avg_booking_value=Decimal("100.00"),
        )


def test_listing_daily_metrics_unique_constraint(room, company):
    ListingDailyMetrics.objects.create(
        listing_id=room.id,
        company_id=company.id,
        date="2026-06-01",
        revenue=Decimal("100.00"),
        bookings_count=1,
        avg_price=Decimal("100.00"),
    )

    with pytest.raises(Exception):
        ListingDailyMetrics.objects.create(
            listing_id=room.id,
            company_id=company.id,
            date="2026-06-01",
            revenue=Decimal("100.00"),
            bookings_count=1,
            avg_price=Decimal("100.00"),
        )


def test_analytics_dirty_date_unique_constraint(company):
    AnalyticsDirtyDate.objects.create(company_id=company.id, date="2026-06-01")

    with pytest.raises(Exception):
        AnalyticsDirtyDate.objects.create(company_id=company.id, date="2026-06-01")


def test_booking_item_marks_company_dirty_date(company, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date="2026-06-10",
        check_out_date="2026-06-12",
        total_price=Decimal("1200.00"),
        currency="ETB",
        status=Booking.BookingStatus.CONFIRMED,
        guest_first_name="Analytics",
        guest_last_name="Guest",
        guest_email="analytics@example.com",
        guest_phone="0911000000",
        booking_reference="AN-001",
        terms_accepted=True,
        terms_version="1",
        terms_content_snapshot="Terms",
    )

    BookingItem.objects.create(
        booking=booking,
        room=room,
        units_booked=1,
        price_per_unit=Decimal("1200.00"),
    )

    assert AnalyticsDirtyDate.objects.filter(
        company_id=company.id,
        date=booking.created_at.date(),
        processed=False,
    ).exists()
