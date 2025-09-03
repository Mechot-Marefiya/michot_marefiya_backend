from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils.translation import gettext_lazy as _

from apps.core.models import AbstractBaseModel, Address
from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile


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
        help_text=_("Title of the listing, e.g., 'Luxury Suite with Pool View'."),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the listing."),
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
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

    name = models.CharField(max_length=255, unique=True, verbose_name=_("Name"))

    icon = models.CharField(max_length=100, blank=True, verbose_name=_("Icon"))

    class Meta:
        verbose_name = _("Amenity")
        verbose_name_plural = _("Amenities")
        db_table = "amenities"

    def __str__(self):
        return self.name


class HotelListing(BaseListing):
    class HotelServiceChoices(models.TextChoices):
        ROOM = "room", _("Room")
        AUDITORIUM = "auditorium", _("Auditorium")
        CONFERENCE_HALL = "conference_hall", _("Conference Hall")

    company = models.ForeignKey(
        HotelProfile,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
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

    capacity = models.PositiveIntegerField(
        verbose_name=_("Capacity"),
        help_text=_("Number of guests this service can accommodate."),
        null=True,
        blank=True,
    )

    service_type = models.CharField(
        max_length=50,
        choices=HotelServiceChoices.choices,
        verbose_name=_("Service Type"),
    )

    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="hotel_listings",
        verbose_name=_("Amenities"),
    )

    class Meta:
        verbose_name = _("Hotel Listing")
        verbose_name_plural = _("Hotel Listings")
        db_table = "hotel_listings"

    def __str__(self):
        return f"{self.company.name}::{self.service_type}"


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

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
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

    is_for_sale = models.BooleanField(
        default=False,
        verbose_name=_("Is for Sale"),
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
                name="owner_must_exist",
            )
        ]

    def __str__(self):
        return f"{self.brand}::{self.model}"


class PropertyListing(BaseListing):
    class PropertyTypeChoices(models.TextChoices):
        APARTMENT = "apartment", _("Apartment")
        CONDO = "condo", _("Condo")
        VILLA = "villa", _("Villa")
        HOUSE = "house", _("House")
        LAND = "land", _("Land")

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name=_("Individual Owner"),
        help_text=_("The individual person that owns this listing."),
        null=True,
        blank=True,
    )

    address = models.OneToOneField(Address, on_delete=models.RESTRICT, related_name="+")

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

    is_for_sale = models.BooleanField(
        default=False,
        verbose_name=_("Is for Sale"),
    )

    class Meta:
        verbose_name = _("Property Listing")
        verbose_name_plural = _("Property Listings")
        db_table = "property_listings"
        constraints = [
            # * Enforcing either one of the owners(company, or individual) must exist
            models.CheckConstraint(
                check=(
                    models.Q(company__isnull=False)
                    | models.Q(individual_owner__isnull=False)
                ),
                name="owner_must_exist",
            )
        ]

    def __str__(self):
        return self.property_type


# -------------------------
# ROOM-TYPE LISTING (discoverable, bookable)
# -------------------------
class RoomType(AbstractBaseModel):
    """
    One row ~= one room type for a given hotel (company with industry=hospitality).
    Example titles: 'Standard Twin Room', 'Deluxe King Suite'
    """

    class BedType(models.TextChoices):
        KING = "king", _("King")
        QUEEN = "queen", _("Queen")
        TWIN = "twin", _("Twin")
        DOUBLE = "double", _("Double")
        MIXED = "mixed", _("Mixed/Multiple")

    listing = models.ForeignKey(
        HotelListing,
        on_delete=models.CASCADE,
        related_name="room_types",
        limit_choices_to={"service_type": HotelListing.HotelServiceChoices.ROOM},
    )

    total_units = models.PositiveIntegerField(
        verbose_name=_("Total Rooms of This Type"),
        help_text=_("How many rooms of this type exist in the property."),
    )

    bed_type = models.CharField(
        max_length=20, choices=BedType.choices, default=BedType.MIXED
    )

    room_size_sqm = models.PositiveIntegerField(blank=True, null=True)

    smoking_allowed = models.BooleanField(default=False)

    children_allowed = models.BooleanField(default=True)

    refundable = models.BooleanField(
        default=True, help_text=_("Whether standard rate is refundable.")
    )

    check_in_time = models.TimeField(blank=True, null=True)

    check_out_time = models.TimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.listing.title}"


class RoomInventory(AbstractBaseModel):
    """
    Per-day stock & price for a given room type.
    price overrides RoomTypeListing.price when set.
    """

    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="inventory",
    )

    date = models.DateField(db_index=True)

    # TODO: Thinking the system will auto monitor taken and available units
    # available_units = models.PositiveIntegerField(
    #     help_text=_("Units available for this date (<= total_units).")
    # )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Price for this date; falls back to room base price if null."),
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = ("room_type", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.room_type} — {self.date}"


# -------------------------
# EVENT SPACE LISTING (halls / auditoriums)
# -------------------------
class EventSpace(AbstractBaseModel):
    class SpaceType(models.TextChoices):
        AUDITORIUM = "auditorium", _("Auditorium")
        CONFERENCE_HALL = "conference_hall", _("Conference Hall")
        MEETING_ROOM = "meeting_room", _("Meeting Room")

    listing = models.ForeignKey(
        HotelListing,
        on_delete=models.CASCADE,
        related_name="room_types",
        limit_choices_to={"service_type": HotelListing.HotelServiceChoices.ROOM},
    )

    space_type = models.CharField(max_length=50, choices=SpaceType.choices)

    floor_area_sqm = models.PositiveIntegerField(blank=True, null=True)

    check_in_time = models.TimeField(blank=True, null=True)

    check_out_time = models.TimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.listing.title}"


class EventSpaceAvailability(AbstractBaseModel):
    """
    Simplified per-day availability for event spaces (MVP).
    Later you can add time-slot granularity.
    """

    space = models.ForeignKey(
        EventSpace, on_delete=models.CASCADE, related_name="availability"
    )

    date = models.DateField(db_index=True)

    # available_units = models.PositiveIntegerField(default=1)

    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ("space", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.space} — {self.date}"


# -------------------------
# BOOKINGS (single table; exactly one target: room OR event space)
# -------------------------
class Booking(AbstractBaseModel):
    class BookingStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Choose ONE of these (enforced by DB constraint below)
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bookings",
    )

    event_space = models.ForeignKey(
        EventSpace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bookings",
    )

    # for rooms: first night; for halls: event start date
    check_in = models.DateField()

    # for rooms: last night (exclusive); for halls: event end date (MVP: same day)
    check_out = models.DateField()

    guests = models.PositiveIntegerField(default=1)

    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING
    )

    class Meta:
        constraints = [
            # Exactly one target must be set
            models.CheckConstraint(
                check=(
                    (Q(room_type__isnull=False) & Q(event_space__isnull=True))
                    | (Q(room_type__isnull=True) & Q(event_space__isnull=False))
                ),
                name="booking_exactly_one_target",
            ),
            # Valid date range
            models.CheckConstraint(
                check=Q(check_in__lt=F("check_out")),
                name="booking_valid_dates",
            ),
        ]

    def __str__(self):
        target = self.room_type or self.event_space
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

    def __str__(self):
        return f"Payment for Booking #{self.booking.id} - {self.status}"
