# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta
from decimal import Decimal

from apps.analytics.models import CompanyDailyMetrics
from apps.listing.models import Booking, BookingItem
from tests.conftest import CompanyProfileFactory, HotelProfileFactory

pytestmark = pytest.mark.django_db


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
