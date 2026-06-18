from io import BytesIO
import json
import pytest
from PIL import Image
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from apps.account.enums import RoleCode


@pytest.mark.django_db
@patch("services.sms.send_sms", return_value=True)
def test_user_creation(mock_send_sms, api_client, normal_role):
    # * Having the normal_role here auto creates it
    # * and that helps our Role.objects.get() code in the serializer
    data = {
        "email": "test@example.com",
        "password": "pass1234",
        "confirm_password": "pass1234",
        "phone": "0911000123",
    }

    res = api_client.post(reverse("users-list"), data, format="json")

    assert res.status_code == 201
    assert res.data["email"] == "test@example.com"
    assert res.data["role"]["id"] == str(normal_role.id)


@pytest.mark.django_db
def test_serializer_raises_validation_error_on_password_mismatch(
    api_client, normal_role
):
    data = {
        "email": "test@example.com",
        "phone": "0911000456",
        "password": "12345678",
        "confirm_password": "1234567",
    }

    res = api_client.post(reverse("users-list"), data, format="json")
    assert res.status_code == 400
    assert "Passwords do not match" in str(res.data)


def create_test_image(name="test.png", ext="PNG", size=(100, 100), color=(255, 0, 0)):
    file = BytesIO()
    image = Image.new("RGB", size=size, color=color)
    image.save(file, ext)
    file.seek(0)
    return SimpleUploadedFile(name, file.read(), content_type=f"image/{ext.lower()}")


@pytest.mark.django_db
def test_company_registration(api_client, company_role):
    license = SimpleUploadedFile(
        "company_license.pdf", b"file_content", content_type="application/pdf"
    )

    logo = create_test_image("logo.png")

    address = json.dumps(
        {
            "street_line1": "wollo sefer",
            "country": "Ethiopia",
            "city": "Addis ababa",
            "sub_city": "Bole",
            "state": "Addis Ababa",
            "postal_code": "1000",
            "latitude": "45.12",
            "longitude": "23.46",
        }
    )

    data = {
        "email": "company@example.com",
        "first_name": "Company",
        "last_name": "Owner",
        "password": "pass1234",
        "confirm_password": "pass1234",
        "name": "michot",
        "phone": "+25111121214",
        "license": license,
        "address": address,
        "logo": logo,
        "category": "hotel",
    }

    res = api_client.post(reverse("companies-list"), data, format="multipart")
    # print("RES", res.data)
    assert res.status_code == 201

    assert res.data["name"] == "michot"
    assert res.data["user"]["role"]["code"] == RoleCode.COMPANY.value
    assert res.data["user"]["company"]["id"] == str(res.data["id"])
    assert res.data["user"]["workspace"] is None


@pytest.mark.django_db
def test_company_registration_fails_on_invalid_data(api_client, company_role):
    license = SimpleUploadedFile(
        "company_license.pdf", b"file_content", content_type="application/pdf"
    )

    logo = create_test_image("logo.png")

    address = json.dumps(
        {
            "street_line1": "",
            "country": "Ethiopia",
            "city": "Addis ababa",
            "sub_city": "Bole",
            "state": "Addis Ababa",
            "postal_code": "1000",
            "latitude": "45.12",
            "longitude": "23.46",
        }
    )

    data = {
        "email": "company@example.com",
        "name": "michot",
        "phone": "+25111121214",
        "license": license,
        "address": address,
        "logo": logo,
        "category": "invalid_choice",
        "description": "",
    }

    res = api_client.post(reverse("companies-list"), data, format="multipart")
    # print("RES", res.data)
    assert res.status_code == 400
