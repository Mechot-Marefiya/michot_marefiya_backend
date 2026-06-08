# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from decimal import Decimal
from datetime import date, timedelta

pytestmark = pytest.mark.django_db

from apps.core.models import CurrencyRate, Facility


def test_get_facilities_public_contract(api_client):
    Facility.objects.create(name="Pool", icon="pool")

    response = api_client.get("/api/v1/core/facilities/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["name"] == "Pool"
    assert "id" in data["results"][0]
    assert "icon" in data["results"][0]


def test_get_facilities_detail_not_found(api_client):
    response = api_client.get("/api/v1/core/facilities/00000000-0000-0000-0000-000000000000/")

    assert response.status_code == 404


def test_post_facility_admin_create_success(admin_client):
    response = admin_client.post(
        "/api/v1/core/facilities/",
        {"name": "Spa", "icon": "spa"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Spa"
    assert data["icon"] == "spa"


def test_patch_facility_admin_update_success(admin_client):
    facility = Facility.objects.create(name="Pool", icon="pool")

    response = admin_client.patch(
        f"/api/v1/core/facilities/{facility.id}/",
        {"icon": "pool-updated"},
        format="json",
    )

    assert response.status_code == 200
    facility.refresh_from_db()
    assert facility.icon == "pool-updated"


def test_delete_facility_admin_delete_success(admin_client):
    facility = Facility.objects.create(name="Gym", icon="gym")

    response = admin_client.delete(f"/api/v1/core/facilities/{facility.id}/")

    assert response.status_code == 204
    assert Facility.objects.filter(id=facility.id).exists() is False


def test_post_facility_non_admin_forbidden(auth_client):
    response = auth_client.post(
        "/api/v1/core/facilities/",
        {"name": "Spa", "icon": "spa"},
        format="json",
    )

    assert response.status_code == 403


def test_get_currencies_public_contract(api_client):
    response = api_client.get("/api/v1/core/currencies/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["code"]
    assert data[0]["name"]
    assert "results" not in data
    assert any(item["code"] == "USD" for item in data)


def test_get_currency_rates_public_contract(api_client):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"), date=date.today())

    response = api_client.get("/api/v1/core/currencies/rates/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["ETB"] == 120.0
    assert "USD" in data


def test_get_currency_rates_uses_latest_rate_date(api_client):
    yesterday = date.today() - timedelta(days=1)
    today = date.today()
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("100.000000"), date=yesterday)
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("125.000000"), date=today)
    CurrencyRate.objects.create(base="USD", target="EUR", rate=Decimal("0.900000"), date=today)

    response = api_client.get("/api/v1/core/currencies/rates/")

    assert response.status_code == 200
    data = response.json()
    assert data["ETB"] == 125.0
    assert data["EUR"] == 0.9
    assert data["USD"] == 1.0


def test_get_currency_rates_not_found_when_empty(api_client):
    response = api_client.get("/api/v1/core/currencies/rates/")

    assert response.status_code == 404
    assert response.json() == {"detail": "No rate data available."}


def test_post_currency_convert_success(api_client):
    rate_date = date.today()
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"), date=rate_date)

    response = api_client.post(
        "/api/v1/core/currency/convert/",
        {"base": "USD", "target": "ETB", "amount": "10", "date": rate_date.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["input_amount"] == 10.0
    assert data["base"] == "USD"
    assert data["target"] == "ETB"
    assert data["converted_amount"] == 1200.0
    assert data["rate_date"] == rate_date.isoformat()
    assert data["rate_used"] == 120.0


def test_post_currency_convert_same_currency_returns_identity(api_client):
    rate_date = date.today()

    response = api_client.post(
        "/api/v1/core/currency/convert/",
        {"base": "USD", "target": "USD", "amount": "10", "date": rate_date.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["converted_amount"] == 10.0
    assert data["rate_used"] == 1.0


def test_post_currency_convert_missing_rate_returns_not_found(api_client):
    response = api_client.post(
        "/api/v1/core/currency/convert/",
        {"base": "EUR", "target": "ETB", "amount": "10", "date": date.today().isoformat()},
        format="json",
    )

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "No exchange rate found" in data["error"]


def test_post_currency_convert_invalid_payload(api_client):
    response = api_client.post("/api/v1/core/currency/convert/", {}, format="json")

    assert response.status_code == 400
    data = response.json()
    assert "base" in data
    assert "target" in data
    assert "amount" in data
    assert "date" in data
