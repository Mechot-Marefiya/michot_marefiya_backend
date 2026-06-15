# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: no
# Last updated: 2026-06-01

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from apps.listing.models import Booking
from apps.payment.models import PaymentPlatformConfig, PaymentTransaction

pytestmark = pytest.mark.django_db


def test_payment_transaction_str_representation(payment_transaction):
    assert str(payment_transaction) == f"Payment {payment_transaction.tx_ref} - {payment_transaction.status}"


def test_payment_transaction_resolved_booking_property(payment_transaction, booking):
    payment_transaction.booking = booking
    payment_transaction.save(update_fields=["booking"])
    assert payment_transaction.resolved_booking == booking


def test_payment_transaction_unique_tx_ref_constraint(booking):
    PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-unique-1",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    with pytest.raises(Exception):
        PaymentTransaction.objects.create(
            content_type=ContentType.objects.get_for_model(Booking),
            object_id=booking.id,
            booking=booking,
            booking_type="booking",
            tx_ref="tx-unique-1",
            amount=Decimal("1000.00"),
            currency="ETB",
            status=PaymentTransaction.PaymentStatus.PENDING,
            metadata={},
        )


def test_payment_transaction_tax_fields_are_nullable_for_existing_shape(booking):
    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking=booking,
        booking_type="booking",
        tx_ref="tx-tax-nullable",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    assert tx.tax_amount is None
    assert tx.tax_rate is None
    assert tx.tax_liability_status is None


def test_payment_transaction_allows_property_rental_booking_type(booking):
    tx = PaymentTransaction.objects.create(
        content_type=ContentType.objects.get_for_model(Booking),
        object_id=booking.id,
        booking_type="propertyrental",
        tx_ref="tx-propertyrental-choice",
        amount=Decimal("1000.00"),
        currency="ETB",
        status=PaymentTransaction.PaymentStatus.PENDING,
        metadata={},
    )

    assert tx.booking_type == "propertyrental"


def test_payment_platform_config_accepts_valid_percentage_default():
    config = PaymentPlatformConfig.objects.create(
        name="main",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0200"),
        default_car_sale_reveal_fee=Decimal("100.00"),
        default_property_sale_reveal_fee=Decimal("150.00"),
    )

    assert config.default_split_type == PaymentPlatformConfig.SplitType.PERCENTAGE
    assert config.default_split_value == Decimal("0.0200")
    assert config.default_car_sale_reveal_fee == Decimal("100.00")
    assert config.default_property_sale_reveal_fee == Decimal("150.00")


def test_payment_platform_config_rejects_invalid_percentage_value():
    config = PaymentPlatformConfig(
        name="bad-percent",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("1.5000"),
    )

    with pytest.raises(ValidationError):
        config.full_clean()


def test_payment_platform_config_rejects_negative_flat_value():
    config = PaymentPlatformConfig(
        name="bad-flat",
        default_split_type=PaymentPlatformConfig.SplitType.FLAT,
        default_split_value=Decimal("-1.0000"),
    )

    with pytest.raises(ValidationError):
        config.full_clean()


def test_payment_platform_config_rejects_non_positive_reveal_fees():
    config = PaymentPlatformConfig(
        name="bad-reveal-fee",
        default_split_type=PaymentPlatformConfig.SplitType.PERCENTAGE,
        default_split_value=Decimal("0.0200"),
        default_car_sale_reveal_fee=Decimal("0.00"),
        default_property_sale_reveal_fee=Decimal("-1.00"),
    )

    with pytest.raises(ValidationError):
        config.full_clean()
