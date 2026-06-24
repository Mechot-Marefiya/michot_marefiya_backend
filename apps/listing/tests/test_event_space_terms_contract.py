from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, Role
from apps.core.models import Address
from apps.listing.models import EventSpaceBooking, EventSpaceListing, TermsAndConditions
from apps.listing.services import EventSpaceAvailabilityService


pytestmark = pytest.mark.django_db(transaction=True)


def create_address(label: str) -> Address:
    return Address.objects.create(
        street_line1=f"{label} Street",
        city="Addis Ababa",
        sub_city=label,
        country="Ethiopia",
        state="Addis Ababa",
        postal_code="1000",
    )


def create_company_owner(django_user_model, *, suffix: str):
    company_role = Role.objects.get_or_create(name="Company", code=RoleCode.COMPANY.value)[0]
    user = django_user_model.objects.create_user(
        email=f"terms-owner-{suffix}@example.com",
        password="pass1234",
        phone=f"+251933000{suffix}",
        role=company_role,
    )
    company = CompanyProfile.objects.create(
        user=user,
        name=f"Terms Co {suffix}",
        phone=f"+251944000{suffix}",
        category=CompanyProfile.CategoryChoice.HOTEL,
        address=create_address(f"Company {suffix} HQ"),
        status=CompanyProfile.StatusChoice.APPROVED,
    )
    user.company = company
    user.save(update_fields=["company"])
    return user, company


def create_event_space_scope(company: CompanyProfile, *, hotel_name="Terms Hotel", space_title="Summit Hall"):
    hotel = HotelProfile.objects.create(
        company=company,
        name=hotel_name,
        stars=4,
        address=create_address(f"{hotel_name} Address"),
        is_active=True,
    )
    event_space = EventSpaceListing.objects.create(
        hotel=hotel,
        address=create_address(f"{space_title} Address"),
        title=space_title,
        description="Configured for conferences",
        base_price="4500.00",
        currency="ETB",
        number_of_guests=120,
        total_units=2,
        space_type=EventSpaceListing.SpaceType.CONFERENCE_HALL,
        is_active=True,
    )
    EventSpaceAvailabilityService.create_availability(event_space, event_space.total_units, days=30)
    return hotel, event_space


def create_regular_user_client(django_user_model):
    user_role = Role.objects.get_or_create(name="User", code=RoleCode.USER.value)[0]
    user = django_user_model.objects.create_user(
        email="terms-booker@example.com",
        password="pass1234",
        phone="+251955000001",
        role=user_role,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def event_space_terms_url(event_space_id):
    return f"/api/v1/listing/terms/event-space/{event_space_id}/"


def event_space_terms_history_url(event_space_id):
    return f"/api/v1/listing/terms/event-space/{event_space_id}/history/"


def test_event_space_terms_fall_back_to_hotel_terms_in_public_endpoints(
    authenticated_company_profile_client,
    company_profile,
):
    hotel, event_space = create_event_space_scope(company_profile, hotel_name="Fallback Hotel", space_title="Fallback Hall")
    hotel_terms = TermsAndConditions.objects.create(
        content_object=hotel,
        version="1.0",
        title="Hotel Terms",
        content="Hotel fallback terms",
        effective_date=date.today(),
        is_active=True,
    )

    public_terms = authenticated_company_profile_client.get(event_space_terms_url(event_space.id))
    assert public_terms.status_code == status.HTTP_200_OK
    assert public_terms.data["id"] == str(hotel_terms.id)
    assert public_terms.data["scope_type"] == "hotel"
    assert public_terms.data["scope_id"] == str(hotel.id)

    detail_response = authenticated_company_profile_client.get(reverse("event-spaces-detail", args=[event_space.id]))
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.data["active_terms"]["id"] == str(hotel_terms.id)
    assert detail_response.data["active_terms"]["scope_type"] == "hotel"
    assert detail_response.data["terms_url"] == event_space_terms_url(event_space.id)

    preview_response = authenticated_company_profile_client.post(
        reverse("bookings-eventspaces-price-preview"),
        {
            "check_in_date": (date.today() + timedelta(days=1)).isoformat(),
            "check_out_date": (date.today() + timedelta(days=2)).isoformat(),
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )
    assert preview_response.status_code == status.HTTP_200_OK
    assert preview_response.data["active_terms"]["id"] == str(hotel_terms.id)
    assert preview_response.data["active_terms"]["scope_type"] == "hotel"
    assert preview_response.data["terms_url"] == event_space_terms_url(event_space.id)


def test_event_space_terms_management_enforces_owner_scope_and_archive_falls_back(
    django_user_model,
    authenticated_company_profile_client,
    company_profile,
):
    hotel, event_space = create_event_space_scope(company_profile, hotel_name="Managed Terms Hotel", space_title="Managed Terms Hall")
    fallback_terms = TermsAndConditions.objects.create(
        content_object=hotel,
        version="2.0",
        title="Hotel Terms",
        content="Hotel fallback terms",
        effective_date=date.today(),
        is_active=True,
    )

    outsider_user, _outsider_company = create_company_owner(django_user_model, suffix="777")
    outsider_client = APIClient()
    outsider_client.force_authenticate(user=outsider_user)

    forbidden_create = outsider_client.post(
        event_space_terms_url(event_space.id),
        {"title": "Blocked", "content": "Nope"},
        format="json",
    )
    assert forbidden_create.status_code == status.HTTP_403_FORBIDDEN

    create_response = authenticated_company_profile_client.post(
        event_space_terms_url(event_space.id),
        {"title": "Event Terms", "content": "Event specific terms"},
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    term_id = create_response.data["id"]
    assert create_response.data["scope_type"] == "event_space"
    assert create_response.data["scope_id"] == str(event_space.id)
    assert create_response.data["is_active"] is False

    public_before_publish = authenticated_company_profile_client.get(event_space_terms_url(event_space.id))
    assert public_before_publish.status_code == status.HTTP_200_OK
    assert public_before_publish.data["id"] == str(fallback_terms.id)
    assert public_before_publish.data["scope_type"] == "hotel"

    owner_history = authenticated_company_profile_client.get(event_space_terms_history_url(event_space.id))
    assert owner_history.status_code == status.HTTP_200_OK
    assert owner_history.data["results"][0]["id"] == term_id

    outsider_history = outsider_client.get(event_space_terms_history_url(event_space.id))
    assert outsider_history.status_code == status.HTTP_403_FORBIDDEN

    publish_response = authenticated_company_profile_client.post(
        reverse("terms-publish", args=[term_id]),
        format="json",
    )
    assert publish_response.status_code == status.HTTP_200_OK
    assert publish_response.data["status"] == TermsAndConditions.Status.ACTIVE

    public_after_publish = authenticated_company_profile_client.get(event_space_terms_url(event_space.id))
    assert public_after_publish.status_code == status.HTTP_200_OK
    assert public_after_publish.data["id"] == term_id
    assert public_after_publish.data["scope_type"] == "event_space"

    archive_response = authenticated_company_profile_client.post(
        reverse("terms-archive", args=[term_id]),
        format="json",
    )
    assert archive_response.status_code == status.HTTP_200_OK
    assert archive_response.data["status"] == TermsAndConditions.Status.ARCHIVED

    public_after_archive = authenticated_company_profile_client.get(event_space_terms_url(event_space.id))
    assert public_after_archive.status_code == status.HTTP_200_OK
    assert public_after_archive.data["id"] == str(fallback_terms.id)
    assert public_after_archive.data["scope_type"] == "hotel"


def test_event_space_booking_accepts_fallback_terms_id_and_exposes_accepted_terms(
    django_user_model,
    company_profile,
):
    hotel, event_space = create_event_space_scope(company_profile, hotel_name="Booking Terms Hotel", space_title="Booking Terms Hall")
    hotel_terms = TermsAndConditions.objects.create(
        content_object=hotel,
        version="3.0",
        title="Hotel Terms",
        content="Hotel booking terms",
        effective_date=date.today(),
        is_active=True,
    )

    booker_client, _booker = create_regular_user_client(django_user_model)
    create_response = booker_client.post(
        reverse("bookings-eventspaces-list"),
        {
            "check_in_date": (date.today() + timedelta(days=1)).isoformat(),
            "check_out_date": (date.today() + timedelta(days=2)).isoformat(),
            "event_type": "conference",
            "guest_first_name": "Booker",
            "guest_last_name": "User",
            "guest_email": "booker@example.com",
            "guest_phone": "0911000000",
            "terms_accepted": True,
            "terms_id": str(hotel_terms.id),
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert create_response.status_code == status.HTTP_201_CREATED
    assert create_response.data["terms_version"] == "3.0"
    assert create_response.data["accepted_terms"] == {
        "id": str(hotel_terms.id),
        "scope_type": "hotel",
        "scope_id": str(hotel.id),
        "version": "3.0",
        "terms_url": f"/api/v1/listing/terms/hotel/{hotel.id}/",
    }
    assert create_response.data["terms_url"] == event_space_terms_url(event_space.id)

    booking = EventSpaceBooking.objects.get(id=create_response.data["id"])
    assert booking.snapshot["accepted_terms"] == {
        "id": str(hotel_terms.id),
        "scope_type": "hotel",
        "scope_id": str(hotel.id),
        "version": "3.0",
        "terms_url": f"/api/v1/listing/terms/hotel/{hotel.id}/",
    }

    lookup_response = booker_client.get(
        f"/api/v1/listing/bookings-eventspaces/lookup/?reference={booking.booking_reference}&guest_phone=0911000000"
    )
    assert lookup_response.status_code == status.HTTP_200_OK
    assert lookup_response.data["accepted_terms"]["id"] == str(hotel_terms.id)
    assert lookup_response.data["accepted_terms"]["scope_type"] == "hotel"
    assert lookup_response.data["terms_version"] == "3.0"
