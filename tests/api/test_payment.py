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
from tests.conftest import CompanyProfileFactory

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


def _build_car_rental(renter, car_listing):
    rental = CarRental.objects.create(
        renter=renter,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=9),
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="Renter",
        guest_email="guest-renter@example.com",
        guest_phone="0911222333",
        booking_reference="C-000001",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )
    return rental


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


def test_post_payment_initiate_not_found(auth_client):
    response = auth_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": "11111111-1111-1111-1111-111111111111", "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 404


def test_post_payment_initiate_invalid_booking_type(api_client):
    response = api_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": "11111111-1111-1111-1111-111111111111", "booking_type": "unsupported"},
        format="json",
    )

    assert response.status_code == 400
    assert "booking_type" in response.json()


def test_get_payment_verify_unauthenticated(api_client):
    response = api_client.get("/api/v1/payment/verify/tx-auth-required/")

    assert response.status_code == 401


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


def test_get_payment_verify_forbidden_for_wrong_user(company_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-verify-forbidden",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    def fail_if_called(payload):
        raise AssertionError("Unauthorized verification must not trigger callback processing")

    monkeypatch.setattr("apps.payment.views.ChapaPaymentService.handle_callback", fail_if_called)

    response = company_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert response.status_code == 403


def test_get_payment_verify_not_found_returns_stable_payload(auth_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": False, "message": "Transaction missing"},
    )

    response = auth_client.get("/api/v1/payment/verify/tx-missing/")

    assert response.status_code == 200
    assert response.json() == {"chapa_verification": {"success": False, "message": "Transaction missing"}}


def test_get_payment_verify_carrental_owner_uses_generic_booking(auth_client, user, car_listing, monkeypatch):
    rental = _build_car_rental(user, car_listing)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(CarRental),
        object_id=rental.id,
        booking_type="carrental",
        tx_ref="tx-rental-verify",
        amount=Decimal("3000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "verified"},
    )

    response = auth_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    assert response.json()["tx_ref"] == payment_tx.tx_ref


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


def test_get_payment_verify_public_not_found_contract(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": False, "message": "Transaction tx-public-missing not found"},
    )

    response = api_client.get("/api/v1/payment/verify-public/tx-public-missing/")

    assert response.status_code == 200
    data = response.json()
    assert "chapa_verification" in data
    assert data["chapa_verification"]["success"] is False


def test_put_payment_cancel_unauthenticated(api_client):
    response = api_client.put("/api/v1/payment/cancel/tx-auth-required/")

    assert response.status_code == 401


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


def test_put_payment_cancel_forbidden_for_wrong_user(company_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-cancel-forbidden",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    def fail_if_called(tx_ref):
        raise AssertionError("Unauthorized cancellation must not call payment service")

    monkeypatch.setattr("apps.payment.views.ChapaPaymentService.cancel_transaction", fail_if_called)

    response = company_client.put(f"/api/v1/payment/cancel/{payment_tx.tx_ref}/")

    assert response.status_code == 403


def test_put_payment_cancel_not_found(auth_client):
    response = auth_client.put("/api/v1/payment/cancel/tx-missing/")

    assert response.status_code == 404


def test_put_payment_cancel_rejects_non_pending(auth_client, user, room):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-cancel-successful",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    response = auth_client.put(f"/api/v1/payment/cancel/{payment_tx.tx_ref}/")

    assert response.status_code == 400


def test_put_payment_cancel_carrental_owner_uses_generic_booking(auth_client, user, car_listing, monkeypatch):
    rental = _build_car_rental(user, car_listing)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(CarRental),
        object_id=rental.id,
        booking_type="carrental",
        tx_ref="tx-rental-cancel",
        amount=Decimal("3000.00"),
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


def test_get_payment_callback_missing_reference(api_client):
    response = api_client.get("/api/v1/payment/callback/chapa/")

    assert response.status_code == 400
    assert response.json()["error"] == "Missing transaction reference"


def test_get_payment_callback_failure_path(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": False, "message": "Verification failed"},
    )

    response = api_client.get("/api/v1/payment/callback/chapa/?tx_ref=tx-failed")

    assert response.status_code == 400
    assert response.json()["error"] == "Verification failed"


def test_post_payment_webhook_public_success(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_webhook",
        lambda request: {"success": True, "message": "webhook received"},
    )

    response = api_client.post("/api/v1/payment/webhook/chapa/", {"tx_ref": "tx-abc"}, format="json")

    assert response.status_code == 200
    assert response.json()["message"] == "webhook received"


def test_post_payment_webhook_invalid_payload(api_client, settings):
    settings.CHAPA_WEBHOOK_SECRET = "secret"

    response = api_client.post("/api/v1/payment/webhook/chapa/", {}, format="json")

    assert response.status_code == 400
    assert "error" in response.json()


def test_post_payment_webhook_failure_path(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_webhook",
        lambda request: {"success": False, "message": "Invalid signature"},
    )

    response = api_client.post("/api/v1/payment/webhook/chapa/", {"tx_ref": "tx-abc"}, format="json")

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid signature"


def test_get_owner_ledger_unauthenticated(api_client):
    response = api_client.get("/api/v1/payment/ledger/")

    assert response.status_code == 401


def test_get_owner_ledger_forbidden_for_regular_user(auth_client):
    response = auth_client.get("/api/v1/payment/ledger/")

    assert response.status_code == 403


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


def test_get_owner_ledger_detail_success(company_client, company, user, room):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-ledger-detail-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        payment_method="telebirr",
        metadata={},
        vendor_company=company,
        commission_rate=Decimal("0.0500"),
        commission_amount=Decimal("50.00"),
        vendor_payout_amount=Decimal("950.00"),
    )

    response = company_client.get(f"/api/v1/payment/ledger/{payment_tx.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["tx_ref"] == payment_tx.tx_ref
    assert data["status"] == PaymentTransaction.PaymentStatus.SUCCESS
    assert data["amount"] == "1000.00"
    assert data["currency"] == "ETB"
    assert data["payment_method"] == "telebirr"
    assert "booking_reference" in data
    assert "listing_title" in data
    assert "customer_name" in data
    assert "booking_dates" in data
    assert "payout_status" in data


def test_get_owner_ledger_detail_not_found_for_other_owner(company_client, user, room):
    other_company = CompanyProfileFactory(user=user, category=CompanyProfile.CategoryChoice.HOTEL)
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-ledger-other-owner",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
        vendor_company=other_company,
    )

    response = company_client.get(f"/api/v1/payment/ledger/{payment_tx.id}/")

    assert response.status_code == 404
