from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile, Role, User
from apps.core.models import Address
from apps.listing.models import (
    Booking,
    BookingItem,
    EventSpaceBooking,
    EventSpaceBookingItem,
    EventSpaceListing,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseProfile,
    GuestHouseRoom,
    RoomListing,
)


class GuestBookingPhoneLookupTests(APITestCase):
    def setUp(self):
        self.company_role, _ = Role.objects.get_or_create(
            name="Company",
            code=RoleCode.COMPANY.value,
        )
        self.company_user = User.objects.create_user(
            email="lookup-company@example.com",
            password="pass1234",
            phone="0911555000",
            role=self.company_role,
        )
        self.company_address = Address.objects.create(
            street_line1="Company Street",
            city="Addis Ababa",
            sub_city="Bole",
            country="Ethiopia",
        )
        self.company = CompanyProfile.objects.create(
            user=self.company_user,
            name="Lookup Hospitality PLC",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=self.company_address,
            phone="0911555000",
        )
        self.company_user.company = self.company
        self.company_user.save(update_fields=["company"])

        self.hotel_address = Address.objects.create(
            street_line1="Hotel Street",
            city="Addis Ababa",
            sub_city="Kazanchis",
            country="Ethiopia",
        )
        self.hotel = HotelProfile.objects.create(
            company=self.company,
            name="Lookup Hotel",
            stars=4,
            address=self.hotel_address,
            is_active=True,
        )
        self.room = RoomListing.objects.create(
            hotel=self.hotel,
            address=self.hotel_address,
            title="Lookup Suite",
            base_price=Decimal("1200.00"),
            currency="ETB",
            total_units=4,
            number_of_guests=2,
            room_size_sqm=30,
            bed_type=RoomListing.BedType.QUEEN,
            is_active=True,
        )

        self.owner_address = Address.objects.create(
            street_line1="Owner Street",
            city="Addis Ababa",
            sub_city="CMC",
            country="Ethiopia",
        )
        self.individual_owner = IndividualOwnerProfile.objects.create(
            first_name="Guesthouse",
            last_name="Owner",
            phone="0911666777",
            address=self.owner_address,
        )
        self.guesthouse_address = Address.objects.create(
            street_line1="Guesthouse Street",
            city="Addis Ababa",
            sub_city="Yeka",
            country="Ethiopia",
        )
        self.guesthouse = GuestHouseProfile.objects.create(
            title="Lookup Guesthouse",
            description="Quiet stay",
            individual_owner=self.individual_owner,
            address=self.guesthouse_address,
            base_price=Decimal("700.00"),
            currency="ETB",
            is_active=True,
        )
        self.guesthouse_room = GuestHouseRoom.objects.create(
            guest_house=self.guesthouse,
            title="Guesthouse Standard",
            description="Standard room",
            base_price=Decimal("700.00"),
            currency="ETB",
            total_units=3,
            number_of_guests=2,
        )

        self.event_space_address = Address.objects.create(
            street_line1="Event Street",
            city="Addis Ababa",
            sub_city="Piassa",
            country="Ethiopia",
        )
        self.event_space = EventSpaceListing.objects.create(
            hotel=self.hotel,
            address=self.event_space_address,
            title="Lookup Hall",
            description="Conference hall",
            base_price=Decimal("4500.00"),
            currency="ETB",
            number_of_guests=120,
            total_units=2,
            space_type=EventSpaceListing.SpaceType.CONFERENCE_HALL,
            is_active=True,
        )

        today = date.today()
        self.hotel_booking = Booking.objects.create(
            check_in_date=today + timedelta(days=3),
            check_out_date=today + timedelta(days=5),
            total_price=Decimal("2520.00"),
            currency="ETB",
            status=Booking.BookingStatus.CONFIRMED,
            guest_first_name="Hotel",
            guest_last_name="Guest",
            guest_email="hotel-guest@example.com",
            guest_phone="251911223344",
            terms_accepted=True,
            terms_version="1.0",
        )
        BookingItem.objects.create(
            booking=self.hotel_booking,
            room=self.room,
            units_booked=1,
            price_per_unit=Decimal("1200.00"),
        )

        self.guesthouse_booking = GuestHouseBooking.objects.create(
            start_date=today + timedelta(days=4),
            end_date=today + timedelta(days=6),
            total_price=Decimal("1470.00"),
            currency="ETB",
            status=GuestHouseBooking.RentStatus.CANCELLED,
            guest_first_name="Guesthouse",
            guest_last_name="Guest",
            guest_email="guesthouse-guest@example.com",
            guest_phone="+251922223344",
            terms_accepted=True,
            terms_version="1.0",
        )
        GuestHouseBookingItem.objects.create(
            booking=self.guesthouse_booking,
            room=self.guesthouse_room,
            units_booked=1,
            price_per_unit=Decimal("700.00"),
        )

        self.event_booking = EventSpaceBooking.objects.create(
            check_in_date=today + timedelta(days=5),
            check_out_date=today + timedelta(days=6),
            total_price=Decimal("4725.00"),
            currency="ETB",
            status=EventSpaceBooking.BookingStatus.PENDING,
            event_type=EventSpaceBooking.EventType.CONFERENCE,
            guest_first_name="Event",
            guest_last_name="Guest",
            guest_email="event-guest@example.com",
            guest_phone="0911333444",
            terms_accepted=True,
            terms_version="1.0",
        )
        EventSpaceBookingItem.objects.create(
            booking=self.event_booking,
            event_space=self.event_space,
            units_booked=1,
            price_per_unit=Decimal("4500.00"),
        )

    def test_hotel_lookup_accepts_normalized_guest_phone(self):
        response = self.client.get(
            reverse("bookings-lookup"),
            {
                "reference": self.hotel_booking.booking_reference,
                "guest_phone": "0911223344",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.hotel_booking.id))

    def test_guesthouse_lookup_accepts_normalized_guest_phone_for_cancelled_booking(self):
        response = self.client.get(
            reverse("guesthouse-bookings-lookup"),
            {
                "reference": self.guesthouse_booking.booking_reference,
                "guest_phone": "0922223344",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.guesthouse_booking.id))
        self.assertEqual(response.data["status"], GuestHouseBooking.RentStatus.CANCELLED)

    def test_event_space_lookup_accepts_normalized_guest_phone(self):
        response = self.client.get(
            reverse("bookings-eventspaces-lookup"),
            {
                "reference": self.event_booking.booking_reference,
                "guest_phone": "251911333444",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.event_booking.id))

    def test_lookup_rejects_email_only_for_all_guest_booking_families(self):
        cases = (
            (reverse("bookings-lookup"), self.hotel_booking.booking_reference),
            (reverse("guesthouse-bookings-lookup"), self.guesthouse_booking.booking_reference),
            (reverse("bookings-eventspaces-lookup"), self.event_booking.booking_reference),
        )

        for url, reference in cases:
            response = self.client.get(
                url,
                {
                    "reference": reference,
                    "email": "legacy@example.com",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("guest_phone", response.data)

    def test_lookup_returns_generic_404_for_wrong_phone_pair(self):
        cases = (
            (reverse("bookings-lookup"), self.hotel_booking.booking_reference),
            (reverse("guesthouse-bookings-lookup"), self.guesthouse_booking.booking_reference),
            (reverse("bookings-eventspaces-lookup"), self.event_booking.booking_reference),
        )

        for url, reference in cases:
            response = self.client.get(
                url,
                {
                    "reference": reference,
                    "guest_phone": "0910000000",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(response.data, {"detail": "Not found."})

    def test_lookup_returns_generic_404_for_wrong_reference(self):
        cases = (
            (reverse("bookings-lookup"), "H-NOPE123"),
            (reverse("guesthouse-bookings-lookup"), "G-NOPE123"),
            (reverse("bookings-eventspaces-lookup"), "E-NOPE123"),
        )

        for url, reference in cases:
            response = self.client.get(
                url,
                {
                    "reference": reference,
                    "guest_phone": "0911223344",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(response.data, {"detail": "Not found."})

    def test_lookup_isolated_to_booking_family_endpoint(self):
        response = self.client.get(
            reverse("bookings-lookup"),
            {
                "reference": self.guesthouse_booking.booking_reference,
                "guest_phone": "0922223344",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {"detail": "Not found."})
