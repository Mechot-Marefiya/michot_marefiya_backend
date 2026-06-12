# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: no
# Last updated: 2026-06-01

from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.listing.models import Booking
from apps.payment.models import PaymentTransaction

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
