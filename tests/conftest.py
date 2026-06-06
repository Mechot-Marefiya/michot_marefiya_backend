# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: yes
# Last updated: 2026-06-01

from __future__ import annotations

from io import BytesIO
from decimal import Decimal
from datetime import date, timedelta

import factory
import pytest
from PIL import Image
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APIClient

from apps.account.enums import RoleCode
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    ListingImage,
    Role,
    User,
)
from apps.analytics.models import AnalyticsDirtyDate, CompanyDailyMetrics, ListingDailyMetrics
from apps.core.models import Address, CurrencyRate, Facility
from apps.favorites.models import Favorite
from apps.listing.models import (
    AddonOffering,
    Amenity,
    Booking,
    BookingAddon,
    BookingItem,
    BookingItemPrice,
    BookingRating,
    CarAvailability,
    CarListing,
    CarRental,
    CarRentalItem,
    EventSpaceAvailability,
    EventSpaceBooking,
    EventSpaceBookingItem,
    EventSpaceListing,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseInventory,
    GuestHouseProfile,
    GuestHouseRoom,
    PropertyListing,
    RoomInventory,
    RoomListing,
    Season,
    SeasonalRate,
    StayAvailability,
    TermsAndConditions,
)
from apps.notifications.models import Notification, NotificationPreference, NotificationTemplate
from apps.payment.models import PaymentTransaction


def _build_image_file(name: str = "test.jpg", color: tuple[int, int, int] = (20, 40, 60)) -> SimpleUploadedFile:
    buffer = BytesIO()
    image = Image.new("RGB", (1, 1), color=color)
    image.save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def _days_from_today(days: int) -> date:
    return date.today() + timedelta(days=days)


def jwt_access_token(user: User) -> str:
    return str(RefreshToken.for_user(user).access_token)


def _auth_client_for(user: User) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_access_token(user)}")
    return client


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role

    name = factory.Sequence(lambda n: f"Role {n}")
    code = factory.Sequence(lambda n: f"role-{n}")


class AddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    street_line1 = factory.Sequence(lambda n: f"{n} Main St")
    country = "Ethiopia"
    city = "Addis Ababa"
    sub_city = "Bole"
    state = "Addis Ababa"
    postal_code = "1000"
    latitude = Decimal("9.012345")
    longitude = Decimal("38.765432")


class FacilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Facility

    name = factory.Sequence(lambda n: f"Facility {n}")
    icon = "star"


class AmenityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Amenity

    name = factory.Sequence(lambda n: f"Amenity {n}")
    icon = "check"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"
    phone = factory.Sequence(lambda n: f"0911000{n:03d}")
    role = None

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        password = extracted or "pass1234"
        self.set_password(password)
        if create:
            self.save(update_fields=["password"])


class CompanyProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CompanyProfile

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Company {n}")
    phone = factory.Sequence(lambda n: f"0922000{n:03d}")
    category = CompanyProfile.CategoryChoice.HOTEL
    description = "Company description"
    address = factory.SubFactory(AddressFactory)
    tin = factory.Sequence(lambda n: f"TIN{n:06d}")
    business_license_number = factory.Sequence(lambda n: f"LIC{n:06d}")

    @factory.post_generation
    def link_user(self, create, extracted, **kwargs):
        self.user.company = self
        self.user.save(update_fields=["company"])


class IndividualOwnerProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IndividualOwnerProfile

    first_name = "Owner"
    last_name = factory.Sequence(lambda n: f"Owner{n}")
    address = factory.SubFactory(AddressFactory)
    phone = factory.Sequence(lambda n: f"0933000{n:03d}")
    national_id_number = factory.Sequence(lambda n: 1000000000 + n)


class HotelProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HotelProfile

    company = factory.SubFactory(CompanyProfileFactory)
    name = factory.Sequence(lambda n: f"Hotel {n}")
    description = "Hotel description"
    phone = factory.Sequence(lambda n: f"0944000{n:03d}")
    website = "https://example.com"
    logo = factory.LazyFunction(_build_image_file)
    license = factory.LazyFunction(lambda: SimpleUploadedFile("license.pdf", b"license", content_type="application/pdf"))
    address = factory.SubFactory(AddressFactory)
    stars = 4
    featured = False


class ListingImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ListingImage

    content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(HotelProfile))
    object_id = factory.LazyAttribute(lambda obj: HotelProfileFactory().id)
    image = factory.LazyFunction(_build_image_file)
    alt_text = "Listing image"
    is_primary = True


class RoomListingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoomListing

    hotel = factory.SubFactory(HotelProfileFactory)
    address = factory.SubFactory(AddressFactory)
    title = factory.Sequence(lambda n: f"Room {n}")
    description = "Room description"
    base_price = Decimal("1000.00")
    currency = "ETB"
    number_of_guests = 2
    total_units = 3
    bed_type = "double"
    room_size_sqm = 20
    smoking_allowed = False
    children_allowed = True
    refundable = True


class GuestHouseProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuestHouseProfile

    company = factory.SubFactory(CompanyProfileFactory)
    title = factory.Sequence(lambda n: f"Guest House {n}")
    description = "Guest house description"
    phone = factory.Sequence(lambda n: f"0955000{n:03d}")
    website = "https://example.com"
    logo = factory.LazyFunction(_build_image_file)
    license = factory.LazyFunction(lambda: SimpleUploadedFile("gh-license.pdf", b"license", content_type="application/pdf"))
    address = factory.SubFactory(AddressFactory)
    rating = 4.5


class GuestHouseRoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuestHouseRoom

    guest_house = factory.SubFactory(GuestHouseProfileFactory)
    title = factory.Sequence(lambda n: f"GH Room {n}")
    description = "Guest house room"
    base_price = Decimal("800.00")
    currency = "ETB"
    number_of_guests = 2
    total_units = 2
    bed_type = "single"
    room_size_sqm = 18


class GuestHouseInventoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuestHouseInventory

    guest_house_room = factory.SubFactory(GuestHouseRoomFactory)
    date = factory.LazyFunction(lambda: _days_from_today(2))
    available_rooms = 2
    price = Decimal("800.00")


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking

    user = factory.SubFactory(UserFactory)
    check_in_date = factory.LazyFunction(lambda: _days_from_today(7))
    check_out_date = factory.LazyFunction(lambda: _days_from_today(9))
    total_price = Decimal("1000.00")
    currency = "ETB"
    status = Booking.BookingStatus.PENDING
    guest_first_name = "Guest"
    guest_last_name = "User"
    guest_email = "guest@example.com"
    guest_phone = "0911000111"
    special_requests = "No peanuts"
    booking_reference = factory.Sequence(lambda n: f"H-{n:06d}")
    terms_version = 1
    terms_accepted = True
    terms_accepted_at = factory.Faker("date_time_this_year")
    terms_content_snapshot = "Terms content"


class BookingItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BookingItem

    booking = factory.SubFactory(BookingFactory)
    room = factory.SubFactory(RoomListingFactory)
    units_booked = 1
    price_per_unit = Decimal("1000.00")


class BookingAddonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BookingAddon

    booking_item = factory.SubFactory(BookingItemFactory)
    offering = factory.SubFactory("tests.conftest.AddonOfferingFactory")
    name = "Breakfast"
    description = "Breakfast"
    category = "food"
    quantity = 1
    price_per_unit = Decimal("100.00")
    currency = "ETB"


class BookingItemPriceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BookingItemPrice

    booking_item = factory.SubFactory(BookingItemFactory)
    date = factory.LazyFunction(lambda: _days_from_today(8))
    price_per_unit = Decimal("1000.00")
    units = 1


class BookingRatingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BookingRating

    booking = factory.SubFactory(BookingFactory)
    rating = 4
    comment = "Great stay"


class StayAvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StayAvailability

    hotel = factory.SubFactory(HotelProfileFactory)
    room = factory.SubFactory(RoomListingFactory)
    date = factory.LazyFunction(lambda: _days_from_today(8))
    available_rooms = 2


class CarListingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CarListing

    company = factory.SubFactory(CompanyProfileFactory)
    brand = CarListing.CarBrandChoices.TOYOTA
    model = "Camry"
    year = 2022
    mileage = 10000
    fuel_type = CarListing.FuelTypeChoices.PETROL
    transmission = CarListing.TransmissionChoices.AUTOMATIC
    listing_type = CarListing.ListingTypeChoices.RENT
    car_class = CarListing.CarClassChoices.NORMAL
    condition = CarListing.ConditionChoices.USED
    title = "Toyota Camry"
    description = "Reliable car"
    base_price = Decimal("1500.00")
    currency = "ETB"
    quantity = 1
    seats = 4


class PropertyListingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PropertyListing

    company = factory.SubFactory(CompanyProfileFactory)
    title = factory.Sequence(lambda n: f"Property {n}")
    description = "Property description"
    base_price = Decimal("3000.00")
    currency = "ETB"
    property_type = "house"
    bedrooms = 2
    bathrooms = 1
    square_meters = 80
    is_furnished = True
    address = factory.SubFactory(AddressFactory)


class CarAvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CarAvailability

    car_listing = factory.SubFactory(CarListingFactory)
    date = factory.LazyFunction(lambda: _days_from_today(5))
    available_units = 1


class CarRentalItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CarRentalItem

    car_rental = factory.SubFactory("tests.conftest.CarRentalFactory")
    car_listing = factory.SubFactory("tests.conftest.CarListingFactory")
    units_rent = 1
    price_per_unit = Decimal("1500.00")


class CarRentalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CarRental

    renter = factory.SubFactory(UserFactory)
    start_date = factory.LazyFunction(lambda: _days_from_today(4))
    end_date = factory.LazyFunction(lambda: _days_from_today(6))
    total_price = Decimal("1500.00")
    currency = "ETB"
    status = CarRental.RentStatus.PENDING
    guest_first_name = "Guest"
    guest_last_name = "User"
    guest_email = "guest@example.com"
    guest_phone = "0911000112"
    special_requests = "Need driver"
    booking_reference = factory.Sequence(lambda n: f"C-{n:06d}")
    terms_version = 1
    terms_accepted = True
    terms_accepted_at = factory.Faker("date_time_this_year")
    terms_content_snapshot = "Terms content"


class EventSpaceListingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventSpaceListing

    hotel = factory.SubFactory(HotelProfileFactory)
    title = factory.Sequence(lambda n: f"Event Space {n}")
    description = "Event space"
    base_price = Decimal("5000.00")
    currency = "ETB"
    address = factory.SubFactory(AddressFactory)
    number_of_guests = 50
    total_units = 1
    space_type = "hall"
    floor_area_sqm = Decimal("120.00")


class EventSpaceAvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventSpaceAvailability

    space_listing = factory.SubFactory(EventSpaceListingFactory)
    date = factory.LazyFunction(lambda: _days_from_today(10))
    price = Decimal("5000.00")
    available_eventspace = 1


class EventSpaceBookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventSpaceBooking

    user = factory.SubFactory(UserFactory)
    check_in_date = factory.LazyFunction(lambda: _days_from_today(10))
    check_out_date = factory.LazyFunction(lambda: _days_from_today(11))
    total_price = Decimal("5000.00")
    currency = "ETB"
    status = EventSpaceBooking.BookingStatus.PENDING
    guest_first_name = "Guest"
    guest_last_name = "User"
    guest_email = "guest@example.com"
    guest_phone = "0911000113"
    special_requests = "Projector"
    booking_reference = factory.Sequence(lambda n: f"E-{n:06d}")
    terms_version = 1
    terms_accepted = True
    terms_accepted_at = factory.Faker("date_time_this_year")
    terms_content_snapshot = "Terms content"
    event_type = "conference"


class EventSpaceBookingItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventSpaceBookingItem

    booking = factory.SubFactory(EventSpaceBookingFactory)
    event_space = factory.SubFactory(EventSpaceListingFactory)
    units_booked = 1
    price_per_unit = Decimal("5000.00")


class GuestHouseBookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuestHouseBooking

    renter = factory.SubFactory(UserFactory)
    start_date = factory.LazyFunction(lambda: _days_from_today(3))
    end_date = factory.LazyFunction(lambda: _days_from_today(5))
    total_price = Decimal("1600.00")
    currency = "ETB"
    status = GuestHouseBooking.RentStatus.PENDING
    guest_first_name = "Guest"
    guest_last_name = "User"
    guest_email = "guest@example.com"
    guest_phone = "0911000114"
    special_requests = "Late check-in"
    booking_reference = factory.Sequence(lambda n: f"G-{n:06d}")
    terms_version = 1
    terms_accepted = True
    terms_accepted_at = factory.Faker("date_time_this_year")
    terms_content_snapshot = "Terms content"


class GuestHouseBookingItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuestHouseBookingItem

    booking = factory.SubFactory(GuestHouseBookingFactory)
    room = factory.SubFactory(GuestHouseRoomFactory)
    units_booked = 1
    price_per_unit = Decimal("800.00")


class AddonOfferingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AddonOffering

    hotel = factory.SubFactory(HotelProfileFactory)
    name = factory.Sequence(lambda n: f"Addon {n}")
    description = "Addon description"
    category = AddonOffering.AddonCategory.MEAL
    price_per_unit = Decimal("100.00")
    currency = "ETB"
    pricing_type = AddonOffering.PricingType.PER_BOOKING
    is_active = True
    max_quantity_per_booking = 5
    requires_inventory = False
    daily_capacity = 10
    icon = "plus"
    display_order = 1


class SeasonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Season

    name = factory.Sequence(lambda n: f"Season {n}")
    start_date = factory.LazyFunction(lambda: _days_from_today(20))
    end_date = factory.LazyFunction(lambda: _days_from_today(25))
    recurring = False
    active = True
    notes = "Season notes"
    company = factory.SubFactory(CompanyProfileFactory)


class SeasonalRateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SeasonalRate

    season = factory.SubFactory(SeasonFactory)
    price_override = Decimal("1200.00")
    multiplier = Decimal("1.20")
    priority = 1
    active = True
    days_of_week = [5, 6]


class TermsAndConditionsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TermsAndConditions

    version = factory.Sequence(lambda n: n + 1)
    title = factory.Sequence(lambda n: f"Terms {n}")
    content = "Terms content"
    effective_date = factory.Faker("date_this_year")
    is_active = True
    content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(HotelProfile))
    object_id = factory.LazyAttribute(lambda obj: HotelProfileFactory().id)


class PaymentTransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentTransaction

    content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(Booking))
    object_id = factory.LazyAttribute(lambda obj: BookingFactory().id)
    booking_type = "booking"
    tx_ref = factory.Sequence(lambda n: f"tx-{n:06d}")
    amount = Decimal("1000.00")
    currency = "ETB"
    status = PaymentTransaction.PaymentStatus.PENDING
    metadata = factory.LazyFunction(dict)


class FavoriteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Favorite

    user = factory.SubFactory(UserFactory)
    content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(HotelProfile))
    object_id = factory.LazyAttribute(lambda obj: str(HotelProfileFactory().id))
    snapshot = factory.LazyFunction(dict)


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    notification_type = Notification.NotificationType.BOOKING_CREATED
    title = "Booking created"
    message = "Your booking has been received."
    metadata = factory.LazyFunction(dict)
    priority = Notification.Priority.MEDIUM


class NotificationPreferenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NotificationPreference

    user = factory.SubFactory(UserFactory)
    email_preferences = factory.LazyFunction(dict)
    in_app_preferences = factory.LazyFunction(dict)
    email_enabled = True


class NotificationTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NotificationTemplate

    notification_type = Notification.NotificationType.BOOKING_CREATED
    title_template = "Booking created"
    message_template = "Your booking has been received."
    email_subject_template = "Booking created"
    email_body_template = "Your booking has been received."
    email_html_template = "<p>Your booking has been received.</p>"
    required_variables = factory.LazyFunction(list)


class CompanyDailyMetricsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CompanyDailyMetrics

    company_id = factory.LazyAttribute(lambda obj: CompanyProfileFactory().id)
    date = factory.LazyFunction(lambda: _days_from_today(1))
    revenue = Decimal("1000.00")
    bookings_count = 1
    confirmed_bookings_count = 1
    cancelled_bookings_count = 0
    avg_booking_value = Decimal("1000.00")
    top_listings = factory.LazyFunction(list)


class ListingDailyMetricsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ListingDailyMetrics

    listing_id = factory.LazyAttribute(lambda obj: RoomListingFactory().id)
    company_id = factory.LazyAttribute(lambda obj: CompanyProfileFactory().id)
    date = factory.LazyFunction(lambda: _days_from_today(1))
    revenue = Decimal("1000.00")
    bookings_count = 1
    avg_price = Decimal("1000.00")


class AnalyticsDirtyDateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnalyticsDirtyDate

    company_id = factory.LazyAttribute(lambda obj: CompanyProfileFactory().id)
    date = factory.LazyFunction(lambda: _days_from_today(1))


@pytest.fixture
def image_file():
    return _build_image_file()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def admin_role():
    return Role.objects.create(name="Admin", code=RoleCode.ADMIN.value)


@pytest.fixture
def user_role():
    return Role.objects.create(name="User", code=RoleCode.USER.value)


@pytest.fixture
def company_role():
    return Role.objects.create(name="Company", code=RoleCode.COMPANY.value)


@pytest.fixture
def front_desk_role():
    return Role.objects.create(name="Front Desk", code=RoleCode.FRONT_DESK.value)


@pytest.fixture
def user(django_user_model, user_role):
    return django_user_model.objects.create_user(
        email="user@example.com",
        password="pass1234",
        role=user_role,
        phone="0900111222",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def company_user(django_user_model, company_role):
    return django_user_model.objects.create_user(
        email="company@example.com",
        password="pass1234",
        role=company_role,
        phone="0900111223",
        first_name="Company",
        last_name="Owner",
    )


@pytest.fixture
def admin_user(django_user_model, admin_role):
    return django_user_model.objects.create_superuser(
        email="admin@example.com",
        password="pass1234",
        role=admin_role,
    )


@pytest.fixture
def individual_owner_user(django_user_model, user_role):
    return django_user_model.objects.create_user(
        email="owner@example.com",
        password="pass1234",
        role=user_role,
        phone="0900111224",
        first_name="Owner",
        last_name="User",
    )


@pytest.fixture
def company(company_user):
    company = CompanyProfileFactory(user=company_user)
    company.status = CompanyProfile.StatusChoice.APPROVED
    company.approved_at = timezone.now()
    company.save(update_fields=["status", "approved_at"])
    company_user.company = company
    company_user.save(update_fields=["company"])
    return company


@pytest.fixture
def individual_owner(individual_owner_user):
    owner = IndividualOwnerProfileFactory()
    individual_owner_user.individual_owner = owner
    individual_owner_user.save(update_fields=["individual_owner"])
    return owner


@pytest.fixture
def hotel(company):
    return HotelProfileFactory(company=company)


@pytest.fixture
def room(hotel):
    return RoomListingFactory(hotel=hotel)


@pytest.fixture
def guest_house(company):
    return GuestHouseProfileFactory(company=company)


@pytest.fixture
def guest_house_room(guest_house):
    return GuestHouseRoomFactory(guest_house=guest_house)


@pytest.fixture
def car_listing(company):
    return CarListingFactory(company=company)


@pytest.fixture
def property_listing(company):
    return PropertyListingFactory(company=company)


@pytest.fixture
def guesthouse_booking():
    return GuestHouseBookingFactory()


@pytest.fixture
def booking(room):
    booking = BookingFactory()
    BookingItemFactory(booking=booking, room=room)
    return booking


@pytest.fixture
def car_rental(car_listing):
    rental = CarRentalFactory()
    CarRentalItemFactory(car_rental=rental, car_listing=car_listing)
    return rental


@pytest.fixture
def event_space(hotel):
    return EventSpaceListingFactory(hotel=hotel)


@pytest.fixture
def eventspace_booking(event_space):
    booking = EventSpaceBookingFactory()
    EventSpaceBookingItemFactory(booking=booking, event_space=event_space)
    return booking


@pytest.fixture
def addon(hotel):
    return AddonOfferingFactory(hotel=hotel)


@pytest.fixture
def season(company):
    return SeasonFactory(company=company)


@pytest.fixture
def seasonal_rate(season):
    return SeasonalRateFactory(season=season)


@pytest.fixture
def favorite(user, hotel):
    return FavoriteFactory(user=user, content_type=ContentType.objects.get_for_model(HotelProfile), object_id=str(hotel.id))


@pytest.fixture
def payment_transaction(booking):
    return PaymentTransactionFactory(content_type=ContentType.objects.get_for_model(Booking), object_id=booking.id)


@pytest.fixture
def notification(user):
    return NotificationFactory(user=user)


@pytest.fixture
def notification_preference(user):
    return NotificationPreferenceFactory(user=user)


@pytest.fixture
def notification_template():
    return NotificationTemplateFactory()


@pytest.fixture
def auth_client(user) -> APIClient:
    return _auth_client_for(user)


@pytest.fixture
def company_client(company_user, company) -> APIClient:
    company_user.company = company
    company_user.save(update_fields=["company"])
    return _auth_client_for(company_user)


@pytest.fixture
def admin_client(admin_user) -> APIClient:
    return _auth_client_for(admin_user)


@pytest.fixture
def individual_owner_client(individual_owner_user, individual_owner) -> APIClient:
    individual_owner_user.individual_owner = individual_owner
    individual_owner_user.save(update_fields=["individual_owner"])
    return _auth_client_for(individual_owner_user)


@pytest.fixture
def front_desk_user(django_user_model, front_desk_role, company, hotel):
    user = django_user_model.objects.create_user(
        email="frontdesk@example.com",
        password="pass1234",
        role=front_desk_role,
        phone="0900111225",
        first_name="Front",
        last_name="Desk",
    )
    user.company = company
    user.workspace = hotel
    user.save()
    return user


@pytest.fixture
def front_desk_client(front_desk_user) -> APIClient:
    return _auth_client_for(front_desk_user)
