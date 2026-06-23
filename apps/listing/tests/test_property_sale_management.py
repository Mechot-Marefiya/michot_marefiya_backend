from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.account.models import CompanyProfile
from apps.core.models import Address
from apps.listing.models import PropertySaleListing


def create_address(*, suffix):
    return Address.objects.create(
        street_line1=f"Property Sale Street {suffix}",
        city="Addis Ababa",
        country="Ethiopia",
        sub_city="Bole",
    )


def create_property_sale_listing(*, owner_company, suffix, is_active=True):
    return PropertySaleListing.objects.create(
        company=owner_company,
        title=f"Property Sale {suffix}",
        description="Managed property sale listing.",
        base_price=Decimal("2500000.00"),
        currency="ETB",
        address=create_address(suffix=suffix),
        property_type=PropertySaleListing.PropertyTypeChoices.APARTMENT,
        bedrooms=3,
        bathrooms=2,
        square_meters=Decimal("125.00"),
        land_size_square_meters=Decimal("200.00"),
        is_furnished=True,
        seller_contact_name="Selam Owner",
        seller_phone="0911223344",
        seller_email="seller@example.com",
        reveal_fee=Decimal("100.00"),
        is_active=is_active,
    )


def create_company_client(*, django_user_model, company_role, suffix):
    user = django_user_model.objects.create_user(
        email=f"property-owner-{suffix}@example.com",
        password="pass1234",
        role=company_role,
    )
    company = CompanyProfile.objects.create(
        user=user,
        name=f"Property Company {suffix}",
        phone="0911000000",
        category=CompanyProfile.CategoryChoice.HOUSE,
        address=create_address(suffix=f"company-{suffix}"),
        status=CompanyProfile.StatusChoice.APPROVED,
    )
    user.company = company
    user.save(update_fields=["company"])

    client = APIClient()
    client.force_authenticate(user=user)
    return client, company


@pytest.mark.django_db
def test_property_sale_managed_detail_and_owner_patch_preserve_public_privacy(
    authenticated_company_profile_client,
    company_profile,
):
    listing = create_property_sale_listing(owner_company=company_profile, suffix="owner")

    public_response = APIClient().get(reverse("property-sales-detail", args=[listing.id]))
    assert public_response.status_code == status.HTTP_200_OK
    assert "seller_contact_name" not in public_response.data
    assert "seller_phone" not in public_response.data
    assert "seller_email" not in public_response.data

    managed_response = authenticated_company_profile_client.get(
        reverse("property-sales-detail", args=[listing.id]),
        {"managed": "true"},
    )
    assert managed_response.status_code == status.HTTP_200_OK
    assert managed_response.data["seller_contact_name"] == "Selam Owner"
    assert managed_response.data["seller_phone"] == "0911223344"
    assert managed_response.data["seller_email"] == "seller@example.com"

    patch_response = authenticated_company_profile_client.patch(
        reverse("property-sales-detail", args=[listing.id]),
        {"title": "Updated Property Sale"},
        format="json",
    )
    assert patch_response.status_code == status.HTTP_200_OK
    assert patch_response.data["title"] == "Updated Property Sale"
    assert patch_response.data["seller_contact_name"] == "Selam Owner"
    assert patch_response.data["seller_phone"] == "0911223344"
    assert patch_response.data["seller_email"] == "seller@example.com"

    listing.refresh_from_db()
    assert listing.title == "Updated Property Sale"
    assert listing.seller_contact_name == "Selam Owner"
    assert listing.seller_phone == "0911223344"
    assert listing.seller_email == "seller@example.com"


@pytest.mark.django_db
def test_property_sale_patch_denies_foreign_owner(
    authenticated_company_profile_client,
    company_profile,
    django_user_model,
    company_role,
):
    listing = create_property_sale_listing(owner_company=company_profile, suffix="foreign-patch")
    outsider_client, _outsider_company = create_company_client(
        django_user_model=django_user_model,
        company_role=company_role,
        suffix="outsider-patch",
    )

    response = outsider_client.patch(
        reverse("property-sales-detail", args=[listing.id]),
        {"title": "Should Not Work"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    listing.refresh_from_db()
    assert listing.title == "Property Sale foreign-patch"


@pytest.mark.django_db
def test_property_sale_public_inactive_listing_is_excluded(company_profile):
    listing = create_property_sale_listing(
        owner_company=company_profile,
        suffix="inactive",
        is_active=False,
    )

    public_client = APIClient()
    list_response = public_client.get(reverse("property-sales-list"))
    detail_response = public_client.get(reverse("property-sales-detail", args=[listing.id]))

    assert list_response.status_code == status.HTTP_200_OK
    assert all(item["id"] != str(listing.id) for item in list_response.data["results"])
    assert detail_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_property_sale_owner_delete_is_scoped(
    authenticated_company_profile_client,
    company_profile,
):
    listing = create_property_sale_listing(owner_company=company_profile, suffix="owner-delete")

    response = authenticated_company_profile_client.delete(
        reverse("property-sales-detail", args=[listing.id])
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not PropertySaleListing.objects.filter(id=listing.id).exists()


@pytest.mark.django_db
def test_property_sale_delete_denies_foreign_owner(
    authenticated_company_profile_client,
    company_profile,
    django_user_model,
    company_role,
):
    listing = create_property_sale_listing(owner_company=company_profile, suffix="foreign-delete")
    outsider_client, _outsider_company = create_company_client(
        django_user_model=django_user_model,
        company_role=company_role,
        suffix="outsider-delete",
    )

    response = outsider_client.delete(reverse("property-sales-detail", args=[listing.id]))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert PropertySaleListing.objects.filter(id=listing.id).exists()
