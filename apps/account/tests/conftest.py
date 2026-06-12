import pytest

from rest_framework.test import APIClient

from apps.account.enums import RoleCode
from apps.account.models import Role


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_role():
    return Role.objects.get_or_create(name="Admin", code=RoleCode.ADMIN.value)[0]


@pytest.fixture
def company_role():
    return Role.objects.get_or_create(name="Company", code=RoleCode.COMPANY.value)[0]


@pytest.fixture
def normal_role():
    return Role.objects.get_or_create(name="User", code=RoleCode.USER.value)[0]


@pytest.fixture
def user(django_user_model, normal_role):
    return django_user_model.objects.create_user(
        email="user@example.com",
        password="pass1234",
        role=normal_role,
    )


@pytest.fixture
def super_user(django_user_model, admin_role):
    return django_user_model.objects.create_superuser(
        email="super@example.com",
        password="pass1234",
        role=admin_role,
    )
