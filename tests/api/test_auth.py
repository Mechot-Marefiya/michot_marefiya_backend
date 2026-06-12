# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
import time
from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from apps.account.models import OtpChallenge
from apps.account.tasks import OtpChallengeCache, cleanup_expired_otp_challenges
from services.sms import normalize_phone_number

pytestmark = pytest.mark.django_db


def test_afromessage_phone_normalization_uses_provider_supported_format():
    assert normalize_phone_number("0980684748") == "251980684748"
    assert normalize_phone_number("+251980684748") == "251980684748"
    assert normalize_phone_number("251980684748") == "251980684748"


def test_post_token_obtain_success(api_client, user):
    response = api_client.post(
        "/api/v1/auth/token/",
        {"email": user.email, "password": "pass1234"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["access"], str)
    assert isinstance(data["refresh"], str)
    assert data["role"] == user.role.code


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_post_otp_request_success(mock_send_sms, mock_generate_code, api_client, user):
    response = api_client.post(
        "/api/v1/auth/otp/request/",
        {"phone": user.phone},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["purpose"] == "login"
    assert data["phone"] == user.phone
    assert "challenge_id" in data
    assert "expires_at" in data
    mock_send_sms.assert_called_once()


@patch("services.sms.send_sms", return_value=True)
def test_post_otp_request_missing_phone_account(mock_send_sms, api_client):
    response = api_client.post(
        "/api/v1/auth/otp/request/",
        {"phone": "0999999999"},
        format="json",
    )

    assert response.status_code == 400
    assert "detail" in response.json()
    mock_send_sms.assert_not_called()


def test_post_otp_verify_login_success(api_client, user):
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
    assert data["success"] is True
    assert data["purpose"] == "login"
    assert isinstance(data["access"], str)
    assert isinstance(data["refresh"], str)
    assert data["role"] == user.role.code
    assert data["user"]["phone"] == user.phone
    challenge.refresh_from_db()
    assert challenge.consumed_at is not None


def test_post_otp_verify_invalid_code(api_client, user):
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
        {"challenge_id": str(challenge.id), "code": "000000"},
        format="json",
    )

    assert response.status_code == 400
    assert "detail" in response.json()
    challenge.refresh_from_db()
    assert challenge.attempts == 1


def test_post_token_obtain_invalid_credentials(api_client):
    response = api_client.post(
        "/api/v1/auth/token/",
        {"email": "missing@example.com", "password": "wrong"},
        format="json",
    )

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_post_change_password_with_phone_otp_success(auth_client, user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.PASSWORD_CHANGE,
        code_hash=make_password("654321"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
    )

    response = auth_client.post(
        "/api/v1/account/users/me/change-password/",
        {
            "otp_challenge_id": str(challenge.id),
            "otp_code": "654321",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        },
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("newpass123") is True
    challenge.refresh_from_db()
    assert challenge.consumed_at is not None


def test_post_token_refresh_success(api_client, user):
    refresh = str(RefreshToken.for_user(user))
    response = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": refresh},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["access"], str)


def test_post_token_refresh_invalid_payload(api_client):
    response = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": "invalid"},
        format="json",
    )

    assert response.status_code in {400, 401}
    assert isinstance(response.json(), dict)


def test_post_logout_success(api_client, user):
    refresh = str(RefreshToken.for_user(user))
    response = api_client.post("/api/v1/auth/logout/", {"refresh": refresh}, format="json")

    assert response.status_code == 200
    assert response.content == b""


def test_post_logout_invalid_payload(api_client):
    response = api_client.post("/api/v1/auth/logout/", {}, format="json")

    assert response.status_code == 400


def test_get_me_unauthenticated(api_client):
    response = api_client.get("/api/v1/auth/me/")

    assert response.status_code == 401


def test_get_me_success(auth_client, user):
    response = auth_client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user.email
    assert "id" in data
    assert "role" in data
    assert "workspace" in data


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_post_otp_request_returns_alias_and_never_plain_code(mock_send_sms, mock_generate_code, api_client, user):
    response = api_client.post(
        "/api/v1/auth/otp/request/",
        {"phone": user.phone},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["challenge_token"] == data["challenge_id"]
    assert data["cooldown_seconds"] >= 0
    assert "code" not in data
    assert "code_hash" not in data


@patch("apps.account.services.send_otp_sms_task.apply")
@patch("apps.account.services.OtpService.generate_code", return_value="123456")
def test_post_otp_request_dispatches_sms_task(mock_generate_code, mock_task_apply, api_client, user):
    cache.clear()
    response = api_client.post(
        "/api/v1/auth/otp/request/",
        {"phone": user.phone},
        format="json",
    )

    assert response.status_code == 200
    mock_task_apply.assert_called_once()


@patch("apps.account.services.send_otp_sms_task.apply", side_effect=RuntimeError("queue down"))
@patch("apps.account.services.OtpService.generate_code", return_value="123456")
def test_post_otp_request_sms_dispatch_failure_returns_400_not_500(mock_generate_code, mock_task_apply, api_client, user):
    response = api_client.post(
        "/api/v1/auth/otp/request/",
        {"phone": user.phone},
        format="json",
    )

    assert response.status_code == 400
    assert "detail" in response.json()


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_post_otp_request_cooldown_blocks_second_request(mock_send_sms, mock_generate_code, api_client, user):
    cache.clear()
    first = api_client.post("/api/v1/auth/otp/request/", {"phone": user.phone}, format="json")
    second = api_client.post("/api/v1/auth/otp/request/", {"phone": user.phone}, format="json")

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["detail"] == "Please wait before requesting another OTP."


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_post_otp_request_allows_request_after_cooldown_expires(mock_send_sms, mock_generate_code, api_client, user, settings):
    cache.clear()
    settings.OTP_COOLDOWN_SECONDS = 1
    first = api_client.post("/api/v1/auth/otp/request/", {"phone": user.phone}, format="json")
    time.sleep(1.1)
    second = api_client.post("/api/v1/auth/otp/request/", {"phone": user.phone}, format="json")

    assert first.status_code == 200
    assert second.status_code == 200


@pytest.mark.parametrize("challenge_factory", ["wrong_code", "expired", "consumed", "locked"])
def test_post_otp_verify_returns_generic_error_for_all_failures(api_client, user, challenge_factory):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
    )
    payload = {"challenge_id": str(challenge.id), "code": "000000"}

    if challenge_factory == "expired":
        challenge.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        challenge.save(update_fields=["expires_at", "updated_at"])
        payload["code"] = "123456"
    elif challenge_factory == "consumed":
        challenge.consumed_at = timezone.now()
        challenge.save(update_fields=["consumed_at", "updated_at"])
        payload["code"] = "123456"
    elif challenge_factory == "locked":
        challenge.attempts = challenge.max_attempts
        challenge.save(update_fields=["attempts", "updated_at"])
        payload["code"] = "123456"

    response = api_client.post("/api/v1/auth/otp/verify/", payload, format="json")

    assert response.status_code == 400
    assert response.json()["detail"] == ["Invalid OTP challenge or code."]


def test_post_otp_verify_consumed_challenge_rejected_even_with_correct_code(api_client, user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        consumed_at=timezone.now(),
        sent_at=timezone.now(),
    )

    response = api_client.post(
        "/api/v1/auth/otp/verify/",
        {"challenge_id": str(challenge.id), "code": "123456"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == ["Invalid OTP challenge or code."]


def test_post_otp_verify_locks_after_max_attempts(api_client, user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
        max_attempts=2,
    )

    for _ in range(2):
        response = api_client.post(
            "/api/v1/auth/otp/verify/",
            {"challenge_id": str(challenge.id), "code": "000000"},
            format="json",
        )
        assert response.status_code == 400

    challenge.refresh_from_db()
    assert challenge.attempts == 2

    locked = api_client.post(
        "/api/v1/auth/otp/verify/",
        {"challenge_id": str(challenge.id), "code": "123456"},
        format="json",
    )
    assert locked.status_code == 400
    assert locked.json()["detail"] == ["Invalid OTP challenge or code."]


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_guest_booking_purpose_is_supported_in_shared_service(mock_send_sms, mock_generate_code):
    from apps.account.services import OtpService

    challenge = OtpService.create_challenge(
        phone="0911000555",
        purpose=OtpChallenge.Purpose.GUEST_HOTEL_BOOKING,
    )

    assert challenge.user is None
    assert challenge.purpose == OtpChallenge.Purpose.GUEST_HOTEL_BOOKING
