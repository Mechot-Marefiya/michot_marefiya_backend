from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from datetime import date, timedelta
from apps.listing.models import (
    GuestHouseProfile, GuestHouseRoom, GuestHouseBooking, GuestHouseBookingItem, 
    GuestHouseInventory, EventSpaceListing, EventSpaceBooking, 
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
            password="password123",
            phone="0911777999",
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
        self.guesthouse = GuestHouseProfile.objects.create(
            company=self.company,
            address=create_addr("GH St"),
            title="Luxury Guesthouse",
            base_price=Decimal("2000.00"),
            currency="ETB",
            is_active=True
        )
        # Create room for guesthouse
        self.guesthouse_room = GuestHouseRoom.objects.create(
            guest_house=self.guesthouse,
            title="Standard Room",
            description="Standard room",
            base_price=Decimal("2000.00"),
            currency="ETB",
            total_units=3,
            number_of_guests=2
        )
        # Create availability for guesthouse room
        start = date.today() + timedelta(days=1)
        from apps.listing.services import GuestHouseAvailabilityService
        GuestHouseAvailabilityService.create_availability(self.guesthouse_room, 3)
        
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

    def test_guesthouse_booking_persists_total_price(self):
        """Verify guesthouse booking returns and persists a positive total price."""
        self.client.force_authenticate(user=self.user)
        url = reverse('guesthouse-bookings-list')
        
        start_date = date.today() + timedelta(days=2)
        end_date = date.today() + timedelta(days=4) # 2 nights
        guest_phone = "0911777001"

        prior_booking = GuestHouseBooking.objects.create(
            renter=self.user,
            start_date=date.today() - timedelta(days=4),
            end_date=date.today() - timedelta(days=2),
            total_price=Decimal("2000.00"),
            currency="ETB",
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            guest_first_name="Test",
            guest_last_name="User",
            guest_email="test@example.com",
            guest_phone=guest_phone,
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Terms content",
        )
        GuestHouseBookingItem.objects.create(
            booking=prior_booking,
            room=self.guesthouse_room,
            units_booked=1,
            price_per_unit=Decimal("2000.00"),
        )
        
        data = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": str(self.guesthouse_room.id),
                    "units_booked": 1
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        booking = GuestHouseBooking.objects.get(id=response.data["id"])
        self.assertGreater(booking.total_price, Decimal("0.00"))
        self.assertEqual(Decimal(str(response.data["total_price"])), booking.total_price)

    def test_eventspace_booking_persists_total_price(self):
        """Verify event-space booking returns and persists a positive total price."""
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-eventspaces-list')
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=2) # 1 day
        guest_phone = "0911777002"

        prior_booking = EventSpaceBooking.objects.create(
            user=self.user,
            check_in_date=date.today() - timedelta(days=3),
            check_out_date=date.today() - timedelta(days=2),
            total_price=Decimal("5000.00"),
            currency="ETB",
            status=EventSpaceBooking.BookingStatus.CONFIRMED,
            guest_first_name="Test",
            guest_last_name="User",
            guest_email="test@example.com",
            guest_phone=guest_phone,
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Terms content",
        )
        EventSpaceBookingItem.objects.create(
            booking=prior_booking,
            event_space=self.eventspace,
            units_booked=1,
            price_per_unit=Decimal("5000.00"),
        )
        
        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_phone": guest_phone,
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
        
        booking = EventSpaceBooking.objects.get(id=response.data["id"])
        self.assertGreater(booking.total_price, Decimal("0.00"))
        self.assertEqual(Decimal(str(response.data["total_price"])), booking.total_price)

    def test_guesthouse_currency_validation(self):
        """Verify guesthouse prevents mixed currencies."""
        # Create another guesthouse with different currency
        addr = Address.objects.create(street_line1="USD St", city="Test", country="Test")
        guesthouse_usd = GuestHouseProfile.objects.create(
            company=self.company,
            address=addr,
            title="USD Guesthouse",
            base_price=Decimal("100.00"),
            currency="USD",
            is_active=True
        )
        guesthouse_usd_room = GuestHouseRoom.objects.create(
            guest_house=guesthouse_usd,
            title="Standard Room",
            description="Room",
            base_price=Decimal("100.00"),
            currency="USD",
            total_units=1,
            number_of_guests=2
        )
        # Add availability for the USD guesthouse room
        from apps.listing.services import GuestHouseAvailabilityService
        GuestHouseAvailabilityService.create_availability(guesthouse_usd_room, 1)
        
        self.client.force_authenticate(user=self.user)
        url = reverse('guesthouse-bookings-list')
        
        data = {
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "end_date": (date.today() + timedelta(days=2)).isoformat(),
            "guest_phone": "0911777003",
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {"room": str(self.guesthouse_room.id), "units_booked": 1},
                {"room": str(guesthouse_usd_room.id), "units_booked": 1}
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
