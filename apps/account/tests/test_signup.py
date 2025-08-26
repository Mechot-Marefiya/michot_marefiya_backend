import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_user_creation(api_client):
    data = {
        "first_name": "",
        "last_name": "",
        "email": "test@example.com",
        "password": "12345678",
        "confirm_password": "12345678",
    }

    res = api_client.post(reverse("signup"), data, format="json")

    assert res.status_code == 201
    assert res.data["email"] == "test@example.com"


@pytest.mark.django_db
def test_serializer_raises_validation_error_on_password_mismatch(api_client):
    data = {
        "first_name": "",
        "last_name": "",
        "email": "test@example.com",
        "password": "12345678",
        "confirm_password": "1234567",
    }

    res = api_client.post(reverse("signup"), data, format="json")
    assert res.status_code == 400
    assert "Password does not match" in str(res.data)
