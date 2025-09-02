from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils.translation import gettext_lazy as _

from apps.core.models import AbstractBaseModel, Address
from apps.account.models import CompanyProfile, IndividualOwnerProfile


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
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name=_("Company"),
        help_text=_("The company that owns this listing."),
        null=True,
        blank=True,
    )

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

    # available_from = models.DateField(
    #     null=True,
    #     blank=True,
    #     verbose_name=_("Available From"),
    # )

    # available_to = models.DateField(
    #     null=True,
    #     blank=True,
    #     verbose_name=_("Available To"),
    # )

    class Meta:
        abstract = True
        constraints = [
            # * Enforcing either one of the owners(company, or individual) must exist
            models.CheckConstraint(
                check=(
                    models.Q(company__isnull=False) | models.Q(
                        individual__isnull=False)
                ),
                name="owner_must_exist",
            )
        ]


class Amenity(AbstractBaseModel):
    """Shared amenities for hotels/properties."""

    name = models.CharField(
        max_length=255,
        verbose_name=_("Amenity Name"),
        help_text=_("Name of the amenity or feature."),
    )

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

    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="+",
        # * Making only optional for validation cause either we use
        # * from payload or reuse company HQ address
        blank=True
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

    def __str__(self):
        return f"{self.brand}::{self.model}"


class PropertyListing(BaseListing):
    class PropertyTypeChoices(models.TextChoices):
        APARTMENT = "apartment", _("Apartment")
        CONDO = "condo", _("Condo")
        VILLA = "villa", _("Villa")
        HOUSE = "house", _("House")
        LAND = "land", _("Land")

    individual_owner = models.ForeignKey(
        IndividualOwnerProfile,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
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

    is_for_sale = models.BooleanField(
        default=False,
        verbose_name=_("Is for Sale"),
    )

    class Meta:
        verbose_name = _("Property Listing")
        verbose_name_plural = _("Property Listings")
        db_table = "property_listings"

    def __str__(self):
        return self.property_type
