import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.account.models import CompanyProfile
from apps.core.models import Address
from apps.listing.models import CarListing, CarSaleListing, ContactRevealRequest
from apps.payment.models import PaymentTransaction
from apps.payment.services import ChapaPaymentService, ContactRevealPaymentService


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


def _create_car_sale_listing(django_user_model, suffix=""):
    owner = django_user_model.objects.create_user(
        email=f"contact-owner{suffix}@example.com",
        password="pass",
    )
    address = Address.objects.create(
        street_line1=f"Contact reveal street {suffix}",
        city="Addis Ababa",
        country="Ethiopia",
    )
    company = CompanyProfile.objects.create(
        user=owner,
        name=f"Contact Reveal Motors {suffix}",
        phone="0911000000",
        category=CompanyProfile.CategoryChoice.VEHICLE,
        address=address,
        status=CompanyProfile.StatusChoice.APPROVED,
    )
    return CarSaleListing.objects.create(
        company=company,
        title=f"Toyota Vitz {suffix}",
        description="Clean car sale listing.",
        base_price=Decimal("800000.00"),
        currency="ETB",
        brand=CarListing.CarBrandChoices.TOYOTA,
        model="Vitz",
        year=2018,
        mileage=45000,
        fuel_type=CarListing.FuelTypeChoices.PETROL,
        transmission=CarListing.TransmissionChoices.AUTOMATIC,
        condition=CarListing.ConditionChoices.USED,
        seller_contact_name="Seller",
        seller_phone="0911223344",
        seller_email="seller@example.com",
        reveal_fee=Decimal("100.00"),
    )


def _create_reveal_request(listing, *, buyer=None, buyer_phone=""):
    return ContactRevealRequest.objects.create(
        listing=listing,
        buyer=buyer,
        buyer_phone=buyer_phone,
        amount=listing.reveal_fee,
        currency=listing.currency,
        expires_at=timezone.now() + timedelta(minutes=30),
    )


@pytest.mark.django_db
@override_settings(
    CHAPA_CALLBACK_URL="https://api.example.com/payment/callback/",
    FRONTEND_URL="https://ui.example.com",
    CHAPA_SECRET_KEY="secret",
)
@patch.object(ChapaPaymentService, "generate_tx_ref", return_value="CONTACT-1782180189-8627")
@patch("apps.payment.services.requests.post")
def test_guest_contact_reveal_uses_chapa_safe_fallback_email(mock_post, mock_tx_ref, django_user_model):
    listing = _create_car_sale_listing(django_user_model, suffix="guest")
    reveal_request = _create_reveal_request(listing, buyer_phone="0911223344")
    mock_post.return_value = _response(
        {
            "status": "success",
            "data": {"checkout_url": "https://checkout.chapa.co/contact"},
        }
    )

    result = ContactRevealPaymentService.initialize_contact_reveal_payment(reveal_request)

    payload = json.loads(mock_post.call_args.kwargs["data"])
    tx = PaymentTransaction.objects.get(tx_ref="CONTACT-1782180189-8627")

    assert result["success"] is True
    assert payload["email"] == "no-reply+contact178218018@gmail.com"
    assert payload["return_url"] == "https://ui.example.com/payments/complete?tx_ref=CONTACT-1782180189-8627"
    assert "-@" not in payload["email"]
    assert tx.booking_type == "contact_reveal"


@pytest.mark.django_db
@override_settings(
    CHAPA_CALLBACK_URL="https://api.example.com/payment/callback/",
    FRONTEND_URL="https://ui.example.com",
    CHAPA_SECRET_KEY="secret",
    CHAPA_FALLBACK_EMAIL="fallback@michotmarefia.com",
)
@patch.object(ChapaPaymentService, "generate_tx_ref", return_value="CONTACT-2000000000-1111")
@patch("apps.payment.services.requests.post")
def test_authenticated_contact_reveal_retries_when_chapa_rejects_email(
    mock_post,
    mock_tx_ref,
    django_user_model,
):
    listing = _create_car_sale_listing(django_user_model, suffix="auth")
    buyer = django_user_model.objects.create_user(
        email="buyer@example.com",
        password="pass",
        first_name="Buyer",
        last_name="One",
    )
    reveal_request = _create_reveal_request(listing, buyer=buyer)
    mock_post.side_effect = [
        _response(
            {
                "status": "failed",
                "message": {"email": ["validation.email"]},
            }
        ),
        _response(
            {
                "status": "success",
                "data": {"checkout_url": "https://checkout.chapa.co/contact-retry"},
            }
        ),
    ]

    result = ContactRevealPaymentService.initialize_contact_reveal_payment(reveal_request)

    first_payload = json.loads(mock_post.call_args_list[0].kwargs["data"])
    retry_payload = json.loads(mock_post.call_args_list[1].kwargs["data"])

    assert result["success"] is True
    assert mock_post.call_count == 2
    assert first_payload["email"] == "buyer@example.com"
    assert retry_payload["email"] == "fallback@michotmarefia.com"
