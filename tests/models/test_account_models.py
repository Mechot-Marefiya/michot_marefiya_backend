# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: no
# Last updated: 2026-06-01

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile, ListingImage, Role, User
from apps.core.models import Address

pytestmark = pytest.mark.django_db


def test_role_str_representation():
    role = Role(name="Admin", code="admin")
    assert str(role) == "Admin"


def test_role_unique_code_constraint():
    Role.objects.create(name="Admin", code="admin")
    with pytest.raises(Exception):
        Role.objects.create(name="Duplicate", code="admin")


def test_user_str_representation(user):
    assert str(user) == user.email


def test_user_custom_manager_methods(django_user_model, user_role, admin_role):
    user = django_user_model.objects.create_user(email="manager@example.com", password="pass1234", role=user_role)
    assert user.check_password("pass1234")

    superuser = django_user_model.objects.create_superuser(email="supermanager@example.com", password="pass1234", role=admin_role)
    assert superuser.is_superuser is True


def test_company_profile_str_representation(company):
    assert str(company) == f"{company.name}::{company.category}"


def test_company_profile_is_approved_property(company):
    assert company.is_approved is True


def test_company_profile_required_fields_validation():
    profile = CompanyProfile()
    with pytest.raises(ValidationError):
        profile.full_clean()


def test_individual_owner_profile_str_representation(individual_owner):
    assert str(individual_owner) == f"{individual_owner.first_name} {individual_owner.last_name}"


def test_individual_owner_profile_unique_phone_constraint(individual_owner):
    with pytest.raises(Exception):
        IndividualOwnerProfile.objects.create(
            first_name="Other",
            last_name="Owner",
            address=Address.objects.create(
                street_line1="Other Street",
                country="Ethiopia",
                city="Addis Ababa",
                sub_city="Bole",
                state="Addis Ababa",
                postal_code="1000",
            ),
            phone=individual_owner.phone,
        )


def test_hotel_profile_str_representation(hotel):
    assert str(hotel) == hotel.company.name


def test_listing_image_str_representation(hotel, image_file):
    image = ListingImage.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        image=image_file,
        alt_text="Listing image",
        is_primary=True,
    )
    assert str(image).startswith("Image for")
