from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from apps.account.managers import CustomUserManager
from apps.core.models import AbstractBaseModel, Address, Facility


class Role(AbstractBaseModel):
    name = models.CharField(max_length=50, verbose_name=_("Name"))

    code = models.CharField(max_length=50, verbose_name=_("Code"))

    class Meta:
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")
        db_table = "roles"
        constraints = [
            models.UniqueConstraint(fields=["code"], name="roles_code_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser, AbstractBaseModel):
    email = models.EmailField(verbose_name=_("Email"), unique=True, null=False)

    role = models.ForeignKey(
        Role, on_delete=models.RESTRICT, related_name="+", null=True
    )

    username = None
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-created_at",)
        db_table = "users"

    def __str__(self) -> str:
        return self.email


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


class CompanyProfile(AbstractBaseModel):
    class CategoryChoice(models.TextChoices):
        HOTEL = "hotel", _("Hotel")
        PENSION = "pension", _("Pension")
        HOUSE = "house", _("House")
        VEHICLE = "vehicle", _("Vehicle")
        # ? I don't see the point having each type than categorizing as House
        # GUEST_HOUSE = "guest_house", _("Guest House")
        # APARTMENT = "apartment", _("Apartment")
        # VILLA = "villa", _("Villa")
        # CONDO = "condo", _("Condominium")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_("User"),
        related_name="profile",
    )

    name = models.CharField(max_length=100, verbose_name=_("Company Name"))

    phone = models.CharField(max_length=15, verbose_name=_("Phone Number"))

    logo = models.ImageField(
        verbose_name=_("Logo"), upload_to="company_logos/", blank=True, null=True
    )

    license = models.FileField(verbose_name=_("License"), upload_to="company_licenses/")

    category = models.CharField(
        max_length=100, choices=CategoryChoice.choices, verbose_name=_("Category")
    )

    description = models.TextField(verbose_name=_("Description"), blank=True)

    address = models.OneToOneField(Address, on_delete=models.RESTRICT, related_name="+")

    class Meta:
        verbose_name = _("Company Profile")
        verbose_name_plural = _("Company Profiles")
        db_table = "company_profiles"

    def __str__(self) -> str:
        return f"{self.name}::{self.category}"


class IndividualOwnerProfile(AbstractBaseModel):
    """This Model is aimed only for handling individual property owners.
    We don't needed neither to give individuals the ability to add properties
    through dashboard like companies. We need our admin to verify them
    in-person and add their detail here than using the AUTH_USER_MODEL.
    """

    # class PropertyCategoryChoice(models.TextChoices):
    #     GUEST_HOUSE = "guest_house", _("Guest House")
    #     APARTMENT = "apartment", _("Apartment")
    #     CONDOMINIUM = "condominium", _("Condominium")
    #     VILLA = "villa", _("Villa")
    #     VEHICLE = "vehicle", _("Vehicle")

    first_name = models.CharField(max_length=255, verbose_name=_("First Name"))

    last_name = models.CharField(max_length=255, verbose_name=_("Last Name"))

    address = models.OneToOneField(Address, on_delete=models.RESTRICT, related_name="+")

    phone = models.CharField(max_length=15, unique=True, verbose_name=("Phone Number"))

    # category = models.CharField(
    #     max_length=100,
    #     verbose_name=_("Category"),
    #     choices=PropertyCategoryChoice.choices,
    # )

    # TODO: Make this unique once it's required in the future.
    national_id_number = models.BigIntegerField(
        verbose_name=_("National Id Number"), blank=True, null=True
    )

    class Meta:
        verbose_name = _("Individual Owner Profile")
        verbose_name_plural = _("Individual Owner Profiles")
        db_table = "individual_owners"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class HotelProfile(AbstractBaseModel):
    # class CategoryChoice(models.TextChoices):
    #     HOTEL = "hotel", _("Hotel")
    #     PENSION = "pension", _("Pension")

    company = models.OneToOneField(
        CompanyProfile, on_delete=models.CASCADE, related_name="hotel"
    )

    images = GenericRelation(ListingImage, related_query_name="listings")

    # category = models.CharField(
    #     max_length=100,
    #     choices=CategoryChoice.choices,
    #     default=CategoryChoice.HOTEL,
    #     verbose_name=_("Category")
    # )

    # * Making these two nullable cause pensions/some hotels might not have those.
    stars = models.PositiveSmallIntegerField(
        verbose_name=_("Stars"), null=True, blank=True
    )

    facilities = models.ManyToManyField(Facility, blank=True)
    featured=models.BooleanField(null=True,default=False)

    class Meta:
        verbose_name = _("Hotel Profile")
        verbose_name_plural = _("Hotel Profiles")
        # db_table = "hotels"

    def __str__(self) -> str:
        return self.company.name