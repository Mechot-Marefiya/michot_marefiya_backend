# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

import json
import hashlib
import hmac
import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.account.models import CompanyProfile, OwnerComplianceAgreement
from apps.listing.models import (
    Booking,
    BookingAddon,
    BookingItem,
    CarAvailability,
    CarListing,
    CarRental,
    CarRentalExtensionRequest,
    CarRentalItem,
    CarSaleListing,
    ContactRevealRequest,
    PropertyRentalAvailability,
    PropertyRentalBooking,
    StayAvailability,
    TermsAndConditions,
)
from apps.listing.services import CarRentalService, get_effective_platform_fee_rate
from apps.payment.models import PaymentPlatformConfig, PaymentTransaction
from apps.payment.serializers import PaymentTransactionSerializer
from apps.payment.services import (
    ChapaPaymentService,
    ContactRevealPaymentService,
    apply_tax_to_transaction,
    calculate_tax,
    get_effective_contact_reveal_fee,
    get_effective_split_config_for_booking,
    get_effective_split_config_for_owner,
    get_effective_platform_split_config,
    get_payment_tax_breakdown,
    is_tax_applicable,
    resolve_payment_owner_for_split,
    validate_split_config,
    verify_webhook_signature,
)
from tests.conftest import (
    CompanyProfileFactory,
    BookingFactory,
    BookingItemFactory,
    CarRentalFactory,
    CarRentalItemFactory,
    EventSpaceBookingFactory,
    EventSpaceBookingItemFactory,
    GuestHouseBookingFactory,
    GuestHouseBookingItemFactory,
    PropertyListingFactory,
)

pytestmark = pytest.mark.django_db


def _build_booking(user, room):
    booking_reference = f"H-{Booking.objects.count() + 1:06d}"
    booking = Booking.objects.create(
        user=user,
        check_in_date=date.today() + timedelta(days=7),
        check_out_date=date.today() + timedelta(days=9),
        total_price=Decimal("1000.00"),
        currency="ETB",
        status=Booking.BookingStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="User",
        guest_email="guest@example.com",
        guest_phone="0911000000",
        special_requests="None",
        booking_reference=booking_reference,
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=Decimal("1000.00"))
    return booking


def _build_car_rental(renter, car_listing):
    rental = CarRental.objects.create(
        renter=renter,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=9),
        total_price=Decimal("3000.00"),
        currency="ETB",
        status=CarRental.RentStatus.PENDING,
        guest_first_name="Guest",
        guest_last_name="Renter",
        guest_email="guest-renter@example.com",
        guest_phone="0911222333",
        booking_reference="C-000001",
        terms_accepted=True,
        terms_version="1",
        terms_accepted_at=timezone.now(),
        terms_content_snapshot="Terms",
    )
    CarRentalItem.objects.create(
        car_rental=rental,
        car_listing=car_listing,
        units_rent=1,
        price_per_unit=Decimal("1500.00"),
    )
    return rental


def _create_car_extension_availability(car_listing, start_date, end_date, available_units=1):
    for offset in range((end_date - start_date).days):
        CarAvailability.objects.create(
            car_listing=car_listing,
            date=start_date + timedelta(days=offset),
            available_units=available_units,
        )


def _build_car_sale(company, **overrides):
    defaults = {
        "company": company,
        "title": "Toyota Vitz for sale",
        "description": "Clean sale listing",
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


def _build_property_rental(property_listing, renter, **overrides):
    defaults = {
        "property_listing": property_listing,
        "renter": renter,
        "start_date": date.today() + timedelta(days=7),
        "end_date": date.today() + timedelta(days=9),
        "total_price": Decimal("6300.00"),
        "currency": "ETB",
        "status": PropertyRentalBooking.RentStatus.PENDING,
        "guest_first_name": "Property",
        "guest_last_name": "Guest",
        "guest_email": "property-guest@example.com",
        "guest_phone": "0911444555",
        "booking_reference": "P-000001",
        "terms_accepted": True,
        "terms_version": "1",
        "terms_accepted_at": timezone.now(),
        "terms_content_snapshot": "Terms",
    }
    defaults.update(overrides)
    return PropertyRentalBooking.objects.create(**defaults)


def _create_property_rental_availability(property_listing, start_date, end_date, *, available_units=1, price=None):
    for day_offset in range((end_date - start_date).days):
        PropertyRentalAvailability.objects.update_or_create(
            property_listing=property_listing,
            date=start_date + timedelta(days=day_offset),
            defaults={"available_units": available_units, "price": price},
        )


def _build_reveal_request(listing, buyer, **overrides):
    defaults = {
        "listing": listing,
        "buyer": buyer,
        "amount": listing.reveal_fee,
        "currency": listing.currency,
        "status": ContactRevealRequest.RevealStatus.PAYMENT_INITIATED,
        "tx_ref": "contact-tx-1",
        "expires_at": timezone.now() + timezone.timedelta(minutes=30),
    }
    defaults.update(overrides)
    return ContactRevealRequest.objects.create(**defaults)


def test_property_rental_tax_applies_to_individual_owner(settings, individual_owner, user):
    settings.PROPERTY_RENTAL_TAX_RATE = Decimal("0.15")
    listing = PropertyListingFactory(company=None, individual_owner=individual_owner, base_price=Decimal("3000.00"))
    OwnerComplianceAgreement.objects.create(
        owner=individual_owner,
        agreement_version="v1",
        status=OwnerComplianceAgreement.Status.SIGNED,
        signed_at=timezone.now(),
    )
    booking = _build_property_rental(listing, user)

    assert is_tax_applicable(booking) is True
    assert calculate_tax(Decimal("6000.00")) == Decimal("900.00")

    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(PropertyRentalBooking),
        object_id=booking.id,
        booking_type="propertyrental",
        tx_ref="property-tax-1",
        amount=Decimal("6900.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
    )

    apply_tax_to_transaction(tx, booking)
    tx.refresh_from_db()
    assert tx.tax_amount == Decimal("900.00")
    assert tx.tax_rate == settings.PROPERTY_RENTAL_TAX_RATE
    assert tx.tax_liability_status == PaymentTransaction.TaxLiabilityStatus.APPLICABLE


def test_property_rental_tax_skipped_for_licensed_company_owner(property_listing, user):
    booking = _build_property_rental(property_listing, user)
    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(PropertyRentalBooking),
        object_id=booking.id,
        booking_type="propertyrental",
        tx_ref="property-tax-skipped-company",
        amount=Decimal("6300.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
    )

    assert is_tax_applicable(booking) is False
    apply_tax_to_transaction(tx, booking)
    tx.refresh_from_db()
    assert tx.tax_amount is None
    assert tx.tax_rate is None
    assert tx.tax_liability_status is None


def test_tax_skipped_for_existing_non_property_flows(booking, guesthouse_booking, company, user):
    car_listing = _build_car_sale(company)
    reveal_request = _build_reveal_request(car_listing, user)

    for booking_object, booking_type, tx_ref in [
        (booking, "booking", "tax-skip-hotel"),
        (guesthouse_booking, "guesthouse", "tax-skip-guesthouse"),
        (reveal_request, "contact_reveal", "tax-skip-car-sale"),
    ]:
        tx = PaymentTransaction.objects.create(
            content_type=ContentType.objects.get_for_model(booking_object),
            object_id=booking_object.id,
            booking_type=booking_type,
            tx_ref=tx_ref,
            amount=Decimal("1000.00"),
            currency="ETB",
            status=PaymentTransaction.PaymentStatus.PENDING,
        )
        apply_tax_to_transaction(tx, booking_object)
        tx.refresh_from_db()
        assert tx.tax_amount is None
        assert tx.tax_rate is None
        assert tx.tax_liability_status is None


def test_property_rental_breakdown_and_serializer_grand_total(settings, individual_owner, user):
    settings.PROPERTY_RENTAL_TAX_RATE = Decimal("0.15")
    listing = PropertyListingFactory(company=None, individual_owner=individual_owner, base_price=Decimal("3000.00"))
    OwnerComplianceAgreement.objects.create(
        owner=individual_owner,
        agreement_version="v1",
        status=OwnerComplianceAgreement.Status.SIGNED,
        signed_at=timezone.now(),
    )
    booking = _build_property_rental(listing, user)

    breakdown = get_payment_tax_breakdown(booking)
    assert breakdown["owner_price"] == Decimal("6000.00")
    assert breakdown["service_fee"] == Decimal("0.00")
    assert breakdown["tax_amount"] == Decimal("900.00")
    assert breakdown["grand_total"] == Decimal("6900.00")

    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(PropertyRentalBooking),
        object_id=booking.id,
        booking_type="propertyrental",
        tx_ref="property-tax-serializer",
        amount=breakdown["grand_total"],
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        tax_amount=breakdown["tax_amount"],
        tax_rate=breakdown["tax_rate"],
        tax_liability_status=breakdown["tax_liability_status"],
    )

    data = PaymentTransactionSerializer(tx).data
    assert data["owner_price"] == "6000.00"
    assert data["service_fee"] == "0.00"
    assert data["tax_amount"] == "900.00"
    assert data["grand_total"] == "6900.00"


def test_serializer_non_tax_flow_returns_null_tax_amount(booking):
    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="non-tax-null",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
    )

    data = PaymentTransactionSerializer(tx).data
    assert data["tax_amount"] is None
    assert data["grand_total"] == "1000.00"


def test_successful_payment_returns_receipt_url(booking):
    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="receipt-success",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        chapa_transaction_id="APQ1kcaiCZi2",
    )

    data = PaymentTransactionSerializer(tx).data

    assert data["receipt_url"] == "https://chapa.link/payment-receipt/APQ1kcaiCZi2"


@pytest.mark.parametrize(
    "payment_status",
    [
        PaymentTransaction.PaymentStatus.PENDING,
        PaymentTransaction.PaymentStatus.FAILED,
        PaymentTransaction.PaymentStatus.CANCELLED,
    ],
)
def test_non_successful_payment_does_not_return_receipt_url(booking, payment_status):
    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref=f"receipt-{payment_status}",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=payment_status,
        chapa_transaction_id="APQ1kcaiCZi2",
    )

    data = PaymentTransactionSerializer(tx).data

    assert data["receipt_url"] is None


def test_successful_payment_missing_chapa_reference_returns_null_receipt_url(booking):
    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="receipt-missing-reference",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        chapa_transaction_id="",
    )

    data = PaymentTransactionSerializer(tx).data

    assert data["receipt_url"] is None


def test_tax_rate_uses_settings_constant(settings):
    settings.PROPERTY_RENTAL_TAX_RATE = Decimal("0.20")
    assert calculate_tax(Decimal("1000.00")) == Decimal("200.00")


def test_effective_platform_split_config_uses_db_default(settings):
    settings.PLATFORM_DEFAULT_SPLIT_TYPE = "percentage"
    settings.PLATFORM_DEFAULT_SPLIT_VALUE = Decimal("0.02")
    PaymentPlatformConfig.objects.create(
        name="active-default",
        default_split_type=PaymentPlatformConfig.SplitType.FLAT,
        default_split_value=Decimal("25.0000"),
    )

    config = get_effective_platform_split_config()

    assert config == {
        "split_type": "flat",
        "split_value": Decimal("25.0000"),
    }


def test_effective_platform_split_config_falls_back_to_settings(settings):
    settings.PLATFORM_DEFAULT_SPLIT_TYPE = "percentage"
    settings.PLATFORM_DEFAULT_SPLIT_VALUE = Decimal("0.02")

    config = get_effective_platform_split_config()

    assert config == {
        "split_type": "percentage",
        "split_value": Decimal("0.02"),
    }


def test_effective_contact_reveal_fee_uses_active_config():
    PaymentPlatformConfig.objects.create(
        name="reveal-defaults",
        default_car_sale_reveal_fee=Decimal("220.00"),
        default_property_sale_reveal_fee=Decimal("330.00"),
    )

    assert get_effective_contact_reveal_fee("car_sale") == Decimal("220.00")
    assert get_effective_contact_reveal_fee("property_sale") == Decimal("330.00")


def test_effective_contact_reveal_fee_falls_back_to_settings(settings):
    settings.DEFAULT_CAR_SALE_REVEAL_FEE = Decimal("125.00")
    settings.DEFAULT_PROPERTY_SALE_REVEAL_FEE = Decimal("175.00")

    assert get_effective_contact_reveal_fee("car_sale") == Decimal("125.00")
    assert get_effective_contact_reveal_fee("property_sale") == Decimal("175.00")


def test_validate_split_config_rejects_invalid_values():
    with pytest.raises(Exception):
        validate_split_config("unsupported", Decimal("0.02"))

    with pytest.raises(Exception):
        validate_split_config("percentage", Decimal("1.01"))

    with pytest.raises(Exception):
        validate_split_config("flat", Decimal("-1.00"))


def test_company_owner_split_override_wins_over_platform_default(room, user):
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0200"),
    )
    company = room.hotel.company
    company.split_config_active = True
    company.split_type = "flat"
    company.split_value = Decimal("35.0000")
    company.save(update_fields=["split_config_active", "split_type", "split_value"])
    booking = _build_booking(user, room)

    assert resolve_payment_owner_for_split(booking) == company
    assert get_effective_split_config_for_booking(booking) == {
        "split_type": "flat",
        "split_value": Decimal("35.0000"),
    }


def test_individual_owner_split_override_wins_over_platform_default(individual_owner, user):
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0200"),
    )
    individual_owner.split_config_active = True
    individual_owner.split_type = "percentage"
    individual_owner.split_value = Decimal("0.0750")
    individual_owner.save(update_fields=["split_config_active", "split_type", "split_value"])
    listing = PropertyListingFactory(company=None, individual_owner=individual_owner)
    booking = _build_property_rental(listing, user)

    assert resolve_payment_owner_for_split(booking) == individual_owner
    assert get_effective_split_config_for_booking(booking) == {
        "split_type": "percentage",
        "split_value": Decimal("0.0750"),
    }


def test_inactive_owner_split_config_falls_back_to_platform_default(company):
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.FLAT,
        default_split_value=Decimal("12.0000"),
    )
    company.split_config_active = False
    company.split_type = "percentage"
    company.split_value = Decimal("0.1500")
    company.save(update_fields=["split_config_active", "split_type", "split_value"])

    assert get_effective_split_config_for_owner(company) == {
        "split_type": "flat",
        "split_value": Decimal("12.0000"),
    }


def test_missing_owner_split_config_falls_back_to_platform_default(company):
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0300"),
    )

    assert get_effective_split_config_for_owner(company) == {
        "split_type": "percentage",
        "split_value": Decimal("0.0300"),
    }


def test_contact_reveal_split_owner_resolution_ignores_owner_config(company, user):
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0200"),
    )
    company.chapa_subaccount_id = "sub-contact-owner"
    company.split_config_active = True
    company.split_type = "flat"
    company.split_value = Decimal("50.0000")
    company.save(
        update_fields=[
            "chapa_subaccount_id",
            "split_config_active",
            "split_type",
            "split_value",
        ]
    )
    listing = _build_car_sale(company)
    reveal_request = _build_reveal_request(listing, user)

    assert resolve_payment_owner_for_split(reveal_request) is None
    assert get_effective_split_config_for_booking(reveal_request) == {
        "split_type": "percentage",
        "split_value": Decimal("0.0200"),
    }


def test_property_rental_tax_skipped_without_active_agreement(settings, individual_owner, user):
    settings.PROPERTY_RENTAL_TAX_RATE = Decimal("0.15")
    listing = PropertyListingFactory(company=None, individual_owner=individual_owner, base_price=Decimal("3000.00"))
    booking = _build_property_rental(listing, user)

    assert is_tax_applicable(booking) is False


@pytest.mark.parametrize(
    "booking_factory,item_factory,owner_attr",
    [
        (BookingFactory, BookingItemFactory, "user"),
        (GuestHouseBookingFactory, GuestHouseBookingItemFactory, "renter"),
        (EventSpaceBookingFactory, EventSpaceBookingItemFactory, "user"),
        (CarRentalFactory, CarRentalItemFactory, "renter"),
    ],
)
def test_first_and_repeat_booking_fee_rates_follow_phone_identity_across_flows(
    booking_factory,
    item_factory,
    owner_attr,
):
    phone = "0911999111"

    first_booking = booking_factory()
    getattr(first_booking, owner_attr).phone = phone
    getattr(first_booking, owner_attr).save(update_fields=["phone", "updated_at"])
    if item_factory is CarRentalItemFactory:
        item_factory(car_rental=first_booking)
    else:
        item_factory(booking=first_booking)
    assert get_effective_platform_fee_rate(booking=first_booking) == Decimal("0.00")

    second_booking = booking_factory()
    getattr(second_booking, owner_attr).phone = phone
    getattr(second_booking, owner_attr).save(update_fields=["phone", "updated_at"])
    if item_factory is CarRentalItemFactory:
        item_factory(car_rental=second_booking)
    else:
        item_factory(booking=second_booking)
    assert get_effective_platform_fee_rate(booking=second_booking) == Decimal("0.05")


def test_contact_reveal_stale_requests_expire_safely(company, user):
    listing = _build_car_sale(company)
    stale = _build_reveal_request(
        listing,
        user,
        status=ContactRevealRequest.RevealStatus.PAYMENT_INITIATED,
        expires_at=timezone.now() - timezone.timedelta(minutes=1),
    )

    expired_count = ContactRevealPaymentService.expire_stale_requests()

    stale.refresh_from_db()
    assert expired_count == 1
    assert stale.status == ContactRevealRequest.RevealStatus.EXPIRED


def test_contact_reveal_callback_unlocks_contact_and_fires_notification(
    company,
    user,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    listing = _build_car_sale(company)
    reveal_request = _build_reveal_request(listing, user, tx_ref="contact-success-1")
    payment = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(ContactRevealRequest),
        object_id=reveal_request.id,
        booking_type="contact_reveal",
        tx_ref="contact-success-1",
        amount=reveal_request.amount,
        currency=reveal_request.currency,
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )
    calls = []

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {
            "status": "success",
            "data": {
                "status": "success",
                "amount": str(payment.amount),
                "currency": payment.currency,
                "id": "chapa-contact-1",
                "method": "test",
            },
        },
    )
    monkeypatch.setattr(
        "apps.listing.tasks.send_contact_reveal_unlocked_notification.delay",
        lambda reveal_id: calls.append(reveal_id),
    )

    with django_capture_on_commit_callbacks(execute=True):
        result = ChapaPaymentService.handle_callback({"tx_ref": payment.tx_ref})

    payment.refresh_from_db()
    reveal_request.refresh_from_db()
    assert result["success"] is True
    assert payment.status == PaymentTransaction.PaymentStatus.SUCCESS
    assert reveal_request.status == ContactRevealRequest.RevealStatus.PAID_REVEALED
    assert reveal_request.contact_snapshot["seller_phone"] == listing.seller_phone
    assert calls == [reveal_request.id]


def test_contact_reveal_callback_rejects_amount_mismatch(company, user, monkeypatch):
    listing = _build_car_sale(company)
    reveal_request = _build_reveal_request(listing, user, tx_ref="contact-mismatch-1")
    payment = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(ContactRevealRequest),
        object_id=reveal_request.id,
        booking_type="contact_reveal",
        tx_ref="contact-mismatch-1",
        amount=reveal_request.amount,
        currency=reveal_request.currency,
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {
            "status": "success",
            "data": {
                "amount": "999.00",
                "currency": payment.currency,
                "id": "chapa-contact-2",
            },
        },
    )

    result = ChapaPaymentService.handle_callback({"tx_ref": payment.tx_ref})

    payment.refresh_from_db()
    reveal_request.refresh_from_db()
    assert result["success"] is False
    assert payment.status == PaymentTransaction.PaymentStatus.FAILED
    assert reveal_request.status == ContactRevealRequest.RevealStatus.PAYMENT_INITIATED


def test_post_payment_initiate_success(auth_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    captured = {}

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.initialize_payment",
        lambda **kwargs: captured.update(kwargs) or {
            "success": True,
            "message": "Payment initialized",
            "checkout_url": "https://checkout.example.com",
            "tx_ref": "tx-123",
        },
    )

    response = auth_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["checkout_url"] == "https://checkout.example.com"
    assert data["tx_ref"] == "tx-123"
    assert "calculated_amount" in data
    assert "payment_currency" in data
    assert data["calculated_amount"] == str(booking.total_price)
    assert captured["amount"] == booking.total_price


def test_hotel_booking_payment_workflow_confirms_booking(auth_client, user, room, settings, monkeypatch):
    settings.CHAPA_CALLBACK_URL = "https://api.example.com/api/v1/payment/callback/chapa/"
    settings.FRONTEND_URL = "https://app.example.com"
    room.hotel.company.chapa_subaccount_id = "sub-hotel-workflow"
    room.hotel.company.save(update_fields=["chapa_subaccount_id"])

    check_in = date.today() + timedelta(days=3)
    check_out = date.today() + timedelta(days=5)
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(room.hotel),
        object_id=room.hotel.id,
        version="1",
        title="Hotel Terms",
        content="Hotel booking terms",
        effective_date=date.today(),
        is_active=True,
    )
    for day_offset in range((check_out - check_in).days):
        StayAvailability.objects.create(
            hotel=room.hotel,
            room=room,
            date=check_in + timedelta(days=day_offset),
            available_rooms=room.total_units,
        )

    captured_initialize = _mock_chapa_initialize(monkeypatch)
    monkeypatch.setattr(
        "apps.listing.services.BookingEmailService.send_booking_confirmation",
        lambda booking: None,
    )

    booking_response = auth_client.post(
        "/api/v1/listing/bookings/",
        {
            "items": [{"room": str(room.id), "units_booked": 1}],
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "terms_accepted": True,
            "terms_version": "1",
            "guest_first_name": "Workflow",
            "guest_last_name": "Guest",
            "guest_email": "workflow@example.com",
            "guest_phone": "0911555666",
            "payment_currency": "ETB",
        },
        format="json",
    )

    assert booking_response.status_code == 201, booking_response.json()
    booking = Booking.objects.get(id=booking_response.json()["id"])
    assert booking.status == Booking.BookingStatus.PENDING
    assert booking.items.count() == 1
    for availability in StayAvailability.objects.filter(room=room, date__gte=check_in, date__lt=check_out):
        assert availability.available_rooms == room.total_units - 1

    initiate_response = auth_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert initiate_response.status_code == 200
    initiate_data = initiate_response.json()
    assert initiate_data["success"] is True
    assert initiate_data["checkout_url"] == "https://checkout.example.com"
    payment_tx = PaymentTransaction.objects.get(tx_ref=initiate_data["tx_ref"])
    assert payment_tx.status == PaymentTransaction.PaymentStatus.PENDING
    assert payment_tx.booking_type == "booking"
    assert payment_tx.resolved_booking == booking
    assert payment_tx.amount == Decimal("2000.00")
    assert payment_tx.commission_amount == Decimal("40.00")
    assert payment_tx.vendor_payout_amount == Decimal("1960.00")
    assert payment_tx.payout_status == PaymentTransaction.PayoutStatus.PENDING

    initialize_payload = json.loads(captured_initialize["data"])
    assert initialize_payload["amount"] == "2000.00"
    assert initialize_payload["subaccounts"] == {
        "id": "sub-hotel-workflow",
    }

    def fake_verify(tx_ref):
        assert tx_ref == payment_tx.tx_ref
        return {
            "status": "success",
            "data": {
                "status": "success",
                "amount": str(payment_tx.amount),
                "currency": payment_tx.currency,
                "reference": "chapa-workflow-ref",
                "method": "telebirr",
            },
        }

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        fake_verify,
    )

    verify_response = auth_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert verify_response.status_code == 200
    booking.refresh_from_db()
    payment_tx.refresh_from_db()
    assert booking.status == Booking.BookingStatus.CONFIRMED
    assert payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS
    assert payment_tx.chapa_transaction_id == "chapa-workflow-ref"
    verify_data = verify_response.json()
    assert verify_data["status"] == PaymentTransaction.PaymentStatus.SUCCESS
    assert verify_data["receipt_url"] == "https://chapa.link/payment-receipt/chapa-workflow-ref"
    assert verify_data["chapa_verification"]["success"] is True


def test_guest_hotel_booking_without_email_can_pay_and_confirm(api_client, room, settings, monkeypatch):
    settings.CHAPA_CALLBACK_URL = "https://api.example.com/api/v1/payment/callback/chapa/"
    settings.FRONTEND_URL = "https://app.example.com"
    room.hotel.company.chapa_subaccount_id = "sub-hotel-guest-workflow"
    room.hotel.company.save(update_fields=["chapa_subaccount_id"])

    monkeypatch.setattr("apps.listing.services.OtpService.generate_code", lambda: "123456")
    monkeypatch.setattr("services.sms.send_sms", lambda phone, message: True)
    monkeypatch.setattr(
        "apps.listing.services.BookingEmailService.send_booking_confirmation",
        lambda booking: None,
    )

    check_in = date.today() + timedelta(days=3)
    check_out = date.today() + timedelta(days=5)
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(room.hotel),
        object_id=room.hotel.id,
        version="1",
        title="Hotel Terms",
        content="Hotel booking terms",
        effective_date=date.today(),
        is_active=True,
    )
    for day_offset in range((check_out - check_in).days):
        StayAvailability.objects.create(
            hotel=room.hotel,
            room=room,
            date=check_in + timedelta(days=day_offset),
            available_rooms=room.total_units,
        )

    otp_response = api_client.post(
        "/api/v1/listing/bookings/guest-otp/request/",
        {"guest_phone": "0911555999"},
        format="json",
    )
    assert otp_response.status_code == 201

    booking_response = api_client.post(
        "/api/v1/listing/bookings/",
        {
            "items": [{"room": str(room.id), "units_booked": 1}],
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "terms_accepted": True,
            "terms_version": "1",
            "guest_first_name": "Phone",
            "guest_last_name": "Guest",
            "guest_phone": "0911555999",
            "otp_challenge_id": otp_response.json()["challenge_id"],
            "otp_code": "123456",
            "payment_currency": "ETB",
        },
        format="json",
    )

    assert booking_response.status_code == 201, booking_response.json()
    booking_data = booking_response.json()
    assert booking_data["booking_reference"].startswith("H-")
    assert booking_data["guest_email"] == ""

    booking = Booking.objects.get(id=booking_data["id"])
    assert booking.user is None
    assert booking.guest_email == ""
    assert booking.guest_phone == "0911555999"
    assert booking.status == Booking.BookingStatus.PENDING

    captured_initialize = _mock_chapa_initialize(monkeypatch)
    initiate_response = api_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert initiate_response.status_code == 200, initiate_response.json()
    initiate_data = initiate_response.json()
    payment_tx = PaymentTransaction.objects.get(tx_ref=initiate_data["tx_ref"])
    initialize_payload = json.loads(captured_initialize["data"])
    assert initialize_payload["email"] == "guest@michotmarefia.com"
    assert initialize_payload["first_name"] == "Phone"
    assert initialize_payload["last_name"] == "Guest"

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {
            "status": "success",
            "data": {
                "status": "success",
                "amount": str(payment_tx.amount),
                "currency": payment_tx.currency,
                "reference": "chapa-guest-workflow-ref",
                "method": "telebirr",
            },
        },
    )

    verify_response = api_client.get(f"/api/v1/payment/verify-public/{payment_tx.tx_ref}/")

    assert verify_response.status_code == 200, verify_response.json()
    booking.refresh_from_db()
    payment_tx.refresh_from_db()
    assert booking.status == Booking.BookingStatus.CONFIRMED
    assert payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS


def test_registered_property_rental_booking_can_pay_and_confirm(
    auth_client,
    user,
    property_listing,
    settings,
    monkeypatch,
):
    settings.CHAPA_CALLBACK_URL = "https://api.example.com/api/v1/payment/callback/chapa/"
    settings.FRONTEND_URL = "https://app.example.com"
    property_listing.booking_forward_window_days = 30
    property_listing.save(update_fields=["booking_forward_window_days"])
    property_listing.company.chapa_subaccount_id = "sub-property-registered-workflow"
    property_listing.company.save(update_fields=["chapa_subaccount_id"])

    start_date = date.today() + timedelta(days=6)
    end_date = start_date + timedelta(days=3)
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(property_listing),
        object_id=property_listing.id,
        version="1",
        title="Property Rental Terms",
        content="Property rental booking terms",
        effective_date=date.today(),
        is_active=True,
    )
    _create_property_rental_availability(
        property_listing,
        start_date,
        end_date,
        price=Decimal("2100.00"),
    )

    booking_response = auth_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        {
            "property_listing": str(property_listing.id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Registered",
            "guest_last_name": "Renter",
            "guest_email": user.email,
            "guest_phone": user.phone,
            "terms_accepted": True,
            "terms_version": "1",
        },
        format="json",
    )

    assert booking_response.status_code == 201, booking_response.json()
    booking = PropertyRentalBooking.objects.get(id=booking_response.json()["id"])
    assert booking.renter == user
    assert booking.status == PropertyRentalBooking.RentStatus.PENDING

    captured_initialize = _mock_chapa_initialize(monkeypatch)
    initiate_response = auth_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "propertyrental"},
        format="json",
    )

    assert initiate_response.status_code == 200, initiate_response.json()
    payment_tx = PaymentTransaction.objects.get(tx_ref=initiate_response.json()["tx_ref"])
    initialize_payload = json.loads(captured_initialize["data"])
    assert initialize_payload["email"] == user.email
    assert initialize_payload["first_name"] == user.first_name
    assert initialize_payload["last_name"] == user.last_name

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {
            "status": "success",
            "data": {
                "status": "success",
                "amount": str(payment_tx.amount),
                "currency": payment_tx.currency,
                "reference": "chapa-property-registered-ref",
                "method": "telebirr",
            },
        },
    )

    verify_response = auth_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert verify_response.status_code == 200, verify_response.json()
    booking.refresh_from_db()
    payment_tx.refresh_from_db()
    assert booking.status == PropertyRentalBooking.RentStatus.CONFIRMED
    assert payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS
    assert payment_tx.chapa_transaction_id == "chapa-property-registered-ref"


def test_guest_property_rental_booking_without_email_can_pay_and_confirm(
    api_client,
    property_listing,
    settings,
    monkeypatch,
):
    settings.CHAPA_CALLBACK_URL = "https://api.example.com/api/v1/payment/callback/chapa/"
    settings.FRONTEND_URL = "https://app.example.com"
    property_listing.booking_forward_window_days = 30
    property_listing.save(update_fields=["booking_forward_window_days"])
    property_listing.company.chapa_subaccount_id = "sub-property-guest-workflow"
    property_listing.company.save(update_fields=["chapa_subaccount_id"])

    monkeypatch.setattr("apps.listing.services.OtpService.generate_code", lambda: "123456")
    monkeypatch.setattr("services.sms.send_sms", lambda phone, message: True)

    start_date = date.today() + timedelta(days=6)
    end_date = start_date + timedelta(days=2)
    TermsAndConditions.objects.create(
        content_type=ContentType.objects.get_for_model(property_listing),
        object_id=property_listing.id,
        version="1",
        title="Property Rental Terms",
        content="Property rental booking terms",
        effective_date=date.today(),
        is_active=True,
    )
    _create_property_rental_availability(
        property_listing,
        start_date,
        end_date,
        price=Decimal("1800.00"),
    )

    otp_response = api_client.post(
        "/api/v1/listing/property-rentals/bookings/guest-otp/request/",
        {"guest_phone": "0911555888"},
        format="json",
    )
    assert otp_response.status_code == 201, otp_response.json()

    booking_response = api_client.post(
        "/api/v1/listing/property-rentals/bookings/",
        {
            "property_listing": str(property_listing.id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_first_name": "Phone",
            "guest_last_name": "Guest",
            "guest_phone": "0911555888",
            "terms_accepted": True,
            "terms_version": "1",
            "otp_challenge_id": otp_response.json()["challenge_id"],
            "otp_code": "123456",
        },
        format="json",
    )

    assert booking_response.status_code == 201, booking_response.json()
    booking = PropertyRentalBooking.objects.get(id=booking_response.json()["id"])
    assert booking.renter is None
    assert booking.guest_email == ""
    assert booking.guest_phone == "0911555888"
    assert booking.status == PropertyRentalBooking.RentStatus.PENDING

    captured_initialize = _mock_chapa_initialize(monkeypatch)
    initiate_response = api_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "propertyrental"},
        format="json",
    )

    assert initiate_response.status_code == 200, initiate_response.json()
    payment_tx = PaymentTransaction.objects.get(tx_ref=initiate_response.json()["tx_ref"])
    initialize_payload = json.loads(captured_initialize["data"])
    assert initialize_payload["email"] == "guest@michotmarefia.com"
    assert initialize_payload["first_name"] == "Phone"
    assert initialize_payload["last_name"] == "Guest"

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {
            "status": "success",
            "data": {
                "status": "success",
                "amount": str(payment_tx.amount),
                "currency": payment_tx.currency,
                "reference": "chapa-property-guest-ref",
                "method": "telebirr",
            },
        },
    )

    verify_response = api_client.get(f"/api/v1/payment/verify-public/{payment_tx.tx_ref}/")

    assert verify_response.status_code == 200, verify_response.json()
    booking.refresh_from_db()
    payment_tx.refresh_from_db()
    assert booking.status == PropertyRentalBooking.RentStatus.CONFIRMED
    assert payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS
    assert payment_tx.chapa_transaction_id == "chapa-property-guest-ref"


def test_post_payment_initiate_allows_walk_in_booking(auth_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    booking.status = Booking.BookingStatus.WALK_IN
    booking.save(update_fields=["status"])
    captured = {}

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.initialize_payment",
        lambda **kwargs: captured.update(kwargs) or {
            "success": True,
            "message": "Payment initialized",
            "checkout_url": "https://checkout.example.com",
            "tx_ref": "tx-walk-in",
        },
    )

    response = auth_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["tx_ref"] == "tx-walk-in"
    assert captured["booking"].status == Booking.BookingStatus.WALK_IN


def _mock_chapa_initialize(monkeypatch):
    captured = {}

    class DummyResponse:
        def json(self):
            return {
                "status": "success",
                "data": {"checkout_url": "https://checkout.example.com"},
            }

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("apps.payment.services.requests.post", fake_post)
    return captured


def _mock_chapa_cancel(monkeypatch, *, status_value="success", message="Checkout link expired successfully"):
    captured = {}

    class DummyResponse:
        def json(self):
            return {
                "status": status_value,
                "message": message,
                "data": {"tx_ref": captured.get("tx_ref")},
            }

    def fake_put(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["tx_ref"] = url.rstrip("/").split("/")[-1]
        return DummyResponse()

    monkeypatch.setattr("apps.payment.services.requests.put", fake_put)
    return captured


def _assert_nested_split_payload(payload, *, subaccount_id, split_type, split_value):
    assert "subaccount_id" not in payload
    assert "split_type" not in payload
    assert "split_value" not in payload
    assert payload["subaccounts"] == {
        "id": subaccount_id,
    }


def _mock_chapa_subaccount(monkeypatch, *, status_value="success", message="Subaccount created successfully", subaccount_id="sub-test-123"):
    captured = {}

    class DummyResponse:
        def json(self):
            return {
                "status": status_value,
                "message": message,
                "data": {"subaccounts[id]": subaccount_id} if subaccount_id else {},
            }

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("apps.payment.services.requests.post", fake_post)
    return captured


def _enable_payment_settings(settings):
    settings.CHAPA_CALLBACK_URL = "https://api.example.com/payment/callback"
    settings.FRONTEND_URL = "https://app.example.com"
    settings.CHAPA_SECRET_KEY = "test-secret"
    settings.CHAPA_BASE_URL = "https://api.chapa.co/v1/"


def _subaccount_payload(**overrides):
    payload = {
        "bank_code": "946",
        "account_number": "100000000001",
        "business_name": "Owner Business",
        "account_name": "Owner Account",
    }
    payload.update(overrides)
    return payload


def test_admin_creates_company_owner_subaccount(settings, monkeypatch, admin_client, company):
    _enable_payment_settings(settings)
    captured = _mock_chapa_subaccount(monkeypatch, subaccount_id="sub-company-001")

    response = admin_client.post(
        "/api/v1/payment/subaccounts/",
        _subaccount_payload(
            owner_type="company",
            owner_id=str(company.id),
            split_type="percentage",
            split_value="0.0400",
        ),
        format="json",
    )

    assert response.status_code == 201
    company.refresh_from_db()
    assert company.chapa_subaccount_id == "sub-company-001"
    assert company.split_config_active is True
    assert company.split_type == "percentage"
    assert company.split_value == Decimal("0.0400")
    data = response.json()
    assert data["owner_type"] == "company"
    assert data["chapa_subaccount_id"] == "sub-company-001"
    assert "account_number" not in data
    chapa_payload = json.loads(captured["data"])
    assert chapa_payload["split_type"] == "percentage"
    assert chapa_payload["split_value"] == 0.04


def test_admin_creates_individual_owner_subaccount(settings, monkeypatch, admin_client, individual_owner):
    _enable_payment_settings(settings)
    _mock_chapa_subaccount(monkeypatch, subaccount_id="sub-individual-001")

    response = admin_client.post(
        "/api/v1/payment/subaccounts/",
        _subaccount_payload(
            owner_type="individual_owner",
            owner_id=str(individual_owner.id),
            split_type="flat",
            split_value="25.0000",
        ),
        format="json",
    )

    assert response.status_code == 201
    individual_owner.refresh_from_db()
    assert individual_owner.chapa_subaccount_id == "sub-individual-001"
    assert individual_owner.split_type == "flat"
    assert individual_owner.split_value == Decimal("25.0000")
    assert individual_owner.split_config_active is True
    assert response.json()["owner_type"] == "individual_owner"


def test_owner_creates_own_subaccount(settings, monkeypatch, company_client, company):
    _enable_payment_settings(settings)
    captured = _mock_chapa_subaccount(monkeypatch, subaccount_id="sub-own-company")
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0200"),
    )

    response = company_client.post(
        "/api/v1/payment/subaccounts/",
        _subaccount_payload(),
        format="json",
    )

    assert response.status_code == 201
    company.refresh_from_db()
    assert company.chapa_subaccount_id == "sub-own-company"
    assert company.split_config_active is False
    chapa_payload = json.loads(captured["data"])
    assert chapa_payload["split_type"] == "percentage"
    assert chapa_payload["split_value"] == 0.02


def test_subaccount_me_returns_current_owner(company_client, company):
    company.chapa_subaccount_id = "sub-current"
    company.split_config_active = True
    company.split_type = "percentage"
    company.split_value = Decimal("0.0300")
    company.save(update_fields=["chapa_subaccount_id", "split_config_active", "split_type", "split_value"])

    response = company_client.get("/api/v1/payment/subaccounts/me/")

    assert response.status_code == 200
    data = response.json()
    assert data["owner_type"] == "company"
    assert data["owner_id"] == str(company.id)
    assert data["chapa_subaccount_id"] == "sub-current"


def test_subaccount_wrong_owner_gets_403(settings, monkeypatch, company_client, individual_owner):
    _enable_payment_settings(settings)
    captured = _mock_chapa_subaccount(monkeypatch)

    response = company_client.post(
        "/api/v1/payment/subaccounts/",
        _subaccount_payload(
            owner_type="individual_owner",
            owner_id=str(individual_owner.id),
        ),
        format="json",
    )

    assert response.status_code == 403
    assert captured == {}


def test_subaccount_missing_fields_return_400(company_client):
    response = company_client.post(
        "/api/v1/payment/subaccounts/",
        {"bank_code": "946"},
        format="json",
    )

    assert response.status_code == 400
    assert "account_number" in response.json()


def test_chapa_subaccount_failure_does_not_persist_subaccount(settings, monkeypatch, company_client, company):
    _enable_payment_settings(settings)
    _mock_chapa_subaccount(
        monkeypatch,
        status_value="failed",
        message="Account number is not valid for bank name",
        subaccount_id=None,
    )

    response = company_client.post(
        "/api/v1/payment/subaccounts/",
        _subaccount_payload(),
        format="json",
    )

    assert response.status_code == 400
    assert "Account number is not valid" in response.json()["detail"]
    company.refresh_from_db()
    assert company.chapa_subaccount_id is None


def test_existing_subaccount_duplicate_handling_is_deterministic(settings, monkeypatch, company_client, company):
    _enable_payment_settings(settings)
    company.chapa_subaccount_id = "sub-existing"
    company.save(update_fields=["chapa_subaccount_id"])
    captured = _mock_chapa_subaccount(monkeypatch)

    response = company_client.post(
        "/api/v1/payment/subaccounts/",
        _subaccount_payload(),
        format="json",
    )

    assert response.status_code == 400
    assert "already has" in str(response.json()["detail"])
    company.refresh_from_db()
    assert company.chapa_subaccount_id == "sub-existing"
    assert captured == {}


def test_contact_reveal_initialize_is_platform_only_even_when_owner_has_subaccount(
    settings,
    monkeypatch,
    company,
    user,
):
    _enable_payment_settings(settings)
    company.chapa_subaccount_id = "sub-contact-owner"
    company.save(update_fields=["chapa_subaccount_id"])
    listing = _build_car_sale(company)
    reveal_request = _build_reveal_request(
        listing,
        user,
        status=ContactRevealRequest.RevealStatus.REQUESTED,
        tx_ref="",
    )
    captured = _mock_chapa_initialize(monkeypatch)

    result = ContactRevealPaymentService.initialize_contact_reveal_payment(reveal_request)

    assert result["success"] is True
    payload = json.loads(captured["data"])
    assert "subaccount_id" not in payload
    assert "subaccounts" not in payload
    assert "split_type" not in payload
    assert "split_value" not in payload

    payment_tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])
    assert payment_tx.booking_type == "contact_reveal"
    assert payment_tx.payout_status == PaymentTransaction.PayoutStatus.NOT_APPLICABLE
    assert payment_tx.vendor_company is None
    assert payment_tx.vendor_individual is None


def test_contact_reveal_initialize_uses_chapa_safe_payload(settings, monkeypatch, company, user):
    _enable_payment_settings(settings)
    user.email = "not-a-valid-email"
    user.save(update_fields=["email"])
    listing = _build_car_sale(company)
    reveal_request = _build_reveal_request(
        listing,
        user,
        status=ContactRevealRequest.RevealStatus.REQUESTED,
        tx_ref="",
    )
    captured = _mock_chapa_initialize(monkeypatch)

    result = ContactRevealPaymentService.initialize_contact_reveal_payment(reveal_request)

    assert result["success"] is True
    payload = json.loads(captured["data"])
    assert payload["email"].startswith("contact-")
    assert payload["email"].endswith("@example.com")
    assert payload["customization"]["title"] == "Contact Reveal"
    assert len(payload["customization"]["title"]) <= 16


def _force_repeat_booking_fee(user, room):
    prior = _build_booking(user, room)
    prior.booking_reference = "H-PRIOR01"
    prior.save(update_fields=["booking_reference"])
    return prior


def test_chapa_split_uses_nested_percentage_default_as_platform_commission(settings, monkeypatch, user, room):
    _enable_payment_settings(settings)
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0200"),
    )
    room.hotel.company.chapa_subaccount_id = "sub-hotel-123"
    room.hotel.company.save(update_fields=["chapa_subaccount_id"])

    booking = _build_booking(user, room)
    item = booking.items.first()
    BookingAddon.objects.create(
        booking_item=item,
        name="Breakfast",
        description="Breakfast",
        category=BookingAddon.AddonCategory.MEAL,
        quantity=1,
        price_per_unit=Decimal("100.00"),
        currency="ETB",
    )
    booking.total_price = Decimal("2200.00")
    booking.save(update_fields=["total_price"])
    captured = _mock_chapa_initialize(monkeypatch)

    result = ChapaPaymentService.initialize_payment(
        booking=booking,
        booking_type="booking",
        amount=booking.total_price,
        currency="ETB",
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    assert result["success"] is True
    payload = json.loads(captured["data"])
    _assert_nested_split_payload(
        payload,
        subaccount_id="sub-hotel-123",
        split_type="percentage",
        split_value=0.02,
    )

    payment_tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])
    assert payment_tx.commission_rate == Decimal("0.0200")
    assert payment_tx.commission_amount == Decimal("44.00")
    assert payment_tx.vendor_payout_amount == Decimal("2156.00")
    assert payment_tx.payout_status == PaymentTransaction.PayoutStatus.PENDING


def test_chapa_split_owner_percentage_override_wins(settings, monkeypatch, user, room):
    _enable_payment_settings(settings)
    room.hotel.company.chapa_subaccount_id = "sub-hotel-456"
    room.hotel.company.split_config_active = True
    room.hotel.company.split_type = "percentage"
    room.hotel.company.split_value = Decimal("0.0750")
    room.hotel.company.save(
        update_fields=["chapa_subaccount_id", "split_config_active", "split_type", "split_value"]
    )

    booking = _build_booking(user, room)
    booking.total_price = Decimal("2000.00")
    booking.save(update_fields=["total_price"])
    captured = _mock_chapa_initialize(monkeypatch)

    result = ChapaPaymentService.initialize_payment(
        booking=booking,
        booking_type="booking",
        amount=booking.total_price,
        currency="ETB",
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    assert result["success"] is True
    payload = json.loads(captured["data"])
    _assert_nested_split_payload(
        payload,
        subaccount_id="sub-hotel-456",
        split_type="percentage",
        split_value=0.075,
    )

    payment_tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])
    assert payment_tx.commission_rate == Decimal("0.0750")
    assert payment_tx.commission_amount == Decimal("150.00")
    assert payment_tx.vendor_payout_amount == Decimal("1850.00")


def test_chapa_split_owner_flat_override_wins(settings, monkeypatch, user, room):
    _enable_payment_settings(settings)
    room.hotel.company.chapa_subaccount_id = "sub-hotel-flat"
    room.hotel.company.split_config_active = True
    room.hotel.company.split_type = "flat"
    room.hotel.company.split_value = Decimal("25.0000")
    room.hotel.company.save(
        update_fields=["chapa_subaccount_id", "split_config_active", "split_type", "split_value"]
    )

    booking = _build_booking(user, room)
    booking.total_price = Decimal("2000.00")
    booking.save(update_fields=["total_price"])
    captured = _mock_chapa_initialize(monkeypatch)

    result = ChapaPaymentService.initialize_payment(
        booking=booking,
        booking_type="booking",
        amount=booking.total_price,
        currency="ETB",
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    assert result["success"] is True
    payload = json.loads(captured["data"])
    _assert_nested_split_payload(
        payload,
        subaccount_id="sub-hotel-flat",
        split_type="flat",
        split_value=25.0,
    )

    payment_tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])
    assert payment_tx.commission_rate is None
    assert payment_tx.commission_amount == Decimal("25.00")
    assert payment_tx.vendor_payout_amount == Decimal("1975.00")


def test_chapa_split_waives_platform_commission_for_walk_in_booking(settings, monkeypatch, user, room):
    _enable_payment_settings(settings)
    room.hotel.company.chapa_subaccount_id = "sub-hotel-789"
    room.hotel.company.save(update_fields=["chapa_subaccount_id"])
    _force_repeat_booking_fee(user, room)

    booking = _build_booking(user, room)
    booking.status = Booking.BookingStatus.WALK_IN
    booking.total_price = Decimal("2000.00")
    booking.save(update_fields=["status", "total_price"])
    captured = _mock_chapa_initialize(monkeypatch)

    result = ChapaPaymentService.initialize_payment(
        booking=booking,
        booking_type="booking",
        amount=booking.total_price,
        currency="ETB",
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    assert result["success"] is True
    payload = json.loads(captured["data"])
    _assert_nested_split_payload(
        payload,
        subaccount_id="sub-hotel-789",
        split_type="flat",
        split_value=0.0,
    )

    payment_tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])
    assert payment_tx.commission_rate is None
    assert payment_tx.commission_amount == Decimal("0.00")
    assert payment_tx.vendor_payout_amount == Decimal("2000.00")


def test_split_eligible_booking_families_use_nested_subaccounts_payload(
    settings,
    monkeypatch,
    user,
    room,
    guest_house_room,
    event_space,
    car_listing,
    property_listing,
):
    _enable_payment_settings(settings)
    PaymentPlatformConfig.objects.create(
        name="platform-default",
        default_split_type=PaymentPlatformConfig.SplitType.FLAT,
        default_split_value=Decimal("10.0000"),
    )
    captured = _mock_chapa_initialize(monkeypatch)

    def assert_initialized_with_subaccount(booking, booking_type, amount, expected_subaccount):
        result = ChapaPaymentService.initialize_payment(
            booking=booking,
            booking_type=booking_type,
            amount=amount,
            currency="ETB",
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
        )

        assert result["success"] is True
        payload = json.loads(captured["data"])
        _assert_nested_split_payload(
            payload,
            subaccount_id=expected_subaccount,
            split_type="flat",
            split_value=10.0,
        )
        payment_tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])
        assert payment_tx.payout_status == PaymentTransaction.PayoutStatus.PENDING
        assert payment_tx.commission_amount == Decimal("10.00")

    room.hotel.company.chapa_subaccount_id = "sub-hotel-flow"
    room.hotel.company.save(update_fields=["chapa_subaccount_id"])
    hotel_booking = _build_booking(user, room)
    assert_initialized_with_subaccount(
        hotel_booking,
        "booking",
        hotel_booking.total_price,
        "sub-hotel-flow",
    )

    guest_house_room.guest_house.company.chapa_subaccount_id = "sub-guesthouse-flow"
    guest_house_room.guest_house.company.save(update_fields=["chapa_subaccount_id"])
    guesthouse_booking = GuestHouseBookingFactory(renter=user, total_price=Decimal("1200.00"))
    GuestHouseBookingItemFactory(
        booking=guesthouse_booking,
        room=guest_house_room,
        units_booked=1,
        price_per_unit=Decimal("1200.00"),
    )
    assert_initialized_with_subaccount(
        guesthouse_booking,
        "guesthouse",
        guesthouse_booking.total_price,
        "sub-guesthouse-flow",
    )

    event_space.hotel.company.chapa_subaccount_id = "sub-event-flow"
    event_space.hotel.company.save(update_fields=["chapa_subaccount_id"])
    event_booking = EventSpaceBookingFactory(user=user, total_price=Decimal("1500.00"))
    EventSpaceBookingItemFactory(
        booking=event_booking,
        event_space=event_space,
        units_booked=1,
        price_per_unit=Decimal("1500.00"),
    )
    assert_initialized_with_subaccount(
        event_booking,
        "eventspace",
        event_booking.total_price,
        "sub-event-flow",
    )

    car_listing.company.chapa_subaccount_id = "sub-car-flow"
    car_listing.company.save(update_fields=["chapa_subaccount_id"])
    rental = _build_car_rental(user, car_listing)
    assert_initialized_with_subaccount(
        rental,
        "carrental",
        rental.total_price,
        "sub-car-flow",
    )

    property_listing.company.chapa_subaccount_id = "sub-property-flow"
    property_listing.company.save(update_fields=["chapa_subaccount_id"])
    property_booking = _build_property_rental(property_listing, user)
    assert_initialized_with_subaccount(
        property_booking,
        "propertyrental",
        property_booking.total_price,
        "sub-property-flow",
    )


def test_missing_subaccount_blocks_checkout_before_chapa(settings, monkeypatch, user, room):
    _enable_payment_settings(settings)
    booking = _build_booking(user, room)
    captured = _mock_chapa_initialize(monkeypatch)

    result = ChapaPaymentService.initialize_payment(
        booking=booking,
        booking_type="booking",
        amount=booking.total_price,
        currency="ETB",
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    assert result["success"] is False
    assert result["code"] == "SPLIT_PAYMENT_CONFIGURATION_ERROR"
    assert "checkout_url" not in result
    assert captured == {}
    payment_tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])
    assert payment_tx.status == PaymentTransaction.PaymentStatus.FAILED
    assert payment_tx.payout_status == PaymentTransaction.PayoutStatus.FAILED
    assert payment_tx.vendor_company == room.hotel.company


def test_post_payment_initiate_unauthenticated_for_registered_booking(api_client, user, room, monkeypatch):
    booking = _build_booking(user, room)

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.initialize_payment",
        lambda **kwargs: {"success": True, "message": "Payment initialized", "checkout_url": "https://checkout.example.com"},
    )

    response = api_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 403


def test_post_payment_initiate_wrong_user_forbidden(company_client, user, room, monkeypatch):
    booking = _build_booking(user, room)

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.initialize_payment",
        lambda **kwargs: {"success": True, "message": "Payment initialized", "checkout_url": "https://checkout.example.com"},
    )

    response = company_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": str(booking.id), "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 403


def test_post_payment_initiate_invalid_payload(api_client):
    response = api_client.post("/api/v1/payment/initiate/", {}, format="json")

    assert response.status_code == 400


def test_post_payment_initiate_not_found(auth_client):
    response = auth_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": "11111111-1111-1111-1111-111111111111", "booking_type": "booking"},
        format="json",
    )

    assert response.status_code == 404


def test_post_payment_initiate_invalid_booking_type(api_client):
    response = api_client.post(
        "/api/v1/payment/initiate/",
        {"booking_id": "11111111-1111-1111-1111-111111111111", "booking_type": "unsupported"},
        format="json",
    )

    assert response.status_code == 400
    assert "booking_type" in response.json()


def test_get_payment_verify_unauthenticated(api_client):
    response = api_client.get("/api/v1/payment/verify/tx-auth-required/")

    assert response.status_code == 401


def test_get_payment_verify_success(auth_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-verify-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "verified"},
    )

    response = auth_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert data["tx_ref"] == payment_tx.tx_ref
    assert "chapa_verification" in data


def test_get_payment_verify_forbidden_for_wrong_user(company_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-verify-forbidden",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    def fail_if_called(payload):
        raise AssertionError("Unauthorized verification must not trigger callback processing")

    monkeypatch.setattr("apps.payment.views.ChapaPaymentService.handle_callback", fail_if_called)

    response = company_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert response.status_code == 403


def test_get_payment_verify_not_found_returns_stable_payload(auth_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": False, "message": "Transaction missing"},
    )

    response = auth_client.get("/api/v1/payment/verify/tx-missing/")

    assert response.status_code == 200
    assert response.json() == {"chapa_verification": {"success": False, "message": "Transaction missing"}}


def test_get_payment_verify_carrental_owner_uses_generic_booking(auth_client, user, car_listing, monkeypatch):
    rental = _build_car_rental(user, car_listing)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(CarRental),
        object_id=rental.id,
        booking_type="carrental",
        tx_ref="tx-rental-verify",
        amount=Decimal("3000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "verified"},
    )

    response = auth_client.get(f"/api/v1/payment/verify/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    assert response.json()["tx_ref"] == payment_tx.tx_ref


def test_car_rental_extension_callback_success_updates_rental_end_date(user, car_listing, monkeypatch):
    rental = _build_car_rental(user, car_listing)
    rental.status = CarRental.RentStatus.CONFIRMED
    rental.save(update_fields=["status"])
    new_end_date = rental.end_date + timedelta(days=2)
    _create_car_extension_availability(car_listing, rental.end_date, new_end_date, available_units=1)

    extension_request, _preview = CarRentalService.create_extension_request(
        rental,
        new_end_date=new_end_date,
        requested_by=user,
        payment_currency="ETB",
    )
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(CarRentalExtensionRequest),
        object_id=extension_request.id,
        booking_type="carrental_extension",
        tx_ref="tx-rental-extension-success",
        amount=extension_request.amount,
        currency=extension_request.currency,
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {
            "status": "success",
            "data": {
                "status": "success",
                "amount": str(extension_request.amount),
                "currency": extension_request.currency,
                "id": f"chapa-{tx_ref}",
                "method": "test",
            },
        },
    )

    result = ChapaPaymentService.handle_callback({"tx_ref": payment_tx.tx_ref})

    assert result["success"] is True
    rental.refresh_from_db()
    extension_request.refresh_from_db()
    payment_tx.refresh_from_db()
    assert rental.end_date == new_end_date
    assert extension_request.status == CarRentalExtensionRequest.ExtensionStatus.PAID_APPLIED
    assert extension_request.availability_held is False
    assert payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS


def test_car_rental_extension_callback_failure_releases_hold(user, car_listing, monkeypatch):
    rental = _build_car_rental(user, car_listing)
    rental.status = CarRental.RentStatus.CONFIRMED
    rental.save(update_fields=["status"])
    original_end_date = rental.end_date
    new_end_date = rental.end_date + timedelta(days=2)
    _create_car_extension_availability(car_listing, rental.end_date, new_end_date, available_units=1)

    extension_request, _preview = CarRentalService.create_extension_request(
        rental,
        new_end_date=new_end_date,
        requested_by=user,
        payment_currency="ETB",
    )
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(CarRentalExtensionRequest),
        object_id=extension_request.id,
        booking_type="carrental_extension",
        tx_ref="tx-rental-extension-failed",
        amount=extension_request.amount,
        currency=extension_request.currency,
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {"status": "failed", "message": "verification failed"},
    )

    result = ChapaPaymentService.handle_callback({"tx_ref": payment_tx.tx_ref})

    assert result["success"] is False
    rental.refresh_from_db()
    extension_request.refresh_from_db()
    payment_tx.refresh_from_db()
    assert rental.end_date == original_end_date
    assert extension_request.status == CarRentalExtensionRequest.ExtensionStatus.FAILED
    assert extension_request.availability_held is False
    assert payment_tx.status == PaymentTransaction.PaymentStatus.FAILED
    restored = list(
        CarAvailability.objects.filter(
            car_listing=car_listing,
            date__gte=original_end_date,
            date__lt=new_end_date,
        ).values_list("available_units", flat=True)
    )
    assert restored == [1, 1]


def test_car_rental_extension_amount_mismatch_releases_hold_and_keeps_dates(user, car_listing, monkeypatch):
    rental = _build_car_rental(user, car_listing)
    rental.status = CarRental.RentStatus.CONFIRMED
    rental.save(update_fields=["status"])
    original_end_date = rental.end_date
    new_end_date = rental.end_date + timedelta(days=2)
    _create_car_extension_availability(car_listing, rental.end_date, new_end_date, available_units=1)

    extension_request, _preview = CarRentalService.create_extension_request(
        rental,
        new_end_date=new_end_date,
        requested_by=user,
        payment_currency="ETB",
    )
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(CarRentalExtensionRequest),
        object_id=extension_request.id,
        booking_type="carrental_extension",
        tx_ref="tx-rental-extension-mismatch",
        amount=extension_request.amount,
        currency=extension_request.currency,
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        lambda tx_ref: {
            "status": "success",
            "data": {
                "amount": str(extension_request.amount + Decimal("10.00")),
                "currency": extension_request.currency,
                "id": f"chapa-{tx_ref}",
                "method": "test",
            },
        },
    )

    result = ChapaPaymentService.handle_callback({"tx_ref": payment_tx.tx_ref})

    assert result["success"] is False
    rental.refresh_from_db()
    extension_request.refresh_from_db()
    payment_tx.refresh_from_db()
    assert rental.end_date == original_end_date
    assert extension_request.status == CarRentalExtensionRequest.ExtensionStatus.FAILED
    assert extension_request.availability_held is False
    assert payment_tx.status == PaymentTransaction.PaymentStatus.FAILED


def test_get_payment_verify_public_success(api_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-verify-public-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "verified"},
    )

    response = api_client.get(f"/api/v1/payment/verify-public/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert data["tx_ref"] == payment_tx.tx_ref
    assert "chapa_verification" in data


def test_get_payment_verify_public_not_found_contract(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": False, "message": "Transaction tx-public-missing not found"},
    )

    response = api_client.get("/api/v1/payment/verify-public/tx-public-missing/")

    assert response.status_code == 200
    data = response.json()
    assert "chapa_verification" in data
    assert data["chapa_verification"]["success"] is False


def test_put_payment_cancel_unauthenticated(api_client):
    response = api_client.put("/api/v1/payment/cancel/tx-auth-required/")

    assert response.status_code == 401


def test_cancel_transaction_calls_chapa_and_marks_local_cancelled(settings, monkeypatch, booking):
    _enable_payment_settings(settings)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-service-cancel",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )
    captured = _mock_chapa_cancel(monkeypatch)

    result = ChapaPaymentService.cancel_transaction(payment_tx.tx_ref)

    assert result == {
        "success": True,
        "message": "Checkout link expired successfully",
    }
    assert captured["url"] == "https://api.chapa.co/v1/transaction/cancel/tx-service-cancel"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"
    payment_tx.refresh_from_db()
    assert payment_tx.status == PaymentTransaction.PaymentStatus.CANCELLED
    assert payment_tx.metadata["chapa_cancel_response"]["status"] == "success"


def test_cancel_transaction_rejects_success_payment_without_chapa_call(settings, monkeypatch, booking):
    _enable_payment_settings(settings)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-service-success-cancel",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Non-pending cancellation must not call Chapa")

    monkeypatch.setattr("apps.payment.services.requests.put", fail_if_called)

    result = ChapaPaymentService.cancel_transaction(payment_tx.tx_ref)

    assert result["success"] is False
    assert "Cannot cancel transaction" in result["error"]
    payment_tx.refresh_from_db()
    assert payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS


def test_cancel_transaction_missing_returns_not_found():
    result = ChapaPaymentService.cancel_transaction("tx-service-missing")

    assert result == {"success": False, "error": "Transaction not found"}


def test_cancel_transaction_chapa_failure_does_not_mark_cancelled(settings, monkeypatch, booking):
    _enable_payment_settings(settings)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-service-cancel-fail",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )
    _mock_chapa_cancel(
        monkeypatch,
        status_value="failed",
        message="Invalid transaction or Transaction not found",
    )

    result = ChapaPaymentService.cancel_transaction(payment_tx.tx_ref)

    assert result["success"] is False
    assert "Invalid transaction" in result["error"]
    payment_tx.refresh_from_db()
    assert payment_tx.status == PaymentTransaction.PaymentStatus.PENDING
    assert payment_tx.metadata["chapa_cancel_error"]["status"] == "failed"


def test_cancel_transaction_already_expired_marks_cancelled(settings, monkeypatch, booking):
    _enable_payment_settings(settings)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-service-already-expired",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )
    _mock_chapa_cancel(
        monkeypatch,
        status_value="failed",
        message="Payment link already expired",
    )

    result = ChapaPaymentService.cancel_transaction(payment_tx.tx_ref)

    assert result == {"success": True, "message": "Payment link already expired"}
    payment_tx.refresh_from_db()
    assert payment_tx.status == PaymentTransaction.PaymentStatus.CANCELLED
    assert payment_tx.metadata["chapa_cancel_response"]["message"] == "Payment link already expired"


def test_put_payment_cancel_success(auth_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-cancel-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.cancel_transaction",
        lambda tx_ref: {"success": True, "message": "Cancelled"},
    )

    response = auth_client.put(f"/api/v1/payment/cancel/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Cancelled"
    assert data["refund_supported"] is False
    assert data["refund_policy"] == "no_refunds"
    assert "No refunds are available" in data["refund_message"]
    assert data["cancellation_effect"] == "pending_payment_cancelled_only"
    payment_tx.refresh_from_db()
    assert payment_tx.status == PaymentTransaction.PaymentStatus.CANCELLED


def test_put_payment_cancel_forbidden_for_wrong_user(company_client, user, room, monkeypatch):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-cancel-forbidden",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    def fail_if_called(tx_ref):
        raise AssertionError("Unauthorized cancellation must not call payment service")

    monkeypatch.setattr("apps.payment.views.ChapaPaymentService.cancel_transaction", fail_if_called)

    response = company_client.put(f"/api/v1/payment/cancel/{payment_tx.tx_ref}/")

    assert response.status_code == 403


def test_put_payment_cancel_not_found(auth_client):
    response = auth_client.put("/api/v1/payment/cancel/tx-missing/")

    assert response.status_code == 404


def test_put_payment_cancel_rejects_non_pending(auth_client, user, room):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-cancel-successful",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
    )

    response = auth_client.put(f"/api/v1/payment/cancel/{payment_tx.tx_ref}/")

    assert response.status_code == 400
    data = response.json()
    assert data["refund_supported"] is False
    assert data["refund_policy"] == "no_refunds"
    assert "non-refundable" in data["error"]
    assert data["cancellation_effect"] == "refund_not_available"


def test_put_payment_cancel_carrental_owner_uses_generic_booking(auth_client, user, car_listing, monkeypatch):
    rental = _build_car_rental(user, car_listing)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(CarRental),
        object_id=rental.id,
        booking_type="carrental",
        tx_ref="tx-rental-cancel",
        amount=Decimal("3000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.cancel_transaction",
        lambda tx_ref: {"success": True, "message": "Cancelled"},
    )

    response = auth_client.put(f"/api/v1/payment/cancel/{payment_tx.tx_ref}/")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Cancelled"
    assert data["refund_supported"] is False
    assert data["refund_policy"] == "no_refunds"


def test_post_payment_callback_public_success(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": True, "message": "callback received"},
    )

    response = api_client.get("/api/v1/payment/callback/chapa/?tx_ref=tx-abc")

    assert response.status_code == 200
    assert response.json()["message"] == "callback received"


def test_get_payment_callback_missing_reference(api_client):
    response = api_client.get("/api/v1/payment/callback/chapa/")

    assert response.status_code == 400
    assert response.json()["error"] == "Missing transaction reference"


def test_get_payment_callback_failure_path(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_callback",
        lambda payload: {"success": False, "message": "Verification failed"},
    )

    response = api_client.get("/api/v1/payment/callback/chapa/?tx_ref=tx-failed")

    assert response.status_code == 400
    assert response.json()["error"] == "Verification failed"


def test_post_payment_webhook_public_success(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_webhook",
        lambda request: {"success": True, "message": "webhook received"},
    )

    response = api_client.post("/api/v1/payment/webhook/chapa/", {"tx_ref": "tx-abc"}, format="json")

    assert response.status_code == 200
    assert response.json()["message"] == "webhook received"


def test_post_payment_webhook_invalid_payload(api_client, settings):
    settings.CHAPA_WEBHOOK_SECRET = "secret"

    response = api_client.post("/api/v1/payment/webhook/chapa/", {}, format="json")

    assert response.status_code == 200
    assert response.json()["message"] == "Webhook ignored"


def _webhook_signature(secret, raw_body):
    return hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()


def _post_signed_webhook(api_client, settings, raw_body, *, header="x", signature=None):
    settings.CHAPA_WEBHOOK_SECRET = "secret"
    signature = signature or _webhook_signature(settings.CHAPA_WEBHOOK_SECRET, raw_body)
    header_kwargs = (
        {"HTTP_X_CHAPA_SIGNATURE": signature}
        if header == "x"
        else {"HTTP_CHAPA_SIGNATURE": signature}
    )
    return api_client.post(
        "/api/v1/payment/webhook/chapa/",
        data=raw_body,
        content_type="application/json",
        **header_kwargs,
    )


def test_post_payment_webhook_accepts_raw_body_hmac_signature(api_client, settings, monkeypatch):
    settings.CHAPA_WEBHOOK_SECRET = "secret"
    raw_body = b'{ "tx_ref" : "tx-raw-hmac" , "status" : "success" }'
    signature = _webhook_signature(settings.CHAPA_WEBHOOK_SECRET, raw_body)
    seen = {}

    def fake_callback(payload):
        seen.update(payload)
        return {"success": True, "message": "raw body accepted"}

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.handle_callback",
        fake_callback,
    )

    response = api_client.post(
        "/api/v1/payment/webhook/chapa/",
        data=raw_body,
        content_type="application/json",
        HTTP_X_CHAPA_SIGNATURE=signature,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "raw body accepted"
    assert seen["tx_ref"] == "tx-raw-hmac"


def test_verify_webhook_signature_uses_raw_body(settings):
    settings.CHAPA_WEBHOOK_SECRET = "secret"
    raw_body = b'{ "tx_ref" : "tx-raw-hmac" , "status" : "success" }'
    signature = _webhook_signature(settings.CHAPA_WEBHOOK_SECRET, raw_body)

    assert verify_webhook_signature(raw_body, signature) is True
    assert verify_webhook_signature(b'{"tx_ref":"tx-raw-hmac","status":"success"}', signature) is False


def test_post_payment_webhook_accepts_chapa_signature_header(api_client, settings, monkeypatch):
    raw_body = b'{"tx_ref":"tx-chapa-header","status":"success"}'
    seen = {}

    def fake_callback(payload):
        seen.update(payload)
        return {"success": True, "message": "chapa header accepted"}

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.handle_callback",
        fake_callback,
    )

    response = _post_signed_webhook(api_client, settings, raw_body, header="chapa")

    assert response.status_code == 200
    assert response.json()["message"] == "chapa header accepted"
    assert seen["tx_ref"] == "tx-chapa-header"


def test_post_payment_webhook_invalid_signature_returns_200_without_processing(api_client, settings, monkeypatch):
    settings.CHAPA_WEBHOOK_SECRET = "secret"

    def fail_if_called(payload):
        raise AssertionError("Invalid webhook signature must not process payload")

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.handle_callback",
        fail_if_called,
    )

    response = api_client.post(
        "/api/v1/payment/webhook/chapa/",
        data=b'{"tx_ref":"tx-invalid-signature","status":"success"}',
        content_type="application/json",
        HTTP_X_CHAPA_SIGNATURE="bad-signature",
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Webhook ignored"


def test_post_payment_webhook_missing_signature_returns_200_without_processing(api_client, settings, monkeypatch):
    settings.CHAPA_WEBHOOK_SECRET = "secret"

    def fail_if_called(payload):
        raise AssertionError("Unsigned webhook must not process payload")

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.handle_callback",
        fail_if_called,
    )

    response = api_client.post(
        "/api/v1/payment/webhook/chapa/",
        data=b'{"tx_ref":"tx-missing-signature","status":"success"}',
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Webhook ignored"


def test_post_payment_webhook_duplicate_success_is_idempotent(api_client, settings, monkeypatch, booking):
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-webhook-duplicate",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )
    raw_body = (
        b'{"event":"charge.success","tx_ref":"tx-webhook-duplicate",'
        b'"reference":"chapa-ref-duplicate","status":"success"}'
    )
    calls = []

    def fake_callback(payload):
        calls.append(payload)
        payment_tx.status = PaymentTransaction.PaymentStatus.SUCCESS
        payment_tx.save(update_fields=["status"])
        return {"success": True, "message": "processed once"}

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.handle_callback",
        fake_callback,
    )

    first = _post_signed_webhook(api_client, settings, raw_body)
    second = _post_signed_webhook(api_client, settings, raw_body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["message"] == "processed once"
    assert second.json()["message"] == "Already processed"
    assert len(calls) == 1


def test_success_webhook_verifies_before_confirming(api_client, settings, monkeypatch, booking):
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-webhook-success-verify",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )
    raw_body = (
        b'{"event":"charge.success","tx_ref":"tx-webhook-success-verify",'
        b'"reference":"chapa-ref-success","status":"success"}'
    )
    calls = []

    def fake_verify(tx_ref):
        calls.append(("verify", tx_ref))
        return {
            "status": "success",
            "data": {
                "status": "success",
                "amount": "1000.00",
                "currency": "ETB",
                "reference": "chapa-ref-success",
                "method": "test",
            },
        }

    def fake_confirm(booking_obj):
        calls.append(("confirm", booking_obj.id))

    monkeypatch.setattr(
        "apps.payment.services.ChapaPaymentService.verify_payment",
        fake_verify,
    )
    monkeypatch.setattr(
        "apps.listing.services.BookingService.confirm_booking",
        fake_confirm,
    )

    response = _post_signed_webhook(api_client, settings, raw_body)

    assert response.status_code == 200
    assert calls[0] == ("verify", payment_tx.tx_ref)
    assert calls[1] == ("confirm", booking.id)
    payment_tx.refresh_from_db()
    assert payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS
    assert payment_tx.chapa_transaction_id == "chapa-ref-success"


def test_failed_webhook_does_not_confirm_booking(api_client, settings, monkeypatch, booking):
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-webhook-failed",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )
    raw_body = (
        b'{"event":"charge.failed/cancelled","tx_ref":"tx-webhook-failed",'
        b'"reference":"chapa-ref-failed","status":"failed"}'
    )

    def fail_if_confirmed(booking_obj):
        raise AssertionError("Failed webhook must not confirm booking")

    monkeypatch.setattr(
        "apps.listing.services.BookingService.confirm_booking",
        fail_if_confirmed,
    )

    response = _post_signed_webhook(api_client, settings, raw_body)

    assert response.status_code == 200
    assert response.json()["message"] == "Webhook processed"
    payment_tx.refresh_from_db()
    assert payment_tx.status == PaymentTransaction.PaymentStatus.FAILED


def test_post_payment_webhook_failure_path(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.payment.views.ChapaPaymentService.handle_webhook",
        lambda request: {"success": False, "message": "Invalid signature"},
    )

    response = api_client.post("/api/v1/payment/webhook/chapa/", {"tx_ref": "tx-abc"}, format="json")

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid signature"


def test_get_owner_ledger_unauthenticated(api_client):
    response = api_client.get("/api/v1/payment/ledger/")

    assert response.status_code == 401


def test_get_owner_ledger_forbidden_for_regular_user(auth_client):
    response = auth_client.get("/api/v1/payment/ledger/")

    assert response.status_code == 403


def test_get_owner_ledger_success(company_client, company, user, room):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-ledger-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
        vendor_company=company,
    )

    response = company_client.get("/api/v1/payment/ledger/")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert data["count"] >= 1
    assert any(item["tx_ref"] == payment_tx.tx_ref for item in data["results"])


def test_get_owner_ledger_detail_success(company_client, company, user, room):
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-ledger-detail-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        payment_method="telebirr",
        metadata={},
        vendor_company=company,
        commission_rate=Decimal("0.0500"),
        commission_amount=Decimal("50.00"),
        vendor_payout_amount=Decimal("950.00"),
    )

    response = company_client.get(f"/api/v1/payment/ledger/{payment_tx.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["tx_ref"] == payment_tx.tx_ref
    assert data["status"] == PaymentTransaction.PaymentStatus.SUCCESS
    assert data["amount"] == "1000.00"
    assert data["currency"] == "ETB"
    assert data["payment_method"] == "telebirr"
    assert "booking_reference" in data
    assert "listing_title" in data
    assert "customer_name" in data
    assert "booking_dates" in data
    assert "payout_status" in data


def test_get_owner_ledger_detail_not_found_for_other_owner(company_client, user, room):
    other_company = CompanyProfileFactory(user=user, category=CompanyProfile.CategoryChoice.HOTEL)
    booking = _build_booking(user, room)
    payment_tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-ledger-other-owner",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.SUCCESS,
        metadata={},
        vendor_company=other_company,
    )

    response = company_client.get(f"/api/v1/payment/ledger/{payment_tx.id}/")

    assert response.status_code == 404


def _create_monitor_transaction(user, room, **overrides):
    defaults = {
        "booking": _build_booking(user, room),
        "tx_ref": f"tx-monitor-{PaymentTransaction.objects.count()}",
        "amount": Decimal("1000.00"),
        "currency": "ETB",
        "status": PaymentTransaction.PaymentStatus.SUCCESS,
        "booking_type": "booking",
        "payout_status": PaymentTransaction.PayoutStatus.PENDING,
        "tax_amount": Decimal("15.00"),
    }
    defaults.update(overrides)
    return PaymentTransaction.objects.create(**defaults)


def _response_results(response):
    data = response.json()
    return data["results"] if "results" in data else data


def test_admin_transaction_monitor_list_success(admin_client, user, room):
    tx = _create_monitor_transaction(user, room)

    response = admin_client.get("/api/v1/payment/admin/transactions/")

    assert response.status_code == 200
    result = _response_results(response)[0]
    assert result["id"] == str(tx.id)
    assert result["tx_ref"] == tx.tx_ref
    assert "tax_amount" in result
    assert "grand_total" in result


def test_admin_transaction_monitor_filters_by_status(admin_client, user, room):
    success_tx = _create_monitor_transaction(user, room, tx_ref="tx-monitor-success")
    _create_monitor_transaction(
        user,
        room,
        tx_ref="tx-monitor-failed",
        status=PaymentTransaction.PaymentStatus.FAILED,
    )

    response = admin_client.get(
        "/api/v1/payment/admin/transactions/",
        {"status": PaymentTransaction.PaymentStatus.SUCCESS},
    )

    assert response.status_code == 200
    refs = {item["tx_ref"] for item in _response_results(response)}
    assert refs == {success_tx.tx_ref}


def test_admin_transaction_monitor_filters_by_date_range(admin_client, user, room):
    old_tx = _create_monitor_transaction(user, room, tx_ref="tx-monitor-old")
    recent_tx = _create_monitor_transaction(user, room, tx_ref="tx-monitor-recent")
    PaymentTransaction.objects.filter(id=old_tx.id).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    PaymentTransaction.objects.filter(id=recent_tx.id).update(
        created_at=timezone.now() - timedelta(days=1)
    )

    response = admin_client.get(
        "/api/v1/payment/admin/transactions/",
        {"date_from": (date.today() - timedelta(days=2)).isoformat()},
    )

    assert response.status_code == 200
    refs = {item["tx_ref"] for item in _response_results(response)}
    assert recent_tx.tx_ref in refs
    assert old_tx.tx_ref not in refs


def test_admin_transaction_monitor_filters_by_has_dispute(admin_client, user, room):
    disputed_tx = _create_monitor_transaction(
        user,
        room,
        tx_ref="tx-monitor-disputed",
        dispute_status=PaymentTransaction.DisputeStatus.OPEN,
    )
    _create_monitor_transaction(user, room, tx_ref="tx-monitor-undisputed")

    response = admin_client.get(
        "/api/v1/payment/admin/transactions/",
        {"has_dispute": "true"},
    )

    assert response.status_code == 200
    refs = {item["tx_ref"] for item in _response_results(response)}
    assert refs == {disputed_tx.tx_ref}


def test_admin_transaction_monitor_filters_by_payout_failed(admin_client, user, room):
    failed_payout_tx = _create_monitor_transaction(
        user,
        room,
        tx_ref="tx-monitor-payout-failed",
        payout_status=PaymentTransaction.PayoutStatus.FAILED,
    )
    _create_monitor_transaction(user, room, tx_ref="tx-monitor-payout-pending")

    response = admin_client.get(
        "/api/v1/payment/admin/transactions/",
        {"payout_failed": "true"},
    )

    assert response.status_code == 200
    refs = {item["tx_ref"] for item in _response_results(response)}
    assert refs == {failed_payout_tx.tx_ref}


def test_admin_transaction_monitor_detail_success(admin_client, user, room):
    tx = _create_monitor_transaction(user, room, tx_ref="tx-monitor-detail")

    response = admin_client.get(f"/api/v1/payment/admin/transactions/{tx.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(tx.id)
    assert data["tx_ref"] == tx.tx_ref
    assert "owner_price" in data
    assert "service_fee" in data
    assert "tax_rate" in data
    assert "dispute_note" in data


def test_admin_transaction_monitor_non_admin_forbidden(auth_client):
    response = auth_client.get("/api/v1/payment/admin/transactions/")

    assert response.status_code == 403


def test_admin_transaction_monitor_unauthenticated_requires_auth(api_client):
    response = api_client.get("/api/v1/payment/admin/transactions/")

    assert response.status_code == 401


def test_admin_opens_dispute_success(admin_client, admin_user, user, room):
    tx = _create_monitor_transaction(user, room, tx_ref="tx-monitor-open-dispute")

    response = admin_client.post(
        f"/api/v1/payment/admin/transactions/{tx.id}/dispute/open/",
        {"note": "Customer reported duplicate charge."},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dispute_status"] == PaymentTransaction.DisputeStatus.OPEN
    assert "duplicate charge" in data["dispute_note"]
    tx.refresh_from_db()
    assert tx.dispute_opened_at is not None
    assert tx.dispute_handled_by == admin_user


def test_admin_updates_dispute_note_success(admin_client, user, room):
    tx = _create_monitor_transaction(
        user,
        room,
        tx_ref="tx-monitor-update-dispute",
        dispute_status=PaymentTransaction.DisputeStatus.OPEN,
        dispute_note="Initial note",
        dispute_opened_at=timezone.now(),
    )

    response = admin_client.patch(
        f"/api/v1/payment/admin/transactions/{tx.id}/dispute/",
        {
            "status": PaymentTransaction.DisputeStatus.UNDER_REVIEW,
            "note": "Reviewed with payment provider.",
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dispute_status"] == PaymentTransaction.DisputeStatus.UNDER_REVIEW
    assert "Initial note" in data["dispute_note"]
    assert "payment provider" in data["dispute_note"]


def test_admin_resolves_dispute_success(admin_client, user, room):
    tx = _create_monitor_transaction(
        user,
        room,
        tx_ref="tx-monitor-resolve-dispute",
        dispute_status=PaymentTransaction.DisputeStatus.OPEN,
        dispute_note="Initial note",
        dispute_opened_at=timezone.now(),
    )

    response = admin_client.post(
        f"/api/v1/payment/admin/transactions/{tx.id}/dispute/resolve/",
        {"note": "Resolved without refund per policy."},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dispute_status"] == PaymentTransaction.DisputeStatus.RESOLVED
    assert data["dispute_resolved_at"] is not None
    assert "without refund" in data["dispute_note"]


def test_non_admin_open_dispute_forbidden(auth_client, user, room):
    tx = _create_monitor_transaction(user, room, tx_ref="tx-monitor-non-admin-dispute")

    response = auth_client.post(
        f"/api/v1/payment/admin/transactions/{tx.id}/dispute/open/",
        {"note": "Should fail"},
        format="json",
    )

    assert response.status_code == 403


def test_invalid_dispute_status_rejected(admin_client, user, room):
    tx = _create_monitor_transaction(
        user,
        room,
        tx_ref="tx-monitor-invalid-dispute",
        dispute_status=PaymentTransaction.DisputeStatus.OPEN,
        dispute_opened_at=timezone.now(),
    )

    response = admin_client.patch(
        f"/api/v1/payment/admin/transactions/{tx.id}/dispute/",
        {"status": "pending"},
        format="json",
    )

    assert response.status_code == 400


def test_open_dispute_not_found(admin_client):
    missing = "00000000-0000-0000-0000-000000000000"

    response = admin_client.post(
        f"/api/v1/payment/admin/transactions/{missing}/dispute/open/",
        {"note": "Missing"},
        format="json",
    )

    assert response.status_code == 404


def test_duplicate_active_dispute_rejected(admin_client, user, room):
    tx = _create_monitor_transaction(
        user,
        room,
        tx_ref="tx-monitor-duplicate-dispute",
        dispute_status=PaymentTransaction.DisputeStatus.OPEN,
        dispute_opened_at=timezone.now(),
    )

    response = admin_client.post(
        f"/api/v1/payment/admin/transactions/{tx.id}/dispute/open/",
        {"note": "Duplicate"},
        format="json",
    )

    assert response.status_code == 400
