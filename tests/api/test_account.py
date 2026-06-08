# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
import json

from datetime import date, timedelta
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from unittest.mock import patch

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile, OtpChallenge, Role, User
from apps.core.models import Address
from apps.favorites.models import Favorite, GuestFavorite
from apps.notifications.models import Notification
from apps.listing.models import (
    AddonOffering,
    Booking,
    CarRental,
    EventSpaceBooking,
    GuestHouseBooking,
    StayAvailability,
)

pytestmark = pytest.mark.django_db


def _address_payload():
    return {
        "street_line1": "Wollo Sefer",
        "country": "Ethiopia",
        "city": "Addis Ababa",
        "sub_city": "Bole",
        "state": "Addis Ababa",
        "postal_code": "1000",
        "latitude": "9.012345",
        "longitude": "38.765432",
    }


def _assert_verification_fields(payload, *, expected_verified=False, expected_verified_by=None):
    assert "is_verified" in payload
    assert "verified_at" in payload
    assert "verified_by" in payload
    assert payload["is_verified"] is expected_verified
    assert payload["verified_by"] == expected_verified_by


def _individual_owner_payload(phone="0911444555", national_id_number=1234567890):
    return {
        "first_name": "Individual",
        "last_name": "Owner",
        "phone": phone,
        "national_id_number": national_id_number,
        "address": _address_payload(),
    }


def _company_application_client(api_client):
    role, _ = Role.objects.get_or_create(
        name="Company",
        code=RoleCode.COMPANY.value,
    )
    user = User.objects.create_user(
        email="company-apply@example.com",
        password="pass1234",
        role=role,
        is_active=True,
    )
    api_client.force_authenticate(user=user)
    return api_client


def _pending_company_profile(company_user, name="Pending Company"):
    return CompanyProfile.objects.create(
        user=company_user,
        name=name,
        phone="0911222333",
        category="hotel",
        description="Pending approval",
        address=Address.objects.create(
            street_line1="Pending Street",
            country="Ethiopia",
            city="Addis Ababa",
            sub_city="Bole",
            state="Addis Ababa",
            postal_code="1000",
        ),
        status=CompanyProfile.StatusChoice.PENDING,
    )


@patch("apps.account.services.OtpService.generate_code", return_value="123456")
@patch("services.sms.send_sms", return_value=True)
def test_post_user_phone_first_signup_success(mock_send_sms, mock_generate_code, api_client):
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)

    response = api_client.post(
        "/api/v1/account/users/",
        {
            "email": "phone-first@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "first_name": "Phone",
            "last_name": "First",
            "phone": "0911000101",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "phone-first@example.com"
    assert data["phone"] == "0911000101"
    assert data["is_active"] is False
    assert data["phone_verified"] is False
    assert data["phone_verification_required"] is True
    assert data["verification_required"] == "phone"
    assert data["otp_purpose"] == "signup"
    assert "otp_challenge_id" in data
    assert "otp_expires_at" in data
    assert User.objects.filter(email="phone-first@example.com", phone="0911000101").exists()
    mock_send_sms.assert_called_once()


def test_post_user_duplicate_phone_validation(api_client, user):
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)

    response = api_client.post(
        "/api/v1/account/users/",
        {
            "email": "duplicate-phone@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "phone": user.phone,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()


def test_post_signup_otp_verify_activates_user_and_issues_tokens(api_client):
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)
    pending_user = User.objects.create_user(
        email="verify-signup@example.com",
        password="pass1234",
        phone="0911000102",
        is_active=False,
    )
    challenge = OtpChallenge.objects.create(
        user=pending_user,
        phone=pending_user.phone,
        purpose=OtpChallenge.Purpose.SIGNUP,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
    )

    response = api_client.post(
        "/api/v1/auth/otp/verify/",
        {
            "challenge_id": str(challenge.id),
            "code": "123456",
            "purpose": "signup",
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["purpose"] == "signup"
    assert isinstance(data["access"], str)
    assert isinstance(data["refresh"], str)
    assert data["user"]["phone_verified"] is True
    pending_user.refresh_from_db()
    assert pending_user.is_active is True
    assert pending_user.phone_verified_at is not None


def test_post_user_legacy_signup_without_phone_keeps_compatibility(api_client):
    Role.objects.get_or_create(name="User", code=RoleCode.USER.value)

    response = api_client.post(
        "/api/v1/account/users/",
        {
            "email": "legacy-signup@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "first_name": "Legacy",
            "last_name": "Client",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "legacy-signup@example.com"
    assert data["verification_required"] == "email"
    assert data["phone_verification_required"] is False
    assert "registration_warning" in data


def test_patch_me_allows_single_phone_change_and_resets_verification(auth_client, user):
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at", "updated_at"])

    response = auth_client.patch(
        "/api/v1/account/users/me/",
        {"phone": "+251911111222"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    user.refresh_from_db()
    assert data["phone"] == "0911111222"
    assert user.phone == "0911111222"
    assert user.phone_change_count == 1
    assert user.phone_last_changed_at is not None
    assert user.phone_verified_at is None
    assert data["phone_verified"] is False


def test_patch_me_rejects_phone_change_within_cooldown(auth_client, user):
    user.phone_change_count = 1
    user.phone_last_changed_at = timezone.now()
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_change_count", "phone_last_changed_at", "phone_verified_at", "updated_at"])

    response = auth_client.patch(
        "/api/v1/account/users/me/",
        {"phone": "0911222333"},
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()
    user.refresh_from_db()
    assert user.phone == "0900111222"
    assert user.phone_change_count == 1


def test_patch_me_rejects_phone_change_after_maximum(auth_client, user):
    user.phone_change_count = 3
    user.phone_last_changed_at = timezone.now() - timedelta(days=8)
    user.save(update_fields=["phone_change_count", "phone_last_changed_at", "updated_at"])

    response = auth_client.patch(
        "/api/v1/account/users/me/",
        {"phone": "0911333444"},
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()
    user.refresh_from_db()
    assert user.phone == "0900111222"
    assert user.phone_change_count == 3


def test_patch_me_allows_noop_phone_update(auth_client, user):
    user.phone_change_count = 2
    user.phone_last_changed_at = timezone.now() - timedelta(days=8)
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_change_count", "phone_last_changed_at", "phone_verified_at", "updated_at"])

    response = auth_client.patch(
        "/api/v1/account/users/me/",
        {"phone": "+251900111222"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    user.refresh_from_db()
    assert data["phone"] == "0900111222"
    assert user.phone == "0900111222"
    assert user.phone_change_count == 2
    assert user.phone_verified_at is not None


def test_post_convert_guest_bookings_links_matching_guest_history(
    auth_client,
    user,
):
    user.phone = "0911888777"
    user.save(update_fields=["phone", "updated_at"])
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at", "updated_at"])

    hotel_booking = Booking.objects.create(
        guest_first_name="Guest",
        guest_last_name="Hotel",
        guest_email="hotel-guest@example.com",
        guest_phone="0911888777",
        check_in_date=date.today() + timedelta(days=2),
        check_out_date=date.today() + timedelta(days=3),
        total_price="1200.00",
        currency="ETB",
    )
    guesthouse_booking = GuestHouseBooking.objects.create(
        guest_first_name="Guest",
        guest_last_name="House",
        guest_email="guesthouse-guest@example.com",
        guest_phone="0911888777",
        start_date=date.today() + timedelta(days=2),
        end_date=date.today() + timedelta(days=4),
        total_price="1800.00",
        currency="ETB",
    )
    car_rental = CarRental.objects.create(
        guest_first_name="Guest",
        guest_last_name="Car",
        guest_email="car-guest@example.com",
        guest_phone="0911888777",
        start_date=date.today() + timedelta(days=2),
        end_date=date.today() + timedelta(days=4),
        total_price="2400.00",
        currency="ETB",
    )
    event_booking = EventSpaceBooking.objects.create(
        guest_first_name="Guest",
        guest_last_name="Event",
        guest_email="event-guest@example.com",
        guest_phone="0911888777",
        check_in_date=date.today() + timedelta(days=5),
        check_out_date=date.today() + timedelta(days=6),
        total_price="3000.00",
        currency="ETB",
    )

    response = auth_client.post(
        "/api/v1/account/users/me/convert-guest-bookings/",
        {},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["phone"] == "0911888777"
    assert data["verified_via"] == "stored_phone_verification"
    assert data["linked_total"] == 4
    assert data["linked_counts"]["hotel_bookings"] == 1
    assert data["linked_counts"]["guesthouse_bookings"] == 1
    assert data["linked_counts"]["car_rentals"] == 1
    assert data["linked_counts"]["eventspace_bookings"] == 1
    assert data["linked_counts"]["guest_favorites"] == 0

    hotel_booking.refresh_from_db()
    guesthouse_booking.refresh_from_db()
    car_rental.refresh_from_db()
    event_booking.refresh_from_db()
    assert hotel_booking.user == user
    assert guesthouse_booking.renter == user
    assert car_rental.renter == user
    assert event_booking.user == user


def test_post_convert_guest_bookings_is_idempotent(auth_client, user):
    user.phone = "0911777666"
    user.save(update_fields=["phone", "updated_at"])
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at", "updated_at"])

    booking = Booking.objects.create(
        user=user,
        guest_first_name="Guest",
        guest_last_name="Repeat",
        guest_email="repeat@example.com",
        guest_phone="0911777666",
        check_in_date=date.today() + timedelta(days=2),
        check_out_date=date.today() + timedelta(days=3),
        total_price="999.00",
        currency="ETB",
    )

    response = auth_client.post(
        "/api/v1/account/users/me/convert-guest-bookings/",
        {},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["linked_total"] == 0
    assert data["already_linked_total"] == 1
    assert data["already_linked_counts"]["hotel_bookings"] == 1
    booking.refresh_from_db()
    assert booking.user == user


def test_post_convert_guest_bookings_links_guest_favorites(auth_client, user, hotel):
    user.phone = "0911555666"
    user.save(update_fields=["phone", "updated_at"])
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at", "updated_at"])

    guest_favorite = GuestFavorite.objects.create(
        guest_phone="0911555666",
        content_type=ContentType.objects.get_for_model(hotel.__class__),
        object_id=str(hotel.id),
        snapshot={"id": str(hotel.id), "type": "account.hotelprofile", "title": "Saved Hotel"},
        snapshot_at=timezone.now(),
    )

    response = auth_client.post(
        "/api/v1/account/users/me/convert-guest-bookings/",
        {},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["linked_counts"]["guest_favorites"] == 1

    guest_favorite.refresh_from_db()
    assert guest_favorite.linked_user == user
    favorite = Favorite.objects.get(user=user, object_id=str(hotel.id))
    assert favorite.snapshot["id"] == str(hotel.id)


def test_post_convert_guest_bookings_rejects_invalid_otp(auth_client, user):
    user.phone = "0911666555"
    user.phone_verified_at = None
    user.save(update_fields=["phone", "phone_verified_at", "updated_at"])

    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash=make_password("123456"),
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        sent_at=timezone.now(),
    )

    response = auth_client.post(
        "/api/v1/account/users/me/convert-guest-bookings/",
        {
            "otp_challenge_id": str(challenge.id),
            "otp_code": "000000",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_post_convert_guest_bookings_blocks_conflicting_existing_link(auth_client, user, django_user_model):
    user.phone = "0911555444"
    user.save(update_fields=["phone", "updated_at"])
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at", "updated_at"])

    other_user = django_user_model.objects.create_user(
        email="other-link@example.com",
        password="pass1234",
        phone="0911999000",
        is_active=True,
    )
    conflict_booking = Booking.objects.create(
        user=other_user,
        guest_first_name="Conflict",
        guest_last_name="Guest",
        guest_email="conflict@example.com",
        guest_phone="0911555444",
        check_in_date=date.today() + timedelta(days=2),
        check_out_date=date.today() + timedelta(days=3),
        total_price="1400.00",
        currency="ETB",
    )

    response = auth_client.post(
        "/api/v1/account/users/me/convert-guest-bookings/",
        {},
        format="json",
    )

    assert response.status_code == 400
    assert "detail" in response.json()
    conflict_booking.refresh_from_db()
    assert conflict_booking.user == other_user


def test_post_company_application_success(api_client, image_file):
    client = _company_application_client(api_client)
    response = client.post(
        "/api/v1/account/companies/apply/",
        {
            "name": "Blue Sky Hotel Group",
            "phone": "0911000999",
            "category": "hotel",
            "description": "Application created from the baseline suite.",
            "address": json.dumps(_address_payload()),
            "logo": image_file,
        },
        format="multipart",
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] in {"pending", "approved"}
    assert "address" in data
    assert "user" in data
    assert "name" in data
    assert "phone" in data
    assert "category" in data


def test_post_individual_owner_create_admin_success(admin_client):
    response = admin_client.post(
        "/api/v1/account/individual-owners/",
        _individual_owner_payload(),
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["first_name"] == "Individual"
    assert data["last_name"] == "Owner"
    assert data["phone"] == "0911444555"
    assert "id" in data
    assert "address" in data


def test_get_roles_admin_list_success(admin_client, admin_role, user_role):
    response = admin_client.get("/api/v1/account/roles/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    codes = {item["code"] for item in data["results"]}
    assert admin_role.code in codes
    assert user_role.code in codes


def test_post_role_admin_create_success(admin_client):
    response = admin_client.post(
        "/api/v1/account/roles/",
        {"name": "Support", "code": "support"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Support"
    assert data["code"] == "support"


def test_patch_role_admin_update_success(admin_client, user_role):
    response = admin_client.patch(
        f"/api/v1/account/roles/{user_role.id}/",
        {"name": "Customer"},
        format="json",
    )

    assert response.status_code == 200
    user_role.refresh_from_db()
    assert user_role.name == "Customer"


def test_delete_role_admin_delete_success(admin_client):
    role = Role.objects.create(name="Temporary", code="temporary")

    response = admin_client.delete(f"/api/v1/account/roles/{role.id}/")

    assert response.status_code == 204
    assert Role.objects.filter(id=role.id).exists() is False


def test_roles_non_admin_forbidden(auth_client):
    response = auth_client.get("/api/v1/account/roles/")

    assert response.status_code == 403


def test_post_individual_owner_create_public_requires_authentication(api_client):
    response = api_client.post(
        "/api/v1/account/individual-owners/",
        _individual_owner_payload(phone="0911444556", national_id_number=1234567891),
        format="json",
    )

    assert response.status_code == 401


def test_post_individual_owner_create_authenticated_non_admin_forbidden(auth_client):
    response = auth_client.post(
        "/api/v1/account/individual-owners/",
        _individual_owner_payload(phone="0911444557", national_id_number=1234567892),
        format="json",
    )

    assert response.status_code == 403


def test_get_individual_owner_list_public_contract(api_client, individual_owner):
    response = api_client.get("/api/v1/account/individual-owners/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(individual_owner.id)
    assert data["results"][0]["phone"] == individual_owner.phone


def test_get_individual_owner_detail_public_contract(api_client, individual_owner):
    response = api_client.get(f"/api/v1/account/individual-owners/{individual_owner.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(individual_owner.id)
    assert data["phone"] == individual_owner.phone
    assert "address" in data


def test_get_company_list_public_contract(api_client, company):
    response = api_client.get("/api/v1/account/companies/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(company.id)


def test_get_company_detail_public_contract(api_client, company):
    response = api_client.get(f"/api/v1/account/companies/{company.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(company.id)
    assert data["status"] == company.status
    assert "approved_at" in data
    assert "approved_by" in data
    assert "address" in data


def test_post_company_application_unauthenticated(api_client, image_file):
    response = api_client.post(
        "/api/v1/account/companies/apply/",
        {
            "name": "Blue Sky Hotel Group",
            "phone": "0911000998",
            "category": "hotel",
            "description": "Application created from the baseline suite.",
            "address": json.dumps(_address_payload()),
            "logo": image_file,
        },
        format="multipart",
    )

    assert response.status_code == 401


def test_post_company_application_invalid_payload(api_client):
    client = _company_application_client(api_client)
    response = client.post("/api/v1/account/companies/apply/", {}, format="json")

    assert response.status_code == 400
    assert isinstance(response.json(), dict)


def test_post_company_application_unauthenticated_invalid_payload(api_client):
    response = api_client.post("/api/v1/account/companies/apply/", {}, format="json")

    assert response.status_code == 401


def test_post_company_approve_forbidden_for_non_admin(auth_client, company):
    response = auth_client.post(f"/api/v1/account/companies/{company.id}/approve/")

    assert response.status_code == 403


def test_post_company_approve_unauthenticated(api_client, company):
    response = api_client.post(f"/api/v1/account/companies/{company.id}/approve/")

    assert response.status_code == 401


def test_post_company_approve_success(admin_client, admin_user, company_user):
    pending_profile = _pending_company_profile(company_user)

    response = admin_client.post(f"/api/v1/account/companies/{pending_profile.id}/approve/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["approved_by"] is not None
    assert data["approved_at"] is not None
    pending_profile.refresh_from_db()
    assert pending_profile.status == CompanyProfile.StatusChoice.APPROVED
    assert pending_profile.approved_by == admin_user


def test_post_company_reject_success(admin_client):
    user = User.objects.create_user(email="reject@example.com", password="pass1234")
    profile = _pending_company_profile(user, name="Reject Company")

    response = admin_client.post(
        f"/api/v1/account/companies/{profile.id}/reject/",
        {"reason": "Incomplete documents"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    profile.refresh_from_db()
    assert profile.status == CompanyProfile.StatusChoice.REJECTED
    assert profile.rejection_reason == "Incomplete documents"


def test_post_company_reject_forbidden_for_non_admin(auth_client, company):
    response = auth_client.post(
        f"/api/v1/account/companies/{company.id}/reject/",
        {"reason": "Missing documents"},
        format="json",
    )

    assert response.status_code == 403


def test_post_company_reject_unauthenticated(api_client, company):
    response = api_client.post(
        f"/api/v1/account/companies/{company.id}/reject/",
        {"reason": "Missing documents"},
        format="json",
    )

    assert response.status_code == 401


def test_post_company_approve_not_found(admin_client):
    response = admin_client.post("/api/v1/account/companies/00000000-0000-0000-0000-000000000000/approve/")

    assert response.status_code == 404


def test_post_company_reject_not_found(admin_client):
    response = admin_client.post(
        "/api/v1/account/companies/00000000-0000-0000-0000-000000000000/reject/",
        {"reason": "Missing"},
        format="json",
    )

    assert response.status_code == 404


def test_get_hotel_list_public_contract(api_client, hotel):
    response = api_client.get("/api/v1/account/hotels/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert isinstance(data["results"], list)
    assert data["results"][0]["id"] == str(hotel.id)
    _assert_verification_fields(data["results"][0])


def test_get_hotel_detail_public_contract(api_client, hotel):
    response = api_client.get(f"/api/v1/account/hotels/{hotel.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(hotel.id)
    assert "name" in data
    assert "status" in data
    assert "facilities" in data
    assert "images" in data
    _assert_verification_fields(data)


def test_get_hotel_list_excludes_inactive_hotel(api_client, company):
    inactive_hotel = HotelProfile.objects.create(
        company=company,
        name="Inactive Hotel",
        address=Address.objects.create(**_address_payload()),
        is_active=False,
    )

    response = api_client.get("/api/v1/account/hotels/")

    assert response.status_code == 200
    data = response.json()
    assert all(item["id"] != str(inactive_hotel.id) for item in data["results"])


def test_post_hotel_create_unauthenticated(api_client, image_file):
    response = api_client.post(
        "/api/v1/account/hotels/",
        {
            "name": "Creations Hotel",
            "description": "Hotel created in tests",
            "phone": "0911222555",
            "website": "https://example.com",
            "address": json.dumps(_address_payload()),
            "stars": 4,
            "featured": False,
            "facilities": json.dumps([]),
            "logo": image_file,
        },
        format="multipart",
    )

    assert response.status_code == 401


def test_post_hotel_create_forbidden_for_non_owner(auth_client, image_file):
    response = auth_client.post(
        "/api/v1/account/hotels/",
        {
            "name": "Creations Hotel",
            "description": "Hotel created in tests",
            "phone": "0911222556",
            "website": "https://example.com",
            "address": json.dumps(_address_payload()),
            "stars": 4,
            "featured": False,
            "facilities": json.dumps([]),
            "logo": image_file,
        },
        format="multipart",
    )

    assert response.status_code == 403


def test_post_hotel_create_success(company_client, company, image_file):
    response = company_client.post(
        "/api/v1/account/hotels/",
        {
            "name": "Creations Hotel",
            "description": "Hotel created in tests",
            "phone": "0911222557",
            "website": "https://example.com",
            "address": json.dumps(_address_payload()),
            "stars": 4,
            "featured": False,
            "facilities": json.dumps([]),
            "logo": image_file,
        },
        format="multipart",
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == company.name
    assert data["is_active"] is False
    hotel_profile = HotelProfile.objects.get(id=data["id"])
    assert hotel_profile.is_active is False


def test_patch_hotel_success(company_client, hotel):
    response = company_client.patch(
        f"/api/v1/account/hotels/{hotel.id}/",
        {"name": "Updated Hotel Name"},
        format="json",
    )

    assert response.status_code == 200
    hotel.refresh_from_db()
    assert hotel.name == "Updated Hotel Name"
    assert "name" in response.json()


def test_patch_hotel_forbidden_for_non_owner(auth_client, hotel):
    response = auth_client.patch(
        f"/api/v1/account/hotels/{hotel.id}/",
        {"name": "Updated Hotel Name"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_hotel_success(company_client, hotel):
    response = company_client.delete(f"/api/v1/account/hotels/{hotel.id}/")

    assert response.status_code == 204


@patch("services.sms.send_sms", return_value=True)
def test_delete_hotel_notifies_saved_users_and_guest_phones(mock_send_sms, company_client, hotel, booking):
    saved_user = User.objects.create_user(email="saved-user@example.com", password="pass1234")
    booked_user = booking.user
    content_type = ContentType.objects.get_for_model(hotel.__class__)

    Favorite.objects.create(
        user=saved_user,
        content_type=content_type,
        object_id=str(hotel.id),
    )
    Favorite.objects.create(
        user=booked_user,
        content_type=content_type,
        object_id=str(hotel.id),
    )
    GuestFavorite.objects.create(
        guest_phone="0911223344",
        content_type=content_type,
        object_id=str(hotel.id),
    )
    GuestFavorite.objects.create(
        guest_phone=booking.guest_phone,
        content_type=content_type,
        object_id=str(hotel.id),
    )

    response = company_client.delete(f"/api/v1/account/hotels/{hotel.id}/")

    assert response.status_code == 204
    assert (
        Notification.objects.filter(
            user=saved_user,
            notification_type=Notification.NotificationType.LISTING_DELETED,
            metadata__listing_id=str(hotel.id),
        ).count()
        == 1
    )
    assert (
        Notification.objects.filter(
            user=booked_user,
            notification_type=Notification.NotificationType.LISTING_DELETED,
            metadata__listing_id=str(hotel.id),
        ).count()
        == 0
    )
    mock_send_sms.assert_called_once()
    assert mock_send_sms.call_args.args[0] == "0911223344"
    assert "no longer available" in mock_send_sms.call_args.args[1]


def test_get_hotel_check_availability_public_contract(api_client, hotel, room):
    StayAvailability.objects.create(hotel=hotel, room=room, date="2026-06-10", available_rooms=2)
    response = api_client.get(
        f"/api/v1/account/hotels/{hotel.id}/check_availability/",
        {"check_in_date": "2026-06-10", "check_out_date": "2026-06-12"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["hotel_id"] == str(hotel.id)
    assert data["check_in"] == "2026-06-10"
    assert isinstance(data["rooms"], list)


def test_get_hotel_featured_public_contract(api_client, hotel):
    hotel.featured = True
    hotel.save(update_fields=["featured"])

    response = api_client.get("/api/v1/account/hotels/featured/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["id"] == str(hotel.id)


def test_post_hotel_verify_success(admin_client, admin_user, hotel):
    response = admin_client.post(f"/api/v1/account/hotels/{hotel.id}/verify/")

    assert response.status_code == 200
    hotel.refresh_from_db()
    assert hotel.is_verified is True
    assert hotel.verified_by == admin_user
    assert hotel.verified_at is not None
    _assert_verification_fields(
        response.json(),
        expected_verified=True,
        expected_verified_by=str(admin_user.id),
    )


def test_post_hotel_unverify_success(admin_client, hotel, admin_user):
    hotel.is_verified = True
    hotel.verified_at = timezone.now()
    hotel.verified_by = admin_user
    hotel.save(update_fields=["is_verified", "verified_at", "verified_by"])

    response = admin_client.post(f"/api/v1/account/hotels/{hotel.id}/unverify/")

    assert response.status_code == 200
    hotel.refresh_from_db()
    assert hotel.is_verified is False
    assert hotel.verified_at is None
    assert hotel.verified_by is None
    _assert_verification_fields(response.json())


def test_post_hotel_deactivate_success(admin_client, hotel):
    response = admin_client.post(f"/api/v1/account/hotels/{hotel.id}/deactivate/")

    assert response.status_code == 200
    hotel.refresh_from_db()
    assert hotel.is_active is False
    assert response.json()["is_active"] is False


def test_post_hotel_activate_success(admin_client, hotel):
    hotel.is_active = False
    hotel.save(update_fields=["is_active"])

    response = admin_client.post(f"/api/v1/account/hotels/{hotel.id}/activate/")

    assert response.status_code == 200
    hotel.refresh_from_db()
    assert hotel.is_active is True
    assert response.json()["is_active"] is True


def test_post_hotel_verify_forbidden_for_non_admin(company_client, hotel):
    response = company_client.post(f"/api/v1/account/hotels/{hotel.id}/verify/")

    assert response.status_code == 403


def test_get_hotel_addons_owner_only(company_client, hotel, addon):
    addon.hotel = hotel
    addon.save(update_fields=["hotel"])

    response = company_client.get(f"/api/v1/account/hotels/{hotel.id}/addons/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["id"] == str(addon.id)


def test_get_hotel_addons_excludes_inactive(company_client, hotel, addon):
    addon.hotel = hotel
    addon.is_active = False
    addon.save(update_fields=["hotel", "is_active"])

    response = company_client.get(f"/api/v1/account/hotels/{hotel.id}/addons/")

    assert response.status_code == 200
    assert response.json() == []


def test_get_hotel_addons_forbidden_for_non_owner(auth_client, hotel):
    response = auth_client.get(f"/api/v1/account/hotels/{hotel.id}/addons/")

    assert response.status_code in {401, 403}


def test_get_available_workspaces_for_company_owner(company_client, hotel):
    response = company_client.get("/api/v1/account/staff/available-workspaces/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(item["id"] == str(hotel.id) for item in data)


def test_get_available_workspaces_for_non_owner_forbidden(auth_client):
    response = auth_client.get("/api/v1/account/staff/available-workspaces/")

    assert response.status_code in {401, 403}


def test_post_password_reset_public(api_client):
    response = api_client.post(
        "/api/v1/account/password-reset/",
        {"email": "user@example.com"},
        format="json",
    )

    assert response.status_code == 200
    assert "detail" in response.json()


def test_post_password_reset_confirm_public_invalid_payload(api_client):
    response = api_client.post("/api/v1/account/password-reset/confirm/", {}, format="json")

    assert response.status_code == 400


def test_post_verify_email_public_invalid_payload(api_client):
    response = api_client.post("/api/v1/account/verify-email/", {}, format="json")

    assert response.status_code == 400


def test_post_verify_email_change_public_invalid_payload(api_client):
    response = api_client.post("/api/v1/account/verify-email-change/", {}, format="json")

    assert response.status_code == 400
