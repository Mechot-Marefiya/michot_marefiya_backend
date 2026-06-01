# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest
from decimal import Decimal

from apps.analytics.models import AnalyticsDirtyDate, CompanyDailyMetrics, ListingDailyMetrics

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
