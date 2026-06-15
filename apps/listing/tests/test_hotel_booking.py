from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from datetime import date, timedelta
from apps.listing.models import (
    RoomListing, Booking, BookingItem, StayAvailability,
    RoomInventory, Season, SeasonalRate, TermsAndConditions
)
from apps.listing.services import StayAvailabilityService, PriceService
from apps.account.models import User, HotelProfile, CompanyProfile
from apps.core.models import Address
from django.contrib.contenttypes.models import ContentType


class HotelBookingAPITests(APITestCase):
    """
    API-based test suite for hotel/room booking functionality.
    Tests platform fee, overbooking prevention, seasonal pricing, and currency handling.
    Follows Django REST framework best practices by testing through HTTP endpoints.
    """
    
    def setUp(self):
        """Create test data used across multiple tests"""
        # Create test user
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123",
            first_name="Test",
            last_name="User",
            phone="0911222333",
        )
        
        # Create address
        self.address = Address.objects.create(
            street_line1="Test St",
            city="Addis Ababa",
            sub_city="Bole",
            country="Ethiopia"
        )
        
        # Create company
        self.company = CompanyProfile.objects.create(
            user=self.user,
            name="Test Hotel Company",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=self.address,
            phone="+251911111111"
        )
        
        # Create hotel
        self.hotel = HotelProfile.objects.create(
            company=self.company,
            stars=5,
            featured=True
        )
        
        # Create room listing
        self.room = RoomListing.objects.create(
            hotel=self.hotel,
            address=self.address,
            title="Deluxe Suite",
            base_price=Decimal("1000.00"),
            currency="ETB",
            total_units=5,
            number_of_guests=2,
            room_size_sqm=50,
            bed_type=RoomListing.BedType.KING,
            is_active=True
        )
        
        # Create availability for next 30 days
        start = date.today() + timedelta(days=1)
        self.create_availability_range(self.room, start, 30)
        
        # Create Terms & Conditions
        ct = ContentType.objects.get_for_model(self.hotel)
        self.tc = TermsAndConditions.objects.create(
            content_type=ct,
            object_id=self.hotel.id,
            version="1.0",
            title="Terms of Service",
            content="These are the terms and conditions.",
            is_active=True,
            effective_date=date.today()
        )
    
    def create_availability_range(self, room, start_date, days):
        """Helper to create availability records"""
        objs = []
        for i in range(days):
            objs.append(
                StayAvailability(
                    hotel=room.hotel,
                    room=room,
                    date=start_date + timedelta(days=i),
                    available_rooms=room.total_units
                )
            )
        StayAvailability.objects.bulk_create(objs, ignore_conflicts=True)
    
    def test_booking_includes_platform_fee(self):
        """
        CRITICAL TEST: Verify that booking total includes 5% platform fee.
        This ensures price parity with previews.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-list')
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=3)
        guest_phone = "0911222333"

        prior_booking = Booking.objects.create(
            user=self.user,
            check_in_date=check_in - timedelta(days=4),
            check_out_date=check_in - timedelta(days=3),
            guest_first_name="Test",
            guest_last_name="User",
            guest_email="test@example.com",
            guest_phone=guest_phone,
            total_price=Decimal("1000.00"),
            currency="ETB",
            status=Booking.BookingStatus.CONFIRMED,
            terms_accepted=True,
            terms_version="1.0",
        )
        BookingItem.objects.create(
            booking=prior_booking,
            room=self.room,
            units_booked=1,
            price_per_unit=Decimal("1000.00"),
        )

        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_phone": guest_phone,
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": str(self.room.id),
                    "units_booked": 1
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Error: {response.data}")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 2 nights * 1000 ETB = 2000 ETB
        # 2000 * 1.05 (5% fee) = 2100 ETB
        booking = Booking.objects.get(id=response.data["id"])
        expected_total = Decimal('2100.00')
        
        self.assertEqual(booking.total_price, expected_total)
        self.assertEqual(booking.status, Booking.BookingStatus.PENDING)
    
    def test_booking_prevents_overbooking(self):
        """
        CRITICAL TEST: Verify that concurrent bookings cannot exceed availability.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-list')
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=2)
        
        # Book all 5 available rooms
        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_phone": "0911222333",
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": str(self.room.id),
                    "units_booked": 5
                }
            ]
        }
        
        response1 = self.client.post(url, data, format='json')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        
        # Try to book 1 more room (should fail)
        data["items"][0]["units_booked"] = 1
        response2 = self.client.post(url, data, format='json')
        
        self.assertEqual(response2.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Not enough rooms available", str(response2.data))
    
    def test_cancel_restores_availability(self):
        """
        CRITICAL TEST: Verify cancellation restores room availability.
        """
        self.client.force_authenticate(user=self.user)
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=2)
        
        # Check initial availability
        initial_avail = StayAvailability.objects.get(
            hotel=self.hotel,
            room=self.room,
            date=check_in
        )
        initial_count = initial_avail.available_rooms
        
        # Create booking
        url = reverse('bookings-list')
        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guest_phone": "0911222333",
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": str(self.room.id),
                    "units_booked": 2
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        booking = Booking.objects.get(id=response.data["id"])
        
        # Verify availability decreased
        after_booking = StayAvailability.objects.get(
            hotel=self.hotel,
            room=self.room,
            date=check_in
        )
        self.assertEqual(after_booking.available_rooms, initial_count - 2)
        
        # Cancel booking
        cancel_url = reverse('bookings-cancel', args=[booking.id])
        cancel_response = self.client.post(cancel_url)
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        
        # Verify availability restored
        after_cancel = StayAvailability.objects.get(
            hotel=self.hotel,
            room=self.room,
            date=check_in
        )
        self.assertEqual(after_cancel.available_rooms, initial_count)
        
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.BookingStatus.CANCELLED)
    
    def test_price_quote_in_room_detail(self):
        """
        TEST: Verify new price_quote field appears in room detail when dates provided.
        """
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=3)
        
        url = reverse('rooms-detail', args=[self.room.id])
        url_with_params = f"{url}?check_in={check_in.isoformat()}&check_out={check_out.isoformat()}&units=1"
        
        response = self.client.get(url_with_params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify price_quote field exists
        self.assertIn('price_quote', response.data)
        
        price_quote = response.data['price_quote']
        
        # Verify structure
        self.assertIn('subtotal', price_quote)
        self.assertIn('platform_fee', price_quote)
        self.assertIn('total', price_quote)
        self.assertIn('daily_breakdown', price_quote)
        
        # Verify platform fee is 5%
        subtotal = Decimal(price_quote['subtotal'])
        platform_fee = Decimal(price_quote['platform_fee'])
        expected_fee = subtotal * Decimal('0.05')
        
        self.assertEqual(platform_fee, expected_fee)
    
    def test_price_quote_not_in_response_without_dates(self):
        """
        TEST: Verify price_quote field is NOT included when dates are not provided.
        """
        url = reverse('rooms-detail', args=[self.room.id])
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # price_quote should not be in response when dates not provided
        self.assertNotIn('price_quote', response.data)


class PriceServiceUnitTests(APITestCase):
    """
    Unit tests for PriceService batch optimization.
    These test the service layer directly (not through HTTP).
    """
    
    def setUp(self):
        """Create minimal test data"""
        self.address = Address.objects.create(
            street_line1="Test",
            city="Test City",
            country="Test Country"
        )
        
        # Create test user for company
        self.company_user = User.objects.create_user(
            email="company@example.com",
            password="password123"
        )
        
        self.company = CompanyProfile.objects.create(
            user=self.company_user,
            name="Test Company",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=self.address,
            phone="+1234567890"
        )
        
        self.hotel = HotelProfile.objects.create(
            company=self.company,
            stars=4
        )
        
        self.room = RoomListing.objects.create(
            hotel=self.hotel,
            address=self.address,
            title="Test Room",
            base_price=Decimal("100.00"),
            currency="USD",
            total_units=10,
            number_of_guests=2,
            room_size_sqm=30,
            is_active=True
        )
    
    def test_batch_method_exists(self):
        """Verify batch method is available"""
        self.assertTrue(
            hasattr(PriceService, 'resolve_price_details_batch'),
            "PriceService should have resolve_price_details_batch method"
        )
    
    def test_batch_returns_correct_count(self):
        """Verify batch method returns correct number of results"""
        start = date.today()
        end = start + timedelta(days=14)
        
        results = PriceService.resolve_price_details_batch(self.room, start, end)
        
        self.assertEqual(len(results), 14, "Should return 14 days of pricing")
    
    def test_batch_includes_date_field(self):
        """Verify each result includes the date"""
        start = date.today()
        end = start + timedelta(days=3)
        
        results = PriceService.resolve_price_details_batch(self.room, start, end)
        
        for result in results:
            self.assertIn('date', result)
            self.assertIsInstance(result['date'], date)
    
    def test_batch_matches_individual_resolution(self):
        """
        TEST: Verify batch method returns same results as individual resolution.
        This validates the performance optimization doesn't change behavior.
        """
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=5)
        
        # Get prices using batch method
        batch_results = PriceService.resolve_price_details_batch(
            self.room, check_in, check_out
        )
        
        # Get prices using individual method
        individual_results = []
        cursor = check_in
        while cursor < check_out:
            detail = PriceService.resolve_price_detail(self.room, cursor)
            detail['date'] = cursor
            individual_results.append(detail)
            cursor += timedelta(days=1)
        
        # Compare results
        self.assertEqual(len(batch_results), len(individual_results))
        
        for batch_item, individual_item in zip(batch_results, individual_results):
            self.assertEqual(batch_item['date'], individual_item['date'])
            self.assertEqual(batch_item['price'], individual_item['price'])
            self.assertEqual(batch_item['source'], individual_item['source'])
    
    def test_inventory_override_priority(self):
        """
        TEST: Verify RoomInventory overrides take precedence over seasonal rates.
        """
        check_in = date.today() + timedelta(days=1)
        
        # Create both seasonal rate and inventory override
        season = Season.objects.create(
            name="High Season",
            start_date=check_in,
            end_date=check_in + timedelta(days=7),
            active=True
        )
        
        SeasonalRate.objects.create(
            season=season,
            room=self.room,
            price_override=Decimal('150.00'),
            active=True
        )
        
        RoomInventory.objects.create(
            room_listing=self.room,
            date=check_in,
            price=Decimal('80.00')
        )
        
        # Test price resolution
        detail = PriceService.resolve_price_detail(self.room, check_in)
        
        # Inventory (80) should win over seasonal (150)
        self.assertEqual(detail['price'], Decimal('80.00'))
        self.assertEqual(detail['source'], 'inventory')
