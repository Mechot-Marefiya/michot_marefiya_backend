import pytest


@pytest.mark.django_db
def test_manager_user_creation(user, django_user_model):
    assert user.is_active
    assert not user.is_staff
    assert not user.is_superuser
    assert user.username is None

    with pytest.raises(ValueError):
        django_user_model.objects.create_user(email=None, password="pass1234")


@pytest.mark.django_db
def test_manager_superuser_creation(super_user, django_user_model):
    assert super_user.is_active
    assert super_user.is_staff
    assert super_user.is_superuser
    assert super_user.username is None

    with pytest.raises(ValueError):
        django_user_model.objects.create_superuser(
            email="super@example.com", password="pass1234", is_superuser=False
        )
