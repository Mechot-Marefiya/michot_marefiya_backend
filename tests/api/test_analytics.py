# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone

from apps.analytics import services as analytics_services
from apps.analytics.models import CompanyDailyMetrics
from apps.listing.models import Booking, BookingItem
from apps.payment.models import PaymentTransaction
from tests.conftest import CompanyProfileFactory, HotelProfileFactory

pytestmark = pytest.mark.django_db


def _create_payment_transaction(
    *,
    amount="100.00",
    status=PaymentTransaction.PaymentStatus.SUCCESS,
    payout_status=PaymentTransaction.PayoutStatus.PAID,
    booking_type="booking",
    commission_amount="5.00",
    vendor_payout_amount="95.00",
    created_at=None,
):
    tx = PaymentTransaction.objects.create(
        tx_ref=f"TX-{timezone.now().timestamp()}-{PaymentTransaction.objects.count()}",
        amount=Decimal(amount),
        currency="ETB",
        status=status,
        booking_type=booking_type,
        commission_amount=Decimal(commission_amount) if commission_amount is not None else None,
        vendor_payout_amount=Decimal(vendor_payout_amount) if vendor_payout_amount is not None else None,
        payout_status=payout_status,
    )
    if created_at is not None:
        PaymentTransaction.objects.filter(pk=tx.pk).update(created_at=created_at)
        tx.refresh_from_db()
    return tx


def test_get_company_overview_unauthenticated(api_client):
    response = api_client.get("/api/v1/analytics/company/overview/")

    assert response.status_code == 401


def test_get_company_overview_wrong_role_forbidden(auth_client):
    response = auth_client.get("/api/v1/analytics/company/overview/")

    assert response.status_code == 403


def test_get_company_overview_success(company_client):
    response = company_client.get("/api/v1/analytics/company/overview/")

    assert response.status_code == 200
    data = response.json()
    assert "total_revenue" in data
    assert "total_bookings" in data
    assert "confirmed_bookings" in data
    assert "cancellations" in data
    assert "avg_booking_value" in data
    assert "top_listings" in data


def test_get_company_overview_reads_materialized_metrics(company_client, company):
    metrics_date = date.today()
    CompanyDailyMetrics.objects.create(
        company_id=company.id,
        date=metrics_date,
        revenue=Decimal("4321.00"),
        bookings_count=3,
        confirmed_count=2,
        cancelled_count=1,
        avg_booking_value=Decimal("1440.33"),
        top_listings=[
            {
                "listing_id": "room-1",
                "title": "Precomputed Room",
                "revenue": 4321.0,
                "bookings_count": 3,
                "type": "hotel_room",
            }
        ],
    )

    response = company_client.get(
        "/api/v1/analytics/company/overview/",
        {"start_date": metrics_date.isoformat(), "end_date": metrics_date.isoformat()},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_revenue"] == 4321.0
    assert data["total_bookings"] == 3
    assert data["confirmed_bookings"] == 2
    assert data["cancellations"] == 1
    assert data["top_listings"][0]["title"] == "Precomputed Room"


def test_get_company_overview_invalid_date_payload(company_client):
    response = company_client.get(
        "/api/v1/analytics/company/overview/",
        {"start_date": "bad-date", "end_date": "2026-06-12"},
    )

    assert response.status_code == 400


def test_get_company_overview_forbidden_for_other_company(company_client, user):
    other_company = CompanyProfileFactory(user=user)

    response = company_client.get(
        "/api/v1/analytics/company/overview/",
        {"company_id": str(other_company.id)},
    )

    assert response.status_code == 403


def test_get_company_revenue_success(company_client):
    response = company_client.get("/api/v1/analytics/company/revenue/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert "period" in data[0]
        assert "revenue" in data[0]


def test_get_company_revenue_unauthenticated(api_client):
    response = api_client.get("/api/v1/analytics/company/revenue/")

    assert response.status_code == 401


def test_get_company_revenue_invalid_date_payload(company_client):
    response = company_client.get(
        "/api/v1/analytics/company/revenue/",
        {"start_date": "bad-date", "end_date": "2026-06-12"},
    )

    assert response.status_code == 400


def test_get_company_revenue_invalid_granularity(company_client):
    response = company_client.get(
        "/api/v1/analytics/company/revenue/",
        {"granularity": "year"},
    )

    assert response.status_code == 400


def test_get_company_revenue_contains_timeseries_item(company_client, company, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=1),
        check_out_date=date.today() + timedelta(days=2),
        total_price=Decimal("1200.00"),
        currency="ETB",
        status=Booking.BookingStatus.CONFIRMED,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email="guest@example.com",
        guest_phone="0911000000",
        booking_reference="H-AN-001",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=None,
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("1200.00"))

    response = company_client.get(
        "/api/v1/analytics/company/revenue/",
        {"start_date": date.today().isoformat(), "end_date": date.today().isoformat()},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert "period" in data[0]
        assert "revenue" in data[0]


def test_get_company_revenue_reads_materialized_metrics(company_client, company):
    metrics_date = date.today()
    CompanyDailyMetrics.objects.create(
        company_id=company.id,
        date=metrics_date,
        revenue=Decimal("987.65"),
        bookings_count=1,
        confirmed_count=1,
        cancelled_count=0,
        avg_booking_value=Decimal("987.65"),
    )

    response = company_client.get(
        "/api/v1/analytics/company/revenue/",
        {"start_date": metrics_date.isoformat(), "end_date": metrics_date.isoformat()},
    )

    assert response.status_code == 200
    assert response.json() == [{"period": metrics_date.isoformat(), "revenue": 987.65}]


def test_get_company_activity_success(company_client):
    response = company_client.get("/api/v1/analytics/company/activity/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_company_activity_unauthenticated(api_client):
    response = api_client.get("/api/v1/analytics/company/activity/")

    assert response.status_code == 401


def test_get_company_activity_forbidden_for_other_company(company_client, user):
    other_company = CompanyProfileFactory(user=user)

    response = company_client.get(
        "/api/v1/analytics/company/activity/",
        {"company_id": str(other_company.id)},
    )

    assert response.status_code == 403


def test_get_company_activity_contains_expected_fields(company_client, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=1),
        check_out_date=date.today() + timedelta(days=2),
        total_price=Decimal("900.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email="guest@example.com",
        guest_phone="0911000000",
        booking_reference="H-ACT-001",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=None,
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("900.00"))

    response = company_client.get("/api/v1/analytics/company/activity/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        for key in ["id", "type", "property_type", "title", "amount", "user_name", "timestamp", "status"]:
            assert key in data[0]


def test_get_frontdesk_stats_success(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "arrivals_today" in data
    assert "departures_today" in data
    assert "in_house_count" in data
    assert "availability_percent" in data
    assert "total_rooms" in data
    assert "occupied_rooms" in data


def test_get_frontdesk_stats_front_desk_success(front_desk_client, hotel):
    response = front_desk_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 200


def test_get_frontdesk_stats_unauthenticated(api_client, hotel):
    response = api_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 401


def test_get_frontdesk_stats_wrong_role_forbidden(auth_client, hotel):
    response = auth_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 403


def test_get_frontdesk_stats_invalid_payload(company_client):
    response = company_client.get("/api/v1/analytics/frontdesk/stats/")

    assert response.status_code == 400


def test_get_frontdesk_stats_forbidden_for_other_workspace(front_desk_client, company):
    other_hotel = HotelProfileFactory(company=company)

    response = front_desk_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(other_hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 403


def test_get_frontdesk_availability_success(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/availability/",
        {
            "workspace_id": str(hotel.id),
            "workspace_type": "hotel",
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        for key in ["room_id", "room_name", "total_units", "availability"]:
            assert key in data[0]


def test_get_frontdesk_availability_front_desk_success(front_desk_client, hotel):
    response = front_desk_client.get(
        "/api/v1/analytics/frontdesk/availability/",
        {
            "workspace_id": str(hotel.id),
            "workspace_type": "hotel",
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200


def test_get_frontdesk_availability_unauthenticated(api_client, hotel):
    response = api_client.get(
        "/api/v1/analytics/frontdesk/availability/",
        {
            "workspace_id": str(hotel.id),
            "workspace_type": "hotel",
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 401


def test_get_frontdesk_availability_invalid_payload(company_client):
    response = company_client.get("/api/v1/analytics/frontdesk/availability/")

    assert response.status_code == 400


def test_get_frontdesk_availability_invalid_date_format(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/availability/",
        {
            "workspace_id": str(hotel.id),
            "workspace_type": "hotel",
            "start_date": "bad-date",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 400


def test_get_frontdesk_availability_range_too_large(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/availability/",
        {
            "workspace_id": str(hotel.id),
            "workspace_type": "hotel",
            "start_date": "2026-06-01",
            "end_date": "2026-09-15",
        },
    )

    assert response.status_code == 400


def test_get_frontdesk_availability_forbidden_for_other_workspace(front_desk_client, company):
    other_hotel = HotelProfileFactory(company=company)

    response = front_desk_client.get(
        "/api/v1/analytics/frontdesk/availability/",
        {
            "workspace_id": str(other_hotel.id),
            "workspace_type": "hotel",
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analytics/admin/overview/",
        "/api/v1/analytics/admin/revenue/",
        "/api/v1/analytics/admin/payout-failures/",
    ],
)
def test_admin_dashboard_metrics_require_authentication(api_client, path):
    response = api_client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analytics/admin/overview/",
        "/api/v1/analytics/admin/revenue/",
        "/api/v1/analytics/admin/payout-failures/",
    ],
)
def test_admin_dashboard_metrics_forbid_non_admin(auth_client, path):
    response = auth_client.get(path)

    assert response.status_code == 403


def test_admin_overview_metrics_success(admin_client):
    analytics_services.invalidate_analytics_cache()
    _create_payment_transaction(amount="250.00")

    response = admin_client.get("/api/v1/analytics/admin/overview/")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {
        "total_revenue",
        "total_transactions",
        "pending_approvals",
        "active_listings",
        "total_users",
        "new_users_in_range",
    }
    assert isinstance(data["active_listings"], list)
    assert {"category", "count"} <= set(data["active_listings"][0].keys())


def test_admin_overview_metrics_filters_new_users_by_date_range(admin_client, django_user_model):
    analytics_services.invalidate_analytics_cache()
    old_user = django_user_model.objects.create_user(email="old-admin-metric@example.com", password="pass1234")
    fresh_user = django_user_model.objects.create_user(email="fresh-admin-metric@example.com", password="pass1234")
    PaymentTransaction.objects.all().delete()
    _create_payment_transaction(amount="150.00", created_at=timezone.now() - timedelta(days=10))
    _create_payment_transaction(amount="300.00", created_at=timezone.now() - timedelta(days=1))
    django_user_model.objects.filter(pk=old_user.pk).update(created_at=timezone.now() - timedelta(days=10))
    django_user_model.objects.filter(pk=fresh_user.pk).update(created_at=timezone.now() - timedelta(days=1))

    response = admin_client.get(
        "/api/v1/analytics/admin/overview/",
        {
            "date_from": (date.today() - timedelta(days=2)).isoformat(),
            "date_to": date.today().isoformat(),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_revenue"] == 300.0
    assert data["total_transactions"] == 1
    assert data["new_users_in_range"] >= 1


def test_admin_overview_metrics_invalid_date_range(admin_client):
    response = admin_client.get(
        "/api/v1/analytics/admin/overview/",
        {"date_from": "2026-06-12", "date_to": "2026-06-01"},
    )

    assert response.status_code == 400
    assert "date_from" in response.json()


def test_admin_overview_metrics_second_request_uses_cache(admin_client):
    analytics_services.invalidate_analytics_cache()
    response = admin_client.get("/api/v1/analytics/admin/overview/")
    assert response.status_code == 200

    with patch.object(analytics_services.PaymentTransaction.objects, "filter", side_effect=AssertionError("db hit")):
        with patch.object(analytics_services.PaymentTransaction.objects, "all", side_effect=AssertionError("db hit")):
            with patch.object(analytics_services.User.objects, "all", side_effect=AssertionError("db hit")):
                with patch("apps.analytics.services._pending_listing_approvals_count", side_effect=AssertionError("db hit")):
                    with patch("apps.analytics.services._active_listing_counts", side_effect=AssertionError("db hit")):
                        second = admin_client.get("/api/v1/analytics/admin/overview/")

    assert second.status_code == 200


def test_admin_revenue_metrics_grouping(admin_client):
    analytics_services.invalidate_analytics_cache()
    PaymentTransaction.objects.all().delete()
    current_day = timezone.now() - timedelta(days=1)
    _create_payment_transaction(
        amount="120.00",
        booking_type="booking",
        commission_amount="6.00",
        created_at=current_day,
    )
    _create_payment_transaction(
        amount="180.00",
        booking_type="propertyrental",
        commission_amount="9.00",
        created_at=current_day,
    )

    response = admin_client.get(
        "/api/v1/analytics/admin/revenue/",
        {
            "date_from": (date.today() - timedelta(days=3)).isoformat(),
            "date_to": date.today().isoformat(),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {
        "revenue_by_period",
        "revenue_by_category",
        "average_transaction",
        "total_service_fees",
    }
    assert data["average_transaction"] == 150.0
    assert data["total_service_fees"] == 15.0
    assert any(item["category"] == "booking" and item["amount"] == 120.0 for item in data["revenue_by_category"])
    assert any(item["category"] == "propertyrental" and item["amount"] == 180.0 for item in data["revenue_by_category"])


def test_admin_revenue_metrics_range_over_365_days_rejected(admin_client):
    response = admin_client.get(
        "/api/v1/analytics/admin/revenue/",
        {"date_from": "2024-01-01", "date_to": "2026-01-02"},
    )

    assert response.status_code == 400
    assert "date_to" in response.json()


def test_admin_payout_failure_metrics_success(admin_client):
    analytics_services.invalidate_analytics_cache()
    PaymentTransaction.objects.all().delete()
    in_range = timezone.now() - timedelta(days=2)
    _create_payment_transaction(
        amount="400.00",
        payout_status=PaymentTransaction.PayoutStatus.FAILED,
        vendor_payout_amount="300.00",
        created_at=in_range,
    )
    _create_payment_transaction(
        amount="200.00",
        payout_status=PaymentTransaction.PayoutStatus.PAID,
        vendor_payout_amount="150.00",
        created_at=in_range,
    )
    _create_payment_transaction(
        amount="100.00",
        payout_status=PaymentTransaction.PayoutStatus.FAILED,
        vendor_payout_amount="70.00",
        created_at=in_range,
    )

    response = admin_client.get(
        "/api/v1/analytics/admin/payout-failures/",
        {
            "date_from": (date.today() - timedelta(days=3)).isoformat(),
            "date_to": date.today().isoformat(),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_failures"] == 2
    assert data["failure_rate"] == 66.67
    assert data["failures_by_reason"] == []
    assert data["total_failed_amount"] == 370.0


def test_admin_payout_failure_metrics_no_params_returns_all_time(admin_client):
    analytics_services.invalidate_analytics_cache()
    PaymentTransaction.objects.all().delete()
    _create_payment_transaction(
        amount="500.00",
        payout_status=PaymentTransaction.PayoutStatus.FAILED,
        vendor_payout_amount="350.00",
    )

    response = admin_client.get("/api/v1/analytics/admin/payout-failures/")

    assert response.status_code == 200
    assert response.json()["total_failures"] == 1
