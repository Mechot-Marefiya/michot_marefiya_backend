# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.account.models import CompanyProfile
from apps.listing.models import Booking, BookingItem, CarRental, CarRentalItem
from apps.payment.models import PaymentTransaction

pytestmark = pytest.mark.django_db


def _build_booking(user, room):
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
        booking_reference="H-000001",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("1000.00"))
    return booking


def test_post_payment_initiate_success(auth_client, user, room, monkeypatch):
    booking = _build_booking(user, room)

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.initialize_payment",
        lambda **kwargs: {
            "success": True,
            "message": "Payment initialized",
            "checkout_url": "https://checkout.example.com",
            "tx_ref": "tx-123",
        },
    )

    response = auth_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["checkout_url"] == "https://checkout.example.com"
    assert data["tx_ref"] == "tx-123"
    assert "calculated_amount" in data
    assert "payment_currency" in data


def test_post_payment_initiate_unauthenticated_for_registered_booking(api_client, user, room, monkeypatch):
    booking = _build_booking(user, room)

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.initialize_payment",
        lambda **kwargs: {"success": True, "message": "Payment initialized", "checkout_url": "https://checkout.example.com"},
    )

    response = api_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 403


def test_post_payment_initiate_wrong_user_forbidden(company_client, user, room, monkeypatch):
    booking = _build_booking(user, room)

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.initialize_payment",
        lambda **kwargs: {"success": True, "message": "Payment initialized", "checkout_url": "https://checkout.example.com"},
    )

    response = company_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 403


def test_post_payment_initiate_invalid_payload(api_client):
    response = api_client.post("/api/v1/payment/initiate/", {}, format="json")

    assert response.status_code == 400


def test_get_payment_verify_success(auth_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-verify-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "verified"},
    )

    response = auth_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert data["tx_ref"] == payment_tx.tx_ref
    assert "chapa_verification" in data


def test_get_payment_verify_public_success(api_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-verify-public-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "verified"},
    )

    response = api_client.get(f"/api/v1/payment/verify-public/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert data["tx_ref"] == payment_tx.tx_ref
    assert "chapa_verification" in data


def test_put_payment_cancel_success(auth_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-cancel-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.cancel_transaction",
        lambda tx_ref: {"success": True, "message": "Cancelled"},
    )

    response = auth_client.put(f"/api/v1/payment/cancel/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    assert response.json()["message"] == "Cancelled"


def test_post_payment_callback_public_success(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "callback received"},
    )

    response = api_client.get("/api/v1/payment/callback/chapa/?tx_ref=tx-abc")

    assert response.status_code == 200
    assert response.json()["message"] == "callback received"


def test_post_payment_webhook_public_success(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_webhook",
        lambda request: {"success": True, "message": "webhook received"},
    )

    response = api_client.post("/api/v1/payment/webhook/chapa/", {"tx_ref": "tx-abc"}, format="json")

    assert response.status_code == 200
    assert response.json()["message"] == "webhook received"


def test_get_owner_ledger_success(company_client, company, user, room):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-ledger-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
        vendor_company=company,
    )

    response = company_client.get("/api/v1/payment/ledger/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert data["count"] >= 1
    assert any(item["tx_ref"] == payment_tx.tx_ref for item in data["results"])
