import json
import pytest
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from apps.core.models import Address
from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile
from apps.listing.models import Amenity


@pytest.fixture
def company_user(django_user_model, company_role):
    return django_user_model.objects.create_user(
        email="company@example.com", password="pass", role=company_role
    )


@pytest.fixture
def michot_admin(django_user_model, admin_role):
    return django_user_model.objects.create_user(
        email="company@example.com", password="pass", role=admin_role
    )


def create_test_image(name="test.png", ext="PNG", size=(100, 100), color=(255, 0, 0)):
    file = BytesIO()
    image = Image.new("RGB", size=size, color=color)
    image.save(file, ext)
    file.seek(0)
    return SimpleUploadedFile(name, file.read(), content_type=f"image/{ext.lower()}")


@pytest.fixture
def images_list():
    imgs = []
    for i in range(1, 4):
        img_name = f"img_{i}.png"
        imgs.append(create_test_image(img_name))
    return imgs


@pytest.fixture
def address_payload():
    return json.dumps(
        {
            "street_line1": "wollo sefer",
            "country": "Ethiopia",
            "city": "Addis Ababa",
            "sub_city": "Bole",
            "state": "Addis Ababa",
            "postal_code": "1000",
            "latitude": "45.12",
            "longitude": "23.46",
        }
    )


@pytest.fixture
def company_profile(company_user) -> CompanyProfile:
    logo = create_test_image("logo.png")
    license = SimpleUploadedFile(
        "company_license.pdf", b"file_content", content_type="application/pdf"
    )
    address_data = {
        "street_line1": "wollo sefer",
        "country": "Ethiopia",
        "city": "Addis ababa",
        "sub_city": "Bole",
        "state": "Addis Ababa",
        "postal_code": "1000",
        "latitude": "45.12",
        "longitude": "23.46",
    }

    address = Address.objects.create(**address_data)

    data = {
        "name": "some vendor",
        "phone": "+25111121214",
        "license": license,
        "address": address,
        "logo": logo,
        "category": CompanyProfile.CategoryChoice.HOTEL,
    }
    return CompanyProfile.objects.create(user=company_user, **data)


@pytest.fixture
def individual_owner_profile() -> IndividualOwnerProfile:
    address_data = {
        "street_line1": "22 mazoria",
        "country": "Ethiopia",
        "city": "Addis Ababa",
        "sub_city": "Yeka",
        "state": "Addis Ababa",
        "postal_code": "1000",
        "latitude": "9.03",
        "longitude": "38.74",
    }

    address = Address.objects.create(**address_data)

    data = {
        "first_name": "Abebe",
        "last_name": "Bekele",
        "address": address,
        "phone": "+251911223344",
        "category": IndividualOwnerProfile.PropertyCategoryChoice.APARTMENT,
        "national_id_number": 123456,
    }
    return IndividualOwnerProfile.objects.create(**data)


@pytest.fixture
def hotel_profile(company_profile) -> HotelProfile:
    return HotelProfile.objects.create(company=company_profile, stars=5)


@pytest.fixture
def authenticated_company_profile_client(company_user, company_profile) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=company_user)
    return client


@pytest.fixture
def authenticated_michot_admin_client(michot_admin) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=michot_admin)
    return client


@pytest.fixture
def authenticated_hotel_profile_client(company_user, hotel_profile) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=company_user)
    return client


@pytest.fixture
def amenities():
    return [Amenity.objects.create(name=am).id for am in ["wifi", "pool", "balcony"]]
