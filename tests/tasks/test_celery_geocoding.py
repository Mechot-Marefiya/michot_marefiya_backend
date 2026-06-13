# BASELINE: written for TASK-403
# Flutter contract: no

from types import SimpleNamespace

import pytest
from django.core.management import call_command
from decimal import Decimal

from apps.account.models import HotelProfile
from apps.account.serializers import HotelProfileSerializer
from apps.listing.models import CarListing, PropertyListing, PropertySaleListing
from apps.listing.serializers import PropertySaleListingSerializer
from apps.listing.services import ListingService
from apps.listing.tasks import GEOCODING_RETRY_DELAYS, geocode_listing_async

pytestmark = pytest.mark.django_db


def _address_payload(street="Bole Road", city="Addis Ababa", sub_city="Bole", state="Addis Ababa"):
    return {
        "street_line1": street,
        "country": "Ethiopia",
        "city": city,
        "sub_city": sub_city,
        "state": state,
        "postal_code": "1000",
    }


def test_geocode_listing_async_updates_coordinates(property_listing, monkeypatch):
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_address",
        lambda address: {
            "lat": Decimal("9.012345"),
            "lng": Decimal("38.765432"),
            "formatted_address": "Bole Road, Addis Ababa, Ethiopia",
            "place_id": "place-123",
            "components": {"city": "Addis Ababa"},
        },
    )

    assert geocode_listing_async(property_listing.id, f"{property_listing._meta.app_label}.{property_listing._meta.model_name}") is True

    property_listing.refresh_from_db()
    assert property_listing.latitude == Decimal("9.012345")
    assert property_listing.longitude == Decimal("38.765432")
    assert property_listing.formatted_address == "Bole Road, Addis Ababa, Ethiopia"
    assert property_listing.place_id == "place-123"
    assert property_listing.address_components == {"city": "Addis Ababa"}


def test_geocode_listing_async_skips_already_geocoded_listing(property_listing, monkeypatch):
    property_listing.latitude = Decimal("9.000001")
    property_listing.longitude = Decimal("38.000001")
    property_listing.save(update_fields=["latitude", "longitude"])

    called = {"value": False}

    def _fail(_address):
        called["value"] = True
        raise AssertionError("geocode_address should not be called for already geocoded listings")

    monkeypatch.setattr("apps.listing.tasks.geocode_address", _fail)

    assert geocode_listing_async(property_listing.id, f"{property_listing._meta.app_label}.{property_listing._meta.model_name}") is False
    assert called["value"] is False


def test_geocode_listing_retry_policy_is_expected():
    assert GEOCODING_RETRY_DELAYS == (30, 120, 300)
    assert geocode_listing_async.max_retries == 3


def test_listing_service_schedule_geocoding_queues_on_commit(django_capture_on_commit_callbacks, monkeypatch, room):
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert ListingService.schedule_geocoding(room) is True

    assert calls == [(room.id, f"{room._meta.app_label}.{room._meta.model_name}")]


def test_listing_service_schedule_geocoding_skips_listings_without_address(
    car_listing,
    monkeypatch,
):
    called = {"value": False}
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda *args, **kwargs: called.__setitem__("value", True),
    )

    assert ListingService.schedule_geocoding(car_listing) is False
    assert called["value"] is False


@pytest.mark.parametrize("instance", ["guest_house", "property_listing", "event_space"])
def test_listing_service_schedule_geocoding_covers_address_bearing_listings(
    request,
    django_capture_on_commit_callbacks,
    monkeypatch,
    instance,
):
    listing = request.getfixturevalue(instance)
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert ListingService.schedule_geocoding(listing) is True

    assert calls == [(listing.id, f"{listing._meta.app_label}.{listing._meta.model_name}")]


def test_property_listing_update_with_address_change_queues_geocoding(
    property_listing,
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    new_address = _address_payload(street="Mexico Square")
    with django_capture_on_commit_callbacks(execute=True):
        ListingService.update_property_listing(property_listing, {"address": new_address})

    property_listing.refresh_from_db()
    assert property_listing.address.street_line1 == "Mexico Square"
    assert calls == [(property_listing.id, f"{property_listing._meta.app_label}.{property_listing._meta.model_name}")]


def test_property_listing_update_with_address_change_clears_stale_coordinates(
    property_listing,
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    property_listing.latitude = Decimal("9.111111")
    property_listing.longitude = Decimal("38.111111")
    property_listing.formatted_address = "Old Address"
    property_listing.place_id = "old-place"
    property_listing.address_components = {"city": "Old City"}
    property_listing.save(
        update_fields=[
            "latitude",
            "longitude",
            "formatted_address",
            "place_id",
            "address_components",
        ]
    )

    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        ListingService.update_property_listing(
            property_listing,
            {"address": _address_payload(street="Kazanchis Avenue")},
        )

    property_listing.refresh_from_db()
    assert property_listing.address.street_line1 == "Kazanchis Avenue"
    assert property_listing.latitude is None
    assert property_listing.longitude is None
    assert property_listing.formatted_address is None
    assert property_listing.place_id is None
    assert property_listing.address_components is None
    assert calls == [(property_listing.id, f"{property_listing._meta.app_label}.{property_listing._meta.model_name}")]


def test_geocode_listing_async_updates_after_address_change_cleared_coordinates(
    property_listing,
    monkeypatch,
):
    property_listing.latitude = None
    property_listing.longitude = None
    property_listing.save(update_fields=["latitude", "longitude"])
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_address",
        lambda address: {
            "lat": Decimal("8.998877"),
            "lng": Decimal("38.554433"),
            "formatted_address": "Kazanchis, Addis Ababa, Ethiopia",
            "place_id": "geoapify-place-999",
            "components": {"city": "Addis Ababa", "country": "Ethiopia"},
        },
    )

    assert geocode_listing_async(
        property_listing.id,
        f"{property_listing._meta.app_label}.{property_listing._meta.model_name}",
    ) is True

    property_listing.refresh_from_db()
    assert property_listing.latitude == Decimal("8.998877")
    assert property_listing.longitude == Decimal("38.554433")
    assert property_listing.formatted_address == "Kazanchis, Addis Ababa, Ethiopia"
    assert property_listing.place_id == "geoapify-place-999"


def test_geocode_listing_async_uses_formatted_address_for_addressless_car_listing(
    car_listing,
    monkeypatch,
):
    car_listing.latitude = None
    car_listing.longitude = None
    car_listing.formatted_address = "Bole, Addis Ababa, Ethiopia"
    car_listing.save(update_fields=["latitude", "longitude", "formatted_address"])
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_address",
        lambda address: {
            "lat": Decimal("9.010000"),
            "lng": Decimal("38.760000"),
            "formatted_address": address,
            "place_id": "geoapify-car-place",
            "components": {"city": "Addis Ababa"},
        },
    )

    assert geocode_listing_async(
        car_listing.id,
        f"{car_listing._meta.app_label}.{car_listing._meta.model_name}",
    ) is True

    car_listing.refresh_from_db()
    assert car_listing.latitude == Decimal("9.010000")
    assert car_listing.longitude == Decimal("38.760000")
    assert car_listing.place_id == "geoapify-car-place"


def test_property_sale_listing_serializer_create_queues_geocoding(
    company_user,
    company,
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    payload = {
        "title": "Sale Property",
        "description": "A property sale listing for TASK-403.",
        "base_price": "4500000.00",
        "currency": "ETB",
        "address": _address_payload(),
        "property_type": PropertySaleListing.PropertyTypeChoices.VILLA.value,
        "bedrooms": 4,
        "bathrooms": 3,
        "square_meters": "240.00",
        "land_size_square_meters": "320.00",
        "is_furnished": True,
        "seller_contact_name": "Seller Name",
        "seller_phone": "0911000000",
        "seller_email": "seller@example.com",
        "reveal_fee": "150.00",
    }

    serializer = PropertySaleListingSerializer(
        data=payload,
        context={"request": SimpleNamespace(user=company_user)},
    )
    assert serializer.is_valid(), serializer.errors

    with django_capture_on_commit_callbacks(execute=True):
        listing = serializer.save()

    assert isinstance(listing, PropertySaleListing)
    assert calls == [(listing.id, f"{listing._meta.app_label}.{listing._meta.model_name}")]


def test_hotel_profile_serializer_create_queues_geocoding(
    company_user,
    company,
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    payload = {
        "name": "Geocode Hotel",
        "description": "Hotel geocoding test",
        "phone": "0911000001",
        "website": "https://example.com",
        "address": _address_payload(),
        "facilities": "{}",
        "images": [],
    }

    serializer = HotelProfileSerializer(
        data=payload,
        context={"request": SimpleNamespace(user=company_user)},
    )
    assert serializer.is_valid(), serializer.errors

    with django_capture_on_commit_callbacks(execute=True):
        hotel = serializer.save()

    assert isinstance(hotel, HotelProfile)
    assert calls == [(hotel.id, f"{hotel._meta.app_label}.{hotel._meta.model_name}")]


def test_geocode_existing_listings_command_dispatches_only_missing(
    monkeypatch,
    property_listing,
):
    from apps.core.models import Address

    PropertyListing.objects.filter(id=property_listing.id).update(latitude=None, longitude=None)
    other_address = Address.objects.create(**_address_payload(street="Old Airport Road"))
    other_listing = PropertyListing.objects.create(
        company=property_listing.company,
        address=other_address,
        title="Already Geocoded",
        description="Has coordinates already",
        base_price=Decimal("2500000.00"),
        currency="ETB",
        property_type=PropertyListing.PropertyTypeChoices.APARTMENT.value,
        bedrooms=2,
        bathrooms=2,
        square_meters=Decimal("120.00"),
        is_furnished=False,
        latitude=Decimal("9.900000"),
        longitude=Decimal("38.900000"),
    )

    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    call_command("geocode_existing_listings", model="property", batch_size=1)

    assert calls == [(property_listing.id, f"{property_listing._meta.app_label}.{property_listing._meta.model_name}")]
    assert other_listing.latitude == Decimal("9.900000")


def test_geocode_existing_listings_command_dry_run(monkeypatch, property_listing, capsys):
    called = {"value": False}

    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda *args, **kwargs: called.__setitem__("value", True),
    )

    call_command("geocode_existing_listings", model="property", batch_size=1, dry_run=True)

    out = capsys.readouterr().out
    assert "Would queue geocoding" in out
    assert called["value"] is False


def test_geocode_existing_listings_command_overwrite_includes_geocoded(
    monkeypatch,
    property_listing,
):
    property_listing.latitude = Decimal("9.900000")
    property_listing.longitude = Decimal("38.900000")
    property_listing.save(update_fields=["latitude", "longitude"])
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    call_command("geocode_existing_listings", model="property", batch_size=1, overwrite=True)

    assert (property_listing.id, f"{property_listing._meta.app_label}.{property_listing._meta.model_name}") in calls


def test_geocode_existing_listings_command_dispatches_car_rental_with_formatted_address(
    monkeypatch,
    car_listing,
):
    car_listing.latitude = None
    car_listing.longitude = None
    car_listing.formatted_address = "Bole, Addis Ababa, Ethiopia"
    car_listing.listing_type = CarListing.ListingTypeChoices.RENT
    car_listing.save(update_fields=["latitude", "longitude", "formatted_address", "listing_type"])
    calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.geocode_listing_async.delay",
        lambda listing_id, model_label: calls.append((listing_id, model_label)),
    )

    call_command("geocode_existing_listings", model="car_rental", batch_size=1)

    assert (car_listing.id, f"{car_listing._meta.app_label}.{car_listing._meta.model_name}") in calls
