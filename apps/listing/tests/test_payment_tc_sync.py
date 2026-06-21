import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework import status
from apps.listing.models import TermsAndConditions, Booking
from apps.payment.services import ChapaPaymentService
from apps.payment.models import PaymentTransaction
from datetime import date, timedelta
from django.utils import timezone
from django.test import override_settings
from django.contrib.contenttypes.models import ContentType

@pytest.mark.django_db
class TestPaymentTCSync:
    """Test suite for T&C enforcement in the payment flow"""

    @pytest.fixture
    def setup_tc_booking(self, hotel_profile, company_user, address):
        # 1. Create T&C
        ct = ContentType.objects.get_for_model(hotel_profile)
        tc = TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="1.0",
            content="Initial Terms",
            is_active=True,
            effective_date=date.today()
        )
        
        # 2. Create Room
        from apps.listing.models import RoomListing
        room = RoomListing.objects.create(
            hotel=hotel_profile, 
            title="Standard Room", 
            base_price=1000, 
            total_units=5, 
            number_of_guests=2,
            address=address,
            room_size_sqm=30
        )
        
        # 3. Create Booking with T&C
        booking = Booking.objects.create(
            user=company_user,
            check_in_date=date.today() + timedelta(days=1),
            check_out_date=date.today() + timedelta(days=3),
            total_price=2000,
            status=Booking.BookingStatus.PENDING,
            terms_accepted=True,
            terms_version="1.0",
            terms_accepted_at=timezone.now(),
            terms_content_snapshot="Initial Terms"
        )
        from apps.listing.models import BookingItem
        BookingItem.objects.create(booking=booking, room=room, units_booked=1, price_per_unit=1000)
        
        return tc, booking, company_user

    def test_initiate_payment_blocks_legacy_booking(self, api_client, company_user):
        # Create a legacy booking (no T&C fields)
        booking = Booking.objects.create(
            user=company_user,
            check_in_date=date.today() + timedelta(days=1),
            check_out_date=date.today() + timedelta(days=3),
            total_price=2000,
            status=Booking.BookingStatus.PENDING,
            # terms_accepted=False (default)
        )
        
        api_client.force_authenticate(user=company_user)
        # Using the base payment-initiate URL
        url = reverse('initiate-payment')
        response = api_client.post(url, {"booking_id": str(booking.id)})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "LEGACY_BOOKING_NOT_PAYABLE"

    def test_initiate_payment_blocks_outdated_terms(self, api_client, setup_tc_booking, hotel_profile):
        tc, booking, user = setup_tc_booking
        
        # Create a newer version of T&C, making the old one inactive
        ct = ContentType.objects.get_for_model(hotel_profile)
        TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="2.0",
            content="Updated Terms",
            is_active=True,
            effective_date=date.today()
        )
        
        api_client.force_authenticate(user=user)
        url = reverse('initiate-payment')
        response = api_client.post(url, {"booking_id": str(booking.id)})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "TERMS_UPDATED"
        assert response.data["current_version"] == "2.0"

    @patch('apps.payment.services.requests.post')
    def test_chapa_payload_contains_tc_metadata(self, mock_post, setup_tc_booking):
        tc, booking, user = setup_tc_booking
        
        # Configure mock response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "status": "success",
            "message": "Checkout URL created",
            "data": {"checkout_url": "https://test.chapa.co/pay/xyz"}
        }

        # Call initialize_payment
        result = ChapaPaymentService.initialize_payment(
            booking=booking,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            amount=2000
        )
        
        # Verify payload sent to Chapa
        args, kwargs = mock_post.call_args
        # Chapa service uses data=json.dumps(payload), not json=payload
        import json
        payload = json.loads(kwargs['data'])
        
        assert "meta" in payload
        assert payload["meta"]["tc_version"] == "1.0"
        assert payload["meta"]["booking_id"] == str(booking.id)
        assert "tc_accepted_at" in payload["meta"]

    @override_settings(
        DEBUG=True,
        CHAPA_SANDBOX_SUBACCOUNT_ID="1aa6f01d-d835-48ab-9dd3-946a74715ef6",
        FRONTEND_URL="https://frontend.example/",
    )
    @patch('apps.payment.services.requests.post')
    def test_chapa_payload_uses_sandbox_subaccount_for_seeded_demo_owner(self, mock_post, setup_tc_booking, hotel_profile):
        tc, booking, user = setup_tc_booking
        company = hotel_profile.company
        company.chapa_subaccount_id = "demo-subaccount-company-1"
        company.save(update_fields=["chapa_subaccount_id", "updated_at"])

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "status": "success",
            "message": "Checkout URL created",
            "data": {"checkout_url": "https://test.chapa.co/pay/xyz"}
        }

        result = ChapaPaymentService.initialize_payment(
            booking=booking,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            amount=2000
        )

        import json
        payload = json.loads(mock_post.call_args.kwargs["data"])

        assert result["success"] is True
        assert payload["subaccounts"] == {
            "id": "1aa6f01d-d835-48ab-9dd3-946a74715ef6"
        }
        assert payload["return_url"] == (
            f"https://frontend.example/payments/complete?tx_ref={result['tx_ref']}"
        )

    @override_settings(DEBUG=True, CHAPA_SANDBOX_SUBACCOUNT_ID="1aa6f01d-d835-48ab-9dd3-946a74715ef6")
    @patch('apps.payment.services.requests.post')
    def test_chapa_blocks_checkout_when_sandbox_subaccount_is_rejected(self, mock_post, setup_tc_booking, hotel_profile):
        tc, booking, user = setup_tc_booking
        company = hotel_profile.company
        company.chapa_subaccount_id = "demo-subaccount-company-1"
        company.save(update_fields=["chapa_subaccount_id", "updated_at"])

        rejected = MagicMock()
        rejected.json.return_value = {
            "status": "failed",
            "message": {
                "subaccounts.id": [
                    "The subaccount ID you provided isn't associated with this account."
                ]
            },
            "data": None,
        }
        mock_post.return_value = rejected

        result = ChapaPaymentService.initialize_payment(
            booking=booking,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            amount=2000
        )

        import json
        first_payload = json.loads(mock_post.call_args.kwargs["data"])
        tx = PaymentTransaction.objects.get(tx_ref=result["tx_ref"])

        assert result["success"] is False
        assert result["code"] == "SPLIT_PAYMENT_CONFIGURATION_ERROR"
        assert "checkout_url" not in result
        assert mock_post.call_count == 1
        assert first_payload["subaccounts"]["id"] == "1aa6f01d-d835-48ab-9dd3-946a74715ef6"
        assert tx.status == PaymentTransaction.PaymentStatus.FAILED
        assert tx.payout_status == PaymentTransaction.PayoutStatus.FAILED
        assert "split_error" in tx.metadata

    @patch.object(ChapaPaymentService, "verify_payment")
    def test_pending_chapa_verification_does_not_confirm_booking(self, mock_verify, setup_tc_booking):
        tc, booking, user = setup_tc_booking
        content_type = ContentType.objects.get_for_model(booking)
        tx = PaymentTransaction.objects.create(
            content_type=content_type,
            object_id=booking.id,
            booking_type="booking",
            tx_ref="MICHOT-PENDING-VERIFY",
            amount=booking.total_price,
            currency="ETB",
            status=PaymentTransaction.PaymentStatus.PENDING,
        )
        mock_verify.return_value = {
            "status": "success",
            "data": {
                "status": "pending",
                "amount": str(booking.total_price),
                "currency": "ETB",
            },
        }

        result = ChapaPaymentService.handle_callback({"tx_ref": tx.tx_ref})

        tx.refresh_from_db()
        booking.refresh_from_db()
        assert result["status"] == "pending"
        assert tx.status == PaymentTransaction.PaymentStatus.PENDING
        assert booking.status == Booking.BookingStatus.PENDING
        assert "verification_pending" in tx.metadata

    def test_confirm_booking_integrity_check(self, setup_tc_booking):
        tc, booking, user = setup_tc_booking
        from apps.listing.services import BookingService
        
        # 1. Success case
        BookingService.confirm_booking(booking)
        booking.refresh_from_db()
        assert booking.status == Booking.BookingStatus.CONFIRMED
        
        # 2. Failure case (corrupt snapshot on a new booking)
        booking.status = Booking.BookingStatus.PENDING
        booking.terms_content_snapshot = ""
        booking.save()
        
        from rest_framework.exceptions import ValidationError
        with pytest.raises(ValidationError): # ValidationError from our integrity check
             BookingService.confirm_booking(booking)
