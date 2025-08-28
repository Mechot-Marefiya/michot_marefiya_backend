from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

from apps.account.managers import CustomUserManager
from apps.core.models import AbstractBaseModel


class Address(AbstractBaseModel):
    street_line1 = models.CharField(max_length=255)

    street_line2 = models.CharField(max_length=255, blank=True, null=True)

    country = models.TextField(
        max_length=100, verbose_name=_("Country"), default="Ethiopia")

    city = models.CharField(max_length=100, verbose_name=_("City"))

    sub_city = models.CharField(max_length=100, verbose_name=_(
        "Sub City"), blank=True, null=True)

    state = models.CharField(max_length=100, blank=True, null=True)

    postal_code = models.CharField(max_length=20, blank=True, null=True)

    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, blank=True, null=True)

    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, blank=True, null=True)

    class Meta:
        verbose_name = _("Address")
        verbose_name_plural = _("Addresses")
        db_table = "addresses"

    def __str__(self) -> str:
        return self.city


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
    email = models.EmailField(verbose_name=_("Email"), unique=True)

    role = models.ForeignKey(
        Role, on_delete=models.RESTRICT, related_name="+"
    )

    username = None

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
    class IndustryChoice(models.TextChoices):
        HOSPITALITY = 'hospitality', _('Hospitality')
        VEHICLE = 'vehicle', _('Vehicle')
        HOUSE = 'house', _('House')

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_("User"),
        related_name="profile"
    )

    name = models.CharField(
        max_length=100, verbose_name=_("Company Name"))

    phone = models.CharField(max_length=15, verbose_name=_("Phone Number"))

    logo = models.ImageField(verbose_name=_(
        "Logo"), upload_to="company_logos/", blank=True, null=True)

    license = models.FileField(
        verbose_name=_("License"), upload_to="company_licenses/")

    industry = models.CharField(
        max_length=100, verbose_name=_("Industry"), choices=IndustryChoice)

    description = models.TextField(verbose_name=_(
        "Description"), blank=True, null=True)

    address = models.OneToOneField(
        Address, on_delete=models.RESTRICT, related_name="+")

    class Meta:
        verbose_name = _("Company Profile")
        verbose_name_plural = _("Company Profiles")
        db_table = "company_profiles"

    def __str__(self) -> str:
        return self.name
