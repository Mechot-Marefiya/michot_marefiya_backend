import pytest
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from datetime import date, timedelta

from rest_framework.test import APIClient

from apps.favorites.models import Favorite
from django.contrib.contenttypes.models import ContentType


@pytest.mark.django_db
def test_hotel_list_includes_is_favorite_and_uses_one_fav_query(
    authenticated_hotel_profile_client, company_user, hotel_profile
):
    client = authenticated_hotel_profile_client

    # create favorite for the user
    ct = ContentType.objects.get(app_label="account", model="hotelprofile")
    Favorite.objects.create(user=company_user, content_type=ct, object_id=str(hotel_profile.id))

    url = "/api/v1/account/hotels/"

    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)

    assert resp.status_code == 200
    data = resp.json()
    # expect at least one result
    assert isinstance(data, list) or data.get("results") is not None

    # find hotel entry
    entries = data if isinstance(data, list) else data.get("results", [])
    assert len(entries) > 0
    first = entries[0]
    assert first.get("is_favorite") is True

    fav_queries = [q for q in ctx.captured_queries if "favorites_favorite" in q["sql"]]
    assert len(fav_queries) == 1


@pytest.mark.django_db
def test_hotel_detail_includes_is_favorite_and_uses_one_fav_query(
    authenticated_hotel_profile_client, company_user, hotel_profile
):
    client = authenticated_hotel_profile_client
    ct = ContentType.objects.get(app_label="account", model="hotelprofile")
    Favorite.objects.create(user=company_user, content_type=ct, object_id=str(hotel_profile.id))

    url = f"/api/v1/account/hotels/{hotel_profile.id}/"

    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("is_favorite") is True

    fav_queries = [q for q in ctx.captured_queries if "favorites_favorite" in q["sql"]]
    assert len(fav_queries) == 1


@pytest.mark.django_db
def test_stay_search_includes_is_favorite_and_uses_one_fav_query(
    authenticated_hotel_profile_client, company_user, hotel_profile
):
    from apps.core.models import Address
    from apps.listing.models import RoomListing, StayAvailability

    client = authenticated_hotel_profile_client

    # create room listing for the hotel
    addr = Address.objects.create(
        street_line1="tst",
        city=hotel_profile.company.address.city,
        country="Ethiopia",
    )

    room = RoomListing.objects.create(
        hotel=hotel_profile,
        address=addr,
        title="Test Room",
        description="x",
        base_price=100,
        currency="ETB",
        number_of_guests=1,
        total_units=2,
        bed_type="mixed",
        room_size_sqm=10,
    )

    # create availability for tomorrow
    check_in = date.today() + timedelta(days=1)
    check_out = check_in + timedelta(days=1)

    StayAvailability.objects.create(hotel=hotel_profile, room=room, date=check_in, available_rooms=2)

    # favorite the hotel
    ct = ContentType.objects.get(app_label="account", model="hotelprofile")
    Favorite.objects.create(user=company_user, content_type=ct, object_id=str(hotel_profile.id))

    url = (
        f"/api/v1/listing/stays/search/?city={hotel_profile.company.address.city}"
        f"&check_in_date={check_in.isoformat()}&check_out_date={check_out.isoformat()}&guests=1"
    )

    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)

    assert resp.status_code == 200
    data = resp.json()
    # `StaySearch.get` returns a list of results (not paginated dict)
    if isinstance(data, list):
        results = data
    else:
        results = data.get("results", [])

    assert results
    first = results[0]
    assert first.get("is_favorite") is True

    fav_queries = [q for q in ctx.captured_queries if "favorites_favorite" in q["sql"]]
    assert len(fav_queries) == 1


@pytest.mark.django_db
def test_guesthouse_list_includes_is_favorite(
    authenticated_hotel_profile_client, company_user, hotel_profile
):
    from apps.listing.models import GuestHouseProfile
    from apps.core.models import Address
    client = authenticated_hotel_profile_client

    # create an address
    addr = Address.objects.create(
        street_line1="gh street",
        city="Addis",
        country="Ethiopia",
    )

    # create a guesthouse
    gh = GuestHouseProfile.objects.create(
        title="Test GH",
        base_price=500,
        is_active=True,
        address=addr,
        company=hotel_profile.company # satisfy constraint
    )

    # create favorite
    ct = ContentType.objects.get(app_label="listing", model="guesthouseprofile")
    Favorite.objects.create(user=company_user, content_type=ct, object_id=str(gh.id))

    url = "/api/v1/listing/guest-houses/"

    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)

    assert resp.status_code == 200
    data = resp.json()
    entries = data if isinstance(data, list) else data.get("results", [])
    
    target = next((item for item in entries if item["id"] == str(gh.id)), None)
    assert target is not None
    assert target.get("is_favorite") is True

    fav_queries = [q for q in ctx.captured_queries if "favorites_favorite" in q["sql"]]
    assert len(fav_queries) == 1

