from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils.translation import gettext_lazy as _

from apps.core.models import AbstractBaseModel, Address
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile
)


class ListingImage(AbstractBaseModel):
    """
    A generic image model for any listing type (hotel, car, property).
    """

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Content Type",
    )
    object_id = models.UUIDField(verbose_name="Object ID")
    content_object = GenericForeignKey()

    image = models.ImageField(
        upload_to="listing_images/",
        verbose_name="Image File",
        help_text="Upload an image for the listing.",
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Alt Text",
        help_text="Alternative text for the image.",
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name="Primary Image",
        help_text="Marks the main image for the listing.",
    )

    class Meta:
        verbose_name = "Listing Image"
        verbose_name_plural = "Listing Images"
        db_table = "listing_images"

    def __str__(self):
        return f"Image for {self.content_object} ({str(self.id)[:6]})"


class BaseListing(AbstractBaseModel):
    images = models.ManyToManyField(ListingImage)

    title = models.CharField(
        max_length=255,
        verbose_name=_("Title"),
        help_text=_(
            "Title of the listing, e.g., 'Luxury Suite with Pool View'."),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the listing."),
    )

    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Price"),
        help_text=_("Price of the service/product (if applicable)."),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Whether the listing is active and visible."),
    )

    class Meta:
        abstract = True


class Amenity(AbstractBaseModel):
    """Shared amenities for room-level (AC, balcony, kettle, TV, etc.)"""

    name = models.CharField(max_length=255, unique=True,
                            verbose_name=_("Name"))

    icon = models.CharField(max_length=100, blank=True, verbose_name=_("Icon"))

    class Meta:
        verbose_name = _("Amenity")
        verbose_name_plural = _("Amenities")
        db_table = "amenities"

    def __str__(self):
        return self.name


class CarListing(BaseListing):
    class FuelTypeChoices(models.TextChoices):
        DIESEL = "diesel", _("Diesel")
        ELECTRIC = "electric", _("Electric")
        PETROL = "petrol", _("Petrol")
        HYBRID = "hybrid", _("Hybrid")

    class TransmissionChoices(models.TextChoices):
        MANUAL = "manual", _("Manual")
        AUTOMATIC = "automatic", _("Automatic")

    class CarBrandChoices(models.TextChoices):
        TOYOTA = "toyota", _("Toyota")
        BMW = "bmw", _("BMW")
        MERCEDES_BENZ = "Mercedes-Benz", _("Mercedes-Benz")
        AUDI = "audi", _("Audi")
        VOLKSWAGEN = "Volkswagen", _("Volkswagen")
        HONDA = "honda", _("Honda")
        FORD = "ford", _("Ford")
        NISSAN = "nissan", _("Nissan")
        CHEVROLET = "chevrolet", _("Chevrolet")
        KIA = "kia", _("Kia")
        HYUNDAI = "hyundai", _("Hyundai")
        VOLVO = "volvo", _("Volvo")
        JEEP = "jeep", _("Jeep")
        PORSCHE = "porsche", _("Porsche")
        LEXUS = "lexus", _("Lexus")
        MAZDA = "mazda", _("Mazda")
        LAND_ROVER = "land_rover", _("Land Rover")
        SUBARU = "subaru", _("Subaru")
        FIAT = "fiat", _("Fiat")
        PEUGEOT = "peugeot", _("Peugeot")

    class ListingTypeChoices(models.TextChoices):
        SELL = "sale", _("For Sale")
        RENT = "rent", _("For Rent")

    class CarClassChoices(models.TextChoices):
        LUXURY = "luxury", _("Luxury")
        NORMAL = "normal", _("Normal")

    class ConditionChoices(models.TextChoices):
        NEW = "new", _("Brand New")
        USED = "used", _("Used")

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="car_listings",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True
    )

    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="car_listings",
        verbose_name=_("Individual Owner"),
        help_text=_("The individual person that owns this listing."),
        null=True,
        blank=True,
    )

    brand = models.CharField(
        max_length=100,
        choices=CarBrandChoices.choices,
        verbose_name=_("Brand"),
        help_text=_("Car brand, e.g., Toyota, BMW."),
    )

    model = models.CharField(
        max_length=100,
        verbose_name=_("Model"),
        help_text=_("Car model, e.g., Camry, X5."),
    )

    year = models.PositiveIntegerField(
        verbose_name=_("Year"),
        help_text=_("Manufacturing year of the car."),
    )

    mileage = models.PositiveIntegerField(
        verbose_name=_("Mileage (km)"),
        help_text=_("Mileage of the car in kilometers."),
    )

    fuel_type = models.CharField(
        max_length=50,
        choices=FuelTypeChoices.choices,
        verbose_name=_("Engine Type"),
    )

    transmission = models.CharField(
        max_length=50,
        choices=TransmissionChoices.choices,
        verbose_name=_("Transmission"),
    )

    listing_type = models.CharField(
        max_length=200,
        choices=ListingTypeChoices.choices,
        default=ListingTypeChoices.RENT,
        verbose_name=_("Listing Type"),
        help_text=_("Whether the item is For sell or Rent."),
    )

    car_class = models.CharField(
        max_length=200,
        choices=CarClassChoices.choices,
        default=CarClassChoices.NORMAL,
        verbose_name=_("Category")
    )

    condition = models.CharField(
        max_length=200, choices=ConditionChoices.choices, verbose_name=_("Condition")
    )

    class Meta:
        verbose_name = _("Car Listing")
        verbose_name_plural = _("Car Listings")
        db_table = "car_listings"
        constraints = [
            # * Enforcing either one of the owners(company, or individual) must exist
            models.CheckConstraint(
                check=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="car_owner_must_exist",
            )
        ]

    def __str__(self):
        return f"{self.brand}::{self.model}::{self.car_class}"


class PropertyListing(BaseListing):
    class PropertyTypeChoices(models.TextChoices):
        APARTMENT = "apartment", _("Apartment")
        CONDO = "condo", _("Condo")
        VILLA = "villa", _("Villa")
        HOUSE = "house", _("House")
        LAND = "land", _("Land")

    class ListingTypeChoices(models.TextChoices):
        SELL = "sale", _("For Sale")
        RENT = "rent", _("For Rent")

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="property_listings",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="property_listings",
        verbose_name=_("Individual Owner"),
        help_text=_("The individual person that owns this listing."),
        null=True,
        blank=True,
    )

    address = models.OneToOneField(
        Address, on_delete=models.RESTRICT, related_name="+")

    property_type = models.CharField(
        max_length=50,
        choices=PropertyTypeChoices.choices,
        verbose_name=_("Property Type"),
    )

    bedrooms = models.PositiveIntegerField(
        verbose_name=_("Bedrooms"),
    )

    bathrooms = models.PositiveIntegerField(
        verbose_name=_("Bathrooms"),
    )

    square_meters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Square Meters"),
    )

    is_furnished = models.BooleanField(
        default=False,
        verbose_name=_("Is Furnished"),
    )

    listing_type = models.CharField(
        max_length=200,
        choices=ListingTypeChoices.choices,
        default=ListingTypeChoices.RENT,
        verbose_name=_("Listing Type"),
        help_text=_("Whether the item is For sell or Rent."),
    )

    class Meta:
        verbose_name = _("Property Listing")
        verbose_name_plural = _("Property Listings")
        db_table = "property_listings"
        constraints = [
            # * Enforcing either one of the owners(company, or individual) must exist
            models.CheckConstraint(
                check=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="property_owner_must_exist",
            )
        ]

    def __str__(self):
        return self.property_type


class GuestHouseListing(BaseListing):
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="guest_house_listings",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="guest_house_listings",
        verbose_name=_("Individual Owner"),
        help_text=_("The individual person that owns this listing."),
        null=True,
        blank=True,
    )

    address = models.OneToOneField(
        Address, on_delete=models.RESTRICT, related_name="+", blank=True
    )

    total_rooms = models.PositiveIntegerField(
        verbose_name=_("Total Rooms"),
        help_text=_("Number of rooms available in the guest house."),
    )

    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="guest_house_listings",
        verbose_name=_("Amenities"),
    )

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Average Rating"),
        help_text=_("Average rating from user reviews (0–5)."),
    )

    class Meta:
        verbose_name = _("Guest House")
        verbose_name_plural = _("Guest Houses")
        db_table = "guest_houses"
        constraints = [
            # * Enforcing either one of the owners(company, or individual) must exist
            models.CheckConstraint(
                check=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="guest_house_owner_must_exist",
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.address.city})"


class RoomListing(BaseListing):
    """
    One row ~= one room type for a given hotel.
    Example titles: 'Standard Twin Room', 'Deluxe King Suite'
    """

    class BedType(models.TextChoices):
        KING = "king", _("King")
        QUEEN = "queen", _("Queen")
        TWIN = "twin", _("Twin")
        DOUBLE = "double", _("Double")
        MIXED = "mixed", _("Mixed/Multiple")

    hotel = models.ForeignKey(
        HotelProfile,
        on_delete=models.CASCADE,
        related_name="room_listings",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="+",
        # * Making only optional for validation cause either we use
        # * from payload or reuse company HQ address
        blank=True,
    )

    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="room_listings",
        verbose_name=_("Amenities"),
    )

    number_of_guests = models.PositiveIntegerField(default=1)

    total_units = models.PositiveIntegerField(
        verbose_name=_("Total Rooms of This Type"),
        help_text=_("How many rooms of this type exist in the property."),
    )

    bed_type = models.CharField(
        max_length=20, choices=BedType.choices, default=BedType.MIXED
    )

    room_size_sqm = models.PositiveIntegerField()

    smoking_allowed = models.BooleanField(default=False)

    children_allowed = models.BooleanField(default=True)

    refundable = models.BooleanField(
        default=True, help_text=_("Whether standard rate is refundable.")
    )

    class Meta:
        verbose_name = _("Room Type")
        verbose_name_plural = _("Room Types")
        db_table = "room_listings"

    def __str__(self):
        return f"{self.title}"


class RoomInventory(AbstractBaseModel):
    """
    Per-day stock & price for a given room type.
    price overrides RoomListing.base_price when set.
    """

    room_listing = models.ForeignKey(
        RoomListing, on_delete=models.CASCADE, related_name="inventories"
    )

    date = models.DateField(db_index=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_(
            "Price for this date; falls back to room base price if null."),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Room Inventory")
        verbose_name_plural = _("Room Inventories")
        db_table = "room_inventories"
        unique_together = ("room_listing", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.room_listing} — {self.date}"


class EventSpaceListing(BaseListing):
    class SpaceType(models.TextChoices):
        AUDITORIUM = "auditorium", _("Auditorium")
        CONFERENCE_HALL = "conference_hall", _("Conference Hall")
        MEETING_ROOM = "meeting_room", _("Meeting Room")

    hotel = models.ForeignKey(
        HotelProfile,
        on_delete=models.CASCADE,
        related_name="event_space_listings",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="+",
        # * Making only optional for validation cause either we use
        # * from payload or reuse company HQ address
        blank=True,
    )

    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="event_space_listings",
        verbose_name=_("Amenities"),
    )

    number_of_guests = models.PositiveIntegerField(default=1)

    space_type = models.CharField(max_length=50, choices=SpaceType.choices)

    floor_area_sqm = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _("Event space")
        verbose_name_plural = _("Event Spaces")
        db_table = "event_spaces"

    def __str__(self):
        return f"{self.title}"


class EventSpaceAvailability(AbstractBaseModel):
    """
    Simplified per-day availability for event spaces (MVP).
    Later you can add time-slot granularity.
    """

    space_listing = models.ForeignKey(
        EventSpaceListing, on_delete=models.CASCADE, related_name="availability"
    )

    date = models.DateField(db_index=True)

    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = _("Event space Availability")
        verbose_name_plural = _("Event Space Availabilities")
        db_table = "event_space_availabilities"
        unique_together = ("space_listing", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.space_listing} — {self.date}"


class Booking(AbstractBaseModel):
    class BookingStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")

    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE)

    # Choose ONE of these (enforced by DB constraint below)
    room = models.ForeignKey(
        RoomListing,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bookings",
    )

    event_space = models.ForeignKey(
        EventSpaceListing,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bookings",
    )

    units_booked = models.PositiveIntegerField(default=1)

    # for rooms: first night; for halls: event start date
    check_in_date = models.DateField()

    # for rooms: last night (exclusive); for halls: event end date (MVP: same day)
    check_out_date = models.DateField()

    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING
    )

    class Meta:
        verbose_name = _("Booking")
        verbose_name_plural = _("Bookings")
        db_table = "bookings"
        constraints = [
            # Exactly one target must be set
            models.CheckConstraint(
                check=(
                    (Q(room__isnull=False) & Q(event_space__isnull=True))
                    | (Q(room__isnull=True) & Q(event_space__isnull=False))
                ),
                name="booking_exactly_one_target",
            ),
            # Valid date range
            models.CheckConstraint(
                check=Q(check_in_date__lt=F("check_out_date")),
                name="booking_valid_dates",
            ),
        ]

    def __str__(self):
        target = self.room or self.event_space
        return f"Booking #{self.id} - {self.user} @ {target}"


class Payment(AbstractBaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        REFUND = "refund", _("Refund")

    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="payment"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    transaction_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        db_table = "payments"

    def __str__(self):
        return f"Payment for Booking #{self.booking.id} - {self.status}"
