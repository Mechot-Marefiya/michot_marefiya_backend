from django.conf import settings
from django.db import models
from decimal import Decimal
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from django.utils.timezone import now
from django.db.models import Q, F
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from apps.core.models import AbstractBaseModel, Address, Facility, GeoLocatedModel
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    ListingImage,
)

# Terms and Conditions Model
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

from apps.listing.utils import generate_booking_reference


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


class BaseListing(GeoLocatedModel):
    # images = models.ManyToManyField(ListingImage)

    images = GenericRelation(ListingImage, related_query_name="listings")

    is_verified = models.BooleanField(
        default=False,
        verbose_name=_("Is Verified"),
        help_text=_("Whether the listing has been verified by an administrator."),
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Verified At"),
        help_text=_("When the listing was last verified by an administrator."),
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Verified By"),
        help_text=_("Administrator who last verified this listing."),
    )

    verification_note = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name=_("Verification Note"),
        help_text=_("Optional note recorded by an administrator during verification."),
    )

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
        null=True,
        blank=True,
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

    booking_forward_window_days = models.PositiveIntegerField(
        default=5,
        verbose_name=_("Booking Forward Window Days"),
        help_text=_("Maximum number of days ahead a booking can start for this listing."),
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

    class RentalModeChoices(models.TextChoices):
        WITH_DRIVER = "with_driver", _("With Driver")
        WITHOUT_DRIVER = "without_driver", _("Without Driver")

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

    rental_mode = models.CharField(
        max_length=32,
        choices=RentalModeChoices.choices,
        default=RentalModeChoices.WITH_DRIVER,
        verbose_name=_("Rental Mode"),
        help_text=_("Whether the vehicle is rented with a driver or as a self-drive booking."),
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
    requires_code_3 = models.BooleanField(
        default=False,
        verbose_name=_("Requires Code 3"),
        help_text=_("Whether self-drive renters must provide a Code 3 license/permit."),
    )
    requires_business_license = models.BooleanField(
        default=False,
        verbose_name=_("Requires Business License"),
        help_text=_("Whether self-drive renters must provide a business license number."),
    )
    pre_rental_requirements = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Pre-rental Requirements"),
        help_text=_("Owner-defined instructions or compliance notes that renters must review before booking."),
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


class CarSaleListing(BaseListing):
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="car_sale_listings",
        verbose_name=_("Company"),
        null=True,
        blank=True,
    )
    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="car_sale_listings",
        verbose_name=_("Individual Owner"),
        null=True,
        blank=True,
    )
    brand = models.CharField(
        max_length=100,
        choices=CarListing.CarBrandChoices.choices,
        verbose_name=_("Brand"),
    )
    model = models.CharField(max_length=100, verbose_name=_("Model"))
    year = models.PositiveIntegerField(verbose_name=_("Year"))
    mileage = models.PositiveIntegerField(verbose_name=_("Mileage (km)"))
    fuel_type = models.CharField(
        max_length=50,
        choices=CarListing.FuelTypeChoices.choices,
        verbose_name=_("Engine Type"),
    )
    transmission = models.CharField(
        max_length=50,
        choices=CarListing.TransmissionChoices.choices,
        verbose_name=_("Transmission"),
    )
    condition = models.CharField(
        max_length=200,
        choices=CarListing.ConditionChoices.choices,
        verbose_name=_("Condition"),
    )
    car_class = models.CharField(
        max_length=200,
        choices=CarListing.CarClassChoices.choices,
        default=CarListing.CarClassChoices.NORMAL,
        verbose_name=_("Class Category"),
    )
    seats = models.PositiveSmallIntegerField(default=3)
    seller_contact_name = models.CharField(max_length=150, blank=True, default="")
    seller_phone = models.CharField(max_length=20)
    seller_email = models.EmailField(blank=True, default="")
    reveal_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("100.00"))

    class Meta:
        verbose_name = _("Car Sale Listing")
        verbose_name_plural = _("Car Sale Listings")
        db_table = "car_sale_listings"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="car_sale_owner_must_exist",
            )
        ]

    def __str__(self):
        return f"{self.brand}::{self.model} sale"


class ContactRevealRequest(AbstractBaseModel):
    class RevealStatus(models.TextChoices):
        REQUESTED = "reveal_requested", _("Reveal Requested")
        PAYMENT_INITIATED = "payment_initiated", _("Payment Initiated")
        PAID_REVEALED = "paid_revealed", _("Paid Revealed")
        EXPIRED = "expired", _("Expired")

    listing = models.ForeignKey(
        CarSaleListing,
        on_delete=models.CASCADE,
        related_name="contact_reveal_requests",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contact_reveal_requests",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=32,
        choices=RevealStatus.choices,
        default=RevealStatus.REQUESTED,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ETB")
    buyer_note = models.TextField(blank=True, default="")
    buyer_phone = models.CharField(max_length=20, blank=True, default="")
    tx_ref = models.CharField(max_length=255, blank=True, default="")
    expires_at = models.DateTimeField()
    unlocked_at = models.DateTimeField(null=True, blank=True)
    contact_snapshot = models.JSONField(default=dict, blank=True)
    payment_transactions = GenericRelation(
        "payment.PaymentTransaction",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="contact_reveal_requests",
    )

    class Meta:
        verbose_name = _("Contact Reveal Request")
        verbose_name_plural = _("Contact Reveal Requests")
        db_table = "contact_reveal_requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer", "listing", "status"]),
            models.Index(fields=["tx_ref"]),
            models.Index(fields=["expires_at"]),
        ]

    @property
    def is_unlocked(self):
        return self.status == self.RevealStatus.PAID_REVEALED

    @property
    def is_expired(self):
        return self.status != self.RevealStatus.PAID_REVEALED and self.expires_at <= now()

    def mark_expired(self):
        if self.status != self.RevealStatus.PAID_REVEALED:
            self.status = self.RevealStatus.EXPIRED
            self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"Reveal {self.listing_id} for {self.buyer_id} - {self.status}"
class CarRental(AbstractBaseModel):
    class RentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")
    # Renter who created the booking
    # Nullable to support guest checkout
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Renter Account")
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

    # Guest Information (who is staying)
    guest_first_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest First Name")
    )
    guest_last_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest Last Name")
    )
    guest_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Guest Email")
    )
    guest_phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("Guest Phone Number")
    )
    special_requests = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Special Requests")
    )
    renter_driver_license_number = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Driver License Number"),
        help_text=_("Driver license number supplied for self-drive compliance."),
    )
    renter_code_3_license_number = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Code 3 License Number"),
        help_text=_("Code 3 license/permit number supplied when required by the owner."),
    )
    renter_business_license_number = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Business License Number"),
        help_text=_("Business license number supplied when required by the owner."),
    )
    
    booking_reference = models.CharField(
        max_length=10,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        default="",
        verbose_name=_("Booking Reference")
    )

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

    @property
    def guest_full_name(self):
        return f"{self.guest_first_name} {self.guest_last_name}"
    
    @property
    def contact_email(self):
        return self.guest_email or (self.renter.email if self.renter else None)

    class Meta:
        verbose_name = _("Car Rental")
        verbose_name_plural = _("Car Rentals")
        db_table = "car_rentals"
        constraints = [
            models.CheckConstraint(
                condition=Q(start_date__lt=F("end_date")),
                name="car_rental_valid_dates",
            ),
            models.CheckConstraint(
                condition=Q(renter__isnull=False) | ~Q(guest_phone=""),
                name="car_rental_must_have_renter_or_guest"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = generate_booking_reference(prefix='C', model_class=CarRental)
        super().save(*args, **kwargs)
    
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
    def subtotal(self, days=None):
        base = self.units_rent * self.price_per_unit
        if days:
            return base * days
        return base


    def __str__(self) -> str:
        return f"Car {self.car_listing} rent for {self.car_rental.start_date}"


class CarRentalExtensionRequest(AbstractBaseModel):
    class ExtensionStatus(models.TextChoices):
        REQUESTED = "requested", _("Requested")
        PAYMENT_INITIATED = "payment_initiated", _("Payment Initiated")
        PAID_APPLIED = "paid_applied", _("Paid & Applied")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    rental = models.ForeignKey(
        CarRental,
        on_delete=models.CASCADE,
        related_name="extension_requests",
        verbose_name=_("Car Rental"),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_rental_extension_requests",
        verbose_name=_("Requested By"),
    )
    original_end_date = models.DateField(verbose_name=_("Original End Date"))
    requested_end_date = models.DateField(verbose_name=_("Requested End Date"))
    extra_days = models.PositiveIntegerField(verbose_name=_("Extra Days"))
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Extension Amount"))
    currency = models.CharField(max_length=3, default="ETB", verbose_name=_("Currency"))
    status = models.CharField(
        max_length=30,
        choices=ExtensionStatus.choices,
        default=ExtensionStatus.REQUESTED,
        verbose_name=_("Status"),
    )
    tx_ref = models.CharField(max_length=255, blank=True, default="", db_index=True)
    availability_held = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Car Rental Extension Request")
        verbose_name_plural = _("Car Rental Extension Requests")
        db_table = "car_rental_extension_requests"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_end_date__gt=F("original_end_date")),
                name="car_rental_extension_requested_end_after_original_end",
            ),
            models.CheckConstraint(
                condition=Q(extra_days__gt=0),
                name="car_rental_extension_extra_days_positive",
            ),
        ]

    @property
    def is_expired(self):
        return bool(
            self.expires_at
            and self.status in {
                self.ExtensionStatus.REQUESTED,
                self.ExtensionStatus.PAYMENT_INITIATED,
            }
            and self.expires_at <= now()
        )

    def __str__(self):
        return f"Extension {self.rental.booking_reference} -> {self.requested_end_date}"
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


class PropertyRentalAvailability(AbstractBaseModel):
    property_listing = models.ForeignKey(
        PropertyListing,
        on_delete=models.CASCADE,
        related_name="rental_availabilities",
    )
    date = models.DateField(db_index=True)
    available_units = models.PositiveIntegerField(default=1)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Price for this date; falls back to property base price if null."),
    )

    class Meta:
        verbose_name = _("Property Rental Availability")
        verbose_name_plural = _("Property Rental Availabilities")
        db_table = "property_rental_availabilities"
        constraints = [
            models.UniqueConstraint(
                fields=["property_listing", "date"],
                name="property_rental_listing_date_unique",
            ),
            models.CheckConstraint(
                condition=Q(available_units__gte=0),
                name="property_rental_availability_non_negative",
            ),
        ]
        indexes = [models.Index(fields=["property_listing", "date"])]

    def __str__(self):
        return f"{self.property_listing} - {self.date}: {self.available_units} available"


class PropertyRentalBooking(AbstractBaseModel):
    class RentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")

    property_listing = models.ForeignKey(
        PropertyListing,
        on_delete=models.CASCADE,
        related_name="rental_bookings",
    )
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Renter Account"),
    )
    start_date = models.DateField()
    end_date = models.DateField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ETB")
    status = models.CharField(max_length=20, choices=RentStatus.choices, default=RentStatus.PENDING)
    guest_first_name = models.CharField(max_length=100, blank=True, default="")
    guest_last_name = models.CharField(max_length=100, blank=True, default="")
    guest_email = models.EmailField(blank=True, default="")
    guest_phone = models.CharField(max_length=20, blank=True, default="")
    special_requests = models.TextField(blank=True, default="")
    booking_reference = models.CharField(
        max_length=10,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        default="",
        verbose_name=_("Booking Reference"),
    )
    snapshot = models.JSONField(null=True, blank=True)
    terms_accepted = models.BooleanField(default=False)
    terms_version = models.CharField(max_length=50, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_content_snapshot = models.TextField(null=True, blank=True)

    @property
    def is_legacy(self):
        return not self.terms_accepted and not self.terms_version

    @property
    def guest_full_name(self):
        return f"{self.guest_first_name} {self.guest_last_name}".strip()

    @property
    def contact_email(self):
        return self.guest_email or (self.renter.email if self.renter else None)

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = generate_booking_reference(prefix="P", model_class=PropertyRentalBooking)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Property Rental Booking")
        verbose_name_plural = _("Property Rental Bookings")
        db_table = "property_rental_bookings"
        constraints = [
            models.CheckConstraint(
                condition=Q(start_date__lt=F("end_date")),
                name="property_rental_booking_valid_dates",
            ),
            models.CheckConstraint(
                condition=Q(renter__isnull=False) | ~Q(guest_phone=""),
                name="property_rental_booking_must_have_renter_or_guest",
            ),
        ]

    def __str__(self):
        return f"Booking {self.booking_reference} - {self.property_listing}"


class PropertySaleListing(BaseListing):
    class PropertyTypeChoices(models.TextChoices):
        APARTMENT = "apartment", _("Apartment")
        CONDO = "condo", _("Condo")
        VILLA = "villa", _("Villa")
        HOUSE = "house", _("House")
        LAND = "land", _("Land")
        COMMERCIAL = "commercial", _("Commercial")
        OTHER = "other", _("Other")

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="property_sale_listings",
        verbose_name=_("Company"),
        null=True,
        blank=True,
    )
    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="property_sale_listings",
        verbose_name=_("Individual Owner"),
        null=True,
        blank=True,
    )
    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="property_sale_listing",
        verbose_name=_("Address"),
    )
    property_type = models.CharField(
        max_length=50,
        choices=PropertyTypeChoices.choices,
        verbose_name=_("Property Type"),
    )
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.PositiveIntegerField(default=0)
    square_meters = models.DecimalField(max_digits=10, decimal_places=2)
    land_size_square_meters = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_furnished = models.BooleanField(default=False)
    seller_contact_name = models.CharField(max_length=150, blank=True, default="")
    seller_phone = models.CharField(max_length=20)
    seller_email = models.EmailField(blank=True, default="")
    reveal_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("100.00"))

    class Meta:
        verbose_name = _("Property Sale Listing")
        verbose_name_plural = _("Property Sale Listings")
        db_table = "property_sale_listings"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="property_sale_owner_must_exist",
            )
        ]

    def __str__(self):
        return f"{self.title} property sale"


class PropertyContactRevealRequest(AbstractBaseModel):
    class RevealStatus(models.TextChoices):
        REQUESTED = "reveal_requested", _("Reveal Requested")
        PAYMENT_INITIATED = "payment_initiated", _("Payment Initiated")
        PAID_REVEALED = "paid_revealed", _("Paid Revealed")
        EXPIRED = "expired", _("Expired")

    listing = models.ForeignKey(
        PropertySaleListing,
        on_delete=models.CASCADE,
        related_name="contact_reveal_requests",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="property_contact_reveal_requests",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=32,
        choices=RevealStatus.choices,
        default=RevealStatus.REQUESTED,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ETB")
    buyer_note = models.TextField(blank=True, default="")
    buyer_phone = models.CharField(max_length=20, blank=True, default="")
    tx_ref = models.CharField(max_length=255, blank=True, default="")
    expires_at = models.DateTimeField()
    unlocked_at = models.DateTimeField(null=True, blank=True)
    contact_snapshot = models.JSONField(default=dict, blank=True)
    payment_transactions = GenericRelation(
        "payment.PaymentTransaction",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="property_contact_reveal_requests",
    )

    class Meta:
        verbose_name = _("Property Contact Reveal Request")
        verbose_name_plural = _("Property Contact Reveal Requests")
        db_table = "property_contact_reveal_requests"
        indexes = [
            models.Index(fields=["listing", "buyer", "status"]),
            models.Index(fields=["tx_ref"]),
            models.Index(fields=["expires_at"]),
        ]

    @property
    def is_unlocked(self):
        return self.status == self.RevealStatus.PAID_REVEALED

    @property
    def is_expired(self):
        return self.status != self.RevealStatus.PAID_REVEALED and self.expires_at <= now()

    def mark_expired(self):
        if self.status != self.RevealStatus.PAID_REVEALED:
            self.status = self.RevealStatus.EXPIRED
            self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"{self.buyer_id} -> {self.listing_id} ({self.status})"


class GuestHouseProfile(BaseListing):
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="guest_house_profiles",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="guest_house_profiles",
        verbose_name=_("Individual Owner"),
        help_text=_("The individual person that owns this listing."),
        null=True,
        blank=True,
    )

    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="guesthouse_profile",
        verbose_name=_("Address"),
        help_text=_("Guesthouse location address")
    )

    phone = models.CharField(
        max_length=20, 
        verbose_name=_("Phone Number"), 
        blank=True, 
        null=True,
        help_text=_("Contact phone number for the guest house.")
    )
    
    website = models.URLField(
        verbose_name=_("Website"), 
        blank=True, 
        null=True,
        help_text=_("Official website URL.")
    )

    logo = models.ImageField(
        verbose_name=_("Logo"), 
        upload_to="guesthouse/logos/", 
        blank=True, 
        null=True
    )
    
    license = models.FileField(
        verbose_name=_("Business License"), 
        upload_to="guesthouse/licenses/", 
        blank=True, 
        null=True,
        help_text=_("Upload a valid business license (PDF/Image).")
    )


    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="guest_house_profiles",
        verbose_name=_("Property Amenities"),
    )
    
    facility = models.ManyToManyField(
        Facility, 
        blank=True, 
        related_name="guest_house_profiles", 
        verbose_name=_("Facility")
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
        verbose_name = _("Guest House Profile")
        verbose_name_plural = _("Guest House Profiles")
        db_table = "guest_houses" 
        
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(individual_owner__isnull=False) & Q(company__isnull=True))
                    | (Q(individual_owner__isnull=True) & Q(company__isnull=False))
                ),
                name="guest_house_owner_must_exist",
            )
        ]

    def __str__(self) -> str:
        try:
            return f"{self.title} ({self.address.city})"
        except:
            return f"{self.title}"

class GuestHouseRoom(BaseListing):
    # represents a specific type of room in a GuestHouse (e.g. Master Bedroom, Single Room).
    class BedType(models.TextChoices):
        KING = "king", _("King")
        QUEEN = "queen", _("Queen")
        TWIN = "twin", _("Twin")
        DOUBLE = "double", _("Double")
        MIXED = "mixed", _("Mixed/Multiple")

    guest_house = models.ForeignKey(
        GuestHouseProfile,
        on_delete=models.CASCADE,
        related_name="rooms",
        verbose_name=_("Guest House"),
    )

    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="guest_house_rooms",
        verbose_name=_("Room Amenities"),
    )

    number_of_guests = models.PositiveIntegerField(default=1)

    total_units = models.PositiveIntegerField(
        verbose_name=_("Total Rooms of This Type"),
        help_text=_("How many rooms of this type exist in the guest house."),
        default=1
    )

    bed_type = models.CharField(
        max_length=20, choices=BedType.choices, default=BedType.MIXED
    )

    room_size_sqm = models.PositiveIntegerField(null=True, blank=True)
    

    class Meta:
        verbose_name = _("Guest House Room")
        verbose_name_plural = _("Guest House Rooms")
        db_table = "guest_house_rooms"

    def __str__(self):
        return f"{self.title} at {self.guest_house.title}"
class GuestHouseInventory(AbstractBaseModel):
    # per-day stock & price for a given guest house room type.
    guest_house_room = models.ForeignKey(
        GuestHouseRoom,
        on_delete=models.CASCADE,
        related_name="inventories",
    )
    date = models.DateField(db_index=True)
    available_rooms = models.PositiveIntegerField()
    
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Price for this date; falls back to room base price if null."),
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = ("guest_house_room", "date")
        ordering = ["date"]
        db_table = "guest_house_inventories"

    def __str__(self):
        return f"{self.guest_house_room} - {self.date}: {self.available_rooms} rooms"
class GuestHouseBooking(AbstractBaseModel):
    class RentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")
        WALK_IN = "walk_in", _("Walk-In")
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Renter Account")
    )
    start_date = models.DateField()
    end_date = models.DateField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ETB")
    status = models.CharField(max_length=20, choices=RentStatus.choices, default=RentStatus.PENDING)

    guest_first_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest First Name")
    )
    guest_last_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest Last Name")
    )
    guest_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Guest Email")
    )
    guest_phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("Guest Phone Number")
    )
    special_requests = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Special Requests")
    )
    
    booking_reference = models.CharField(
        max_length=10,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        default="",
        verbose_name=_("Booking Reference")
    )

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

    @property
    def guest_full_name(self):
        return f"{self.guest_first_name} {self.guest_last_name}"
    
    @property
    def contact_email(self):
        return self.guest_email or (self.renter.email if self.renter else None)

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = generate_booking_reference(prefix='G', model_class=GuestHouseBooking)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Booking #{self.id} ({self.start_date} → {self.end_date})"

    class Meta:
        verbose_name = _("Guesthouse Booking")
        verbose_name_plural = _("Guesthouse Bookings")
        db_table = "guest_house_bookings"
        constraints = [
            # Valid date range
            models.CheckConstraint(
                condition=Q(start_date__lt=F("end_date")),
                name="guesthouse_booking_valid_dates",
            ),
            # Either renter OR guest_email must exist (for guest checkout)
            # Either renter OR guest_email must exist (for guest checkout)
            models.CheckConstraint(
                condition=Q(renter__isnull=False) | ~Q(guest_phone=""),
                name="guesthouse_booking_must_have_renter_or_guest"
            ),
        ]
class GuestHouseBookingItem(AbstractBaseModel):
    booking = models.ForeignKey(
        GuestHouseBooking,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Booking")
    )

    room = models.ForeignKey(
        GuestHouseRoom,
        on_delete=models.CASCADE,
        related_name="booking_items",
        verbose_name=_("Room")
    )

    units_booked = models.PositiveIntegerField(default=1)

    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = _("Guesthouse Booking Item")
        verbose_name_plural = _("Guesthouse Booking Items")
        db_table = "guest_house_booking_items"

    def subtotal(self, nights=None):
        base = self.units_booked * self.price_per_unit
        if nights:
            return base * nights
        return base


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

    # User who created the booking (the "Booker")
    # Nullable to support guest checkout (booking without account)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Booker Account"),
        help_text=_("User account of the person making the booking (if logged in)")
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

    # these fields capture the actual guest details, separate from the booker account
    guest_first_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest First Name"),
        help_text=_("First name of the person staying")
    )
    guest_last_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest Last Name"),
        help_text=_("Last name of the person staying")
    )
    guest_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Guest Email"),
        help_text=_("Email address for booking confirmations and communication")
    )
    guest_phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("Guest Phone Number"),
        help_text=_("Contact phone number for the guest")
    )
    special_requests = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Special Requests"),
        help_text=_("Guest requests (e.g., late check-in, non-smoking room, dietary needs)")
    )
    
    booking_reference = models.CharField(
        max_length=10,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        default="",
        verbose_name=_("Booking Reference"),
        help_text=_("Human-readable booking code (e.g., H-X7Y2Z9)")
    )



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
    
    @property
    def guest_full_name(self):
        return f"{self.guest_first_name} {self.guest_last_name}"
    
    @property
    def contact_email(self):
        return self.guest_email or (self.user.email if self.user else None)

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
            # Either user OR a guest phone must exist (for lightweight guest checkout)
            models.CheckConstraint(
                condition=Q(user__isnull=False) | ~Q(guest_phone=""),
                name="booking_must_have_user_or_guest"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = generate_booking_reference(prefix='H', model_class=Booking)
        super().save(*args, **kwargs)

    def __str__(self):
        if hasattr(self, 'booking_reference') and self.booking_reference:
            return f"Booking {self.booking_reference} - {self.guest_full_name}"
        return f"Booking #{self.id} by {self.user or 'Guest'}"


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

    snapshot = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = _("Booking Item")
        verbose_name_plural = _("Booking Items")
        db_table = "booking_items"

    def subtotal(self, nights=None):
        """Calculate subtotal. If nights provided, reflects total stay cost."""
        base = self.units_booked * self.price_per_unit
        if nights:
            return base * nights
        return base

    def __str__(self) -> str:
        return f"Room {self.room} booked for {self.booking.check_in_date}"


class AddonOffering(AbstractBaseModel):
    
    class AddonCategory(models.TextChoices):
        MEAL = "meal", _("Meal/Food")
        TRANSPORT = "transport", _("Transportation")
        SERVICE = "service", _("Service")
        AMENITY = "amenity", _("Amenity/Equipment")
    
    class PricingType(models.TextChoices):
        PER_PERSON = "per_person", _("Per Person")
        PER_NIGHT = "per_night", _("Per Night")
        PER_BOOKING = "per_booking", _("Per Booking (One-time)")
        PER_UNIT = "per_unit", _("Per Unit")
    
    hotel = models.ForeignKey(
        HotelProfile,
        on_delete=models.CASCADE,
        related_name="addon_offerings",
        verbose_name=_("Hotel"),
        help_text=_("The hotel that provides this addon")
    )
    
    name = models.CharField(
        max_length=100,
        verbose_name=_("Addon Name"),
        help_text=_("e.g., 'Breakfast Buffet', 'Airport Shuttle'")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the addon service")
    )
    category = models.CharField(
        max_length=20,
        choices=AddonCategory.choices,
        default=AddonCategory.SERVICE,
        verbose_name=_("Category")
    )
    
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Price per Unit"),
        help_text=_("Base price for one unit of this addon")
    )
    currency = models.CharField(
        max_length=3,
        default="ETB",
        verbose_name=_("Currency"),
        help_text=_("ISO 4217 currency code")
    )
    
    pricing_type = models.CharField(
        max_length=20,
        choices=PricingType.choices,
        default=PricingType.PER_UNIT,
        verbose_name=_("Pricing Type"),
        help_text=_("How this addon is priced")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Whether this addon is currently available for booking")
    )
    max_quantity_per_booking = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Max Quantity per Booking"),
        help_text=_("Maximum number of units per booking (null = unlimited)")
    )
    
    # optional: inventory tracking (for future enhancement)
    requires_inventory = models.BooleanField(
        default=False,
        verbose_name=_("Requires Inventory"),
        help_text=_("Whether this addon has limited daily inventory")
    )
    daily_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Daily Capacity"),
        help_text=_("Total available units per day (if inventory tracked)")
    )
    
    icon = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Icon"),
        help_text=_("Icon identifier for frontend (e.g., 'breakfast', 'shuttle')")
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Display Order"),
        help_text=_("Order in which addon appears in lists (lower numbers first)")
    )
    
    class Meta:
        verbose_name = _("Addon Offering")
        verbose_name_plural = _("Addon Offerings")
        db_table = "addon_offerings"
        ordering = ['hotel', 'display_order', 'name']
        unique_together = [['hotel', 'name']] 
        indexes = [
            models.Index(fields=['hotel', 'is_active']),
            models.Index(fields=['category']),
        ]
    
    def clean(self):
        super().clean()
        
        if self.requires_inventory and not self.daily_capacity:
            raise ValidationError({
                'daily_capacity': _("Daily capacity is required when inventory tracking is enabled")
            })
        
        if self.price_per_unit is not None and self.price_per_unit <= 0:
            raise ValidationError({
                'price_per_unit': _("Price must be greater than zero")
            })
    
    def __str__(self):
        hotel_name = getattr(self.hotel, 'company', None).name if self.hotel and hasattr(self.hotel, 'company') else "N/A"
        return f"{hotel_name} - {self.name} ({self.price_per_unit} {self.currency})"


class BookingAddon(AbstractBaseModel):
    
    class AddonCategory(models.TextChoices):
        MEAL = "meal", _("Meal/Food")
        TRANSPORT = "transport", _("Transportation")
        SERVICE = "service", _("Service")
        AMENITY = "amenity", _("Amenity/Equipment")
    
    booking_item = models.ForeignKey(
        BookingItem,
        on_delete=models.CASCADE,
        related_name="addons",
        verbose_name=_("Booking Item"),
        help_text=_("The room/item this addon is attached to")
    )
    
    offering = models.ForeignKey(
        AddonOffering,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_instances",
        verbose_name=_("Addon Offering"),
        help_text=_("Reference to the hotel's addon offering definition (null for legacy bookings)")
    )
    
    name = models.CharField(
        max_length=100,
        verbose_name=_("Addon Name"),
        help_text=_("e.g., 'Breakfast', 'Airport Pickup', 'Extra Bed'")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the addon")
    )
    category = models.CharField(
        max_length=20,
        choices=AddonCategory.choices,
        default=AddonCategory.SERVICE,
        verbose_name=_("Category")
    )
    
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Quantity"),
        help_text=_("Number of units (e.g., 2 breakfasts)")
    )
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Price per Unit"),
        help_text=_("Price for one unit of this addon (snapshot at booking time)")
    )
    currency = models.CharField(
        max_length=3,
        default="ETB",
        verbose_name=_("Currency"),
        help_text=_("Currency code (snapshot at booking time)")
    )
    
    class Meta:
        verbose_name = _("Booking Addon")
        verbose_name_plural = _("Booking Addons")
        db_table = "booking_addons"
    
    @extend_schema_field(OpenApiTypes.STR)
    def subtotal(self):
        return self.quantity * self.price_per_unit
    
    def __str__(self):
        return f"{self.name} x{self.quantity} for {self.booking_item}"


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

    company = models.ForeignKey(
        "account.CompanyProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="seasons"
    )
    individual_owner = models.ForeignKey(
        "account.IndividualOwnerProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="seasons"
    )

    class Meta:
        db_table = "seasons"

    def __str__(self) -> str:
        return f"{self.name} ({'recurring' if self.recurring else self.start_date})"


class SeasonalRate(AbstractBaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="rates")
    hotel = models.ForeignKey(HotelProfile, on_delete=models.CASCADE, null=True, blank=True)
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, null=True, blank=True)
    room = models.ForeignKey(RoomListing, on_delete=models.CASCADE, null=True, blank=True)
    individual_owner = models.ForeignKey(
        "account.IndividualOwnerProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="seasonal_rates"
    )

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
        null=True,
        blank=True,
        verbose_name=_("Booker Account")
    )

    check_in_date = models.DateField(verbose_name=_("Check-In Date"))
    check_out_date = models.DateField(verbose_name=_("Check-Out Date"))

    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name=_("Total Price"))
    currency = models.CharField(max_length=3, default="ETB", verbose_name=_("Currency"))

    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING, verbose_name=_("Status")
    )

    guest_first_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest First Name")
    )
    guest_last_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Guest Last Name")
    )
    guest_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Guest Email")
    )
    guest_phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("Guest Phone Number")
    )
    special_requests = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Special Requests")
    )
    
    booking_reference = models.CharField(
        max_length=10,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        default="",
        verbose_name=_("Booking Reference")
    )

    snapshot = models.JSONField(null=True, blank=True)

    @property
    def guest_full_name(self):
        return f"{self.guest_first_name} {self.guest_last_name}"
    
    @property
    def contact_email(self):
        return self.guest_email or (self.user.email if self.user else None)

    class Meta:
        abstract = True
        constraints = [
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

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = generate_booking_reference(prefix='E', model_class=EventSpaceBooking)
        super().save(*args, **kwargs)

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

    def subtotal(self, nights=None):
        base = self.units_booked * self.price_per_unit
        if nights:
            return base * nights
        return base


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
