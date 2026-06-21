from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework import status

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, Role, User
from apps.core.models import Address
from apps.listing.models import EventSpaceListing


pytestmark = pytest.mark.django_db(transaction=True)


def create_address(label: str) -> Address:
    return Address.objects.create(
        street_line1=f"{label} Street",
        city="Addis Ababa",
        sub_city=label,
        country="Ethiopia",
        state="Addis Ababa",
        postal_code="1000",
    )


def create_company_owner(*, suffix: str):
    company_role = Role.objects.get_or_create(name="Company", code=RoleCode.COMPANY.value)[0]
    user = User.objects.create_user(
        email=f"company-{suffix}@example.com",
        password="pass1234",
        phone=f"+251911000{suffix}",
        role=company_role,
    )
    company = CompanyProfile.objects.create(
        user=user,
        name=f"Company {suffix}",
        phone=f"+251922000{suffix}",
        category=CompanyProfile.CategoryChoice.HOTEL,
        address=create_address(f"Company {suffix} HQ"),
        status=CompanyProfile.StatusChoice.APPROVED,
    )
    user.company = company
    user.save(update_fields=["company"])
    return user, company


def create_admin_user():
    admin_role = Role.objects.get_or_create(name="Admin", code=RoleCode.ADMIN.value)[0]
    return User.objects.create_user(
        email="event-space-admin@example.com",
        password="pass1234",
        phone="+251911999999",
        role=admin_role,
    )


def create_hotel(*, company: CompanyProfile, name: str, label: str) -> HotelProfile:
    return HotelProfile.objects.create(
        company=company,
        name=name,
        stars=4,
        address=create_address(label),
        is_active=True,
    )


def event_space_payload(*, hotel_id, title="Grand Ballroom"):
    return {
        "title": title,
        "hotel_id": str(hotel_id),
        "description": "Flexible event venue",
        "base_price": "7500.00",
        "currency": "ETB",
        "number_of_guests": 200,
        "total_units": 2,
        "space_type": EventSpaceListing.SpaceType.CONFERENCE_HALL,
        "floor_area_sqm": 320,
    }


def unwrap_results(data):
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def test_event_space_create_requires_explicit_owned_hotel_and_inherits_hotel_address(api_client):
    owner, company = create_company_owner(suffix="001")
    hotel_one = create_hotel(company=company, name="North Hotel", label="North")
    hotel_two = create_hotel(company=company, name="South Hotel", label="South")

    api_client.force_authenticate(user=owner)
    response = api_client.post(
        reverse("event-spaces-list"),
        event_space_payload(hotel_id=hotel_two.id, title="South Ballroom"),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    created = EventSpaceListing.objects.get(id=response.data["id"])

    assert created.hotel_id == hotel_two.id
    assert created.address_id != hotel_two.address_id
    assert created.address.street_line1 == hotel_two.address.street_line1
    assert created.address.city == hotel_two.address.city
    assert created.address_id != hotel_one.address_id
    assert response.data["hotel_id"] == str(hotel_two.id)
    assert response.data["hotel"] == {"id": str(hotel_two.id), "name": "South Hotel"}
    assert response.data["is_active"] is False


def test_event_space_create_rejects_hotel_owned_by_other_company(api_client):
    owner, _company = create_company_owner(suffix="002")
    _other_owner, other_company = create_company_owner(suffix="003")
    foreign_hotel = create_hotel(company=other_company, name="Foreign Hotel", label="Foreign")

    api_client.force_authenticate(user=owner)
    response = api_client.post(
        reverse("event-spaces-list"),
        event_space_payload(hotel_id=foreign_hotel.id, title="Blocked Hall"),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "You do not have permission to manage this hotel." in str(response.data["hotel_id"])


def test_event_space_managed_responses_show_state_and_activation_requires_verification(api_client):
    owner, company = create_company_owner(suffix="004")
    admin_user = create_admin_user()
    hotel = create_hotel(company=company, name="Managed Hotel", label="Managed")

    api_client.force_authenticate(user=owner)
    create_response = api_client.post(
        reverse("event-spaces-list"),
        event_space_payload(hotel_id=hotel.id, title="Managed Hall"),
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    event_space_id = create_response.data["id"]

    managed_response = api_client.get(reverse("event-spaces-list"), {"managed": "true"})
    assert managed_response.status_code == status.HTTP_200_OK
    managed_results = unwrap_results(managed_response.data)
    assert managed_results[0]["id"] == event_space_id
    assert managed_results[0]["hotel"] == {"id": str(hotel.id), "name": "Managed Hotel"}
    assert managed_results[0]["is_active"] is False

    denied_activation = api_client.patch(
        reverse("event-spaces-detail", args=[event_space_id]),
        {"is_active": True},
        format="json",
    )
    assert denied_activation.status_code == status.HTTP_400_BAD_REQUEST
    assert "Event spaces can only be activated after admin verification." in str(
        denied_activation.data["is_active"]
    )

    api_client.force_authenticate(user=admin_user)
    verify_response = api_client.post(
        reverse("event-spaces-verify", args=[event_space_id]),
        {"verification_note": "Reviewed"},
        format="json",
    )
    assert verify_response.status_code == status.HTTP_200_OK
    assert verify_response.data["is_verified"] is True
    assert verify_response.data["is_active"] is False

    api_client.force_authenticate(user=owner)
    activation_response = api_client.patch(
        reverse("event-spaces-detail", args=[event_space_id]),
        {"is_active": True},
        format="json",
    )
    assert activation_response.status_code == status.HTTP_200_OK
    assert activation_response.data["is_active"] is True
    assert activation_response.data["hotel_id"] == str(hotel.id)


def test_event_space_public_list_and_search_hide_inactive_until_verified_and_activated(api_client):
    owner, company = create_company_owner(suffix="005")
    admin_user = create_admin_user()
    hotel = create_hotel(company=company, name="Public Hotel", label="Public")

    api_client.force_authenticate(user=owner)
    create_response = api_client.post(
        reverse("event-spaces-list"),
        event_space_payload(hotel_id=hotel.id, title="Public Hall"),
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    event_space_id = create_response.data["id"]

    api_client.force_authenticate(user=None)
    public_list_before = api_client.get(reverse("event-spaces-list"))
    assert public_list_before.status_code == status.HTTP_200_OK
    assert event_space_id not in {item["id"] for item in unwrap_results(public_list_before.data)}

    check_in = date.today() + timedelta(days=1)
    check_out = check_in + timedelta(days=1)
    public_search_before = api_client.get(
        reverse("event-spaces-search"),
        {
            "quantity": 1,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
        },
    )
    assert public_search_before.status_code == status.HTTP_200_OK
    assert event_space_id not in {item["id"] for item in public_search_before.data}

    api_client.force_authenticate(user=admin_user)
    verify_response = api_client.post(
        reverse("event-spaces-verify", args=[event_space_id]),
        {"verification_note": "Ready"},
        format="json",
    )
    assert verify_response.status_code == status.HTTP_200_OK

    api_client.force_authenticate(user=owner)
    activation_response = api_client.patch(
        reverse("event-spaces-detail", args=[event_space_id]),
        {"is_active": True},
        format="json",
    )
    assert activation_response.status_code == status.HTTP_200_OK

    api_client.force_authenticate(user=None)
    public_list_after = api_client.get(reverse("event-spaces-list"))
    assert public_list_after.status_code == status.HTTP_200_OK
    assert event_space_id in {item["id"] for item in unwrap_results(public_list_after.data)}

    public_search_after = api_client.get(
        reverse("event-spaces-search"),
        {
            "quantity": 1,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
        },
    )
    assert public_search_after.status_code == status.HTTP_200_OK
    assert event_space_id in {item["id"] for item in public_search_after.data}
