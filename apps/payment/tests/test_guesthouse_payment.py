from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from datetime import date, timedelta
from django.utils import timezone
from decimal import Decimal

from apps.account.models import User, Role
from apps.account.enums import RoleCode
from apps.listing.models import GuestHouseBooking, GuestHouseBookingItem, TermsAndConditions, GuestHouseProfile, GuestHouseRoom
from apps.listing.services import GuestHouseAvailabilityService
from apps.payment.models import PaymentTransaction
from apps.core.models import Address
from apps.account.models import IndividualOwnerProfile
from django.contrib.contenttypes.models import ContentType

class GuestHousePaymentTests(APITestCase):
    def setUp(self):
        # Create Users
        self.renter_user = User.objects.create_user(
            email="renter_pay@example.com", 
            password="password123",
            first_name="Renter",
            last_name="Pay"
        )
        
        self.owner_user = User.objects.create_user(
            email="owner_pay@example.com", 
            password="password123",
            first_name="Owner",
            last_name="Pay"
        )
        
        # Setup Address
        self.address = Address.objects.create(
            street_line1="123 Pay St",
            city="Addis Ababa",
            country="Ethiopia"
        )
        
        # Owner Profile
        self.owner_profile = IndividualOwnerProfile.objects.create(
            first_name="Owner",
            last_name="Person",
            phone="+251911223355",
            address=self.address
        )

        # Guesthouse Profile
        self.gh_profile = GuestHouseProfile.objects.create(
            title="Payment Enabled GH",
            individual_owner=self.owner_profile,
            address=Address.objects.create(street_line1="GH Addr", city="Addis"),
            phone="+251911223399"
        )

        # Guesthouse Room
        self.gh_room = GuestHouseRoom.objects.create(
            guest_house=self.gh_profile,
            title="Standard Room",
            base_price=Decimal("1000.00"),
            total_units=5,
            bed_type=GuestHouseRoom.BedType.DOUBLE
        )
        
        GuestHouseAvailabilityService.create_availability(self.gh_room, 5)
        
        # T&C
        ct = ContentType.objects.get_for_model(self.gh_profile)
        TermsAndConditions.objects.create(
            content_type=ct,
            object_id=self.gh_profile.id,
            version="1.0",
            content="Terms",
            is_active=True,
            effective_date=date.today()
        )

        # Create Booking
        self.booking = GuestHouseBooking.objects.create(
            renter=self.renter_user,
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=3),
            total_price=Decimal("2000.00"),
            terms_accepted=True,
            terms_version="1.0",
            terms_accepted_at=timezone.now(),
            terms_content_snapshot="Terms content"
        )
        
        GuestHouseBookingItem.objects.create(
            booking=self.booking,
            room=self.gh_room,
            units_booked=1,
            price_per_unit=Decimal("1000.00")
        )

    @patch('apps.payment.services.requests.post')
    def test_initiate_payment_guesthouse(self, mock_post):
        # Mock Chapa API response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "status": "success",
            "data": {"checkout_url": "https://test.chapa.co/pay/xyz"}
        }
        
        self.client.force_authenticate(user=self.renter_user)
        url = reverse('initiate-payment')
        
        data = {
            "booking_id": str(self.booking.id),
            "booking_type": "guesthouse"
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("success"))
        
        # Verify transaction created
        tx_ref = response.data.get("tx_ref")
        tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
        self.assertEqual(tx.content_type.model, "guesthousebooking")
        self.assertEqual(str(tx.object_id), str(self.booking.id))

