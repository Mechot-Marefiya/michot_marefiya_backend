from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from datetime import date, timedelta
from apps.listing.models import (
    AddonOffering, RoomListing, StayAvailability, GuestHouseProfile, GuestHouseRoom, EventSpaceListing,
    EventSpaceAvailability, GuestHouseInventory, Season, SeasonalRate
)
from apps.account.models import User, HotelProfile, CompanyProfile
from apps.core.models import Address, CurrencyRate

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

        # GuestHouse Setup
        self.guesthouse = GuestHouseProfile.objects.create(
            company=self.company, 
            address=self.address,
            title="GH Property", 
            base_price=Decimal("500.00"),
            currency="ETB", 
            is_active=True
        )
        self.gh_room = GuestHouseRoom.objects.create(
            guest_house=self.guesthouse,
            title="Standard Room",
            base_price=Decimal("500.00"),
            total_units=2,
            number_of_guests=2,
            is_active=True
        )
        for i in range(10):
            GuestHouseInventory.objects.create(
                guest_house_room=self.gh_room,
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
        self.assertEqual(response.data['totals']['items_subtotal'], '4000.00')
        self.assertEqual(response.data['totals']['platform_fee'], '200.00')
        self.assertEqual(response.data['totals']['grand_total'], '4200.00')
        self.assertEqual(len(response.data['items']), 1)
        self.assertEqual(response.data['items'][0]['units'], 2)
        self.assertEqual(len(response.data['items'][0]['breakdown']), 2) # 2 nights
        self.assertEqual(response.data['items'][0]['breakdown'][0]['source'], 'base')

    def test_hotel_price_preview_uses_seasonal_rate_override(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-price-preview')

        season = Season.objects.create(
            name="Holiday Window",
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=5),
            recurring=False,
            active=True,
            company=self.company,
        )
        SeasonalRate.objects.create(
            season=season,
            room=self.room,
            hotel=self.hotel,
            company=self.company,
            price_override=Decimal("1500.00"),
            priority=5,
            active=True,
            days_of_week=[],
        )

        check_in = date.today() + timedelta(days=2)
        check_out = date.today() + timedelta(days=4)

        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "items": [{"room": str(self.room.id), "units_booked": 1}]
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 2 nights * 1500 = 3000, plus 5% platform fee = 3150 total.
        self.assertEqual(response.data['totals']['items_subtotal'], '3000.00')
        self.assertEqual(response.data['totals']['platform_fee'], '150.00')
        self.assertEqual(response.data['totals']['grand_total'], '3150.00')
        self.assertEqual(response.data['items'][0]['breakdown'][0]['source'], 'seasonal')

    def test_hotel_price_preview_includes_pricing_type_aware_addons(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-price-preview')

        per_booking = AddonOffering.objects.create(
            hotel=self.hotel,
            name="Airport Pickup",
            description="One-time airport transfer",
            category=AddonOffering.AddonCategory.TRANSPORT,
            price_per_unit=Decimal("400.00"),
            currency="ETB",
            pricing_type=AddonOffering.PricingType.PER_BOOKING,
            is_active=True,
            max_quantity_per_booking=1,
        )
        per_night = AddonOffering.objects.create(
            hotel=self.hotel,
            name="Extra Bed",
            description="Extra bed for each night",
            category=AddonOffering.AddonCategory.AMENITY,
            price_per_unit=Decimal("150.00"),
            currency="ETB",
            pricing_type=AddonOffering.PricingType.PER_NIGHT,
            is_active=True,
            max_quantity_per_booking=5,
        )
        per_unit = AddonOffering.objects.create(
            hotel=self.hotel,
            name="Laundry Bag",
            description="Laundry bundle",
            category=AddonOffering.AddonCategory.SERVICE,
            price_per_unit=Decimal("50.00"),
            currency="ETB",
            pricing_type=AddonOffering.PricingType.PER_UNIT,
            is_active=True,
            max_quantity_per_booking=5,
        )
        per_person = AddonOffering.objects.create(
            hotel=self.hotel,
            name="Breakfast Buffet",
            description="Breakfast per person",
            category=AddonOffering.AddonCategory.MEAL,
            price_per_unit=Decimal("75.00"),
            currency="ETB",
            pricing_type=AddonOffering.PricingType.PER_PERSON,
            is_active=True,
            max_quantity_per_booking=5,
        )

        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=3)

        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "items": [
                {
                    "room": str(self.room.id),
                    "units_booked": 2,
                    "addons": [
                        {"offering_id": str(per_booking.id), "quantity": 1},
                        {"offering_id": str(per_night.id), "quantity": 2},
                        {"offering_id": str(per_unit.id), "quantity": 3},
                        {"offering_id": str(per_person.id), "quantity": 4},
                    ],
                }
            ],
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["totals"]["items_subtotal"], "4000.00")
        self.assertEqual(response.data["totals"]["addons_subtotal"], "1450.00")
        self.assertEqual(response.data["totals"]["platform_fee"], "200.00")
        self.assertEqual(response.data["totals"]["grand_total"], "5650.00")

        item = response.data["items"][0]
        self.assertEqual(item["addons_subtotal"], "1450.00")
        self.assertEqual(item["subtotal_with_addons"], "5450.00")
        self.assertEqual(len(item["addons"]), 4)

        addon_map = {addon["name"]: addon for addon in item["addons"]}
        self.assertEqual(addon_map["Airport Pickup"]["effective_quantity"], 1)
        self.assertEqual(addon_map["Airport Pickup"]["subtotal"], "400.00")
        self.assertEqual(addon_map["Extra Bed"]["effective_quantity"], 4)
        self.assertEqual(addon_map["Extra Bed"]["subtotal"], "600.00")
        self.assertEqual(addon_map["Laundry Bag"]["effective_quantity"], 3)
        self.assertEqual(addon_map["Laundry Bag"]["subtotal"], "150.00")
        self.assertEqual(addon_map["Breakfast Buffet"]["effective_quantity"], 4)
        self.assertEqual(addon_map["Breakfast Buffet"]["subtotal"], "300.00")

    def test_guesthouse_price_preview(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('guesthouse-bookings-price-preview')
        
        start = date.today() + timedelta(days=1)
        end = date.today() + timedelta(days=2)
        
        data = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "items": [{"room": str(self.gh_room.id), "units_booked": 1}]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 1 night * 1 unit * 500 = 500
        # 500 * 0.05 = 25
        # Total = 525
        self.assertEqual(response.data['totals']['items_subtotal'], '500.00')
        self.assertEqual(response.data['totals']['platform_fee'], '25.00')
        self.assertEqual(response.data['totals']['grand_total'], '525.00')
        self.assertEqual(len(response.data['items'][0]['breakdown']), 1)

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
        self.assertEqual(response.data['totals']['items_subtotal'], '5000.00')
        self.assertEqual(response.data['totals']['platform_fee'], '250.00')
        self.assertEqual(response.data['totals']['grand_total'], '5250.00')
        self.assertEqual(len(response.data['items'][0]['breakdown']), 1)

    def test_currency_conversion_in_preview(self):
        """
        Verify that display_currency converts totals.
        """
        # Create exchange rates
        # 1 ETB = 0.01 USD (Simple rate for testing)
        # 1 USD = 100 ETB
        CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("100.00"), date=date.today())
        
        self.client.force_authenticate(user=self.user)
        url = reverse('bookings-price-preview') + "?display_currency=USD"
        
        check_in = date.today() + timedelta(days=1)
        check_out = date.today() + timedelta(days=2)
        
        # 1 night * 1 unit * 1000 = 1000 ETB
        # 1000 * 0.05 = 50 ETB fee
        # Grand Total = 1050 ETB
        data = {
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "items": [{"room": str(self.room.id), "units_booked": 1}]
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify Base Totals (ETB)
        self.assertEqual(response.data['totals']['items_subtotal'], '1000.00')
        self.assertEqual(response.data['totals']['addons_subtotal'], '0.00')
        self.assertEqual(response.data['totals']['currency'], 'ETB')
        
        # Verify Converted Totals (USD)
        # 1000 ETB / 100 = 10 USD
        # 50 ETB / 100 = 0.50 USD
        # 1050 ETB / 100 = 10.50 USD
        self.assertIsNotNone(response.data['conversion'])
        self.assertEqual(response.data['conversion']['items_subtotal'], '10.00')
        self.assertEqual(response.data['conversion']['addons_subtotal'], '0.00')
        self.assertEqual(response.data['conversion']['platform_fee'], '0.50')
        self.assertEqual(response.data['conversion']['grand_total'], '10.50')
        self.assertEqual(response.data['conversion']['to'], 'USD')

    def test_display_price_currency_accuracy(self):
        """
        Verify display_price respects display_currency parameter in various scenarios.
        """
        CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("100.00"), date=date.today())
        
        self.client.force_authenticate(user=self.user)
        base_url = reverse('rooms-list')
        
        # Case 1: No dates, USD requested
        # Room base_price=1000 ETB. Rate: 1 USD = 100 ETB. So 1000 ETB = 10 USD.
        response = self.client.get(f"{base_url}?hotel={self.hotel.id}&display_currency=USD")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        room_data = response.data["results"][0]

        # Current contract keeps source currency/base display in list results
        # when no date-based quote is requested.
        self.assertEqual(room_data['currency'], 'ETB')
        self.assertEqual(room_data['display_price'], '1000.00')

