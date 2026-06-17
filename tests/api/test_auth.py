# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from apps.account.enums import RoleCode
from apps.account.models import OtpChallenge, Role
from apps.account.tasks import OtpChallengeCache, cleanup_expired_otp_challenges
from apps.favorites.models import Favorite, GuestFavorite
from services.sms import normalize_phone_number

pytestmark = pytest.mark.django_db


def test_afromessage_phone_normalization_uses_provider_supported_format():
    assert normalize_phone_number("0980684748") == "251980684748"
    assert normalize_phone_number("+251980684748") == "251980684748"
    assert normalize_phone_number("251980684748") == "251980684748"


def test_post_token_obtain_success(api_client, user):
    cache.clear()
    response = api_client.post(
        "/api/v1/auth/token/",
        {"phone": user.phone, "password": "pass1234"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["access"], str)
    assert isinstance(data["refresh"], str)
    assert data["role"] == user.role.code


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_phone_first_signup_login_and_password_reset_flow(mock_send_sms, mock_generate_code, api_client):
    cache.clear()
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)
    phone = "0911222444"

    signup_response = api_client.post(
        "/api/v1/account/users/",
        {
            "password": "pass1234",
            "confirm_password": "pass1234",
            "first_name": "Phone",
            "last_name": "Flow",
            "phone": phone,
        },
        format="json",
    )

    assert signup_response.status_code == 201, signup_response.json()
    signup_data = signup_response.json()
    assert signup_data["phone"] == phone
    assert signup_data["email"] == f"{phone}@phone.local"
    assert signup_data["verification_required"] == "phone"
    assert signup_data["phone_verification_required"] is True

    verify_response = api_client.post(
        "/api/v1/auth/otp/verify/",
        {
            "challenge_id": signup_data["otp_challenge_id"],
            "code": "123456",
            "purpose": "signup",
        },
        format="json",
    )

    assert verify_response.status_code == 200, verify_response.json()
    verify_data = verify_response.json()
    assert verify_data["success"] is True
    assert verify_data["user"]["is_active"] is True
    assert verify_data["user"]["phone_verified"] is True

    login_response = api_client.post(
        "/api/v1/auth/token/",
        {"phone": phone, "password": "pass1234"},
        format="json",
    )

    assert login_response.status_code == 200, login_response.json()
    assert isinstance(login_response.json()["access"], str)

    reset_response = api_client.post(
        "/api/v1/account/password-reset/",
        {"phone": phone},
        format="json",
    )

    assert reset_response.status_code == 200, reset_response.json()
    reset_data = reset_response.json()
    assert reset_data["phone"] == phone
    assert "challenge_id" in reset_data

    reset_confirm_response = api_client.post(
        "/api/v1/account/password-reset/confirm/",
        {
            "challenge_id": reset_data["challenge_id"],
            "code": "123456",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        },
        format="json",
    )

    assert reset_confirm_response.status_code == 200, reset_confirm_response.json()

    new_login_response = api_client.post(
        "/api/v1/auth/token/",
        {"phone": phone, "password": "newpass123"},
        format="json",
    )

    assert new_login_response.status_code == 200, new_login_response.json()
    assert isinstance(new_login_response.json()["refresh"], str)
    assert mock_send_sms.call_count == 2


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_signup_phone_verification_transfers_guest_favorites(mock_send_sms, mock_generate_code, api_client, hotel):
    cache.clear()
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)
    phone = "0911444555"
    GuestFavorite.objects.create(
        guest_phone=phone,
        content_type=ContentType.objects.get_for_model(hotel.__class__),
        object_id=str(hotel.id),
        snapshot={"id": str(hotel.id), "type": "account.hotelprofile", "title": "Saved Before Signup"},
        snapshot_at=timezone.now(),
    )

    signup_response = api_client.post(
        "/api/v1/account/users/",
        {
            "password": "pass1234",
            "confirm_password": "pass1234",
            "first_name": "Guest",
            "last_name": "Convert",
            "phone": phone,
        },
        format="json",
    )
    assert signup_response.status_code == 201, signup_response.json()

    verify_response = api_client.post(
        "/api/v1/auth/otp/verify/",
        {
            "challenge_id": signup_response.json()["otp_challenge_id"],
            "code": "123456",
            "purpose": "signup",
        },
        format="json",
    )

    assert verify_response.status_code == 200, verify_response.json()
    data = verify_response.json()
    assert data["guest_history_transfer"]["success"] is True
    assert data["guest_history_transfer"]["linked_counts"]["guest_favorites"] == 1
    assert Favorite.objects.filter(
        user_id=data["user"]["id"],
        object_id=str(hotel.id),
    ).exists()


def test_post_token_obtain_front_desk_success_with_phone(api_client, front_desk_user):
    cache.clear()
    response = api_client.post(
        "/api/v1/auth/token/",
        {"phone": front_desk_user.phone, "password": "pass1234"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["access"], str)
    assert isinstance(data["refresh"], str)
    assert data["role"] == front_desk_user.role.code
    assert data["workspace"]["id"] == str(front_desk_user.workspace.id)


def test_post_token_obtain_rejects_email_login(api_client, front_desk_user):
    cache.clear()
    response = api_client.post(
        "/api/v1/auth/token/",
        {"email": front_desk_user.email, "password": "pass1234"},
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()


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


def test_post_otp_verify_login_marks_active_unverified_user_phone_verified(api_client, user):
    user.phone_verified_at = None
    user.is_active = True
    user.save(update_fields=["phone_verified_at", "is_active", "updated_at"])
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
        {
            "challenge_id": str(challenge.id),
            "code": "123456",
            "purpose": "login",
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"]["phone_verified"] is True
    assert isinstance(data["access"], str)
    assert isinstance(data["refresh"], str)
    user.refresh_from_db()
    assert user.phone_verified_at is not None


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
    cache.clear()
    response = api_client.post(
        "/api/v1/auth/token/",
        {"phone": "0999999999", "password": "wrong"},
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
def test_post_otp_request_allows_repeated_requests_without_cooldown(mock_send_sms, mock_generate_code, api_client, user):
    cache.clear()
    first = api_client.post("/api/v1/auth/otp/request/", {"phone": user.phone}, format="json")
    second = api_client.post("/api/v1/auth/otp/request/", {"phone": user.phone}, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cooldown_seconds"] == 0
    assert second.json()["cooldown_seconds"] == 0
    assert first.json()["challenge_id"] != second.json()["challenge_id"]


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


def test_post_otp_verify_guest_challenge_returns_reusable_phone_token(api_client):
    from apps.account.services import GuestPhoneVerificationService

    phone = "0911000777"
    challenge = OtpChallenge.objects.create(
        phone=phone,
        purpose=OtpChallenge.Purpose.GUEST_CAR_SALE_REVEAL,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
    )

    response = api_client.post(
        "/api/v1/auth/otp/verify/",
        {
            "challenge_id": str(challenge.id),
            "code": "123456",
            "purpose": OtpChallenge.Purpose.GUEST_CAR_SALE_REVEAL,
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is None
    assert data["guest_verification_token"]
    assert GuestPhoneVerificationService.verify_token(
        token=data["guest_verification_token"],
        phone=phone,
    )
