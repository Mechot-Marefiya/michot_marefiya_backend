from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, HotelProfile, Role, User
from apps.core.models import Address
from apps.listing.models import (
    Booking,
    BookingItem,
    EventSpaceBooking,
    EventSpaceBookingItem,
    EventSpaceListing,
    RoomListing,
    TermsAndConditions,
)


class EventSpacePaymentTermsTests(APITestCase):
    def setUp(self):
        self.user_role = Role.objects.get_or_create(name="User", code=RoleCode.USER.value)[0]
        self.booker = User.objects.create_user(
            email="event-booker@example.com",
            password="pass1234",
            phone="+251911000101",
            role=self.user_role,
            first_name="Event",
            last_name="Booker",
        )

        company_user = User.objects.create_user(
            email="event-company@example.com",
            password="pass1234",
            phone="+251911000102",
        )
        self.company = CompanyProfile.objects.create(
            user=company_user,
            name="Events Co",
            phone="+251911000103",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=Address.objects.create(
                street_line1="Company Street",
                city="Addis Ababa",
                country="Ethiopia",
            ),
            status=CompanyProfile.StatusChoice.APPROVED,
        )
        self.hotel = HotelProfile.objects.create(
            company=self.company,
            name="Scope Hotel",
            stars=4,
            address=Address.objects.create(
                street_line1="Hotel Street",
                city="Addis Ababa",
                country="Ethiopia",
            ),
            is_active=True,
        )
        self.event_space = EventSpaceListing.objects.create(
            hotel=self.hotel,
            address=Address.objects.create(
                street_line1="Hall Street",
                city="Addis Ababa",
                country="Ethiopia",
            ),
            title="Sky Hall",
            description="Conference hall",
            base_price=Decimal("5000.00"),
            currency="ETB",
            total_units=1,
            number_of_guests=100,
            space_type=EventSpaceListing.SpaceType.CONFERENCE_HALL,
            is_active=True,
        )

    @patch("apps.payment.services.requests.post")
    def test_payment_init_uses_event_space_effective_terms_scope(self, mock_post):
        hotel_ct = ContentType.objects.get_for_model(self.hotel)
        event_space_ct = ContentType.objects.get_for_model(self.event_space)

        TermsAndConditions.objects.create(
            content_type=hotel_ct,
            object_id=self.hotel.id,
            version="1.0",
            title="Hotel Terms",
            content="Hotel terms",
            is_active=True,
            effective_date=date.today(),
        )
        TermsAndConditions.objects.create(
            content_type=event_space_ct,
            object_id=self.event_space.id,
            version="2.0",
            title="Event Space Terms",
            content="Event space terms",
            is_active=True,
            effective_date=date.today(),
        )

        booking = EventSpaceBooking.objects.create(
            user=self.booker,
            check_in_date=date.today() + timedelta(days=1),
            check_out_date=date.today() + timedelta(days=2),
            total_price=Decimal("5250.00"),
            currency="ETB",
            status=EventSpaceBooking.BookingStatus.PENDING,
            guest_first_name="Event",
            guest_last_name="Booker",
            guest_email="event-booker@example.com",
            guest_phone="0911000101",
            terms_accepted=True,
            terms_version="2.0",
            terms_content_snapshot="Event space terms",
        )
        EventSpaceBookingItem.objects.create(
            booking=booking,
            event_space=self.event_space,
            units_booked=1,
            price_per_unit=Decimal("5000.00"),
        )

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "status": "success",
            "data": {"checkout_url": "https://test.chapa.co/pay/eventspace"},
        }

        self.client.force_authenticate(user=self.booker)
        response = self.client.post(
            reverse("initiate-payment"),
            {
                "booking_id": str(booking.id),
                "booking_type": "eventspace",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertNotEqual(response.data.get("code"), "TERMS_UPDATED")


class HotelRoomPaymentTermsTests(APITestCase):
    def setUp(self):
        self.user_role = Role.objects.get_or_create(name="User", code=RoleCode.USER.value)[0]
        self.booker = User.objects.create_user(
            email="hotel-booker@example.com",
            password="pass1234",
            phone="+251911000111",
            role=self.user_role,
            first_name="Hotel",
            last_name="Booker",
        )

        company_user = User.objects.create_user(
            email="hotel-company@example.com",
            password="pass1234",
            phone="+251911000112",
        )
        self.company = CompanyProfile.objects.create(
            user=company_user,
            name="Hotel Co",
            phone="+251911000113",
            category=CompanyProfile.CategoryChoice.HOTEL,
            address=Address.objects.create(
                street_line1="Company Avenue",
                city="Addis Ababa",
                country="Ethiopia",
            ),
            status=CompanyProfile.StatusChoice.APPROVED,
        )
        self.hotel = HotelProfile.objects.create(
            company=self.company,
            name="Room Scope Hotel",
            stars=4,
            address=Address.objects.create(
                street_line1="Room Hotel Street",
                city="Addis Ababa",
                country="Ethiopia",
            ),
            is_active=True,
        )
        self.room = RoomListing.objects.create(
            hotel=self.hotel,
            address=Address.objects.create(
                street_line1="Room Street",
                city="Addis Ababa",
                country="Ethiopia",
            ),
            title="Deluxe Room",
            base_price=Decimal("3000.00"),
            currency="ETB",
            total_units=2,
            number_of_guests=2,
            room_size_sqm=30,
            bed_type=RoomListing.BedType.KING,
            is_active=True,
        )

    @patch("apps.payment.services.requests.post")
    def test_payment_init_does_not_flag_unchanged_hotel_terms(self, mock_post):
        hotel_ct = ContentType.objects.get_for_model(self.hotel)
        TermsAndConditions.objects.create(
            content_type=hotel_ct,
            object_id=self.hotel.id,
            version="1.0",
            title="Hotel Terms",
            content="Hotel room terms",
            is_active=True,
            effective_date=date.today(),
        )

        booking = Booking.objects.create(
            user=self.booker,
            check_in_date=date.today() + timedelta(days=1),
            check_out_date=date.today() + timedelta(days=3),
            total_price=Decimal("6300.00"),
            currency="ETB",
            status=Booking.BookingStatus.PENDING,
            guest_first_name="Hotel",
            guest_last_name="Booker",
            guest_email="hotel-booker@example.com",
            guest_phone="0911000111",
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Hotel room terms",
        )
        BookingItem.objects.create(
            booking=booking,
            room=self.room,
            units_booked=1,
            price_per_unit=Decimal("3000.00"),
        )

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "status": "success",
            "data": {"checkout_url": "https://test.chapa.co/pay/hotel"},
        }

        self.client.force_authenticate(user=self.booker)
        response = self.client.post(
            reverse("initiate-payment"),
            {
                "booking_id": str(booking.id),
                "booking_type": "booking",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertNotEqual(response.data.get("code"), "TERMS_UPDATED")
