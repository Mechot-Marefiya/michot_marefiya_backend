from django.conf import settings
from django.db import models
from django.utils.timezone import now
from django.db.models import Q, F
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from apps.core.models import AbstractBaseModel, Address
from apps.core.models import AbstractBaseModel, Address,Facility
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    ListingImage,
)

# Terms and Conditions Model
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


def validate_days_of_week(value):
    """Validator to ensure `days_of_week` is a list of integers 0..6.

    Accepts empty list. Raises ValidationError on invalid types or values.
    """
    if value is None:
        return
    if not isinstance(value, (list, tuple)):
        raise ValidationError("days_of_week must be a list of integers 0..6")
    for v in value:
        if not isinstance(v, int):
            raise ValidationError("each entry in days_of_week must be an integer 0..6")
        if v < 0 or v > 6:
            raise ValidationError("each entry in days_of_week must be between 0 and 6 (Mon=0..Sun=6)")


class BaseListing(AbstractBaseModel):
    # images = models.ManyToManyField(ListingImage)

    images = GenericRelation(ListingImage, related_query_name="listings")

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
    currency = models.CharField(
        max_length=3,
        default="ETB",
        verbose_name=_("Currency"),
        help_text=_("ISO 4217 currency code for the price fields, e.g., 'ETB'."),
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
        blank=True,
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
        verbose_name=_("Class Category"),
    )

    condition = models.CharField(
        max_length=200, choices=ConditionChoices.choices, verbose_name=_("Condition")
    )
    images = GenericRelation(ListingImage, related_query_name="listings")
    quantity=models.PositiveSmallIntegerField(default=1,null=False)
    seats=models.PositiveSmallIntegerField(default=3,null=False)
    class Meta:
        verbose_name = _("Car Listing")
        verbose_name_plural = _("Car Listings")
        db_table = "car_listings"
        constraints = [
            # * Enforcing either one of the owners(company, or individual) must exist
            models.CheckConstraint(
                condition=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="car_owner_must_exist",
            )
        ]

    def __str__(self):
        return f"{self.brand}::{self.model}"
class CarRental(AbstractBaseModel):
    class RentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    start_date = models.DateField(
        verbose_name=_("Rental Start Date"),
    )

    end_date = models.DateField(
        verbose_name=_("Rental End Date"),
    )

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Total Rental Price"),
    )
    currency = models.CharField(max_length=3, default="ETB")

    status = models.CharField(
         max_length=20, choices=RentStatus.choices, default=RentStatus.PENDING
    )

    # Terms and Conditions tracking
    terms_accepted = models.BooleanField(
        default=False,
        verbose_name=_("Terms Accepted"),
        help_text=_("Whether the user confirmed they read and accepted the T&C")
    )
    
    terms_version = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("T&C Version"),
        help_text=_("Version of T&C that user accepted")
    )
    
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Terms Accepted At"),
        help_text=_("Timestamp when user accepted T&C")
    )
    
    terms_content_snapshot = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("T&C Content Snapshot"),
        help_text=_("Full T&C content at time of booking (for legal record)")
    )

    @property
    def is_legacy(self):
        return not self.terms_accepted and not self.terms_version

    class Meta:
        verbose_name = _("Car Rental")
        verbose_name_plural = _("Car Rentals")
    
    def __str__(self):
        return f"Rental by {self.renter} from {self.start_date} to {self.end_date}"

class CarRentalItem(AbstractBaseModel):
    car_rental = models.ForeignKey(
        CarRental,
        on_delete=models.CASCADE,
        related_name="rental_items",
        verbose_name=_("Car Rental"),
    )

    car_listing = models.ForeignKey(
        CarListing,
        on_delete=models.CASCADE,
        related_name="rental_items",
        verbose_name=_("Car Listing"),
    )

    units_rent = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Quantity"),
        help_text=_("Number of cars being rented.")
    )
    price_per_unit= models.DecimalField(max_digits=10, decimal_places=2)
    class Meta:
        verbose_name = _("Car Rental Item")
        verbose_name_plural = _("Car Rental Items")
    def subtotal(self):
        return self.units_rent * self.price_per_unit

    def __str__(self) -> str:
        return f"Car {self.car_listing} rent for {self.car_rental.start_date}"
# class CarSale(AbstractBaseModel):
#     class SaleStatus(models.TextChoices):
#         PENDING = "pending", _("Pending")
#         CONFIRMED = "confirmed", _("Confirmed")
#         CANCELLED = "cancelled", _("Cancelled")
#     buyer = models.ForeignKey(
#        settings.AUTH_USER_MODEL,
#         on_delete=models.CASCADE
#     )

#     sale_date = models.DateField(
#         auto_now_add=True,
#         verbose_name=_("Sale Date"),
#     )

#     total_price = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         verbose_name=_("Total Sale Price"),
#     )

#     status = models.CharField(
#         max_length=20, choices=SaleStatus.choices, default=SaleStatus.PENDING
#     )

#     class Meta:
#         verbose_name = _("Car Sale")
#         verbose_name_plural = _("Car Sales")
    
#     def __str__(self):
#         return f"Sale to {self.buyer} on {self.sale_date}"
# class CarSaleItem(AbstractBaseModel):
#     car_sale = models.ForeignKey(
#         CarSale,
#         on_delete=models.CASCADE,
#         related_name="sale_items",
#         verbose_name=_("Car Sale"),
#     )

#     car_listing = models.ForeignKey(
#         CarListing,
#         on_delete=models.CASCADE,
#         related_name="sale_items",
#         verbose_name=_("Car Listing"),
#     )
#     units_sale = models.PositiveIntegerField(
#         default=1,
#         verbose_name=_("Quantity"),
#         help_text=_("Number of cars being sold.")
#     )
#     price_per_unit=models.DecimalField(max_digits=10, decimal_places=2)
#     class Meta:
#         verbose_name = _("Car Sale Item")
#         verbose_name_plural = _("Car Sale Items")
#     def subtotal(self):
#         return self.units_sale * self.price_per_unit

#     def __str__(self) -> str:
#         return f"Car {self.car_listing} sell for {self.car_sale.sale_date}"
# models.py
class CarAvailability(AbstractBaseModel):
    car_listing = models.ForeignKey(
        CarListing,
        on_delete=models.CASCADE,
        related_name="daily_availabilities"
    )
    date = models.DateField()
    available_units = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Car Availability")
        verbose_name_plural = _("Car Availabilities")
        constraints = [
            models.UniqueConstraint(
                fields=["car_listing", "date"], name="car_listing_date_unique"
            )
        ]
        indexes = [models.Index(fields=["car_listing", "date"])]
    
    def __str__(self):
        return f"{self.car_listing} on {self.date} — {self.available_units} units available"

class PropertyListing(BaseListing):
    class PropertyTypeChoices(models.TextChoices):
        APARTMENT = "apartment", _("Apartment")
        CONDO = "condo", _("Condo")
        VILLA = "villa", _("Villa")

    # class ListingTypeChoices(models.TextChoices):
    #     SELL = "sale", _("For Sale")
    #     RENT = "rent", _("For Rent")

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
        Address,
        on_delete=models.RESTRICT,
        related_name="property_listing",
        verbose_name=_("Address"),
        help_text=_("Property location address")
    )

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

    # listing_type = models.CharField(
    #     max_length=200,
    #     choices=ListingTypeChoices.choices,
    #     default=ListingTypeChoices.RENT,
    #     verbose_name=_("Listing Type"),
    #     help_text=_("Whether the item is For sell or Rent."),
    # )

    class Meta:
        verbose_name = _("Property Listing")
        verbose_name_plural = _("Property Listings")
        db_table = "property_listings"
        constraints = [
            # * Enforcing either one of the owners(company, or individual) must exist
            models.CheckConstraint(
                condition=(
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
        Address,
        on_delete=models.RESTRICT,
        related_name="guesthouse_listing",
        verbose_name=_("Address"),
        help_text=_("Guesthouse location address")
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
    facility=models.ManyToManyField(Facility,blank=True,related_name="guest_house_listing",verbose_name=_("Facility"))
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
                condition=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="guest_house_owner_must_exist",
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.address.city})"
class GuestHouseAvailability(AbstractBaseModel):
    guest_house = models.ForeignKey(
        GuestHouseListing,
        on_delete=models.CASCADE,
        related_name="availability",
    )
    date = models.DateField()
    available_rooms = models.PositiveIntegerField()
    
    class Meta:
        unique_together = ("guest_house", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.guest_house.title} - {self.date}: {self.available_rooms} rooms"
class GuestHouseBooking(AbstractBaseModel):
    class RentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")
        WALK_IN = "walk_in", _("Walk-In")
    renter = models.ForeignKey(settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ETB")
    status = models.CharField(max_length=20, choices=RentStatus.choices, default=RentStatus.PENDING)
    
    # Terms and Conditions tracking
    terms_accepted = models.BooleanField(
        default=False,
        verbose_name=_("Terms Accepted"),
        help_text=_("Whether the user confirmed they read and accepted the T&C")
    )
    
    terms_version = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("T&C Version"),
        help_text=_("Version of T&C that user accepted")
    )
    
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Terms Accepted At"),
        help_text=_("Timestamp when user accepted T&C")
    )
    
    terms_content_snapshot = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("T&C Content Snapshot"),
        help_text=_("Full T&C content at time of booking (for legal record)")
    )

    @property
    def is_legacy(self):
        return not self.terms_accepted and not self.terms_version

    def __str__(self):
        return f"Booking #{self.id} ({self.start_date} → {self.end_date})"
class GuestHouseBookingItem(AbstractBaseModel):
    booking = models.ForeignKey(
        GuestHouseBooking,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Booking")
    )

    room = models.ForeignKey(
        GuestHouseListing,
        on_delete=models.CASCADE,
        related_name="booking_items",
        verbose_name=_("Room")
    )

    units_booked = models.PositiveIntegerField(default=1)

    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = _("Guesthouse Booking Item")
        verbose_name_plural = _("GuestBooking Items")
        db_table = "guesthouse_booking_items"

    def subtotal(self):
        return self.units_booked * self.price_per_unit

    def __str__(self):
        return f"{self.room.title} booked on {self.booking.start_date}"
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
        verbose_name=_("Hotel"),
        help_text=_("The hotel that owns this room type."),
        null=False,
        blank=False,
    )

    # Branch-specific address for hotels with multiple locations.
    # This address should correspond to the specific branch where this room type is available.
    address = models.ForeignKey(
        Address,
        on_delete=models.RESTRICT,
        related_name="room_listings",
        verbose_name=_("Address"),
        help_text=_("Branch address for this room type. Must correspond to a hotel branch location."),
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
        verbose_name = _("Room Listing")
        verbose_name_plural = _("Room Listings")
        db_table = "room_listings"
        constraints = [
            models.CheckConstraint(
                condition=Q(hotel__isnull=False),
                name="room_must_have_hotel",
            ),
        ]

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
class Booking(AbstractBaseModel):
    class BookingStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")
        WALK_IN = "walk_in", _("Walk-In")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    # for rooms: first night; for halls: event start date
    check_in_date = models.DateField()

    # for rooms: last night (exclusive); for halls: event end date (MVP: same day)
    check_out_date = models.DateField()

    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    currency = models.CharField(
        max_length=3,
        default="ETB",
        verbose_name=_("Currency"),
        help_text=_("ISO 4217 currency code for the price fields, e.g., 'ETB'."),
    )

    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING
    )

    # Immutable snapshot of booking-level display data captured at creation time
    snapshot = models.JSONField(null=True, blank=True)

    # Terms and Conditions tracking
    terms_accepted = models.BooleanField(
        default=False,
        verbose_name=_("Terms Accepted"),
        help_text=_("Whether the user confirmed they read and accepted the T&C")
    )
    
    terms_version = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("T&C Version"),
        help_text=_("Version of T&C that user accepted")
    )
    
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Terms Accepted At"),
        help_text=_("Timestamp when user accepted T&C")
    )
    
    terms_content_snapshot = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("T&C Content Snapshot"),
        help_text=_("Full T&C content at time of booking (for legal record)")
    )

    @property
    def is_legacy(self):
        return not self.terms_accepted and not self.terms_version

    class Meta:
        verbose_name = _("Booking")
        verbose_name_plural = _("Bookings")
        db_table = "bookings"
        constraints = [
            # Valid date range
            models.CheckConstraint(
                condition=Q(check_in_date__lt=F("check_out_date")),
                name="booking_valid_dates",
            ),
        ]

    def __str__(self):
        return f"Booking #{self.id} by {self.user}"


class BookingItem(AbstractBaseModel):
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Booking")
    )

    room = models.ForeignKey(
        RoomListing,
        on_delete=models.CASCADE,
        related_name="booking_items",
        verbose_name=_("Room")
    )

    units_booked = models.PositiveIntegerField(default=1)

    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    # Immutable snapshot of item-level display data captured at booking time
    snapshot = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = _("Booking Item")
        verbose_name_plural = _("Booking Items")
        db_table = "booking_items"

    def subtotal(self):
        return self.units_booked * self.price_per_unit

    def __str__(self) -> str:
        return f"Room {self.room} booked for {self.booking.check_in_date}"

class BookingRating(models.Model):
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="rating"
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

class Transaction(AbstractBaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        REFUND = "refund", _("Refund")

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="transaction"
    )

    provider = models.CharField(max_length=50)

    # Actual transaction id returned from the provider
    provider_payment_id = models.CharField(max_length=100)

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    currency = models.CharField(max_length=10)

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        db_table = "transactions"

    def __str__(self):
        return f"Transaction for Booking #{self.booking.id} - {self.status}"


class StayAvailability(AbstractBaseModel):
    hotel = models.ForeignKey(HotelProfile, on_delete=models.CASCADE)
    room = models.ForeignKey(RoomListing, on_delete=models.CASCADE)
    date = models.DateField()
    available_rooms = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Stay Availability")
        verbose_name_plural = _("Stay Availabilities")
        constraints = [
            models.UniqueConstraint(
                fields=["date", "hotel", "room"], name="hotel_date_room_idx"),
            models.CheckConstraint(
                condition=models.Q(available_rooms__gte=0),
                name="stay_availability_non_negative"
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "date"]),
            models.Index(fields=["hotel", "room", "date"]),
        ]
        

    def __str__(self) -> str:
        return f"{self.room.title} for {self.date}"


class Season(AbstractBaseModel):
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    recurring = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "seasons"

    def __str__(self) -> str:
        return f"{self.name} ({'recurring' if self.recurring else self.start_date})"


class SeasonalRate(AbstractBaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="rates")
    hotel = models.ForeignKey(HotelProfile, on_delete=models.CASCADE, null=True, blank=True)
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, null=True, blank=True)
    room = models.ForeignKey(RoomListing, on_delete=models.CASCADE, null=True, blank=True)

    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    multiplier = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)

    priority = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    days_of_week = models.JSONField(default=list, blank=True, validators=[validate_days_of_week])
    min_stay = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "seasonal_rates"

    def __str__(self) -> str:
        scope = self.room or self.hotel or self.company or "global"
        return f"Rate {self.id} for {scope} ({self.season.name})"


class BookingItemPrice(AbstractBaseModel):
    booking_item = models.ForeignKey(BookingItem, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField(db_index=True)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    units = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "booking_item_prices"
        ordering = ["date"]

    def subtotal(self):
        return self.price_per_unit * self.units

    def __str__(self) -> str:
        return f"{self.booking_item} - {self.date}: {self.price_per_unit} x {self.units}"
class EventSpaceListing(BaseListing):
    class SpaceType(models.TextChoices):
        AUDITORIUM = "auditorium", _("Auditorium")
        CONFERENCE_HALL = "conference_hall", _("Conference Hall")
        MEETING_ROOM = "meeting_room", _("Meeting Room")

    hotel = models.ForeignKey(
        HotelProfile,
        on_delete=models.CASCADE,
        related_name="event_space_listings",
        verbose_name=_("Hotel"),
        help_text=_("The hotel that owns this event space."),
        null=False,
        blank=False,
    )

    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="event_space_listing",
        verbose_name=_("Address"),
        help_text=_("Event space location address"),
    )

    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="event_space_listings",
        verbose_name=_("Amenities"),
    )

    number_of_guests = models.PositiveIntegerField(default=1)
    total_units = models.PositiveIntegerField(
        verbose_name=_("Total eventspace of This Type"),
        help_text=_("How many eventspace of this type exist in the property."),
        default=1
    )
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
    available_eventspace = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Available Event Spaces")
    )
    class Meta:
        verbose_name = _("Event space Availability")
        verbose_name_plural = _("Event Space Availabilities")
        db_table = "event_space_availabilities"
        unique_together = ("space_listing", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.space_listing} — {self.date}"
class BookingBase(AbstractBaseModel):
    """
    Abstract Base Class for all Booking types (Room, Event Space, etc.).
    """
    class BookingStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")
        WALK_IN = "walk_in", _("Walk-In")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_("User")
    )

    check_in_date = models.DateField(verbose_name=_("Check-In Date"))
    check_out_date = models.DateField(verbose_name=_("Check-Out Date"))

    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name=_("Total Price"))
    currency = models.CharField(max_length=3, default="ETB", verbose_name=_("Currency"))

    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING, verbose_name=_("Status")
    )

    class Meta:
        abstract = True
        constraints = [
            # Valid date range
            models.CheckConstraint(
                condition=Q(check_in_date__lt=F("check_out_date")),
                name="booking_valid_dates",
            ),
        ]

    def __str__(self):
        return f"Booking #{self.id} by {self.user} ({self.status})"
class EventSpaceBooking(BookingBase):
    """
    Top-level Booking for Event Spaces.
    """
    class EventType(models.TextChoices):
        WALK_IN = "walk_in", _("Walk-In")
        MEETING = "meeting", _("Meeting")
        CONFERENCE = "conference", _("Conference")
        SEMINAR = "seminar", _("Seminar")
        WORKSHOP = "workshop", _("Workshop")
        WEBINAR = "webinar", _("Webinar")
        NETWORKING = "networking", _("Networking")
        TRADE_SHOW = "trade_show", _("Trade Show")
        SOCIAL = "social", _("Social Event")
        FUNDRAISER = "fundraiser", _("Fundraiser")
        RETREAT = "retreat", _("Retreat")
    event_type = event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        default=EventType.MEETING,
    ) 
    
    # Terms and Conditions tracking
    terms_accepted = models.BooleanField(
        default=False,
        verbose_name=_("Terms Accepted"),
        help_text=_("Whether the user confirmed they read and accepted the T&C")
    )
    
    terms_version = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("T&C Version"),
        help_text=_("Version of T&C that user accepted")
    )
    
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Terms Accepted At"),
        help_text=_("Timestamp when user accepted T&C")
    )
    
    terms_content_snapshot = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("T&C Content Snapshot"),
        help_text=_("Full T&C content at time of booking (for legal record)")
    )
    
    @property
    def is_legacy(self):
        return not self.terms_accepted and not self.terms_version

    class Meta:
        verbose_name = _("Event Space Booking")
        verbose_name_plural = _("Event Space Bookings")
        db_table = "event_space_bookings"

    def __str__(self):
        return f"Event Space Booking #{self.id} - {self.status}"


class EventSpaceBookingItem(AbstractBaseModel):
    """
    Represents a single event space unit booking within an EventSpaceBooking.
    """
    booking = models.ForeignKey(
        EventSpaceBooking, # ForeignKey to the dedicated booking model
        on_delete=models.CASCADE,
        related_name="items", # Simple 'items' related_name is clean here
        verbose_name=_("Booking")
    )

    event_space = models.ForeignKey(
        EventSpaceListing,
        on_delete=models.CASCADE,
        related_name="event_space_booking_items",
        verbose_name=_("Event Space")
    )

    units_booked = models.PositiveIntegerField(default=1)

    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = _("Event Space Booking Item")
        verbose_name_plural = _("Event Space Booking Items")
        db_table = "event_space_booking_items" 

    def subtotal(self):
        return self.units_booked * self.price_per_unit

    def __str__(self) -> str:
        return f"Space {self.event_space.title} booked for {self.booking.check_in_date}"



class TermsAndConditions(AbstractBaseModel):
    """
    Stores Terms & Conditions documents for hotels, event spaces, and guesthouses.
    Each object (hotel/space/guesthouse) can have multiple versions with only one active.
    """
    # Polymorphic relationship: can be linked to Hotel, EventSpace, or GuestHouse
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("Content Type"),
        help_text=_("Type of object these terms apply to (Hotel, EventSpace, etc.)")
    )
    object_id = models.UUIDField(
        verbose_name=_("Object ID"),
        help_text=_("ID of the specific hotel/space/guesthouse")
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    version = models.CharField(
        max_length=50,
        verbose_name=_("Version"),
        help_text=_("Version identifier (e.g., '1.0', '2024-Q1', 'v2.5')")
    )
    
    title = models.CharField(
        max_length=255,
        default="Terms and Conditions",
        verbose_name=_("Title"),
        help_text=_("Title of the terms document")
    )
    
    content = models.TextField(
        verbose_name=_("Content"),
        help_text=_("Full T&C text in HTML or Markdown format")
    )
    
    effective_date = models.DateField(
        verbose_name=_("Effective Date"),
        help_text=_("Date when this version becomes active")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Only one version should be active at a time per object")
    )
    
    class Meta:
        verbose_name = _("Terms and Conditions")
        verbose_name_plural = _("Terms and Conditions")
        db_table = "terms_and_conditions"
        ordering = ['-effective_date', '-created_at']
        constraints = [
            # Ensure unique version per object
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'version'],
                name='unique_tc_version_per_object'
            )
        ]
        indexes = [
            models.Index(fields=['content_type', 'object_id', 'is_active']),
            models.Index(fields=['effective_date']),
        ]
    
    def __str__(self) -> str:
        obj_name = str(self.content_object) if self.content_object else f"{self.content_type}:{self.object_id}"
        return f"T&C v{self.version} for {obj_name}"
    
    def save(self, *args, **kwargs):
        """Override save to ensure only one active version per object"""
        if self.is_active:
            # Deactivate all other versions for this object
            TermsAndConditions.objects.filter(
                content_type=self.content_type,
                object_id=self.object_id,
                is_active=True
            ).exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)