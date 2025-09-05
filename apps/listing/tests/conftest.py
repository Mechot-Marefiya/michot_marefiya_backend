from io import BytesIO
from PIL import Image
import pytest
from rest_framework.test import APIClient
from apps.account.models import CompanyProfile, HotelProfile
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import Address


@pytest.fixture
def company_user(django_user_model):
    return django_user_model.objects.create_user(
        email="company@example.com", password="pass"
    )


def create_test_image(name="test.png", ext="PNG", size=(100, 100), color=(255, 0, 0)):
    file = BytesIO()
    image = Image.new("RGB", size=size, color=color)
    image.save(file, ext)
    file.seek(0)
    return SimpleUploadedFile(name, file.read(), content_type=f"image/{ext.lower()}")


@pytest.fixture
def company_profile(company_user):
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
        "name": "michot",
        "phone": "+25111121214",
        "license": license,
        "address": address,
        "logo": logo,
        "category": "hotel",
    }
    return CompanyProfile.objects.create(user=company_user, **data)


@pytest.fixture
def hotel_profile(company_profile):
    return HotelProfile.objects.create(company=company_profile, stars=5)


@pytest.fixture
def authenticated_company_client(company_user, company_profile) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=company_user)
    return client


@pytest.fixture
def authenticated_hotel_profile_client(company_user, hotel_profile):
    client = APIClient()
    client.force_authenticate(user=company_user)
    return client
