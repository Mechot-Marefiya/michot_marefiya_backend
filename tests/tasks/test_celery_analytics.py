from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.conf import settings

from apps.analytics.models import AnalyticsDirtyDate, CompanyDailyMetrics
from apps.analytics.tasks import process_dirty_analytics_dates
from apps.listing.models import Booking, BookingItem

pytestmark = pytest.mark.django_db


def test_process_dirty_analytics_dates_materializes_metrics(company, user, room):
    metrics_date = date.today()
    booking = Booking.objects.create(
        user=user,
        check_in_date=metrics_date,
        check_out_date=metrics_date + timedelta(days=1),
        total_price=Decimal("1500.00"),
        currency="ETB",
        status=Booking.BookingStatus.CONFIRMED,
        guest_first_name="Task",
        guest_last_name="Guest",
        guest_email="task@example.com",
        guest_phone="0911000001",
        booking_reference="AN-TASK-001",
        terms_accepted=True,
        terms_version="1",
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(
        booking=booking,
        room=room,
        units_booked=1,
        price_per_unit=Decimal("1500.00"),
    )
    dirty = AnalyticsDirtyDate.objects.update_or_create(
        company_id=company.id,
        date=metrics_date,
        defaults={"processed": False},
    )[0]

    result = process_dirty_analytics_dates()

    dirty.refresh_from_db()
    assert result["processed"] >= 1
    assert dirty.processed is True
    metric = CompanyDailyMetrics.objects.get(company_id=company.id, date=metrics_date)
    assert metric.revenue == Decimal("1500.00")
    assert metric.bookings_count == 1


def test_process_dirty_analytics_dates_beat_schedule_registered():
    schedule = settings.CELERY_BEAT_SCHEDULE["process-dirty-analytics-dates-every-10-minutes"]
    assert schedule["task"] == "apps.analytics.tasks.process_dirty_analytics_dates"
