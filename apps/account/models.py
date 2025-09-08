from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

from apps.account.managers import CustomUserManager
from apps.core.models import AbstractBaseModel, Address


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
    last_name = None
    last_name = None

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


class CompanyProfile(AbstractBaseModel):
    class CategoryChoice(models.TextChoices):
        HOTEL = "hotel", _("Hotel")
        PENSION = "pension", _("Pension")
        GUEST_HOUSE = "guest_house", _("Guest House")
        REALESTATE = "real_estate", _("Real Estate")
        APARTMENT = "apartment", _("Apartment")
        VEHICLE = "vehicle", _("Vehicle")

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
        max_length=100, verbose_name=_("Category"), choices=CategoryChoice.choices
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
    """This Model is aimed only for handling individual property owners. We don't needed neither to give
    individuals the ability to add properties through dashboard like companies. We need our admin to verify them in-person and
    add their detail here than using the AUTH_USER_MODEL.
    """

    class PropertyCategoryChoice(models.TextChoices):
        CONDOMINIUM = "condominium", _("Condominium")
        LAND = "land", _("Land")
        APARTMENT = "apartment", _("Apartment")
        VEHICLE = "vehicle", _("Vehicle")

    first_name = models.CharField(max_length=255, verbose_name=_("First Name"))

    last_name = models.CharField(max_length=255, verbose_name=_("LAst Name"))

    address = models.OneToOneField(Address, on_delete=models.RESTRICT, related_name="+")

    phone = models.CharField(max_length=15, verbose_name=("Phone Number"))

    category = models.CharField(
        max_length=100,
        verbose_name=_("Category"),
        choices=PropertyCategoryChoice.choices,
    )

    national_id_number = models.SmallIntegerField(
        verbose_name=_("National Id Number"), blank=True, null=True
    )

    class Meta:
        verbose_name = _("Individual Owner Profile")
        verbose_name_plural = _("Individual Owner Profiles")
        db_table = "individual_owners"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Facility(AbstractBaseModel):
    """
    Shared Hotel level things(pool, spa, gym, parking, etc.)
    """

    name = models.CharField(max_length=255, unique=True, verbose_name=_("Name"))

    icon = models.CharField(max_length=100, blank=True, verbose_name=_("Icon"))

    class Meta:
        verbose_name = _("Facility")
        verbose_name_plural = _("Facilities")
        db_table = "facilities"

    def __str__(self):
        return self.name


class HotelProfile(AbstractBaseModel):
    company = models.OneToOneField(
        CompanyProfile, on_delete=models.CASCADE, related_name="+"
    )
    # * Making these two nullable cause pensions/some hotels might not have those.
    stars = models.PositiveSmallIntegerField(
        verbose_name=_("Stars"), null=True, blank=True
    )
    facilities = models.ManyToManyField(Facility, blank=True)
