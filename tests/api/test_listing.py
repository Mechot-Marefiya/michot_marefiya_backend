import json
from uuid import uuid4

# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.account.models import HotelProfile, OwnerComplianceAgreement
from apps.core.models import Address, CurrencyRate
from apps.favorites.models import Favorite
from apps.listing.models import (
    AddonOffering,
    Amenity,
    Booking,
    BookingItem,
    CarAvailability,
    CarListing,
    CarSaleListing,
    ContactRevealRequest,
    PropertyContactRevealRequest,
    PropertyRentalAvailability,
    PropertyRentalBooking,
    PropertyListing,
    PropertySaleListing,
    CarRental,
    CarRentalItem,
    EventSpaceAvailability,
    EventSpaceListing,
    EventSpaceBooking,
    EventSpaceBookingItem,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseInventory,
    GuestHouseProfile,
    GuestHouseRoom,
    RoomListing,
    Season,
    SeasonalRate,
    StayAvailability,
    TermsAndConditions,
)
from apps.payment.models import PaymentTransaction
from apps.payment.services import ContactRevealPaymentService
from apps.notifications.models import Notification
from apps.account.models import User
from apps.listing.services import ListingService, BookingService

pytestmark = pytest.mark.django_db


def _listing_address_payload():
    return {
        "street_line1": "Wollo Sefer",
        "country": "Ethiopia",
        "city": "Addis Ababa",
        "sub_city": "Bole",
        "state": "Addis Ababa",
        "postal_code": "1000",
        "latitude": "9.012345",
        "longitude": "38.765432",
    }


def _create_stay_availability(room, start_date, end_date, available_rooms=None):
    available_rooms = available_rooms or room.total_units
    for offset in range((end_date - start_date).days):
        StayAvailability.objects.create(
            hotel=room.hotel,
            room=room,
            date=start_date + timedelta(days=offset),
            available_rooms=available_rooms,
        )


def _create_car_availability(car_listing, start_date, end_date, available_units=None):
    available_units = car_listing.quantity if available_units is None else available_units
    for offset in range((end_date - start_date).days):
        CarAvailability.objects.create(
            car_listing=car_listing,
            date=start_date + timedelta(days=offset),
            available_units=available_units,
        )


def _create_car_sale_listing(company, **overrides):
    defaults = {
        "company": company,
        "title": "Toyota Vitz for sale",
        "description": "Clean private sale listing",
        "base_price": Decimal("850000.00"),
        "currency": "ETB",
        "brand": CarListing.CarBrandChoices.TOYOTA,
        "model": "Vitz",
        "year": 2018,
        "mileage": 65000,
        "fuel_type": CarListing.FuelTypeChoices.PETROL,
        "transmission": CarListing.TransmissionChoices.AUTOMATIC,
        "condition": CarListing.ConditionChoices.USED,
        "car_class": CarListing.CarClassChoices.NORMAL,
        "seats": 5,
        "seller_contact_name": "Seller One",
        "seller_phone": "0911777888",
        "seller_email": "seller@example.com",
        "reveal_fee": Decimal("100.00"),
        "is_active": True,
    }
    defaults.update(overrides)
    return CarSaleListing.objects.create(**defaults)


def _create_property_sale_listing(company, **overrides):
    address = overrides.pop("address", None) or Address.objects.create(**_listing_address_payload())
    defaults = {
        "company": company,
        "address": address,
        "title": "Bole villa for sale",
        "description": "Connector listing for a private property sale",
        "base_price": Decimal("4500000.00"),
        "currency": "ETB",
        "property_type": PropertySaleListing.PropertyTypeChoices.VILLA,
        "bedrooms": 4,
        "bathrooms": 3,
        "square_meters": Decimal("240.00"),
        "land_size_square_meters": Decimal("320.00"),
        "is_furnished": True,
        "seller_contact_name": "Property Seller",
        "seller_phone": "0911222333",
        "seller_email": "property-seller@example.com",
        "reveal_fee": Decimal("150.00"),
        "is_active": True,
    }
    defaults.update(overrides)
    return PropertySaleListing.objects.create(**defaults)


def _mock_contact_reveal_chapa(settings, monkeypatch):
    settings.CHAPA_CALLBACK_URL = "https://api.example.com/payment/callback"
    settings.FRONTEND_URL = "https://app.example.com"
    settings.CHAPA_SECRET_KEY = "test-secret"

    class DummyResponse:
        def json(self):
            return {
                "status": "success",
                "data": {"checkout_url": "https://checkout.example.com/contact"},
            }

    monkeypatch.setattr("apps.payment.services.requests.post", lambda *args, **kwargs: DummyResponse())


def _create_guesthouse_inventory(room, start_date, end_date, available_rooms=None):
    available_rooms = available_rooms or room.total_units
    for offset in range((end_date - start_date).days):
        GuestHouseInventory.objects.create(
            guest_house_room=room,
            date=start_date + timedelta(days=offset),
            available_rooms=available_rooms,
            price=room.base_price,
        )


def _create_eventspace_availability(space, start_date, end_date, available_units=None):
    available_units = available_units or space.total_units
    for offset in range((end_date - start_date).days):
        EventSpaceAvailability.objects.create(
            space_listing=space,
            date=start_date + timedelta(days=offset),
            available_eventspace=available_units,
            price=space.base_price,
        )


def _create_hotel_booking(*, room, user=None, phone="0911777666", booking_reference="H-900001", guest_email="guest@example.com"):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=7),
        check_out_date=date.today() + timedelta(days=9),
        total_price=Decimal("1000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=guest_email,
        guest_phone=phone,
        special_requests="None",
        booking_reference=booking_reference,
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(
        booking=booking,
        room=room,
        units_booked=1,
        price_per_unit=Decimal("1000.00"),
    )
    return booking


def _create_terms(content_object, version="1"):
    return TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(content_object),
        object_id=content_object.id,
        version=version,
        title=f"{content_object.__class__.__name__} Terms",
        content="Terms content",
        effective_date=date.today(),
        is_active=True,
    )


def _create_property_rental_availability(property_listing, start_date, end_date, *, available_units=1, price=None):
    for day_offset in range((end_date - start_date).days):
        PropertyRentalAvailability.objects.update_or_create(
            property_listing=property_listing,
            date=start_date + timedelta(days=day_offset),
            defaults={"available_units": available_units, "price": price},
        )


def _property_rental_booking_payload(property_listing, start_date, end_date, **overrides):
    payload = {
        "property_listing": str(property_listing.id),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "guest_first_name": "Rental",
        "guest_last_name": "Guest",
        "guest_email": "property-rental@example.com",
        "guest_phone": "0911555666",
        "terms_accepted": True,
        "terms_version": "1",
    }
    payload.update(overrides)
    return payload


def _assert_verification_fields(payload, *, expected_verified=False, expected_verified_by=None, expected_note=None):
    assert "is_verified" in payload
    assert "verified_at" in payload
    assert "verified_by" in payload
    assert "verification_note" in payload
    assert payload["is_verified"] is expected_verified
    assert payload["verified_by"] == expected_verified_by
    assert payload["verification_note"] == expected_note


def _prepare_guest_booking_otp(monkeypatch):
    monkeypatch.setattr("apps.listing.services.OtpService.generate_code", lambda: "123456")
    monkeypatch.setattr("services.sms.send_sms", lambda phone, message: True)


def _issue_guest_booking_otp(api_client, path, guest_phone):
    cache.clear()
    response = api_client.post(path, {"guest_phone": guest_phone}, format="json")
    assert response.status_code == 201
    return response.json()["challenge_id"]


def test_get_amenities_public_list_success(api_client):
    Amenity.objects.create(name="WiFi", icon="wifi")

    response = api_client.get("/api/v1/listing/amenities/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["name"] == "WiFi"


def test_car_sales_happy_path_all_four_endpoints(api_client, auth_client, user, company, settings, monkeypatch):
    listing = _create_car_sale_listing(company)

    list_response = api_client.get("/api/v1/listing/car-sales/")
    assert list_response.status_code == 200
    list_item = list_response.json()["results"][0]
    assert list_item["id"] == str(listing.id)
    assert "seller_phone" not in list_item
    assert "seller_email" not in list_item
    assert "seller_contact_name" not in list_item

    detail_response = api_client.get(f"/api/v1/listing/car-sales/{listing.id}/")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == str(listing.id)
    assert detail["reveal_state"] is None
    assert "seller_phone" not in detail

    _mock_contact_reveal_chapa(settings, monkeypatch)
    request_response = auth_client.post(
        f"/api/v1/listing/car-sales/{listing.id}/request-contact/",
        {"buyer_note": "I want to inspect it.", "buyer_phone": user.phone},
        format="json",
    )
    assert request_response.status_code == 201
    request_data = request_response.json()
    assert request_data["checkout_url"] == "https://checkout.example.com/contact"
    assert request_data["reveal_request"]["status"] == ContactRevealRequest.RevealStatus.PAYMENT_INITIATED
    assert PaymentTransaction.objects.filter(
        tx_ref=request_data["tx_ref"],
        booking_type="contact_reveal",
    ).exists()
    assert "seller_phone" not in request_data

    blocked_contact = auth_client.get(f"/api/v1/listing/car-sales/{listing.id}/contact/")
    assert blocked_contact.status_code == 403

    reveal_request = ContactRevealRequest.objects.get(id=request_data["reveal_request"]["id"])
    reveal_request.status = ContactRevealRequest.RevealStatus.PAID_REVEALED
    reveal_request.unlocked_at = timezone.now()
    reveal_request.contact_snapshot = {
        "seller_contact_name": listing.seller_contact_name,
        "seller_phone": listing.seller_phone,
        "seller_email": listing.seller_email,
        "off_platform_notice": "The sale closes off-platform.",
    }
    reveal_request.save(update_fields=["status", "unlocked_at", "contact_snapshot", "updated_at"])

    contact_response = auth_client.get(f"/api/v1/listing/car-sales/{listing.id}/contact/")
    assert contact_response.status_code == 200
    contact = contact_response.json()
    assert contact["seller_phone"] == listing.seller_phone
    assert contact["seller_email"] == listing.seller_email
    assert "off_platform_notice" in contact


def test_car_sales_create_success_for_company_owner(company_client):
    response = company_client.post(
        "/api/v1/listing/car-sales/",
        {
            "title": "Sale Corolla",
            "description": "Ready for transfer",
            "base_price": "900000.00",
            "currency": "ETB",
            "brand": CarListing.CarBrandChoices.TOYOTA,
            "model": "Corolla",
            "year": 2020,
            "mileage": 40000,
            "fuel_type": CarListing.FuelTypeChoices.PETROL,
            "transmission": CarListing.TransmissionChoices.AUTOMATIC,
            "condition": CarListing.ConditionChoices.USED,
            "car_class": CarListing.CarClassChoices.NORMAL,
            "seats": 5,
            "seller_contact_name": "Fleet Seller",
            "seller_phone": "0911222000",
            "seller_email": "fleet@example.com",
            "reveal_fee": "100.00",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Sale Corolla"
    assert data["is_active"] is False
    assert "seller_phone" not in data


def test_car_sales_auth_errors_and_wrong_role(api_client, auth_client, company):
    listing = _create_car_sale_listing(company)

    assert api_client.post(f"/api/v1/listing/car-sales/{listing.id}/request-contact/", {}, format="json").status_code == 401
    assert api_client.get(f"/api/v1/listing/car-sales/{listing.id}/contact/").status_code == 401

    response = auth_client.post(
        "/api/v1/listing/car-sales/",
        {
            "title": "Unauthorized Sale",
            "base_price": "900000.00",
            "currency": "ETB",
            "brand": CarListing.CarBrandChoices.TOYOTA,
            "model": "Corolla",
            "year": 2020,
            "mileage": 40000,
            "fuel_type": CarListing.FuelTypeChoices.PETROL,
            "transmission": CarListing.TransmissionChoices.AUTOMATIC,
            "condition": CarListing.ConditionChoices.USED,
            "seller_phone": "0911222000",
            "reveal_fee": "100.00",
        },
        format="json",
    )
    assert response.status_code == 403


def test_car_sales_owner_cannot_request_own_contact(company_client, company):
    listing = _create_car_sale_listing(company)

    response = company_client.post(
        f"/api/v1/listing/car-sales/{listing.id}/request-contact/",
        {},
        format="json",
    )

    assert response.status_code == 403


def test_car_sales_validation_errors(company_client):
    response = company_client.post(
        "/api/v1/listing/car-sales/",
        {
            "title": "Bad Sale",
            "base_price": "0.00",
            "currency": "ETB",
            "brand": CarListing.CarBrandChoices.TOYOTA,
            "model": "Corolla",
            "year": 2020,
            "mileage": 40000,
            "fuel_type": CarListing.FuelTypeChoices.PETROL,
            "transmission": CarListing.TransmissionChoices.AUTOMATIC,
            "condition": CarListing.ConditionChoices.USED,
            "seller_phone": "",
            "reveal_fee": "0.00",
        },
        format="json",
    )

    assert response.status_code == 400


def _property_sale_payload(**overrides):
    payload = {
        "title": "Bole villa sale",
        "description": "Property sale connector listing",
        "base_price": "4500000.00",
        "currency": "ETB",
        "address": _listing_address_payload(),
        "property_type": PropertySaleListing.PropertyTypeChoices.VILLA,
        "bedrooms": 4,
        "bathrooms": 3,
        "square_meters": "240.00",
        "land_size_square_meters": "320.00",
        "is_furnished": True,
        "seller_contact_name": "Property Seller",
        "seller_phone": "0911222333",
        "seller_email": "property-seller@example.com",
        "reveal_fee": "150.00",
    }
    payload.update(overrides)
    return payload


def test_property_sales_happy_path_all_three_endpoints(api_client, auth_client, user, company, settings, monkeypatch):
    _mock_contact_reveal_chapa(settings, monkeypatch)
    listing = _create_property_sale_listing(company)

    list_response = api_client.get("/api/v1/listing/property-sales/")
    assert list_response.status_code == 200
    list_data = list_response.json()["results"]
    assert len(list_data) >= 1
    assert "seller_phone" not in list_data[0]
    assert "seller_email" not in list_data[0]

    detail_response = api_client.get(f"/api/v1/listing/property-sales/{listing.id}/")
    assert detail_response.status_code == 200
    detail_data = detail_response.json()
    assert detail_data["id"] == str(listing.id)
    assert detail_data["reveal_state"] is None
    assert "seller_phone" not in detail_data

    request_response = auth_client.post(
        f"/api/v1/listing/property-sales/{listing.id}/request-contact/",
        {"buyer_note": "I want to schedule a visit", "buyer_phone": "0911999888"},
        format="json",
    )
    assert request_response.status_code == 201
    request_data = request_response.json()
    assert request_data["success"] is True
    assert request_data["checkout_url"] == "https://checkout.example.com/contact"
    assert request_data["reveal_request"]["status"] == PropertyContactRevealRequest.RevealStatus.PAYMENT_INITIATED
    assert "contact" not in request_data
    assert "seller_phone" not in json.dumps(request_data)

    reveal_request = PropertyContactRevealRequest.objects.get(id=request_data["reveal_request"]["id"])
    assert reveal_request.listing == listing
    assert reveal_request.buyer == user
    assert reveal_request.amount == listing.reveal_fee
    assert PaymentTransaction.objects.filter(
        object_id=reveal_request.id,
        booking_type="contact_reveal",
        tx_ref=request_data["tx_ref"],
    ).exists()


def test_property_sales_create_success_for_company_owner(company_client):
    response = company_client.post(
        "/api/v1/listing/property-sales/",
        _property_sale_payload(),
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Bole villa sale"
    assert data["property_type"] == PropertySaleListing.PropertyTypeChoices.VILLA
    assert data["is_active"] is False
    assert "seller_phone" not in data
    assert PropertySaleListing.objects.filter(title="Bole villa sale").exists()


def test_property_sales_auth_errors_and_wrong_role(api_client, auth_client, company):
    listing = _create_property_sale_listing(company)

    assert api_client.post(f"/api/v1/listing/property-sales/{listing.id}/request-contact/", {}, format="json").status_code == 401

    response = auth_client.post(
        "/api/v1/listing/property-sales/",
        _property_sale_payload(title="Wrong role property"),
        format="json",
    )
    assert response.status_code == 403


def test_property_sales_owner_cannot_request_own_contact(company_client, company):
    listing = _create_property_sale_listing(company)

    response = company_client.post(
        f"/api/v1/listing/property-sales/{listing.id}/request-contact/",
        {},
        format="json",
    )

    assert response.status_code == 403


def test_property_sales_validation_errors(company_client):
    response = company_client.post(
        "/api/v1/listing/property-sales/",
        _property_sale_payload(base_price="-1.00", reveal_fee="0.00", seller_phone=""),
        format="json",
    )

    assert response.status_code == 400


def test_property_sales_reveal_blocked_before_payment_success(auth_client, company, settings, monkeypatch):
    _mock_contact_reveal_chapa(settings, monkeypatch)
    listing = _create_property_sale_listing(company)

    request_response = auth_client.post(
        f"/api/v1/listing/property-sales/{listing.id}/request-contact/",
        {},
        format="json",
    )

    assert request_response.status_code == 201
    assert "seller_phone" not in json.dumps(request_response.json())
    detail_response = auth_client.get(f"/api/v1/listing/property-sales/{listing.id}/")
    assert detail_response.status_code == 200
    detail_data = detail_response.json()
    assert detail_data["reveal_state"]["status"] == PropertyContactRevealRequest.RevealStatus.PAYMENT_INITIATED
    assert "seller_phone" not in detail_data


def test_property_sales_notification_task_fires_after_reveal(
    django_capture_on_commit_callbacks,
    monkeypatch,
    user,
    company,
):
    listing = _create_property_sale_listing(company)
    reveal_request = PropertyContactRevealRequest.objects.create(
        listing=listing,
        buyer=user,
        amount=listing.reveal_fee,
        currency=listing.currency,
        status=PropertyContactRevealRequest.RevealStatus.PAYMENT_INITIATED,
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(PropertyContactRevealRequest),
        object_id=reveal_request.id,
        booking_type="contact_reveal",
        tx_ref="PROPERTY-CONTACT-1",
        amount=reveal_request.amount,
        currency=reveal_request.currency,
    )
    delay_calls = []
    monkeypatch.setattr(
        "apps.listing.tasks.send_contact_reveal_unlocked_notification.delay",
        lambda reveal_request_id: delay_calls.append(reveal_request_id),
    )

    with django_capture_on_commit_callbacks(execute=True):
        result = ContactRevealPaymentService.unlock_contact_reveal(
            payment_tx,
            {
                "amount": str(reveal_request.amount),
                "currency": reveal_request.currency,
                "id": "chapa-property-contact",
                "method": "test",
            },
        )

    reveal_request.refresh_from_db()
    assert result["success"] is True
    assert reveal_request.status == PropertyContactRevealRequest.RevealStatus.PAID_REVEALED
    assert delay_calls == [reveal_request.id]


def test_property_rental_booking_happy_path_all_four_endpoints(auth_client, property_listing):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(property_listing)
    _create_property_rental_availability(property_listing, start_date, end_date, price=Decimal("3000.00"))

    preview_response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/price-preview/",
        {
            "property_listing": str(property_listing.id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_phone": "0911555601",
        },
        format="json",
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["nights"] == 2
    assert preview["items"][0]["units"] == 1
    assert Decimal(preview["totals"]["items_subtotal"]) == Decimal("6000.00")

    create_response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_phone="0911555601"),
        format="json",
    )
    assert create_response.status_code == 201
    booking_data = create_response.json()
    assert booking_data["booking_reference"].startswith("P")
    assert booking_data["status"] == PropertyRentalBooking.RentStatus.PENDING

    booking = PropertyRentalBooking.objects.get(id=booking_data["id"])
    for availability in PropertyRentalAvailability.objects.filter(property_listing=property_listing, date__gte=start_date, date__lt=end_date):
        assert availability.available_units == 0

    detail_response = auth_client.get(f"/api/v1/listing/property-rentals/bookings/{booking.id}/")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == str(booking.id)

    cancel_response = auth_client.post(f"/api/v1/listing/property-rentals/bookings/{booking.id}/cancel/")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == PropertyRentalBooking.RentStatus.CANCELLED
    for availability in PropertyRentalAvailability.objects.filter(property_listing=property_listing, date__gte=start_date, date__lt=end_date):
        assert availability.available_units == 1


def test_property_rental_booking_unauthenticated_detail_and_cancel(api_client, property_listing):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    booking = PropertyRentalBooking.objects.create(
        property_listing=property_listing,
        start_date=start_date,
        end_date=end_date,
        total_price=Decimal("6000.00"),
        currency="ETB",
        status=PropertyRentalBooking.RentStatus.PENDING,
        guest_first_name="Unauth",
        guest_last_name="Guest",
        guest_email="property-rental-unauth@example.com",
        guest_phone="0911555602",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )

    assert api_client.get(f"/api/v1/listing/property-rentals/bookings/{booking.id}/").status_code == 401
    assert api_client.post(f"/api/v1/listing/property-rentals/bookings/{booking.id}/cancel/").status_code == 401


def test_property_rental_booking_forbidden_for_wrong_user_and_owner(company_client, api_client, django_user_model, property_listing):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    renter = django_user_model.objects.create_user(
        email="property-rental-owner-renter@example.com",
        password="pass1234",
        phone="0911555603",
    )
    other = django_user_model.objects.create_user(
        email="property-rental-other@example.com",
        password="pass1234",
        phone="0911555604",
    )
    booking = PropertyRentalBooking.objects.create(
        property_listing=property_listing,
        renter=renter,
        start_date=start_date,
        end_date=end_date,
        total_price=Decimal("6000.00"),
        currency="ETB",
        status=PropertyRentalBooking.RentStatus.PENDING,
        guest_first_name="Rental",
        guest_last_name="Guest",
        guest_email=renter.email,
        guest_phone=renter.phone,
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )

    api_client.force_authenticate(user=other)
    assert api_client.get(f"/api/v1/listing/property-rentals/bookings/{booking.id}/").status_code == 403

    _create_terms(property_listing)
    _create_property_rental_availability(property_listing, start_date, end_date)
    owner_response = company_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_email="owner-booking@example.com"),
        format="json",
    )
    assert owner_response.status_code == 403


def test_property_rental_booking_validation_errors(auth_client, property_listing):
    start_date = date.today() + timedelta(days=5)
    response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(
            property_listing,
            start_date,
            start_date,
            terms_accepted=False,
            guest_email="property-rental-invalid@example.com",
        ),
        format="json",
    )
    assert response.status_code == 400


def test_property_rental_booking_rejects_availability_conflict(auth_client, property_listing):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(property_listing)
    _create_property_rental_availability(property_listing, start_date, end_date, available_units=0)

    response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_email="property-rental-conflict@example.com"),
        format="json",
    )

    assert response.status_code == 409
    assert not PropertyRentalBooking.objects.filter(guest_email="property-rental-conflict@example.com").exists()


def test_property_rental_price_preview_returns_correct_calculation(auth_client, property_listing):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=3)
    _create_property_rental_availability(property_listing, start_date, end_date, price=Decimal("1250.00"))

    response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/price-preview/",
        {
            "property_listing": str(property_listing.id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_phone": "0911555605",
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["nights"] == 3
    assert Decimal(data["totals"]["items_subtotal"]) == Decimal("3750.00")
    assert Decimal(data["totals"]["grand_total"]) == Decimal("3750.00")


def test_property_rental_forward_booking_window_rejection(auth_client, property_listing):
    property_listing.booking_forward_window_days = 1
    property_listing.save(update_fields=["booking_forward_window_days"])
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(property_listing)
    _create_property_rental_availability(property_listing, start_date, end_date)

    response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_email="property-rental-window@example.com"),
        format="json",
    )

    assert response.status_code == 400
    assert "start_date" in response.json()


def test_property_rental_booking_terms_snapshot_preserved(auth_client, property_listing):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    terms = _create_terms(property_listing)
    terms.content = "Original rental terms"
    terms.save(update_fields=["content"])
    _create_property_rental_availability(property_listing, start_date, end_date)

    response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_email="property-rental-snapshot@example.com"),
        format="json",
    )

    assert response.status_code == 201
    booking = PropertyRentalBooking.objects.get(id=response.json()["id"])
    terms.content = "Updated rental terms"
    terms.save(update_fields=["content"])
    booking.refresh_from_db()
    assert booking.terms_content_snapshot == "Original rental terms"


def test_property_rental_booking_requires_signed_owner_agreement(api_client, individual_owner):
    property_listing = PropertyListing.objects.create(
        company=None,
        individual_owner=individual_owner,
        title="Owner rental property",
        description="Individual-owner rental requiring compliance agreement",
        base_price=Decimal("3000.00"),
        currency="ETB",
        property_type=PropertyListing.PropertyTypeChoices.VILLA,
        bedrooms=3,
        bathrooms=2,
        square_meters=Decimal("140.00"),
        is_furnished=True,
        address=Address.objects.create(**_listing_address_payload()),
    )
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(property_listing)
    _create_property_rental_availability(property_listing, start_date, end_date)

    response = api_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_email="owner-agreement-missing@example.com"),
        format="json",
    )

    assert response.status_code == 400
    assert "Owner has not completed compliance agreement." in response.json()[0]


def test_property_rental_booking_allows_signed_owner_agreement(api_client, admin_user, individual_owner):
    property_listing = PropertyListing.objects.create(
        company=None,
        individual_owner=individual_owner,
        title="Compliant owner rental",
        description="Individual-owner rental with signed agreement",
        base_price=Decimal("3000.00"),
        currency="ETB",
        property_type=PropertyListing.PropertyTypeChoices.VILLA,
        bedrooms=3,
        bathrooms=2,
        square_meters=Decimal("140.00"),
        is_furnished=True,
        address=Address.objects.create(**_listing_address_payload()),
    )
    OwnerComplianceAgreement.objects.create(
        owner=individual_owner,
        agreement_version="v1",
        status=OwnerComplianceAgreement.Status.SIGNED,
        signed_at=timezone.now(),
        signed_by_admin=admin_user,
    )
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(property_listing)
    _create_property_rental_availability(property_listing, start_date, end_date)

    response = api_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_email="owner-agreement-present@example.com"),
        format="json",
    )

    assert response.status_code == 201


def test_property_rental_booking_company_owner_unaffected_by_agreement_gate(api_client, property_listing):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(property_listing)
    _create_property_rental_availability(property_listing, start_date, end_date)

    response = api_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        _property_rental_booking_payload(property_listing, start_date, end_date, guest_email="company-owner-unaffected@example.com"),
        format="json",
    )

    assert response.status_code == 201


def test_post_amenity_admin_create_success(admin_client):
    response = admin_client.post(
        "/api/v1/listing/amenities/",
        {"name": "Projector", "icon": "projector"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Projector"
    assert data["icon"] == "projector"


def test_patch_amenity_admin_update_success(admin_client):
    amenity = Amenity.objects.create(name="Pool Table", icon="pool-table")

    response = admin_client.patch(
        f"/api/v1/listing/amenities/{amenity.id}/",
        {"icon": "billiards"},
        format="json",
    )

    assert response.status_code == 200
    amenity.refresh_from_db()
    assert amenity.icon == "billiards"


def test_delete_amenity_admin_delete_success(admin_client):
    amenity = Amenity.objects.create(name="Speaker", icon="speaker")

    response = admin_client.delete(f"/api/v1/listing/amenities/{amenity.id}/")

    assert response.status_code == 204
    assert Amenity.objects.filter(id=amenity.id).exists() is False


def test_amenity_non_admin_forbidden(auth_client):
    response = auth_client.post(
        "/api/v1/listing/amenities/",
        {"name": "Projector", "icon": "projector"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("path", "booking_type"),
    [
        ("/api/v1/listing/bookings/guest-otp/request/", "hotel"),
        ("/api/v1/listing/guesthouse-bookings/guest-otp/request/", "guesthouse"),
        ("/api/v1/listing/bookings-eventspaces/guest-otp/request/", "eventspace"),
        ("/api/v1/listing/car-rentals/guest-otp/request/", "car_rental"),
    ],
)
def test_post_guest_booking_otp_request_success(api_client, monkeypatch, path, booking_type):
    monkeypatch.setattr("apps.listing.services.OtpService.generate_code", lambda: "123456")
    sent_messages = []
    monkeypatch.setattr("services.sms.send_sms", lambda phone, message: sent_messages.append((phone, message)) or True)

    response = api_client.post(path, {"guest_phone": "0911002000"}, format="json")

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["purpose"] == "guest_booking"
    assert data["booking_type"] == booking_type
    assert data["phone"] == "0911002000"
    assert data["challenge_id"]
    assert data["expires_at"]
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "0911002000"
    assert "123456" in sent_messages[0][1]


def test_get_room_list_public_contract(api_client, room):
    response = api_client.get("/api/v1/listing/rooms/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(room.id)
    assert data["results"][0]["title"] == room.title


def test_get_room_detail_public_contract(api_client, room):
    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(room.id)
    assert data["title"] == room.title
    assert "base_price" in data
    assert "currency" in data


def test_get_room_detail_includes_conversion_when_display_currency_requested(api_client, room):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("100.000000"), date=date.today())

    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/", {"display_currency": "USD"})

    assert response.status_code == 200
    data = response.json()
    assert data["conversion"]["from"] == room.currency
    assert data["conversion"]["to"] == "USD"
    assert "rate" in data["conversion"]
    assert "total" in data["conversion"]
    assert "calculated_at" in data["conversion"]


def test_get_room_list_includes_conversion_when_display_currency_requested(api_client, room):
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("100.000000"), date=date.today())

    response = api_client.get("/api/v1/listing/rooms/", {"display_currency": "USD"})

    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["id"] == str(room.id)
    assert data["results"][0]["conversion"]["from"] == room.currency
    assert data["results"][0]["conversion"]["to"] == "USD"


def test_get_room_price_preview_public_contract(api_client, room):
    response = api_client.get(
        f"/api/v1/listing/rooms/{room.id}/price-preview/",
        {"check_in": "2026-06-10", "check_out": "2026-06-12"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "lines" in data
    assert "total" in data
    assert "has_discount" in data
    assert "warning" in data


def test_get_room_price_preview_invalid_payload(api_client, room):
    response = api_client.get(f"/api/v1/listing/rooms/{room.id}/price-preview/")

    assert response.status_code == 400


def test_get_room_detail_price_quote_waives_then_charges_based_on_phone(api_client, room, user):
    phone = "0911777666"
    user.phone = phone
    user.save(update_fields=["phone", "updated_at"])

    first_response = api_client.get(
        f"/api/v1/listing/rooms/{room.id}/",
        {"check_in": "2026-06-10", "check_out": "2026-06-12", "guest_phone": phone},
    )

    assert first_response.status_code == 200
    first_data = first_response.json()
    assert first_data["price_quote"]["platform_fee"] == "0.00"
    assert first_data["price_quote"]["platform_fee_percentage"] == "0.00"

    _create_hotel_booking(room=room, user=user, phone=phone, booking_reference="H-900001")

    repeat_response = api_client.get(
        f"/api/v1/listing/rooms/{room.id}/",
        {"check_in": "2026-06-10", "check_out": "2026-06-12", "guest_phone": phone},
    )

    assert repeat_response.status_code == 200
    repeat_data = repeat_response.json()
    assert repeat_data["price_quote"]["platform_fee_percentage"] == "5.00"
    assert Decimal(repeat_data["price_quote"]["platform_fee"]) > Decimal("0.00")


def test_booking_service_applies_first_booking_waiver_across_guest_and_authenticated_flows(room, user):
    phone = "0911888777"
    user.phone = phone
    user.save(update_fields=["phone", "updated_at"])

    guest_booking = _create_hotel_booking(
        room=room,
        user=None,
        phone=phone,
        booking_reference="H-900010",
        guest_email="guest-first@example.com",
    )
    assert BookingService.get_booking_total(guest_booking) == Decimal("2000.00")

    auth_booking = _create_hotel_booking(
        room=room,
        user=user,
        phone=phone,
        booking_reference="H-900011",
        guest_email="auth-repeat@example.com",
    )
    assert BookingService.get_booking_total(auth_booking) == Decimal("2100.00")


def test_get_room_availability_matrix_owner_only(company_client, hotel, room):
    matrix_date = date(2026, 6, 10)
    StayAvailability.objects.create(hotel=hotel, room=room, date=matrix_date, available_rooms=2)

    response = company_client.get(
        "/api/v1/listing/rooms/availability-matrix/",
        {
            "workspace": str(hotel.id),
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["room_id"] == str(room.id)
    assert data[0]["availability"][0]["date"] == matrix_date.isoformat()
    assert data[0]["availability"][0]["available"] == 2
    assert data[0]["availability"][0]["status"] == "partial"


def test_get_room_availability_matrix_invalid_payload(company_client):
    response = company_client.get(
        "/api/v1/listing/rooms/availability-matrix/",
        {"workspace": str(uuid4()), "start_date": "bad-date", "end_date": "2026-06-12"},
    )

    assert response.status_code == 400


def test_get_guesthouse_list_public_contract(api_client, guest_house):
    response = api_client.get("/api/v1/listing/guest-houses/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(guest_house.id)
    _assert_verification_fields(data["results"][0])


def test_get_guesthouse_detail_public_contract(api_client, guest_house):
    response = api_client.get(f"/api/v1/listing/guest-houses/{guest_house.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(guest_house.id)
    assert data["title"] == guest_house.title
    assert "rooms" in data
    _assert_verification_fields(data)


def test_post_guesthouse_create_unauthenticated(api_client, image_file, company):
    response = api_client.post(
        "/api/v1/listing/guest-houses/",
        {
            "title": "Guest House Draft",
            "description": "Draft guest house",
            "company": str(company.id),
            "address": json.dumps(_listing_address_payload()),
            "amenities": json.dumps([]),
            "images": [image_file],
        },
        format="multipart",
    )

    assert response.status_code == 401


def test_post_guesthouse_create_success(company_client, api_client, company, image_file):
    response = company_client.post(
        "/api/v1/listing/guest-houses/",
        {
            "title": "Guest House Draft",
            "description": "Draft guest house",
            "company": str(company.id),
            "address": json.dumps(_listing_address_payload()),
            "amenities": json.dumps([]),
            "images": [image_file],
        },
        format="multipart",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Guest House Draft"
    guest_house_profile = GuestHouseProfile.objects.get(id=data["id"])
    assert guest_house_profile.is_active is False
    list_response = api_client.get("/api/v1/listing/guest-houses/")
    assert all(item["id"] != data["id"] for item in list_response.json()["results"])


def test_patch_guesthouse_success(company_client, guest_house):
    response = company_client.patch(
        f"/api/v1/listing/guest-houses/{guest_house.id}/",
        {"title": "Updated Guest House"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Guest House"


def test_patch_guesthouse_forbidden_for_non_owner(auth_client, guest_house):
    response = auth_client.patch(
        f"/api/v1/listing/guest-houses/{guest_house.id}/",
        {"title": "Updated Guest House"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_guesthouse_success(company_client, guest_house):
    response = company_client.delete(f"/api/v1/listing/guest-houses/{guest_house.id}/")

    assert response.status_code == 204


def test_get_guesthouse_check_availability_public_contract(api_client, guest_house):
    response = api_client.get(
        "/api/v1/listing/guest-houses/check-availability/",
        {
            "check_in": "2026-06-10",
            "check_out": "2026-06-12",
            "guesthouse_id": str(guest_house.id),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data


def test_get_guesthouse_room_list_public_contract(api_client, guest_house_room):
    response = api_client.get("/api/v1/listing/guest-house-rooms/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(guest_house_room.id)


def test_get_guesthouse_room_detail_public_contract(api_client, guest_house_room):
    response = api_client.get(f"/api/v1/listing/guest-house-rooms/{guest_house_room.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(guest_house_room.id)
    assert data["title"] == guest_house_room.title


def test_post_guesthouse_room_create_unauthenticated(api_client, guest_house):
    response = api_client.post(
        "/api/v1/listing/guest-house-rooms/",
        {
            "guest_house_id": str(guest_house.id),
            "title": "Room Draft",
            "base_price": "900.00",
            "currency": "ETB",
            "number_of_guests": 2,
            "total_units": 2,
            "bed_type": "twin",
            "room_size_sqm": 18,
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_guesthouse_room_create_success(company_client, guest_house):
    response = company_client.post(
        "/api/v1/listing/guest-house-rooms/",
        {
            "guest_house_id": str(guest_house.id),
            "title": "Room Draft",
            "base_price": "900.00",
            "currency": "ETB",
            "number_of_guests": 2,
            "total_units": 2,
            "bed_type": "twin",
            "room_size_sqm": 18,
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Room Draft"
    guest_house_room = GuestHouseRoom.objects.get(id=data["id"])
    assert guest_house_room.is_active is False


def test_patch_guesthouse_room_success(company_client, guest_house_room):
    response = company_client.patch(
        f"/api/v1/listing/guest-house-rooms/{guest_house_room.id}/",
        {"title": "Updated Guest House Room"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Guest House Room"


def test_delete_guesthouse_room_success(company_client, guest_house_room):
    response = company_client.delete(f"/api/v1/listing/guest-house-rooms/{guest_house_room.id}/")

    assert response.status_code == 204


def test_get_guesthouse_room_availability_matrix_owner_only(company_client, guest_house, guest_house_room):
    matrix_date = date(2026, 6, 10)
    GuestHouseInventory.objects.create(
        guest_house_room=guest_house_room,
        date=matrix_date,
        available_rooms=1,
        price=guest_house_room.base_price,
    )

    response = company_client.get(
        "/api/v1/listing/guest-house-rooms/availability-matrix/",
        {
            "workspace": str(guest_house.id),
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["room_id"] == str(guest_house_room.id)
    assert data[0]["availability"][0]["date"] == matrix_date.isoformat()
    assert data[0]["availability"][0]["available"] == 1
    assert data[0]["availability"][0]["status"] == "partial"


def test_get_guesthouse_room_availability_matrix_missing_payload(company_client):
    response = company_client.get("/api/v1/listing/guest-house-rooms/availability-matrix/")

    assert response.status_code == 400


def test_get_car_list_public_contract(api_client, car_listing):
    response = api_client.get("/api/v1/listing/cars/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(car_listing.id)
    _assert_verification_fields(data["results"][0])


def test_get_car_detail_public_contract(api_client, car_listing):
    response = api_client.get(f"/api/v1/listing/cars/{car_listing.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(car_listing.id)
    assert data["brand"] == car_listing.brand
    assert data["model"] == car_listing.model
    _assert_verification_fields(data)


def test_post_car_listing_create_success(company_client, company):
    response = company_client.post(
        "/api/v1/listing/cars/",
        {
            "title": "Car Draft",
            "description": "Car created in tests",
            "base_price": "1500.00",
            "currency": "ETB",
            "company": str(company.id),
            "brand": CarListing.CarBrandChoices.TOYOTA,
            "model": "Camry",
            "year": 2024,
            "mileage": 1000,
            "fuel_type": CarListing.FuelTypeChoices.PETROL,
            "transmission": CarListing.TransmissionChoices.AUTOMATIC,
            "condition": CarListing.ConditionChoices.USED,
            "seats": 4,
            "listing_type": CarListing.ListingTypeChoices.RENT,
            "rental_mode": CarListing.RentalModeChoices.WITHOUT_DRIVER,
            "car_class": CarListing.CarClassChoices.NORMAL,
            "quantity": 1,
            "requires_code_3": True,
            "requires_business_license": True,
            "pre_rental_requirements": "Bring original IDs and complete a pre-rental checklist.",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Car Draft"
    assert data["rental_mode"] == CarListing.RentalModeChoices.WITHOUT_DRIVER
    assert data["requires_code_3"] is True
    assert data["requires_business_license"] is True
    car_listing = CarListing.objects.get(id=data["id"])
    assert car_listing.is_active is False
    assert car_listing.pre_rental_requirements == "Bring original IDs and complete a pre-rental checklist."


def test_patch_car_listing_success(company_client, car_listing):
    response = company_client.patch(
        f"/api/v1/listing/cars/{car_listing.id}/",
        {"title": "Updated Car Title"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Car Title"


def test_patch_car_listing_forbidden_for_non_owner(auth_client, car_listing):
    response = auth_client.patch(
        f"/api/v1/listing/cars/{car_listing.id}/",
        {"title": "Updated Car Title"},
        format="json",
    )

    assert response.status_code == 403


def test_patch_car_listing_compliance_forbidden_for_non_owner(auth_client, car_listing):
    response = auth_client.patch(
        f"/api/v1/listing/cars/{car_listing.id}/",
        {
            "rental_mode": CarListing.RentalModeChoices.WITHOUT_DRIVER,
            "requires_code_3": True,
        },
        format="json",
    )

    assert response.status_code == 403


def test_delete_car_listing_success(company_client, car_listing):
    response = company_client.delete(f"/api/v1/listing/cars/{car_listing.id}/")

    assert response.status_code == 204


@patch("services.sms.send_sms", return_value=True)
def test_delete_car_listing_notifies_saved_users(mock_send_sms, company_client, car_listing):
    saved_user = User.objects.create_user(email="saved-car@example.com", password="pass1234")
    content_type = ContentType.objects.get_for_model(car_listing.__class__)

    Favorite.objects.create(
        user=saved_user,
        content_type=content_type,
        object_id=str(car_listing.id),
    )

    response = company_client.delete(f"/api/v1/listing/cars/{car_listing.id}/")

    assert response.status_code == 204
    assert (
        Notification.objects.filter(
            user=saved_user,
            notification_type=Notification.NotificationType.LISTING_DELETED,
            metadata__listing_id=str(car_listing.id),
        ).count()
        == 1
    )
    mock_send_sms.assert_not_called()


def test_post_car_check_availability_success(api_client, car_listing):
    start_date = date.today() + timedelta(days=1)
    end_date = start_date + timedelta(days=2)
    CarAvailability.objects.create(car_listing=car_listing, date=start_date, available_units=1)
    CarAvailability.objects.create(car_listing=car_listing, date=start_date + timedelta(days=1), available_units=1)

    response = api_client.post(
        f"/api/v1/listing/cars/{car_listing.id}/check_availability/",
        {"quantity": 1, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    assert response.content in {b"", b"null"}


def test_get_car_available_for_rent_public_contract(api_client, car_listing):
    CarAvailability.objects.create(car_listing=car_listing, date=date.today() + timedelta(days=1), available_units=1)

    response = api_client.get(
        "/api/v1/listing/cars/available_for_rent/",
        {
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
            "brand": car_listing.brand,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data


def test_get_car_lookup_public_contract(api_client, car_rental):
    response = api_client.get(
        "/api/v1/listing/car-rentals/lookup/",
        {"reference": car_rental.booking_reference, "email": car_rental.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == car_rental.booking_reference


def test_post_car_rental_with_driver_success(auth_client, car_listing):
    car_listing.rental_mode = CarListing.RentalModeChoices.WITH_DRIVER
    car_listing.save(update_fields=["rental_mode"])
    _create_terms(car_listing.company)
    start_date = date.today() + timedelta(days=4)
    end_date = start_date + timedelta(days=2)
    _create_car_availability(car_listing, start_date, end_date)

    response = auth_client.post(
        "/api/v1/listing/car-rentals/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "rental_items": [
                {
                    "car_listing": str(car_listing.id),
                    "units_rent": 1,
                    "price_per_unit": "1500.00",
                }
            ],
            "terms_accepted": True,
            "terms_version": "1",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["renter_driver_license_number"] == ""


def test_post_car_rental_without_driver_missing_document_failure(auth_client, car_listing):
    car_listing.rental_mode = CarListing.RentalModeChoices.WITHOUT_DRIVER
    car_listing.save(update_fields=["rental_mode"])
    _create_terms(car_listing.company)
    start_date = date.today() + timedelta(days=4)
    end_date = start_date + timedelta(days=2)
    _create_car_availability(car_listing, start_date, end_date)

    response = auth_client.post(
        "/api/v1/listing/car-rentals/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "rental_items": [
                {
                    "car_listing": str(car_listing.id),
                    "units_rent": 1,
                    "price_per_unit": "1500.00",
                }
            ],
            "terms_accepted": True,
            "terms_version": "1",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "renter_driver_license_number" in response.json()


def test_get_room_booking_lookup_public_contract(api_client, booking):
    response = api_client.get(
        "/api/v1/listing/bookings/lookup/",
        {"reference": booking.booking_reference, "email": booking.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == booking.booking_reference


def test_get_room_booking_lookup_invalid_payload(api_client):
    response = api_client.get("/api/v1/listing/bookings/lookup/")

    assert response.status_code == 400


def test_room_booking_partial_cancel_success(api_client, user, room):
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=2),
        check_out_date=date.today() + timedelta(days=4),
        total_price=Decimal("4000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000111",
        special_requests="No peanuts",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    booking_item = BookingItem.objects.create(
        booking=booking,
        room=room,
        units_booked=2,
        price_per_unit=Decimal("1000.00"),
    )
    _create_stay_availability(room, booking.check_in_date, booking.check_out_date)

    api_client.force_authenticate(user=user)
    response = api_client.post(
        f"/api/v1/listing/bookings/{booking.id}/partial-cancel/",
        {"item_id": str(booking_item.id), "units_to_cancel": 1},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    booking_item.refresh_from_db()
    assert booking.status == Booking.BookingStatus.PENDING
    assert booking_item.units_booked == 1


def test_hotel_booking_cancel_returns_no_refund_policy(api_client, user, room):
    booking = _create_hotel_booking(
        room=room,
        user=user,
        phone=user.phone,
        booking_reference="H-900013",
        guest_email=user.email,
    )
    _create_stay_availability(room, booking.check_in_date, booking.check_out_date)

    api_client.force_authenticate(user=user)
    response = api_client.post(f"/api/v1/listing/bookings/{booking.id}/cancel/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(booking.id)
    assert data["status"] == Booking.BookingStatus.CANCELLED
    assert data["refund_supported"] is False
    assert data["refund_policy"] == "no_refunds"
    assert "No refunds are available" in data["refund_message"]
    assert data["cancellation_effect"] == "booking_cancelled"


def test_room_booking_workspace_bookings_success(front_desk_client, front_desk_user, room):
    booking = Booking.objects.create(
        user=front_desk_user,
        check_in_date=date.today() + timedelta(days=2),
        check_out_date=date.today() + timedelta(days=4),
        total_price=Decimal("2000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Front",
        guest_last_name="Desk",
        guest_email=front_desk_user.email,
        guest_phone="0911000112",
        special_requests="Window seat",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    BookingItem.objects.create(
        booking=booking,
        room=room,
        units_booked=1,
        price_per_unit=Decimal("1000.00"),
    )
    _create_stay_availability(room, booking.check_in_date, booking.check_out_date)

    response = front_desk_client.get("/api/v1/listing/bookings/workspace-bookings/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["booking_reference"] == booking.booking_reference


def test_room_booking_patch_not_allowed(api_client, booking):
    api_client.force_authenticate(user=booking.user)
    response = api_client.patch(
        f"/api/v1/listing/bookings/{booking.id}/",
        {"status": Booking.BookingStatus.CANCELLED},
        format="json",
    )

    assert response.status_code == 405


def test_room_booking_delete_not_allowed(api_client, booking):
    api_client.force_authenticate(user=booking.user)
    response = api_client.delete(f"/api/v1/listing/bookings/{booking.id}/")

    assert response.status_code == 405


def test_post_guest_room_booking_requires_otp(api_client, room):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=2)

    response = api_client.post(
        "/api/v1/listing/bookings/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Otp",
            "guest_last_name": "Guest",
            "guest_email": "missing-otp-hotel@example.com",
            "guest_phone": "0911002001",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["otp_code"] == ["Guest booking phone OTP verification is required."]


def test_post_guest_room_booking_with_verified_otp_success(api_client, monkeypatch, room):
    _prepare_guest_booking_otp(monkeypatch)

    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    guest_phone = "0911002111"
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=2)

    challenge_id = _issue_guest_booking_otp(api_client, "/api/v1/listing/bookings/guest-otp/request/", guest_phone)

    response = api_client.post(
        "/api/v1/listing/bookings/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Otp",
            "guest_last_name": "Guest",
            "guest_email": "otp-hotel@example.com",
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": challenge_id,
            "otp_code": "123456",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["booking_reference"]
    assert data["guest_phone"] == guest_phone


def test_post_guest_room_booking_rejects_invalid_otp(api_client, monkeypatch, room):
    _prepare_guest_booking_otp(monkeypatch)

    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    guest_phone = "0911002222"
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=2)

    challenge_id = _issue_guest_booking_otp(api_client, "/api/v1/listing/bookings/guest-otp/request/", guest_phone)

    response = api_client.post(
        "/api/v1/listing/bookings/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Otp",
            "guest_last_name": "Guest",
            "guest_email": "bad-otp-hotel@example.com",
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": challenge_id,
            "otp_code": "000000",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "otp_code" in response.json()
    assert not Booking.objects.filter(guest_email="bad-otp-hotel@example.com").exists()


def test_post_guesthouse_booking_requires_otp(api_client, guest_house_room):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=2)

    response = api_client.post(
        "/api/v1/listing/guesthouse-bookings/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Guest",
            "guest_last_name": "House",
            "guest_email": "missing-otp-guesthouse@example.com",
            "guest_phone": "0911002002",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["otp_code"] == ["Guest booking phone OTP verification is required."]


def test_post_guesthouse_booking_with_verified_otp_success(api_client, monkeypatch, guest_house_room):
    _prepare_guest_booking_otp(monkeypatch)
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    guest_phone = "0911002112"
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=2)
    challenge_id = _issue_guest_booking_otp(
        api_client,
        "/api/v1/listing/guesthouse-bookings/guest-otp/request/",
        guest_phone,
    )

    response = api_client.post(
        "/api/v1/listing/guesthouse-bookings/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Guest",
            "guest_last_name": "House",
            "guest_email": "otp-guesthouse@example.com",
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": challenge_id,
            "otp_code": "123456",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["booking_reference"]


def test_post_eventspace_booking_requires_otp(api_client, event_space):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=1)
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)

    response = api_client.post(
        "/api/v1/listing/bookings-eventspaces/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Event",
            "guest_last_name": "Guest",
            "guest_email": "missing-otp-eventspace@example.com",
            "guest_phone": "0911002003",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["otp_code"] == ["Guest booking phone OTP verification is required."]


def test_post_eventspace_booking_with_verified_otp_success(api_client, monkeypatch, event_space):
    _prepare_guest_booking_otp(monkeypatch)
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=1)
    guest_phone = "0911002113"
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)
    challenge_id = _issue_guest_booking_otp(
        api_client,
        "/api/v1/listing/bookings-eventspaces/guest-otp/request/",
        guest_phone,
    )

    response = api_client.post(
        "/api/v1/listing/bookings-eventspaces/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Event",
            "guest_last_name": "Guest",
            "guest_email": "otp-eventspace@example.com",
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": challenge_id,
            "otp_code": "123456",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["booking_reference"]


def test_post_guest_car_rental_requires_otp(api_client, car_listing):
    car_listing.rental_mode = CarListing.RentalModeChoices.WITH_DRIVER
    car_listing.save(update_fields=["rental_mode"])
    start_date = date.today() + timedelta(days=4)
    end_date = start_date + timedelta(days=2)
    _create_terms(car_listing.company)
    _create_car_availability(car_listing, start_date, end_date)

    response = api_client.post(
        "/api/v1/listing/car-rentals/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Car",
            "guest_last_name": "Guest",
            "guest_email": "missing-otp-car@example.com",
            "guest_phone": "0911002004",
            "terms_accepted": True,
            "terms_version": "1",
            "rental_items": [
                {"car_listing": str(car_listing.id), "units_rent": 1, "price_per_unit": "1500.00"}
            ],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["otp_code"] == ["Guest booking phone OTP verification is required."]


def test_post_guest_car_rental_with_verified_otp_success(api_client, monkeypatch, car_listing):
    _prepare_guest_booking_otp(monkeypatch)
    car_listing.rental_mode = CarListing.RentalModeChoices.WITH_DRIVER
    car_listing.save(update_fields=["rental_mode"])
    start_date = date.today() + timedelta(days=4)
    end_date = start_date + timedelta(days=2)
    guest_phone = "0911002114"
    _create_terms(car_listing.company)
    _create_car_availability(car_listing, start_date, end_date)
    challenge_id = _issue_guest_booking_otp(
        api_client,
        "/api/v1/listing/car-rentals/guest-otp/request/",
        guest_phone,
    )

    response = api_client.post(
        "/api/v1/listing/car-rentals/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Car",
            "guest_last_name": "Guest",
            "guest_email": "otp-car@example.com",
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": challenge_id,
            "otp_code": "123456",
            "rental_items": [
                {"car_listing": str(car_listing.id), "units_rent": 1, "price_per_unit": "1500.00"}
            ],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["booking_reference"]


@pytest.mark.parametrize(
    ("booking_type", "days_ahead", "expected_status", "expected_error_key", "expected_label"),
    [
        ("hotel", 5, 201, None, None),
        ("hotel", 6, 400, "check_in_date", "Check-in date"),
        ("guesthouse", 5, 201, None, None),
        ("guesthouse", 6, 400, "start_date", "Start date"),
        ("eventspace", 5, 201, None, None),
        ("eventspace", 6, 400, "check_in_date", "Check-in date"),
        ("car_rental", 5, 201, None, None),
        ("car_rental", 6, 400, "start_date", "Start date"),
    ],
)
def test_guest_booking_create_respects_forward_window(
    api_client,
    monkeypatch,
    room,
    guest_house_room,
    event_space,
    car_listing,
    booking_type,
    days_ahead,
    expected_status,
    expected_error_key,
    expected_label,
):
    _prepare_guest_booking_otp(monkeypatch)
    booking_date = date.today() + timedelta(days=days_ahead)
    end_date = booking_date + timedelta(days=2)
    guest_phone = f"0911004{days_ahead}55"

    if booking_type == "hotel":
        _create_terms(room.hotel)
        _create_stay_availability(room, booking_date, end_date, available_rooms=2)
        challenge_id = _issue_guest_booking_otp(
            api_client,
            "/api/v1/listing/bookings/guest-otp/request/",
            guest_phone,
        )
        response = api_client.post(
            "/api/v1/listing/bookings/",
            {
                "check_in_date": booking_date.isoformat(),
                "check_out_date": end_date.isoformat(),
                "guest_first_name": "Window",
                "guest_last_name": "Hotel",
                "guest_email": f"window-hotel-{days_ahead}@example.com",
                "guest_phone": guest_phone,
                "terms_accepted": True,
                "terms_version": "1",
                "otp_challenge_id": challenge_id,
                "otp_code": "123456",
                "items": [{"room": str(room.id), "units_booked": 1}],
            },
            format="json",
        )
    elif booking_type == "guesthouse":
        _create_terms(guest_house_room.guest_house)
        _create_guesthouse_inventory(guest_house_room, booking_date, end_date, available_rooms=2)
        challenge_id = _issue_guest_booking_otp(
            api_client,
            "/api/v1/listing/guesthouse-bookings/guest-otp/request/",
            guest_phone,
        )
        response = api_client.post(
            "/api/v1/listing/guesthouse-bookings/",
            {
                "start_date": booking_date.isoformat(),
                "end_date": end_date.isoformat(),
                "guest_first_name": "Window",
                "guest_last_name": "Guesthouse",
                "guest_email": f"window-guesthouse-{days_ahead}@example.com",
                "guest_phone": guest_phone,
                "terms_accepted": True,
                "terms_version": "1",
                "otp_challenge_id": challenge_id,
                "otp_code": "123456",
                "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
            },
            format="json",
        )
    elif booking_type == "eventspace":
        _create_terms(event_space.hotel)
        _create_eventspace_availability(event_space, booking_date, end_date, available_units=1)
        challenge_id = _issue_guest_booking_otp(
            api_client,
            "/api/v1/listing/bookings-eventspaces/guest-otp/request/",
            guest_phone,
        )
        response = api_client.post(
            "/api/v1/listing/bookings-eventspaces/",
            {
                "check_in_date": booking_date.isoformat(),
                "check_out_date": end_date.isoformat(),
                "event_type": "conference",
                "guest_first_name": "Window",
                "guest_last_name": "Event",
                "guest_email": f"window-eventspace-{days_ahead}@example.com",
                "guest_phone": guest_phone,
                "terms_accepted": True,
                "terms_version": "1",
                "otp_challenge_id": challenge_id,
                "otp_code": "123456",
                "items": [{"event_space": str(event_space.id), "units_booked": 1}],
            },
            format="json",
        )
    else:
        car_listing.rental_mode = CarListing.RentalModeChoices.WITH_DRIVER
        car_listing.save(update_fields=["rental_mode"])
        _create_terms(car_listing.company)
        _create_car_availability(car_listing, booking_date, end_date)
        challenge_id = _issue_guest_booking_otp(
            api_client,
            "/api/v1/listing/car-rentals/guest-otp/request/",
            guest_phone,
        )
        response = api_client.post(
            "/api/v1/listing/car-rentals/",
            {
                "start_date": booking_date.isoformat(),
                "end_date": end_date.isoformat(),
                "guest_first_name": "Window",
                "guest_last_name": "Car",
                "guest_email": f"window-car-{days_ahead}@example.com",
                "guest_phone": guest_phone,
                "terms_accepted": True,
                "terms_version": "1",
                "otp_challenge_id": challenge_id,
                "otp_code": "123456",
                "rental_items": [
                    {"car_listing": str(car_listing.id), "units_rent": 1, "price_per_unit": "1500.00"}
                ],
            },
            format="json",
        )

    assert response.status_code == expected_status
    if expected_status == 400:
        assert response.json()[expected_error_key] == [
            f"{expected_label} exceeds the maximum allowed booking window for this listing."
        ]


@pytest.mark.parametrize(
    ("preview_type", "days_ahead", "expected_status", "expected_error_key", "expected_label"),
    [
        ("hotel", 5, 200, None, None),
        ("hotel", 6, 400, "check_in_date", "Check-in date"),
        ("guesthouse", 5, 200, None, None),
        ("guesthouse", 6, 400, "start_date", "Start date"),
        ("eventspace", 5, 200, None, None),
        ("eventspace", 6, 400, "check_in_date", "Check-in date"),
    ],
)
def test_booking_price_preview_respects_forward_window(
    api_client,
    room,
    guest_house_room,
    event_space,
    preview_type,
    days_ahead,
    expected_status,
    expected_error_key,
    expected_label,
):
    booking_date = date.today() + timedelta(days=days_ahead)
    end_date = booking_date + timedelta(days=2)

    if preview_type == "hotel":
        _create_terms(room.hotel)
        _create_stay_availability(room, booking_date, end_date, available_rooms=2)
        response = api_client.post(
            "/api/v1/listing/bookings/price-preview/",
            {
                "check_in_date": booking_date.isoformat(),
                "check_out_date": end_date.isoformat(),
                "items": [{"room": str(room.id), "units_booked": 1}],
            },
            format="json",
        )
    elif preview_type == "guesthouse":
        _create_terms(guest_house_room.guest_house)
        _create_guesthouse_inventory(guest_house_room, booking_date, end_date, available_rooms=2)
        response = api_client.post(
            "/api/v1/listing/guesthouse-bookings/price-preview/",
            {
                "start_date": booking_date.isoformat(),
                "end_date": end_date.isoformat(),
                "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
            },
            format="json",
        )
    else:
        _create_terms(event_space.hotel)
        _create_eventspace_availability(event_space, booking_date, end_date, available_units=1)
        response = api_client.post(
            "/api/v1/listing/bookings-eventspaces/price-preview/",
            {
                "check_in_date": booking_date.isoformat(),
                "check_out_date": end_date.isoformat(),
                "items": [{"event_space": str(event_space.id), "units_booked": 1}],
            },
            format="json",
        )

    assert response.status_code == expected_status
    if expected_status == 400:
        assert response.json()[expected_error_key] == [
            f"{expected_label} exceeds the maximum allowed booking window for this listing."
        ]


def test_room_booking_window_can_be_customized_by_owner(api_client, monkeypatch, room):
    _prepare_guest_booking_otp(monkeypatch)
    room.booking_forward_window_days = 2
    room.save(update_fields=["booking_forward_window_days"])

    allowed_check_in = date.today() + timedelta(days=2)
    allowed_check_out = allowed_check_in + timedelta(days=2)
    blocked_check_in = date.today() + timedelta(days=3)
    blocked_check_out = blocked_check_in + timedelta(days=2)
    guest_phone = "0911002999"

    _create_terms(room.hotel)
    _create_stay_availability(room, allowed_check_in, allowed_check_out, available_rooms=2)

    challenge_id = _issue_guest_booking_otp(api_client, "/api/v1/listing/bookings/guest-otp/request/", guest_phone)

    allowed_response = api_client.post(
        "/api/v1/listing/bookings/",
        {
            "check_in_date": allowed_check_in.isoformat(),
            "check_out_date": allowed_check_out.isoformat(),
            "guest_first_name": "Owner",
            "guest_last_name": "Window",
            "guest_email": "owner-window@example.com",
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": challenge_id,
            "otp_code": "123456",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert allowed_response.status_code == 201

    blocked_challenge_id = _issue_guest_booking_otp(
        api_client,
        "/api/v1/listing/bookings/guest-otp/request/",
        guest_phone,
    )
    blocked_response = api_client.post(
        "/api/v1/listing/bookings/",
        {
            "check_in_date": blocked_check_in.isoformat(),
            "check_out_date": blocked_check_out.isoformat(),
            "guest_first_name": "Owner",
            "guest_last_name": "Window",
            "guest_email": "owner-window-blocked@example.com",
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": blocked_challenge_id,
            "otp_code": "123456",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert blocked_response.status_code == 400
    assert blocked_response.json()["check_in_date"] == [
        "Check-in date exceeds the maximum allowed booking window for this listing."
    ]


def test_room_walk_in_booking_success(front_desk_client, room):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=2)

    response = front_desk_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Walk",
            "guest_last_name": "In",
            "guest_email": "walkin-hotel@example.com",
            "guest_phone": "0911000222",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == Booking.BookingStatus.WALK_IN
    assert data["booking_reference"]

    availability = StayAvailability.objects.get(room=room, date=check_in)
    assert availability.available_rooms == 1


def test_room_walk_in_booking_forbidden_for_non_staff(auth_client, room):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=2)

    response = auth_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Denied",
            "guest_last_name": "Guest",
            "guest_email": "denied-hotel@example.com",
            "guest_phone": "0911000333",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 403


def test_room_walk_in_booking_invalid_payload(front_desk_client, room):
    check_in = date.today() + timedelta(days=5)
    _create_terms(room.hotel)

    response = front_desk_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_in.isoformat(),
            "guest_first_name": "Invalid",
            "guest_last_name": "Range",
            "guest_email": "invalid-hotel@example.com",
            "guest_phone": "0911000444",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "check_out_date" in response.json()


def test_room_walk_in_booking_inventory_conflict(front_desk_client, room):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)
    _create_terms(room.hotel)
    _create_stay_availability(room, check_in, check_out, available_rooms=1)

    response = front_desk_client.post(
        "/api/v1/listing/bookings/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_first_name": "Inventory",
            "guest_last_name": "Conflict",
            "guest_email": "inventory-hotel@example.com",
            "guest_phone": "0911000555",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(room.id), "units_booked": 2}],
        },
        format="json",
    )

    assert response.status_code == 409


def test_get_guesthouse_booking_lookup_public_contract(api_client, guesthouse_booking):
    response = api_client.get(
        "/api/v1/listing/guesthouse-bookings/lookup/",
        {"reference": guesthouse_booking.booking_reference, "email": guesthouse_booking.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == guesthouse_booking.booking_reference


def test_guesthouse_booking_cancel_returns_no_refund_policy(api_client, user, guest_house_room):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    booking = GuestHouseBooking.objects.create(
        renter=user,
        start_date=start_date,
        end_date=end_date,
        total_price=Decimal("1800.00"),
        currency="ETB",
        status=GuestHouseBooking.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="House",
        guest_email=user.email,
        guest_phone=user.phone,
        terms_accepted=True,
        terms_version="1",
        terms_content_snapshot="Terms content",
        terms_accepted_at=timezone.now(),
    )
    GuestHouseBookingItem.objects.create(
        booking=booking,
        room=guest_house_room,
        units_booked=1,
        price_per_unit=Decimal("900.00"),
    )
    _create_guesthouse_inventory(guest_house_room, start_date, end_date)

    api_client.force_authenticate(user=user)
    response = api_client.post(f"/api/v1/listing/guesthouse-bookings/{booking.id}/cancel/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(booking.id)
    assert data["status"] == GuestHouseBooking.RentStatus.CANCELLED
    assert data["refund_supported"] is False
    assert data["refund_policy"] == "no_refunds"
    assert "No refunds are available" in data["refund_message"]
    assert data["cancellation_effect"] == "booking_cancelled"


def test_guesthouse_booking_workspace_bookings_success(api_client, guest_house, guest_house_room, django_user_model):
    workspace_user = django_user_model.objects.create_user(
        email="guesthouse-workspace@example.com",
        password="password123",
        first_name="Guesthouse",
        last_name="Workspace",
    )
    workspace_user.workspace = guest_house
    workspace_user.save()

    booking = GuestHouseBooking.objects.create(
        renter=workspace_user,
        start_date=date.today() + timedelta(days=3),
        end_date=date.today() + timedelta(days=5),
        total_price=Decimal("1600.00"),
        currency="ETB",
        status=GuestHouseBooking.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=workspace_user.email,
        guest_phone="0911000114",
        special_requests="Late check-in",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    GuestHouseBookingItem.objects.create(
        booking=booking,
        room=guest_house_room,
        units_booked=2,
        price_per_unit=Decimal("800.00"),
    )

    api_client.force_authenticate(user=workspace_user)
    response = api_client.get("/api/v1/listing/guesthouse-bookings/workspace-bookings/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1


def test_guesthouse_walk_in_booking_success(company_client, guest_house_room):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=2)

    response = company_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Guest",
            "guest_last_name": "House",
            "guest_email": "walkin-guesthouse@example.com",
            "guest_phone": "0911000666",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == GuestHouseBooking.RentStatus.WALK_IN
    assert data["booking_reference"]

    inventory = GuestHouseInventory.objects.get(guest_house_room=guest_house_room, date=start_date)
    assert inventory.available_rooms == 1


def test_guesthouse_walk_in_booking_forbidden_for_non_staff(auth_client, guest_house_room):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=2)

    response = auth_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Denied",
            "guest_last_name": "Guesthouse",
            "guest_email": "denied-guesthouse@example.com",
            "guest_phone": "0911000777",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 403


def test_guesthouse_walk_in_booking_invalid_payload(company_client, guest_house_room):
    start_date = date.today() + timedelta(days=5)
    _create_terms(guest_house_room.guest_house)

    response = company_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": start_date.isoformat(),
            "guest_first_name": "Invalid",
            "guest_last_name": "Guesthouse",
            "guest_email": "invalid-guesthouse@example.com",
            "guest_phone": "0911000888",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400


def test_guesthouse_walk_in_booking_inventory_conflict(company_client, guest_house_room):
    start_date = date.today() + timedelta(days=5)
    end_date = start_date + timedelta(days=2)
    _create_terms(guest_house_room.guest_house)
    _create_guesthouse_inventory(guest_house_room, start_date, end_date, available_rooms=1)

    response = company_client.post(
        "/api/v1/listing/guesthouse-bookings/walk-in/",
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Inventory",
            "guest_last_name": "Guesthouse",
            "guest_email": "inventory-guesthouse@example.com",
            "guest_phone": "0911000999",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"room": str(guest_house_room.id), "units_booked": 2}],
        },
        format="json",
    )

    assert response.status_code == 409


def test_get_eventspace_booking_lookup_public_contract(api_client, eventspace_booking):
    response = api_client.get(
        "/api/v1/listing/bookings-eventspaces/lookup/",
        {"reference": eventspace_booking.booking_reference, "email": eventspace_booking.guest_email},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["booking_reference"] == eventspace_booking.booking_reference


def test_car_rentals_my_rentals_success(api_client, user, car_listing):
    rental = CarRental.objects.create(
        renter=user,
        start_date=date.today() + timedelta(days=4),
        end_date=date.today() + timedelta(days=6),
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000112",
        special_requests="Need driver",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )

    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1/listing/car-rentals/my_rentals/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["booking_reference"] == rental.booking_reference


def test_car_rental_confirm_and_cancel_success(api_client, user, car_listing):
    rental = CarRental.objects.create(
        renter=user,
        start_date=date.today() + timedelta(days=4),
        end_date=date.today() + timedelta(days=6),
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000112",
        special_requests="Need driver",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )
    _create_car_availability(car_listing, rental.start_date, rental.end_date)

    api_client.force_authenticate(user=user)
    confirm_response = api_client.post(f"/api/v1/listing/car-rentals/{rental.id}/confirm/")
    assert confirm_response.status_code == 200

    rental.refresh_from_db()
    assert rental.status == CarRental.RentStatus.CONFIRMED

    cancel_response = api_client.post(f"/api/v1/listing/car-rentals/{rental.id}/cancel/")
    assert cancel_response.status_code == 200
    cancel_data = cancel_response.json()
    assert cancel_data["refund_supported"] is False
    assert cancel_data["refund_policy"] == "no_refunds"
    assert "No refunds are available" in cancel_data["refund_message"]
    assert cancel_data["cancellation_effect"] == "booking_cancelled"

    rental.refresh_from_db()
    assert rental.status == CarRental.RentStatus.CANCELLED


def test_post_car_rental_reschedule_success(auth_client, user, car_listing):
    start_date = date.today() + timedelta(days=4)
    end_date = start_date + timedelta(days=2)
    new_start_date = date.today() + timedelta(days=9)
    new_end_date = new_start_date + timedelta(days=4)

    rental = CarRental.objects.create(
        renter=user,
        start_date=start_date,
        end_date=end_date,
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000112",
        special_requests="Need driver",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )
    _create_car_availability(car_listing, start_date, end_date)
    _create_car_availability(car_listing, new_start_date, new_end_date)

    response = auth_client.post(
        f"/api/v1/listing/car-rentals/{rental.id}/reschedule/",
        {
            "start_date": new_start_date.isoformat(),
            "end_date": new_end_date.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 200
    rental.refresh_from_db()
    assert rental.start_date == new_start_date
    assert rental.end_date == new_end_date
    assert rental.total_price == Decimal("6000.00")
    assert response.json()["start_date"] == new_start_date.isoformat()
    assert response.json()["end_date"] == new_end_date.isoformat()


def test_post_car_rental_reschedule_conflict_when_inventory_unavailable(auth_client, user, car_listing):
    start_date = date.today() + timedelta(days=4)
    end_date = start_date + timedelta(days=2)
    new_start_date = date.today() + timedelta(days=9)
    new_end_date = new_start_date + timedelta(days=2)

    rental = CarRental.objects.create(
        renter=user,
        start_date=start_date,
        end_date=end_date,
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000112",
        special_requests="Need driver",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )
    _create_car_availability(car_listing, start_date, end_date)
    _create_car_availability(car_listing, new_start_date, new_end_date, available_units=0)

    response = auth_client.post(
        f"/api/v1/listing/car-rentals/{rental.id}/reschedule/",
        {
            "start_date": new_start_date.isoformat(),
            "end_date": new_end_date.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 409
    rental.refresh_from_db()
    assert rental.start_date == start_date
    assert rental.end_date == end_date


def test_post_car_rental_reschedule_forbidden_for_non_owner(api_client, user, car_listing, django_user_model, user_role):
    start_date = date.today() + timedelta(days=4)
    end_date = start_date + timedelta(days=2)
    new_start_date = date.today() + timedelta(days=9)
    new_end_date = new_start_date + timedelta(days=2)

    rental = CarRental.objects.create(
        renter=user,
        start_date=start_date,
        end_date=end_date,
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email=user.email,
        guest_phone="0911000112",
        special_requests="Need driver",
        terms_version=1,
        terms_accepted=True,
        terms_content_snapshot="Terms content",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )
    _create_car_availability(car_listing, start_date, end_date)
    _create_car_availability(car_listing, new_start_date, new_end_date)

    other_user = django_user_model.objects.create_user(
        email="other-renter@example.com",
        password="pass1234",
        role=user_role,
        phone="0911222000",
    )
    api_client.force_authenticate(user=other_user)

    response = api_client.post(
        f"/api/v1/listing/car-rentals/{rental.id}/reschedule/",
        {
            "start_date": new_start_date.isoformat(),
            "end_date": new_end_date.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 404


def test_get_eventspace_list_public_contract(api_client, event_space):
    response = api_client.get("/api/v1/listing/event-spaces/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(event_space.id)
    _assert_verification_fields(data["results"][0])


def test_get_eventspace_detail_public_contract(api_client, event_space):
    response = api_client.get(f"/api/v1/listing/event-spaces/{event_space.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(event_space.id)
    assert data["title"] == event_space.title
    assert "base_price" in data
    _assert_verification_fields(data)


def test_post_eventspace_create_unauthenticated(api_client, hotel):
    response = api_client.post(
        "/api/v1/listing/event-spaces/",
        {
            "title": "Event Space Draft",
            "company_id": str(hotel.company.id),
            "description": "Event space draft",
            "base_price": "5000.00",
            "currency": "ETB",
            "number_of_guests": 100,
            "total_units": 1,
            "space_type": "conference_hall",
            "floor_area_sqm": 120,
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_eventspace_create_success(company_client, api_client, hotel):
    response = company_client.post(
        "/api/v1/listing/event-spaces/",
        {
            "title": "Event Space Draft",
            "company_id": str(hotel.company.id),
            "description": "Event space draft",
            "base_price": "5000.00",
            "currency": "ETB",
            "number_of_guests": 100,
            "total_units": 1,
            "space_type": "conference_hall",
            "floor_area_sqm": 120,
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Event Space Draft"
    event_space_listing = EventSpaceListing.objects.get(id=data["id"])
    assert event_space_listing.is_active is False
    list_response = api_client.get("/api/v1/listing/event-spaces/")
    assert all(item["id"] != data["id"] for item in list_response.json()["results"])


def test_patch_eventspace_success(company_client, event_space):
    response = company_client.patch(
        f"/api/v1/listing/event-spaces/{event_space.id}/",
        {"title": "Updated Event Space"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Event Space"


def test_patch_eventspace_forbidden_for_non_owner(auth_client, event_space):
    response = auth_client.patch(
        f"/api/v1/listing/event-spaces/{event_space.id}/",
        {"title": "Updated Event Space"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_eventspace_success(company_client, event_space):
    response = company_client.delete(f"/api/v1/listing/event-spaces/{event_space.id}/")

    assert response.status_code == 204


def test_eventspace_walk_in_booking_success(front_desk_client, event_space):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=1)
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)

    response = front_desk_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Event",
            "guest_last_name": "Walkin",
            "guest_email": "walkin-eventspace@example.com",
            "guest_phone": "0911001111",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == EventSpaceBooking.BookingStatus.WALK_IN
    assert data["booking_reference"]

    availability = EventSpaceAvailability.objects.get(space_listing=event_space, date=check_in)
    assert availability.available_eventspace == 0


def test_eventspace_walk_in_booking_forbidden_for_non_staff(auth_client, event_space):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=1)
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)

    response = auth_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Denied",
            "guest_last_name": "Event",
            "guest_email": "denied-eventspace@example.com",
            "guest_phone": "0911001222",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 403


def test_eventspace_walk_in_booking_invalid_payload(front_desk_client, event_space):
    check_in = date.today() + timedelta(days=5)
    _create_terms(event_space.hotel)

    response = front_desk_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_in.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Invalid",
            "guest_last_name": "Event",
            "guest_email": "invalid-eventspace@example.com",
            "guest_phone": "0911001333",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "check_out_date" in response.json()


def test_eventspace_walk_in_booking_inventory_conflict(front_desk_client, event_space):
    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=1)
    _create_terms(event_space.hotel)
    _create_eventspace_availability(event_space, check_in, check_out, available_units=1)

    response = front_desk_client.post(
        "/api/v1/listing/bookings-eventspaces/walk-in/",
        {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "event_type": "conference",
            "guest_first_name": "Inventory",
            "guest_last_name": "Event",
            "guest_email": "inventory-eventspace@example.com",
            "guest_phone": "0911001444",
            "terms_accepted": True,
            "terms_version": "1",
            "items": [{"event_space": str(event_space.id), "units_booked": 2}],
        },
        format="json",
    )

    assert response.status_code == 409


def test_get_property_list_public_contract(api_client, property_listing):
    response = api_client.get("/api/v1/listing/properties/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(property_listing.id)
    _assert_verification_fields(data["results"][0])


def test_get_property_detail_public_contract(api_client, property_listing):
    response = api_client.get(f"/api/v1/listing/properties/{property_listing.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(property_listing.id)
    assert data["title"] == property_listing.title
    assert "property_type" in data
    _assert_verification_fields(data)


def test_post_property_listing_create_success(company):
    property_listing = ListingService.create_property_listing(
        {
            "title": "Property Draft",
            "description": "Property created in tests",
            "base_price": "3000.00",
            "currency": "ETB",
            "company": company,
            "address": _listing_address_payload(),
            "property_type": "house",
            "bedrooms": 2,
            "bathrooms": 1,
            "square_meters": 80,
            "is_furnished": True,
            "images": [],
        }
    )

    assert property_listing.title == "Property Draft"
    assert property_listing.is_active is False


def test_patch_property_success(company_client, property_listing):
    response = company_client.patch(
        f"/api/v1/listing/properties/{property_listing.id}/",
        {"title": "Updated Property"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Property"


def test_patch_property_forbidden_for_non_owner(auth_client, property_listing):
    response = auth_client.patch(
        f"/api/v1/listing/properties/{property_listing.id}/",
        {"title": "Updated Property"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_property_success(company_client, property_listing):
    response = company_client.delete(f"/api/v1/listing/properties/{property_listing.id}/")

    assert response.status_code == 204


@pytest.mark.parametrize(
    ("fixture_name", "path_template"),
    [
        ("room", "/api/v1/listing/rooms/{id}/verify/"),
        ("guest_house", "/api/v1/listing/guest-houses/{id}/verify/"),
        ("guest_house_room", "/api/v1/listing/guest-house-rooms/{id}/verify/"),
        ("car_listing", "/api/v1/listing/cars/{id}/verify/"),
        ("property_listing", "/api/v1/listing/properties/{id}/verify/"),
        ("event_space", "/api/v1/listing/event-spaces/{id}/verify/"),
    ],
)
def test_post_listing_verify_success(admin_client, admin_user, request, fixture_name, path_template):
    listing = request.getfixturevalue(fixture_name)
    note = "Verified on-site by admin"

    response = admin_client.post(path_template.format(id=listing.id), {"verification_note": note}, format="json")

    assert response.status_code == 200
    listing.refresh_from_db()
    assert listing.is_verified is True
    assert listing.verified_by == admin_user
    assert listing.verified_at is not None
    assert listing.verification_note == note
    _assert_verification_fields(
        response.json(),
        expected_verified=True,
        expected_verified_by=str(admin_user.id),
        expected_note=note,
    )


@pytest.mark.parametrize(
    ("fixture_name", "path_template"),
    [
        ("room", "/api/v1/listing/rooms/{id}/unverify/"),
        ("guest_house", "/api/v1/listing/guest-houses/{id}/unverify/"),
        ("guest_house_room", "/api/v1/listing/guest-house-rooms/{id}/unverify/"),
        ("car_listing", "/api/v1/listing/cars/{id}/unverify/"),
        ("property_listing", "/api/v1/listing/properties/{id}/unverify/"),
        ("event_space", "/api/v1/listing/event-spaces/{id}/unverify/"),
    ],
)
def test_post_listing_unverify_success(admin_client, admin_user, request, fixture_name, path_template):
    listing = request.getfixturevalue(fixture_name)
    listing.is_verified = True
    listing.verified_at = timezone.now()
    listing.verified_by = admin_user
    listing.verification_note = "Previously verified"
    listing.save(update_fields=["is_verified", "verified_at", "verified_by", "verification_note"])

    response = admin_client.post(path_template.format(id=listing.id), {"verification_note": "ignored"}, format="json")

    assert response.status_code == 200
    listing.refresh_from_db()
    assert listing.is_verified is False
    assert listing.verified_at is None
    assert listing.verified_by is None
    assert listing.verification_note is None
    _assert_verification_fields(response.json())


def test_post_car_sale_listing_verify_success(admin_client, admin_user, company):
    listing = CarSaleListing.objects.create(
        company=company,
        title="Verify Car Sale",
        description="Needs admin verification",
        base_price=Decimal("850000.00"),
        currency="ETB",
        brand=CarListing.CarBrandChoices.TOYOTA,
        model="Corolla",
        year=2020,
        mileage=45000,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        condition=CarListing.ConditionChoices.USED,
        car_class=CarListing.CarClassChoices.NORMAL,
        seats=5,
        seller_contact_name="Seller",
        seller_phone="0911222333",
        reveal_fee=Decimal("100.00"),
    )

    response = admin_client.post(
        f"/api/v1/listing/car-sales/{listing.id}/verify/",
        {"verification_note": "Physical inspection completed"},
        format="json",
    )

    assert response.status_code == 200
    listing.refresh_from_db()
    assert listing.is_verified is True
    assert listing.verified_by == admin_user
    assert listing.verification_note == "Physical inspection completed"
    _assert_verification_fields(
        response.json(),
        expected_verified=True,
        expected_verified_by=str(admin_user.id),
        expected_note="Physical inspection completed",
    )


def test_post_property_sale_listing_verify_success(admin_client, admin_user, company):
    address = Address.objects.create(
        street_line1="Kazanchis",
        country="Ethiopia",
        city="Addis Ababa",
        sub_city="Kirkos",
        state="Addis Ababa",
        postal_code="1000",
        latitude="9.03",
        longitude="38.74",
    )
    listing = PropertySaleListing.objects.create(
        company=company,
        address=address,
        title="Verify Property Sale",
        description="Needs admin verification",
        base_price=Decimal("4500000.00"),
        currency="ETB",
        property_type=PropertySaleListing.PropertyTypeChoices.APARTMENT,
        bedrooms=3,
        bathrooms=2,
        square_meters=Decimal("180.00"),
        is_furnished=False,
        seller_contact_name="Property Seller",
        seller_phone="0911666777",
        reveal_fee=Decimal("150.00"),
    )

    response = admin_client.post(
        f"/api/v1/listing/property-sales/{listing.id}/verify/",
        {"verification_note": "Documents reviewed"},
        format="json",
    )

    assert response.status_code == 200
    listing.refresh_from_db()
    assert listing.is_verified is True
    assert listing.verified_by == admin_user
    assert listing.verification_note == "Documents reviewed"
    _assert_verification_fields(
        response.json(),
        expected_verified=True,
        expected_verified_by=str(admin_user.id),
        expected_note="Documents reviewed",
    )


def test_post_guesthouse_verify_forbidden_for_owner(company_client, guest_house):
    response = company_client.post(f"/api/v1/listing/guest-houses/{guest_house.id}/verify/")

    assert response.status_code == 403


def test_get_terms_list_public_contract(api_client, hotel):
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        version=1,
        title="Hotel Terms",
        content="Hotel terms content",
        effective_date=date.today(),
        is_active=True,
    )

    response = api_client.get("/api/v1/listing/terms/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["title"] == "Hotel Terms"


def test_get_terms_detail_public_contract(api_client, hotel):
    terms = TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(HotelProfile),
        object_id=hotel.id,
        version=1,
        title="Hotel Terms",
        content="Hotel terms content",
        effective_date=date.today(),
        is_active=True,
    )

    response = api_client.get(f"/api/v1/listing/terms/{terms.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(terms.id)
    assert data["title"] == "Hotel Terms"


def test_get_terms_company_public_contract(api_client, company):
    terms = TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(company),
        object_id=company.id,
        version=1,
        title="Company Terms",
        content="Company terms content",
        effective_date=date.today(),
        is_active=True,
    )

    response = api_client.get(f"/api/v1/listing/terms/company/{company.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(terms.id)
    assert data["title"] == "Company Terms"


def test_get_terms_company_not_found(api_client, company):
    response = api_client.get(f"/api/v1/listing/terms/company/{company.id}/")

    assert response.status_code == 404
    assert "No terms and conditions available for this company." in response.json()["detail"]


def test_get_terms_hotel_not_found(api_client, hotel):
    response = api_client.get(f"/api/v1/listing/terms/hotel/{hotel.id}/")

    assert response.status_code == 404
    assert "No terms and conditions available for this hotel." in response.json()["detail"]


def test_get_terms_guesthouse_not_found(api_client, guest_house):
    response = api_client.get(f"/api/v1/listing/terms/guesthouse/{guest_house.id}/")

    assert response.status_code == 404
    assert "No terms and conditions available for this guest house." in response.json()["detail"]


def test_get_addons_public_contract(api_client, addon):
    response = api_client.get("/api/v1/listing/addon-offerings/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(addon.id)


def test_get_addon_detail_public_contract(api_client, addon):
    response = api_client.get(f"/api/v1/listing/addon-offerings/{addon.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(addon.id)
    assert data["name"] == addon.name
    assert "price_per_unit" in data


def test_post_addon_create_unauthenticated(api_client, hotel):
    response = api_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Breakfast Tray",
            "description": "Breakfast service",
            "category": "meal",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_addon_create_success(company_client, hotel):
    response = company_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Breakfast Tray",
            "description": "Breakfast service",
            "category": "meal",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Breakfast Tray"
    assert data["hotel"] == str(hotel.id)


def test_post_addon_create_forbidden_for_other_owner(auth_client, hotel):
    response = auth_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Breakfast Tray",
            "description": "Breakfast service",
            "category": "meal",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 403


def test_post_addon_create_invalid_payload(company_client, hotel):
    response = company_client.post(
        "/api/v1/listing/addon-offerings/",
        {
            "hotel": str(hotel.id),
            "name": "Inventory Addon",
            "description": "Tracked inventory service",
            "category": "service",
            "price_per_unit": "250.00",
            "currency": "ETB",
            "pricing_type": "per_unit",
            "requires_inventory": True,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "daily_capacity" in response.json()


def test_patch_addon_success(company_client, addon, hotel):
    addon.hotel = hotel
    addon.save(update_fields=["hotel"])

    response = company_client.patch(
        f"/api/v1/listing/addon-offerings/{addon.id}/",
        {"price_per_unit": "300.00", "description": "Updated description"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["price_per_unit"] == "300.00"
    assert data["description"] == "Updated description"


def test_patch_addon_forbidden_for_non_owner(auth_client, addon):
    response = auth_client.patch(
        f"/api/v1/listing/addon-offerings/{addon.id}/",
        {"price_per_unit": "300.00"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_addon_success(company_client, addon, hotel):
    addon.hotel = hotel
    addon.save(update_fields=["hotel"])

    response = company_client.delete(f"/api/v1/listing/addon-offerings/{addon.id}/")

    assert response.status_code == 204


def test_get_addon_not_found(api_client):
    response = api_client.get(f"/api/v1/listing/addon-offerings/{uuid4()}/")

    assert response.status_code == 404


def test_get_season_list_owner_contract(company_client, season):
    response = company_client.get("/api/v1/listing/seasons/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(season.id)


def test_get_season_detail_owner_contract(company_client, season):
    response = company_client.get(f"/api/v1/listing/seasons/{season.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(season.id)
    assert data["name"] == season.name


def test_post_season_create_unauthenticated(api_client):
    response = api_client.post(
        "/api/v1/listing/seasons/",
        {
            "name": "Holiday Window",
            "start_date": "2026-12-20",
            "end_date": "2026-12-27",
            "recurring": False,
            "active": True,
            "notes": "Peak dates",
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_season_create_success(company_client, company):
    response = company_client.post(
        "/api/v1/listing/seasons/",
        {
            "name": "Holiday Window",
            "start_date": "2026-12-20",
            "end_date": "2026-12-27",
            "recurring": False,
            "active": True,
            "notes": "Peak dates",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Holiday Window"
    assert data["company"] == str(company.id)


def test_post_season_invalid_dates(company_client):
    response = company_client.post(
        "/api/v1/listing/seasons/",
        {
            "name": "Broken Window",
            "start_date": "2026-12-27",
            "end_date": "2026-12-20",
            "recurring": False,
            "active": True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "end_date" in response.json()


def test_patch_season_success(company_client, season):
    response = company_client.patch(
        f"/api/v1/listing/seasons/{season.id}/",
        {"notes": "Updated seasonal notes"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["notes"] == "Updated seasonal notes"


def test_patch_season_non_owner_hidden(auth_client, season):
    response = auth_client.patch(
        f"/api/v1/listing/seasons/{season.id}/",
        {"notes": "Should not work"},
        format="json",
    )

    assert response.status_code == 403


def test_delete_season_success(company_client, season):
    response = company_client.delete(f"/api/v1/listing/seasons/{season.id}/")

    assert response.status_code == 204


def test_get_season_not_found(company_client):
    response = company_client.get(f"/api/v1/listing/seasons/{uuid4()}/")

    assert response.status_code == 404


def test_get_seasonal_rate_list_owner_contract(company_client, seasonal_rate):
    response = company_client.get("/api/v1/listing/seasonal-rates/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(seasonal_rate.id)


def test_get_seasonal_rate_detail_owner_contract(company_client, seasonal_rate):
    response = company_client.get(f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(seasonal_rate.id)
    assert data["season"] == str(seasonal_rate.season.id)


def test_post_seasonal_rate_create_unauthenticated(api_client, season, room):
    response = api_client.post(
        "/api/v1/listing/seasonal-rates/",
        {
            "season": str(season.id),
            "room": str(room.id),
            "price_override": "1500.00",
            "priority": 3,
            "active": True,
            "days_of_week": [],
        },
        format="json",
    )

    assert response.status_code == 401


def test_post_seasonal_rate_create_success(company_client, season, room, company):
    response = company_client.post(
        "/api/v1/listing/seasonal-rates/",
        {
            "season": str(season.id),
            "room": str(room.id),
            "price_override": "1500.00",
            "priority": 3,
            "active": True,
            "days_of_week": [],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["season"] == str(season.id)
    assert data["room"] == str(room.id)
    assert data["hotel"] == str(room.hotel.id)
    assert data["company"] == str(company.id)


def test_post_seasonal_rate_invalid_payload(company_client, season, room):
    response = company_client.post(
        "/api/v1/listing/seasonal-rates/",
        {
            "season": str(season.id),
            "room": str(room.id),
            "priority": 3,
            "active": True,
            "days_of_week": [],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "Either a Multiplier or a Price Override must be set." in str(response.json())


def test_patch_seasonal_rate_success(company_client, seasonal_rate):
    response = company_client.patch(
        f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/",
        {"priority": 9, "active": False},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["priority"] == 9
    assert data["active"] is False


def test_patch_seasonal_rate_non_owner_hidden(auth_client, seasonal_rate):
    response = auth_client.patch(
        f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/",
        {"priority": 9},
        format="json",
    )

    assert response.status_code == 403


def test_delete_seasonal_rate_success(company_client, seasonal_rate):
    response = company_client.delete(f"/api/v1/listing/seasonal-rates/{seasonal_rate.id}/")

    assert response.status_code == 204


def test_get_seasonal_rate_not_found(company_client):
    response = company_client.get(f"/api/v1/listing/seasonal-rates/{uuid4()}/")

    assert response.status_code == 404


def test_put_stay_availability_update_success(company_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = company_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["available_rooms"] == 0
    availability.refresh_from_db()
    assert availability.available_rooms == 0


def test_put_stay_availability_update_unauthenticated(api_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = api_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 401


def test_put_stay_availability_update_forbidden(auth_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = auth_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 403


def test_put_stay_availability_update_invalid_payload(company_client, hotel, room):
    availability = StayAvailability.objects.create(
        hotel=hotel,
        room=room,
        date=date.today() + timedelta(days=1),
        available_rooms=2,
    )

    response = company_client.put(
        f"/api/v1/listing/stays/availability/{availability.id}/update/",
        {"available_rooms": -1},
        format="json",
    )

    assert response.status_code == 400


def test_put_stay_availability_update_not_found(company_client):
    response = company_client.put(
        f"/api/v1/listing/stays/availability/{uuid4()}/update/",
        {"available_rooms": 0},
        format="json",
    )

    assert response.status_code == 404


def test_patch_car_availability_update_success(company_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 200
    availability.refresh_from_db()
    assert availability.available_units == 0


def test_patch_car_availability_update_accepts_available_units(company_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"available_units": 2},
        format="json",
    )

    assert response.status_code == 200
    availability.refresh_from_db()
    assert availability.available_units == 2


def test_patch_car_availability_update_unauthenticated(api_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = api_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 401


def test_patch_car_availability_update_forbidden(auth_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = auth_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 403


def test_patch_car_availability_update_invalid_payload(company_client, car_listing):
    availability = CarAvailability.objects.create(
        car_listing=car_listing,
        date=date.today() + timedelta(days=1),
        available_units=1,
    )

    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{availability.id}/update/",
        {"quantity_available": -1},
        format="json",
    )

    assert response.status_code == 400


def test_patch_car_availability_update_not_found(company_client):
    response = company_client.patch(
        f"/api/v1/listing/car-availabilities/{uuid4()}/update/",
        {"quantity_available": 0},
        format="json",
    )

    assert response.status_code == 404


def test_get_inventory_grid_owner_only(company_client, hotel):
    response = company_client.get(
        "/api/v1/listing/inventory/grid/",
        {"property_id": str(hotel.id), "property_type": "hotel", "days": 7},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["property_id"] == str(hotel.id)
    assert data["property_type"] == "hotel"
    assert "units" in data


def test_get_inventory_grid_unauthenticated(api_client, hotel):
    response = api_client.get(
        "/api/v1/listing/inventory/grid/",
        {"property_id": str(hotel.id), "property_type": "hotel", "days": 7},
    )

    assert response.status_code == 401


def test_get_inventory_grid_forbidden(auth_client, hotel):
    response = auth_client.get(
        "/api/v1/listing/inventory/grid/",
        {"property_id": str(hotel.id), "property_type": "hotel", "days": 7},
    )

    assert response.status_code == 403


def test_get_inventory_grid_invalid_payload(company_client):
    response = company_client.get("/api/v1/listing/inventory/grid/")

    assert response.status_code == 400
