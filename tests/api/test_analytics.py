# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta

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


def test_get_company_revenue_success(company_client):
    response = company_client.get("/api/v1/analytics/company/revenue/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_company_activity_success(company_client):
    response = company_client.get("/api/v1/analytics/company/activity/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_frontdesk_stats_success(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "arrivals_today" in data
    assert "departures_today" in data


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
    assert isinstance(response.json(), list)


def test_get_frontdesk_availability_invalid_payload(company_client):
    response = company_client.get("/api/v1/analytics/frontdesk/availability/")

    assert response.status_code == 400
