import pytest

from apps.account.models import Role


@pytest.fixture
def admin_role():
    return Role.objects.create(name='Admin', code='admin')


@pytest.fixture
def normal_role():
    return Role.objects.create(name='User', code='user')


@pytest.fixture
def company_role():
    return Role.objects.create(name='Company', code='company')


@pytest.fixture
def user(django_user_model, normal_role):
    return django_user_model.objects.create_user(
        email="user@example.com", password="pass1234", role=normal_role)


@pytest.fixture
def super_user(django_user_model, admin_role):
    return django_user_model.objects.create_superuser(
        email="super@example.com", password="pass1234", role=admin_role)
