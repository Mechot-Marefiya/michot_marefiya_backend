import pytest


@pytest.fixture
def super_user(django_user_model):
    return django_user_model.objects.create_superuser(
        email="super@example.com", password="pass1234"
    )
