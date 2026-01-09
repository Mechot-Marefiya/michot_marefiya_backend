from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.listing.models import GuestHouseListing, GuestHouseBooking, GuestHouseBookingItem, TermsAndConditions
from apps.account.models import User, Role
from apps.account.enums import RoleCode
from apps.core.models import Address

# Note: Factories might not exist or be named differently, referencing common patterns. 
# Better to create objects manually if factories aren't confirmed.
# I'll create helper methods for setup.

import datetime
from decimal import Decimal

class GuestHouseBookingTests(APITestCase):
    def setUp(self):
        # Create Users
        self.renter_user = User.objects.create_user(
            email="renter@example.com", 
            password="password123",
            first_name="Renter",
            last_name="User"
        )
        
        self.owner_user = User.objects.create_user(
            email="owner@example.com", 
            password="password123",
            first_name="Owner",
            last_name="User"
        )
        
        # Setup Address for Owner
        self.owner_address = Address.objects.create(
            street_line1="123 Owner St",
            city="Addis Ababa",
            sub_city="Bole",
            country="Ethiopia"
        )
        
        # Setup Address for GuestHouse
        self.guesthouse_address = Address.objects.create(
            street_line1="456 Guest St",
            city="Addis Ababa",
            sub_city="Yeka",
            country="Ethiopia"
        )

        # Create GuestHouse Listing
        from apps.listing.models import IndividualOwnerProfile
        self.owner_profile = IndividualOwnerProfile.objects.create(
            first_name="Owner",
            last_name="Person",
            phone="+251911223344",
            address=self.owner_address
        )
        
        self.guesthouse = GuestHouseListing.objects.create(
            title="Cozy GuestHouse",
            description="A nice place",
            individual_owner=self.owner_profile,
            address=self.guesthouse_address,
            total_rooms=5,
            base_price=Decimal("500.00") 
        )

        # Setup Availability
        from apps.listing.services import GuestHouseAvailabilityService
        GuestHouseAvailabilityService.create_availability(self.guesthouse, 5)

        # Setup Terms and Conditions
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.guesthouse)
        self.tc = TermsAndConditions.objects.create(
            content_type=ct,
            object_id=self.guesthouse.id,
            version="1.0",
            title="Terms of Service",
            content="These are the terms and conditions.",
            is_active=True,
            effective_date=datetime.date.today()
        )

    def test_create_booking_success(self):
        self.client.force_authenticate(user=self.renter_user)
        url = reverse('guesthouse-bookings-list') # Standard router name
        
        data = {
            "start_date": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
            "end_date": (datetime.date.today() + datetime.timedelta(days=3)).isoformat(),
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": self.guesthouse.id, 
                    "units_booked": 1,
                    "price_per_unit": 500.00
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        if response.status_code == 400:
            print(f"Error details: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(GuestHouseBooking.objects.count(), 1)
        booking = GuestHouseBooking.objects.first()
        self.assertEqual(booking.renter, self.renter_user)
        self.assertEqual(booking.status, GuestHouseBooking.RentStatus.PENDING)

    def test_list_bookings(self):
        # Create a booking first
        # (Already created objects in setUp don't include a booking)
        # We need a booking for this test
        GuestHouseBooking.objects.create(
            renter=self.renter_user,
            start_date=datetime.date.today() + datetime.timedelta(days=1),
            end_date=datetime.date.today() + datetime.timedelta(days=3),
            total_price=Decimal("1000.00"),
            status=GuestHouseBooking.RentStatus.PENDING,
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Terms..."
        )
        
        self.client.force_authenticate(user=self.renter_user)
        url = reverse('guesthouse-bookings-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check if response data is a list or paginated
        if isinstance(response.data, list):
            self.assertEqual(len(response.data), 1)
        else:
            self.assertEqual(len(response.data['results']), 1) # Pagination enabled

    def test_cancel_booking(self):
        booking = GuestHouseBooking.objects.create(
            renter=self.renter_user,
            start_date=datetime.date.today() + datetime.timedelta(days=1),
            end_date=datetime.date.today() + datetime.timedelta(days=3),
            total_price=Decimal("1000.00"),
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Terms..."
        )
        # Create an item for it
        GuestHouseBookingItem.objects.create(
            booking=booking,
            room=self.guesthouse,
            units_booked=1,
            price_per_unit=Decimal("500.00")
        )
        # Create item to test availability restoration logic (if possible without full setup)
        # For this test, we accept simple cancel status change.
        
        self.client.force_authenticate(user=self.renter_user)
        url = reverse('guesthouse-bookings-cancel', args=[booking.id])
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, GuestHouseBooking.RentStatus.CANCELLED)

    def test_cancel_booking_permission_denied(self):
        booking = GuestHouseBooking.objects.create(
            renter=self.renter_user,
            start_date=datetime.date.today() + datetime.timedelta(days=1),
            end_date=datetime.date.today() + datetime.timedelta(days=3),
            total_price=Decimal("1000.00"),
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Terms..."
        )
        
        other_user = User.objects.create_user(email="other@example.com", password="pw")
        self.client.force_authenticate(user=other_user)
        url = reverse('guesthouse-bookings-cancel', args=[booking.id])
        response = self.client.post(url)
        
        # ViewSet get_queryset filters by user, so it returns 404 if not found
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
