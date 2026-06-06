# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
import json

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile, Role, User
from apps.core.models import Address
from apps.listing.models import AddonOffering, StayAvailability

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


def test_get_hotel_detail_public_contract(api_client, hotel):
    response = api_client.get(f"/api/v1/account/hotels/{hotel.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(hotel.id)
    assert "name" in data
    assert "status" in data
    assert "facilities" in data
    assert "images" in data


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
