from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile, Role, User
from apps.core.models import Address
from apps.listing.models import CarListing, EventSpaceListing, GuestHouseProfile


pytestmark = pytest.mark.django_db


def create_address(street_line1):
    return Address.objects.create(
        street_line1=street_line1,
        city="Addis Ababa",
        country="Ethiopia",
    )


def create_company_user():
    company_role = Role.objects.get_or_create(name="Company", code=RoleCode.COMPANY.value)[0]
    user = User.objects.create_user(
        email="company-owner@example.com",
        password="pass1234",
        phone="+251911000001",
        role=company_role,
    )
    company = CompanyProfile.objects.create(
        user=user,
        name="Workspace Co",
        phone="+251911000002",
        category=CompanyProfile.CategoryChoice.HOTEL,
        address=create_address("Company HQ"),
        status=CompanyProfile.StatusChoice.APPROVED,
    )
    user.company = company
    user.save(update_fields=["company"])
    return user, company


def create_individual_owner_user():
    normal_role = Role.objects.get_or_create(name="User", code=RoleCode.USER.value)[0]
    owner = IndividualOwnerProfile.objects.create(
        first_name="Abebe",
        last_name="Bekele",
        phone="+251911000010",
        address=create_address("Owner Address"),
    )
    user = User.objects.create_user(
        email="owner@example.com",
        password="pass1234",
        phone="+251911000011",
        role=normal_role,
    )
    user.individual_owner = owner
    user.save(update_fields=["individual_owner"])
    return user, owner


def create_guesthouse(*, company=None, individual_owner=None, title="Guest House"):
    return GuestHouseProfile.objects.create(
        company=company,
        individual_owner=individual_owner,
        address=create_address(f"{title} Address"),
        title=title,
        base_price=Decimal("1500.00"),
        currency="ETB",
        is_active=True,
    )


def create_rental_car(*, company=None, individual_owner=None, model="Corolla", listing_type=None):
    return CarListing.objects.create(
        title=f"Toyota {model}",
        company=company,
        individual_owner=individual_owner,
        brand=CarListing.CarBrandChoices.TOYOTA,
        model=model,
        year=2023,
        mileage=10000,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        base_price=Decimal("2000.00"),
        currency="ETB",
        listing_type=listing_type or CarListing.ListingTypeChoices.RENT,
        rental_mode=CarListing.RentalModeChoices.WITH_DRIVER,
        car_class=CarListing.CarClassChoices.NORMAL,
        condition=CarListing.ConditionChoices.USED,
        quantity=2,
        seats=4,
        is_active=True,
    )


def create_event_space(hotel, title="Grand Hall"):
    return EventSpaceListing.objects.create(
        hotel=hotel,
        address=create_address(f"{title} Address"),
        title=title,
        base_price=Decimal("5000.00"),
        currency="ETB",
        space_type=EventSpaceListing.SpaceType.CONFERENCE_HALL,
        number_of_guests=100,
        is_active=True,
    )


def test_company_available_workspaces_include_supported_workspace_types(api_client):
    user, company = create_company_user()
    hotel = HotelProfile.objects.create(company=company, name="Sky Hotel", stars=4)
    create_guesthouse(company=company, title="Blue Guesthouse")
    create_rental_car(company=company, model="Corolla")
    create_rental_car(company=company, model="X5", listing_type=CarListing.ListingTypeChoices.SELL)
    create_event_space(hotel, title="Grand Hall")

    api_client.force_authenticate(user=user)
    response = api_client.get(reverse("staff-available-workspaces"))

    assert response.status_code == 200
    assert {(item["type"], item["name"]) for item in response.data} == {
        ("hotel", "Sky Hotel"),
        ("guesthouse", "Blue Guesthouse"),
        ("car_rental", "toyota Corolla"),
        ("event_space", "Grand Hall"),
    }


@patch("apps.account.serializers.send_sms", return_value=True)
def test_company_profile_fallback_can_still_assign_staff(mock_send_sms, api_client):
    user, company = create_company_user()
    user.company = None
    user.save(update_fields=["company"])
    hotel = HotelProfile.objects.create(company=company, name="Fallback Hotel", stars=4)

    api_client.force_authenticate(user=user)

    response = api_client.get(reverse("staff-available-workspaces"))
    assert response.status_code == 200
    assert response.data[0]["type"] == "hotel"
    assert response.data[0]["name"] == "Fallback Hotel"

    create_response = api_client.post(
        reverse("staff-list"),
        {
            "first_name": "Front",
            "last_name": "Desk",
            "phone": "+251911000014",
            "workspace_id": str(hotel.id),
            "workspace_type": "hotel",
        },
        format="json",
    )

    assert create_response.status_code == 201
    created_staff = User.objects.get(phone="0911000014")
    assert created_staff.company_id == company.id
    assert created_staff.workspace_object_id == hotel.id
    assert mock_send_sms.called


@patch("apps.account.serializers.send_sms", return_value=True)
def test_individual_owner_can_view_workspaces_and_create_staff(mock_send_sms, api_client):
    user, owner = create_individual_owner_user()
    create_guesthouse(individual_owner=owner, title="Owner Guesthouse")
    rent_car = create_rental_car(individual_owner=owner, model="Yaris")
    sale_car = create_rental_car(
        individual_owner=owner,
        model="Camry",
        listing_type=CarListing.ListingTypeChoices.SELL,
    )

    api_client.force_authenticate(user=user)

    workspace_response = api_client.get(reverse("staff-available-workspaces"))
    assert workspace_response.status_code == 200
    assert {(item["type"], item["name"]) for item in workspace_response.data} == {
        ("guesthouse", "Owner Guesthouse"),
        ("car_rental", "toyota Yaris"),
    }

    create_response = api_client.post(
        reverse("staff-list"),
        {
            "first_name": "Rental",
            "last_name": "Agent",
            "phone": "+251911000012",
            "workspace_id": str(rent_car.id),
            "workspace_type": "car_rental",
        },
        format="json",
    )

    assert create_response.status_code == 201
    created_staff = User.objects.get(phone="0911000012")
    assert created_staff.role.code == RoleCode.FRONT_DESK.value
    assert created_staff.individual_owner_id == owner.id
    assert created_staff.workspace_object_id == rent_car.id

    invalid_response = api_client.post(
        reverse("staff-list"),
        {
            "first_name": "Wrong",
            "last_name": "Workspace",
            "phone": "+251911000013",
            "workspace_id": str(sale_car.id),
            "workspace_type": "car_rental",
        },
        format="json",
    )

    assert invalid_response.status_code == 400
    assert "Only rent car listings can be assigned as car-rental workspaces." in str(
        invalid_response.data["workspace_id"]
    )

    list_response = api_client.get(reverse("staff-list"))
    assert list_response.status_code == 200
    assert list_response.data["results"][0]["workspace"] == {
        "id": str(rent_car.id),
        "name": "toyota Yaris",
        "workspace_type": "car_rental",
    }
    assert mock_send_sms.called


@patch("apps.account.serializers.send_sms", return_value=True)
@patch("apps.account.serializers.generate_password", return_value="KnownPass123")
def test_front_desk_auth_responses_include_event_space_workspace(
    mock_generate_password, mock_send_sms, api_client
):
    user, company = create_company_user()
    hotel = HotelProfile.objects.create(company=company, name="Event Hotel", stars=5)
    event_space = create_event_space(hotel, title="Ballroom")
    api_client.force_authenticate(user=user)
    create_response = api_client.post(
        reverse("staff-list"),
        {
            "first_name": "Front",
            "last_name": "Desk",
            "phone": "+251911000020",
            "workspace_id": str(event_space.id),
            "workspace_type": "event_space",
        },
        format="json",
    )

    assert create_response.status_code == 201
    front_desk = User.objects.get(phone="0911000020")

    token_response = api_client.post(
        reverse("token_obtain_pair"),
        {
            "phone": front_desk.phone,
            "password": "KnownPass123",
        },
        format="json",
    )

    assert token_response.status_code == 200
    assert token_response.data["workspace"] == {
        "id": str(event_space.id),
        "name": "Ballroom",
        "workspace_type": "event_space",
    }

    api_client.force_authenticate(user=front_desk)
    me_response = api_client.get(reverse("auth_me"))

    assert me_response.status_code == 200
    assert me_response.data["workspace"] == {
        "id": str(event_space.id),
        "name": "Ballroom",
        "workspace_type": "event_space",
    }
    assert mock_generate_password.called
    assert mock_send_sms.called
