# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from apps.account.models import HotelProfile
from apps.core.models import CurrencyRate
from apps.listing.models import Booking, BookingItem, TermsAndConditions
from apps.payment.models import PaymentTransaction

pytestmark = pytest.mark.django_db


def test_flutter_contract_auth_me(auth_client, user):
    response = auth_client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    data = response.json()
    for key in ["id", "email", "first_name", "last_name", "phone", "is_active", "role", "workspace"]:
        assert key in data


def test_flutter_contract_core_currency_convert(api_client):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"))
    response = api_client.post(
        "/api/v1/core/currency/convert/",
        {"base": "USD", "target": "ETB", "amount": "10", "date": "2026-06-01"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["converted_amount", "rate_used"]:
        assert key in data


def test_flutter_contract_account_hotels(api_client, hotel):
    response = api_client.get("/api/v1/account/hotels/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data and "results" in data
    assert isinstance(data["results"], list)


def test_flutter_contract_listing_room_detail(api_client, room):
    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/")

    assert response.status_code == 200
    data = response.json()
    for key in ["id", "title", "description", "base_price", "currency"]:
        assert key in data


def test_flutter_contract_listing_terms(api_client, hotel):
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        version=1,
        title="Hotel Terms",
        content="Hotel terms content",
        effective_date=date.today(),
        is_active=True,
    )
    response = api_client.get("/api/v1/listing/terms/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)


def test_flutter_contract_payment_verify_public(api_client, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=7),
        check_out_date=date.today() + timedelta(days=9),
        total_price=Decimal("1000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email="guest@example.com",
        guest_phone="0911000000",
        special_requests="None",
        booking_reference="H-000777",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=None,
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("1000.00"))
    payment = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-contract-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    response = api_client.get(f"/api/v1/payment/verify-public/{payment.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert "chapa_verification" in data


def test_flutter_contract_favorites_list(auth_client, favorite):
    response = auth_client.get("/api/v1/favorites/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data


def test_flutter_contract_notifications_list(auth_client, notification):
    response = auth_client.get("/api/v1/notifications/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data


def test_flutter_contract_analytics_overview(company_client):
    response = company_client.get("/api/v1/analytics/company/overview/")

    assert response.status_code == 200
    data = response.json()
    assert "total_revenue" in data
    assert "total_bookings" in data
