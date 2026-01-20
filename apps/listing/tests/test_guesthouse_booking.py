from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.listing.models import GuestHouseProfile, GuestHouseRoom, GuestHouseBooking, GuestHouseBookingItem, TermsAndConditions
from apps.account.models import User, IndividualOwnerProfile
from apps.core.models import Address

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

        # Create Owner Profile
        self.owner_profile = IndividualOwnerProfile.objects.create(
            first_name="Owner",
            last_name="Person",
            phone="+251911223344",
            address=self.owner_address
        )
        
        # Create GuestHouse Profile
        self.guesthouse = GuestHouseProfile.objects.create(
            title="Cozy GuestHouse",
            description="A nice place",
            individual_owner=self.owner_profile,
            address=self.guesthouse_address,
            base_price=Decimal("500.00"),
            currency="ETB"
        )

        # Create GuestHouse Room (the new bookable unit)
        self.standard_room = GuestHouseRoom.objects.create(
            guest_house=self.guesthouse,
            title="Standard Room",
            description="Comfortable standard room",
            base_price=Decimal("500.00"),
            currency="ETB",
            total_units=5,
            number_of_guests=2
        )

        # Setup Availability for the room
        from apps.listing.services import GuestHouseAvailabilityService
        GuestHouseAvailabilityService.create_availability(self.standard_room, 5)

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
        url = reverse('guesthouse-bookings-list')
        
        data = {
            "start_date": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
            "end_date": (datetime.date.today() + datetime.timedelta(days=3)).isoformat(),
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": self.standard_room.id,  # Now references GuestHouseRoom
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
        booking = GuestHouseBooking.objects.create(
            renter=self.renter_user,
            start_date=datetime.date.today() + datetime.timedelta(days=1),
            end_date=datetime.date.today() + datetime.timedelta(days=3),
            total_price=Decimal("1000.00"),
            status=GuestHouseBooking.RentStatus.PENDING,
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Terms..."
        )
        GuestHouseBookingItem.objects.create(
            booking=booking,
            room=self.standard_room,  # Now references GuestHouseRoom
            units_booked=1,
            price_per_unit=Decimal("500.00")
        )
        
        self.client.force_authenticate(user=self.renter_user)
        url = reverse('guesthouse-bookings-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check if response data is a list or paginated
        if isinstance(response.data, list):
            self.assertEqual(len(response.data), 1)
        else:
            self.assertEqual(len(response.data['results']), 1)

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
            room=self.standard_room,  # Now references GuestHouseRoom
            units_booked=1,
            price_per_unit=Decimal("500.00")
        )
        
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

    def test_booking_with_multiple_room_types(self):
        """Test booking multiple room types in same guesthouse"""
        # Create a deluxe room
        deluxe_room = GuestHouseRoom.objects.create(
            guest_house=self.guesthouse,
            title="Deluxe Room",
            description="Luxury deluxe room",
            base_price=Decimal("800.00"),
            currency="ETB",
            total_units=3,
            number_of_guests=2
        )
        
        from apps.listing.services import GuestHouseAvailabilityService
        GuestHouseAvailabilityService.create_availability(deluxe_room, 3)
        
        self.client.force_authenticate(user=self.renter_user)
        url = reverse('guesthouse-bookings-list')
        
        data = {
            "start_date": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
            "end_date": (datetime.date.today() + datetime.timedelta(days=3)).isoformat(),
            "terms_accepted": True,
            "terms_version": "1.0",
            "items": [
                {
                    "room": self.standard_room.id,
                    "units_booked": 2,
                    "price_per_unit": 500.00
                },
                {
                    "room": deluxe_room.id,
                    "units_booked": 1,
                    "price_per_unit": 800.00
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        if response.status_code != 201:
            print(f"Error: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        booking = GuestHouseBooking.objects.first()
        self.assertEqual(booking.items.count(), 2)

    def test_availability_check_per_room_type(self):
        """Test that availability is tracked per room type, not per guesthouse"""
        from apps.listing.services import GuestHouseAvailabilityService
        from apps.listing.models import GuestHouseInventory
        
        # Book all standard rooms
        start_date = datetime.date.today() + datetime.timedelta(days=1)
        end_date = datetime.date.today() + datetime.timedelta(days=3)
        
        room_infos = [{
            "guesthouse_room": self.standard_room,
            "quantity": 5  # All 5 units
        }]
        
        GuestHouseAvailabilityService.update_availability(
            room_infos, start_date, end_date, increment=False
        )
        
        # Verify that standard room's inventory is depleted
        inventory = GuestHouseInventory.objects.filter(
            guest_house_room=self.standard_room,
            date=start_date
        ).first()
        self.assertIsNotNone(inventory)
        self.assertEqual(inventory.available_rooms, 0)
        
        # But a new deluxe room should still have full availability
        deluxe_room = GuestHouseRoom.objects.create(
            guest_house=self.guesthouse,
            title="Deluxe Room",
            description="Luxury room",
            base_price=Decimal("800.00"),
            currency="ETB",
            total_units=2,
            number_of_guests=2
        )
        GuestHouseAvailabilityService.create_availability(deluxe_room, 2)
        
        deluxe_inventory = GuestHouseInventory.objects.filter(
            guest_house_room=deluxe_room,
            date=start_date
        ).first()
        self.assertIsNotNone(deluxe_inventory)
        self.assertEqual(deluxe_inventory.available_rooms, 2)
