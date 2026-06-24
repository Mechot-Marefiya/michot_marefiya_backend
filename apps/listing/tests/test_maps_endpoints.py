from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.account.enums import RoleCode
from apps.account.models import Role


pytestmark = pytest.mark.django_db


def _authenticated_client(django_user_model):
    user_role = Role.objects.get_or_create(name="User", code=RoleCode.USER.value)[0]
    user = django_user_model.objects.create_user(
        email="maps-user@example.com",
        password="pass1234",
        phone="0911009999",
        role=user_role,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@patch("apps.listing.maps_views.autocomplete_address")
def test_maps_autocomplete_is_public_and_stable_for_anonymous_and_authenticated(
    mock_autocomplete,
    django_user_model,
):
    mock_autocomplete.return_value = [
        {
            "place_id": "geo-1",
            "description": "Bole Road, Addis Ababa, Ethiopia",
            "main_text": "Bole Road",
            "secondary_text": "Addis Ababa, Ethiopia",
        }
    ]

    anonymous_client = APIClient()
    authenticated_client = _authenticated_client(django_user_model)
    url = reverse("maps-autocomplete")
    params = {"input": "bole", "session_token": "session-123"}

    anonymous_response = anonymous_client.get(url, params)
    authenticated_response = authenticated_client.get(url, params)

    assert anonymous_response.status_code == status.HTTP_200_OK
    assert authenticated_response.status_code == status.HTTP_200_OK
    assert anonymous_response.data == authenticated_response.data
    assert anonymous_response.data[0]["place_id"] == "geo-1"
    assert "description" in anonymous_response.data[0]


@patch("apps.listing.maps_views.get_place_detail")
def test_maps_place_detail_is_public_and_returns_documented_payload(
    mock_get_place_detail,
    django_user_model,
):
    mock_get_place_detail.return_value = {
        "lat": "9.012345",
        "lng": "38.765432",
        "formatted_address": "Bole Medhanialem, Addis Ababa, Ethiopia",
        "place_id": "geo-place-1",
        "components": {
            "city": "Addis Ababa",
            "sub_city": "Bole",
            "region": "Addis Ababa",
            "country": "Ethiopia",
            "postcode": "1000",
        },
    }

    anonymous_client = APIClient()
    authenticated_client = _authenticated_client(django_user_model)
    url = reverse("maps-place-detail")
    payload = {"place_id": "geo-place-1", "session_token": "session-123"}

    anonymous_response = anonymous_client.post(url, payload, format="json")
    authenticated_response = authenticated_client.post(url, payload, format="json")

    assert anonymous_response.status_code == status.HTTP_200_OK
    assert authenticated_response.status_code == status.HTTP_200_OK
    assert anonymous_response.data == authenticated_response.data
    assert anonymous_response.data["place_id"] == "geo-place-1"
    assert anonymous_response.data["components"]["sub_city"] == "Bole"


@patch("apps.listing.maps_views.reverse_geocode")
def test_maps_reverse_geocode_is_public_and_returns_documented_payload(
    mock_reverse_geocode,
    django_user_model,
):
    mock_reverse_geocode.return_value = {
        "formatted_address": "Kazanchis, Addis Ababa, Ethiopia",
        "components": {
            "city": "Addis Ababa",
            "sub_city": "Kirkos",
            "region": "Addis Ababa",
            "country": "Ethiopia",
            "postcode": "1010",
        },
    }

    anonymous_client = APIClient()
    authenticated_client = _authenticated_client(django_user_model)
    url = reverse("maps-reverse-geocode")
    params = {"lat": "9.022222", "lng": "38.744444"}

    anonymous_response = anonymous_client.get(url, params)
    authenticated_response = authenticated_client.get(url, params)

    assert anonymous_response.status_code == status.HTTP_200_OK
    assert authenticated_response.status_code == status.HTTP_200_OK
    assert anonymous_response.data == authenticated_response.data
    assert anonymous_response.data["components"]["sub_city"] == "Kirkos"


def test_maps_endpoints_do_not_redirect_or_require_login_for_anonymous(django_user_model):
    anonymous_client = APIClient()

    autocomplete_response = anonymous_client.get(
        reverse("maps-autocomplete"),
        {"input": "bole", "session_token": "session-123"},
    )
    place_detail_response = anonymous_client.post(
        reverse("maps-place-detail"),
        {"place_id": "geo-place-1", "session_token": "session-123"},
        format="json",
    )
    reverse_geocode_response = anonymous_client.get(
        reverse("maps-reverse-geocode"),
        {"lat": "9.022222", "lng": "38.744444"},
    )

    assert autocomplete_response.status_code != status.HTTP_401_UNAUTHORIZED
    assert autocomplete_response.status_code != status.HTTP_403_FORBIDDEN
    assert place_detail_response.status_code != status.HTTP_401_UNAUTHORIZED
    assert place_detail_response.status_code != status.HTTP_403_FORBIDDEN
    assert reverse_geocode_response.status_code != status.HTTP_401_UNAUTHORIZED
    assert reverse_geocode_response.status_code != status.HTTP_403_FORBIDDEN
