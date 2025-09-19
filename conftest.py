import pytest
from rest_framework.test import APIClient

from apps.account.models import Role
from apps.core.models import Address


@pytest.fixture
def address():
    return Address.objects.create(
        street_line1="Wollo Sefer",
        country="Ethiopia",
        city="Addis Ababa",
        sub_city="Bole",
        state="Addis Ababa",
        postal_code="1000",
        latitude=9.012345,
        longitude=38.765432,
    )


@pytest.fixture
def admin_role():
    return Role.objects.create(name="Admin", code="admin")


@pytest.fixture
def normal_role():
    return Role.objects.create(name="User", code="user")


@pytest.fixture
def company_role():
    return Role.objects.create(name="Company", code="company")


@pytest.fixture
def user(django_user_model, normal_role):
    return django_user_model.objects.create_user(
        email="user@example.com", password="pass1234", role=normal_role
    )


@pytest.fixture
def super_user(django_user_model, admin_role):
    return django_user_model.objects.create_superuser(
        email="super@example.com", password="pass1234", role=admin_role
    )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def authenticated_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client
