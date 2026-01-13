from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from datetime import date, timedelta
from apps.listing.models import (
    GuestHouseListing, GuestHouseBooking, GuestHouseBookingItem, 
    GuestHouseAvailability, EventSpaceListing, EventSpaceBooking, 
    EventSpaceBookingItem, EventSpaceAvailability, TermsAndConditions
)
from apps.account.models import User, HotelProfile, CompanyProfile
from apps.core.models import Address
from django.contrib.contenttypes.models import ContentType


class GuesthouseEventSpacePricingTests(APITestCase):
    """
    Verification tests for Guesthouse and Event Space pricing hardening.
    Verifies 5% platform fee, currency validation, and consistency with hotel pricing.
    """

    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123"
        )
        
        # Helper to create fresh address for each listing
        def create_addr(street):
            return Address.objects.create(
                street_line1=street,
                city="Addis Ababa",
                country="Ethiopia"
            )
        
        # Create company
        self.company = CompanyProfile.objects.create(
            user=self.user,
            name="Test Accommodation Co",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=create_addr("Company St"),
            phone="+251911111111"
        )
        
        # --- Guesthouse Setup ---
        self.guesthouse = GuestHouseListing.objects.create(
            company=self.company,
            address=create_addr("GH St"),
            title="Luxury Guesthouse",
            base_price=Decimal("2000.00"),
            currency="ETB",
            total_rooms=3,
            is_active=True
        )
        # Create availability for guesthouse
        start = date.today() + timedelta(days=1)
        for i in range(10):
            GuestHouseAvailability.objects.create(
                guest_house=self.guesthouse,
                date=start + timedelta(days=i),
                available_rooms=3
            )
        # T&C for Guesthouse
        ct_gh = ContentType.objects.get_for_model(self.guesthouse)
        TermsAndConditions.objects.create(
            content_type=ct_gh,
            object_id=self.guesthouse.id,
            version="1.0",
            title="Guesthouse Terms",
            content="Terms content",
            is_active=True,
            effective_date=date.today()
        )

        # --- Event Space Setup ---
        # Event spaces require a HotelProfile
        self.hotel_profile = HotelProfile.objects.create(company=self.company, stars=4)
        self.eventspace = EventSpaceListing.objects.create(
            hotel=self.hotel_profile,
            address=create_addr("ES St"),
            title="Grand Ballroom",
            base_price=Decimal("5000.00"),
            currency="ETB",
            total_units=1,
            space_type=EventSpaceListing.SpaceType.CONFERENCE_HALL,
            is_active=True
        )
        # Create availability for event space
        for i in range(10):
            EventSpaceAvailability.objects.create(
                space_listing=self.eventspace,
                date=start + timedelta(days=i),
                available_eventspace=1
            )
        # T&C for Event Space (Associated with the HotelProfile it belongs to)
        ct_hotel = ContentType.objects.get_for_model(self.hotel_profile)
        TermsAndConditions.objects.create(
            content_type=ct_hotel,
            object_id=self.hotel_profile.id,
            version="1.0",
            title="Hotel Terms",
            content="Terms content",
            is_active=True,
            effective_date=date.today()
        )

    def test_guesthouse_booking_includes_platform_fee(self):
        """Verify guesthouse booking adds 5% platform fee."""
        self.client.force_authenticate(user=self.user)
        url = reverse('guesthouse-bookings-list')
        
        start_date = date.today() + timedelta(days=2)
        end_date = date.today() + timedelta(days=4) # 2 nights
        
        data = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": str(self.guesthouse.id),
                    "units_booked": 1
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 2 nights * 1 unit * 2000 = 4000
        # 4000 * 1.05 = 4200
        booking = GuestHouseBooking.objects.first()
        self.assertEqual(booking.total_price, Decimal('4200.00'))

    def test_eventspace_booking_includes_platform_fee(self):
        """Verify eventspace booking adds 5% platform fee."""
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-eventspaces-list')
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=2) # 1 day
        
        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "event_space": str(self.eventspace.id),
                    "units_booked": 1
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 1 day * 1 unit * 5000 = 5000
        # 5000 * 1.05 = 5250
        booking = EventSpaceBooking.objects.first()
        self.assertEqual(booking.total_price, Decimal('5250.00'))

    def test_guesthouse_currency_validation(self):
        """Verify guesthouse prevents mixed currencies."""
        # Create another guesthouse with different currency
        addr = Address.objects.create(street_line1="USD St", city="Test", country="Test")
        guesthouse_usd = GuestHouseListing.objects.create(
            company=self.company,
            address=addr,
            title="USD Guesthouse",
            base_price=Decimal("100.00"),
            currency="USD",
            total_rooms=1,
            is_active=True
        )
        # Add availability for the USD guesthouse to avoid conflict before currency check
        for i in range(10):
             GuestHouseAvailability.objects.create(
                guest_house=guesthouse_usd,
                date=date.today() + timedelta(days=1+i),
                available_rooms=1
            )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('guesthouse-bookings-list')
        
        data = {
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "end_date": (date.today() + timedelta(days=2)).isoformat(),
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {"room": str(self.guesthouse.id), "units_booked": 1},
                {"room": str(guesthouse_usd.id), "units_booked": 1}
            ]
        }
        
        response = self.client.post(url, data, format='json')
        # Currency validation should return 400 Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("items", response.data)
        self.assertIn("same currency", str(response.data["items"]))

    def test_eventspace_legacy_hydration(self):
        """Verify EventSpace detail hydrates legacy fields from price_quote."""
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=2)
        
        url = reverse('event-spaces-detail', args=[self.eventspace.id])
        url_with_params = f"{url}?check_in={check_in.isoformat()}&check_out={check_out.isoformat()}"
        
        response = self.client.get(url_with_params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check for hydrated legacy fields
        self.assertIn('display_price', response.data)
        self.assertIn('preview_total', response.data)
        self.assertIn('price_quote', response.data)
        
        quote = response.data['price_quote']
        self.assertIsNotNone(quote, "Price quote should not be None")
        self.assertEqual(Decimal(str(response.data['preview_total'])), Decimal(quote['base_total']))
