# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.account.enums import RoleCode
from apps.account.models import HotelProfile
from apps.account.models import OtpChallenge, Role
from apps.core.models import CurrencyRate
from apps.listing.models import Booking, BookingItem, TermsAndConditions
from apps.payment.models import PaymentTransaction

pytestmark = pytest.mark.django_db


def _assert_verification_fields(payload):
    assert "is_verified" in payload
    assert "verified_at" in payload
    assert "verified_by" in payload


def test_flutter_contract_auth_me(auth_client, user):
    response = auth_client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    data = response.json()
    for key in ["id", "email", "first_name", "last_name", "phone", "is_active", "role", "workspace"]:
        assert key in data


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_flutter_contract_auth_otp_request(mock_send_sms, mock_generate_code, api_client, user):
    response = api_client.post(
        "/api/v1/auth/otp/request/",
        {"phone": user.phone},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["success", "challenge_id", "purpose", "expires_at", "phone"]:
        assert key in data


def test_flutter_contract_auth_otp_verify(api_client, user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
    )

    response = api_client.post(
        "/api/v1/auth/otp/verify/",
        {"challenge_id": str(challenge.id), "code": "123456"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["success", "purpose", "user", "access", "refresh", "role"]:
        assert key in data
    for key in ["id", "email", "first_name", "last_name", "phone", "is_active", "role", "workspace"]:
        assert key in data["user"]


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_flutter_contract_phone_first_signup(mock_send_sms, mock_generate_code, api_client):
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)

    response = api_client.post(
        "/api/v1/account/users/",
        {
            "email": "flutter-signup@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "first_name": "Flutter",
            "last_name": "Signup",
            "phone": "0911000201",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    for key in [
        "id",
        "email",
        "first_name",
        "last_name",
        "phone",
        "phone_verified",
        "phone_verified_at",
        "is_active",
        "role",
        "workspace",
        "verification_required",
        "phone_verification_required",
        "otp_challenge_id",
        "otp_expires_at",
        "otp_purpose",
    ]:
        assert key in data
    assert data["verification_required"] == "phone"
    assert data["phone_verification_required"] is True
    assert data["otp_purpose"] == "signup"


def test_flutter_contract_convert_guest_bookings(auth_client, user):
    user.phone = "0911444333"
    user.save(update_fields=["phone", "updated_at"])
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at", "updated_at"])

    response = auth_client.post(
        "/api/v1/account/users/me/convert-guest-bookings/",
        {},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in [
        "success",
        "phone",
        "verified_via",
        "linked_counts",
        "already_linked_counts",
        "linked_total",
        "already_linked_total",
    ]:
        assert key in data


def test_flutter_contract_core_currency_convert(api_client):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"), date=date.today())
    response = api_client.post(
        "/api/v1/core/currency/convert/",
        {"base": "USD", "target": "ETB", "amount": "10", "date": date.today().isoformat()},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["status", "input_amount", "base", "target", "converted_amount", "rate_date", "rate_used"]:
        assert key in data


def test_flutter_contract_core_currencies_list(api_client):
    response = api_client.get("/api/v1/core/currencies/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data
    for key in ["code", "name"]:
        assert key in data[0]


def test_flutter_contract_core_currency_rates(api_client):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"), date=date.today())
    response = api_client.get("/api/v1/core/currencies/rates/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "ETB" in data
    assert "USD" in data


def test_flutter_contract_account_hotels(api_client, hotel):
    response = api_client.get("/api/v1/account/hotels/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data and "results" in data
    assert isinstance(data["results"], list)
    _assert_verification_fields(data["results"][0])


def test_flutter_contract_listing_verification_fields(
    api_client,
    guest_house,
    car_listing,
    property_listing,
    event_space,
):
    endpoints = [
        f"/api/v1/listing/guest-houses/{guest_house.id}/",
        f"/api/v1/listing/cars/{car_listing.id}/",
        f"/api/v1/listing/properties/{property_listing.id}/",
        f"/api/v1/listing/event-spaces/{event_space.id}/",
    ]

    for endpoint in endpoints:
        response = api_client.get(endpoint)
        assert response.status_code == 200
        _assert_verification_fields(response.json())


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


def test_flutter_contract_listing_company_terms(api_client, company):
    terms = TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(company),
        object_id=company.id,
        version=1,
        title="Company Terms",
        content="Company terms content",
        effective_date=date.today(),
        is_active=True,
    )

    response = api_client.get(f"/api/v1/listing/terms/company/{company.id}/")

    assert response.status_code == 200
    data = response.json()
    for key in ["id", "version", "title", "content", "effective_date", "is_active"]:
        assert key in data
    assert data["id"] == str(terms.id)


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
    assert "snapshot" in data["results"][0]


def test_flutter_contract_guest_favorites_list(api_client, hotel):
    response = api_client.post(
        "/api/v1/favorites/guest/",
        {
            "guest_phone": "0911223344",
            "content_type": "account.hotelprofile",
            "object_id": str(hotel.id),
        },
        format="json",
    )
    assert response.status_code == 201

    response = api_client.get("/api/v1/favorites/guest/", {"guest_phone": "0911223344"})

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    for key in ["id", "guest_phone", "object_id", "content_type_display", "snapshot", "object", "created_at"]:
        assert key in data["results"][0]


def test_flutter_contract_notifications_list(auth_client, notification):
    response = auth_client.get("/api/v1/notifications/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    item = data["results"][0]
    for key in [
        "id",
        "notification_type",
        "notification_type_display",
        "title",
        "message",
        "action_url",
        "metadata",
        "is_read",
        "read_at",
        "priority",
        "priority_display",
        "created_at",
        "delivered_in_app",
        "delivered_email",
        "delivered_sms",
        "delivered_push",
        "email_sent_at",
        "sms_sent_at",
        "push_sent_at",
    ]:
        assert key in item


def test_flutter_contract_notification_preferences(auth_client, notification_preference):
    response = auth_client.get("/api/v1/notifications/preferences/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    for key in [
        "email_preferences",
        "in_app_preferences",
        "sms_preferences",
        "push_preferences",
        "email_enabled",
        "sms_enabled",
        "push_enabled",
    ]:
        assert key in data["data"]


def test_flutter_contract_analytics_overview(company_client):
    response = company_client.get("/api/v1/analytics/company/overview/")

    assert response.status_code == 200
    data = response.json()
    assert "total_revenue" in data
    assert "total_bookings" in data


def test_flutter_contract_analytics_frontdesk_stats(company_client, hotel):
    response = company_client.get(
        "/api/v1/analytics/frontdesk/stats/",
        {"workspace_id": str(hotel.id), "workspace_type": "hotel"},
    )

    assert response.status_code == 200
    data = response.json()
    for key in ["arrivals_today", "departures_today", "in_house_count", "availability_percent", "total_rooms", "occupied_rooms"]:
        assert key in data


def test_flutter_contract_analytics_frontdesk_availability(company_client, hotel):
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
