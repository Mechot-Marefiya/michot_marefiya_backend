from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from datetime import date, timedelta
from apps.listing.models import (
    RoomListing, StayAvailability, GuestHouseListing, EventSpaceListing,
    EventSpaceAvailability, GuestHouseAvailability
)
from apps.account.models import User, HotelProfile, CompanyProfile
from apps.core.models import Address

class PricePreviewAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123"
        )
        self.address = Address.objects.create(
            street_line1="Test St", city="Addis Ababa", country="Ethiopia"
        )
        self.company = CompanyProfile.objects.create(
            user=self.user, name="Test Company",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=self.address, phone="+251911111111"
        )
        self.hotel = HotelProfile.objects.create(company=self.company, stars=5)

        # Hotel Room
        self.room = RoomListing.objects.create(
            hotel=self.hotel, 
            address=self.address,
            title="Deluxe Room", 
            base_price=Decimal("1000.00"),
            currency="ETB", 
            total_units=5, 
            room_size_sqm=30,
            is_active=True
        )
        for i in range(10):
            StayAvailability.objects.create(
                hotel=self.hotel, room=self.room,
                date=date.today() + timedelta(days=i+1),
                available_rooms=5
            )

        # GuestHouse Room
        self.guesthouse = GuestHouseListing.objects.create(
            company=self.company, 
            address=self.address,
            title="GH Room", 
            base_price=Decimal("500.00"),
            currency="ETB", 
            total_rooms=2, 
            is_active=True
        )
        for i in range(10):
            GuestHouseAvailability.objects.create(
                guest_house=self.guesthouse,
                date=date.today() + timedelta(days=i+1),
                available_rooms=2
            )

        # Event Space
        self.eventspace = EventSpaceListing.objects.create(
            hotel=self.hotel, 
            address=self.address,
            title="Grand Hall", 
            base_price=Decimal("5000.00"),
            currency="ETB", 
            total_units=1, 
            space_type="conference_hall",
            is_active=True
        )
        for i in range(10):
            EventSpaceAvailability.objects.create(
                space_listing=self.eventspace,
                date=date.today() + timedelta(days=i+1),
                available_eventspace=1
            )

    def test_hotel_price_preview(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-price-preview')
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=3)
        
        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "items": [{"room": str(self.room.id), "units_booked": 2}]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 2 nights * 2 units * 1000 = 4000
        # 4000 * 0.05 = 200
        # Total = 4200
        self.assertEqual(response.data['totals']['rooms_subtotal'], '4000.00')
        self.assertEqual(response.data['totals']['platform_fee'], '200.00')
        self.assertEqual(response.data['totals']['grand_total'], '4200.00')
        self.assertEqual(len(response.data['items']), 1)
        self.assertEqual(response.data['items'][0]['units'], 2)

    def test_guesthouse_price_preview(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('guesthouse-bookings-price-preview')
        
        start = date.today() + timedelta(days=1)
        end = date.today() + timedelta(days=2)
        
        data = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "items": [{"room": str(self.guesthouse.id), "units_booked": 1}]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 1 night * 1 unit * 500 = 500
        # 500 * 0.05 = 25
        # Total = 525
        self.assertEqual(response.data['totals']['rooms_subtotal'], '500.00')
        self.assertEqual(response.data['totals']['platform_fee'], '25.00')
        self.assertEqual(response.data['totals']['grand_total'], '525.00')

    def test_eventspace_price_preview(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-eventspaces-price-preview')
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=2)
        
        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "items": [{"event_space": str(self.eventspace.id), "units_booked": 1}]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 1 night * 1 unit * 5000 = 5000
        # 5000 * 0.05 = 250
        # Total = 5250
        self.assertEqual(response.data['totals']['rooms_subtotal'], '5000.00')
        self.assertEqual(response.data['totals']['platform_fee'], '250.00')
        self.assertEqual(response.data['totals']['grand_total'], '5250.00')
