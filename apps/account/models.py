from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from apps.account.managers import CustomUserManager
from apps.core.models import AbstractBaseModel, Address, Facility, GeoLocatedModel


def normalize_phone_number(phone: str | None) -> str:
    value = (phone or "").strip().replace(" ", "").replace("-", "")
    if value.startswith("+251"):
        return "0" + value[4:]
    if value.startswith("251") and len(value) == 12:
        return "0" + value[3:]
    return value


class Role(AbstractBaseModel):
    name = models.CharField(max_length=50, verbose_name=_("Name"))

    code = models.CharField(max_length=50, verbose_name=_("Code"))
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_roles')

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
    PHONE_CHANGE_LIMIT = 3
    PHONE_CHANGE_COOLDOWN = timedelta(days=7)

    email = models.EmailField(verbose_name=_("Email"), unique=True, null=False)
    phone = models.CharField(max_length=20, verbose_name=_("Phone Number"), blank=True, null=True)
    phone_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Phone Verified At"),
    )
    phone_change_count = models.PositiveSmallIntegerField(default=0, verbose_name=_("Phone Change Count"))
    phone_last_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Phone Last Changed At"),
    )
    last_known_lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Last Known Latitude"),
    )
    last_known_lng = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Last Known Longitude"),
    )
    location_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Location Updated At"),
    )
    location_permission_granted = models.BooleanField(
        default=False,
        verbose_name=_("Location Permission Granted"),
    )

    role = models.ForeignKey(
        Role, on_delete=models.RESTRICT, related_name="+", null=True
    )

    username = None
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)

    company = models.ForeignKey(
        'CompanyProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
        help_text=_('Company this staff member belongs to (for hired employees)')
    )

    individual_owner = models.ForeignKey(
        'IndividualOwnerProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
        help_text=_('Individual owner this staff works for (for small guesthouses/rentals)')
    )

    workspace_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'model__in': ['hotelprofile', 'guesthouseprofile', 'carlisting', 'eventspacelisting']}
    )
    workspace_object_id = models.UUIDField(null=True, blank=True)
    workspace = GenericForeignKey('workspace_content_type', 'workspace_object_id')

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-created_at",)
        db_table = "users"
        constraints = [
            models.CheckConstraint(
                check=Q(company__isnull=False) | Q(individual_owner__isnull=False) | 
                      (Q(company__isnull=True) & Q(individual_owner__isnull=True)),
                name='user_has_at_most_one_employer'
            )
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def phone_verified(self) -> bool:
        return self.phone_verified_at is not None

    def phone_change_cooldown_expires_at(self):
        if not self.phone_last_changed_at:
            return None
        return self.phone_last_changed_at + self.PHONE_CHANGE_COOLDOWN

    def _phone_change_error(self, message: str):
        raise ValidationError({"phone": message})

    def can_change_phone(self, phone: str | None):
        normalized_original_phone = normalize_phone_number(self.phone)
        normalized_new_phone = normalize_phone_number(phone)

        if normalized_original_phone == normalized_new_phone:
            return normalized_new_phone

        if self.phone_change_count >= self.PHONE_CHANGE_LIMIT:
            self._phone_change_error(
                "Phone number can only be changed three times. Please contact support if you need help."
            )

        cooldown_expires_at = self.phone_change_cooldown_expires_at()
        if cooldown_expires_at and timezone.now() < cooldown_expires_at:
            self._phone_change_error(
                "Phone number can only be changed once every 7 days. Please try again later."
            )

        return normalized_new_phone

    def _apply_phone_change_policy(self, original_phone: str | None):
        normalized_new_phone = self.can_change_phone(self.phone)
        self.phone = normalized_new_phone

        if normalize_phone_number(original_phone) == normalized_new_phone:
            return

        self.phone_change_count += 1
        self.phone_last_changed_at = timezone.now()
        self.phone_verified_at = None

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).only(
                "phone",
                "phone_change_count",
                "phone_last_changed_at",
                "phone_verified_at",
            ).first()
            if original:
                if normalize_phone_number(original.phone) != normalize_phone_number(self.phone):
                    self.phone_change_count = original.phone_change_count
                    self.phone_last_changed_at = original.phone_last_changed_at
                    self._apply_phone_change_policy(original.phone)
                    if update_fields is not None:
                        update_fields = set(update_fields)
                        update_fields.update({"phone", "phone_change_count", "phone_last_changed_at", "phone_verified_at"})
                        kwargs["update_fields"] = list(update_fields)
        else:
            self.phone = normalize_phone_number(self.phone)

        super().save(*args, **kwargs)


class OtpChallenge(AbstractBaseModel):
    class Purpose(models.TextChoices):
        LOGIN = "login", _("Login")
        SIGNUP = "signup", _("Signup")
        PASSWORD_CHANGE = "password_change", _("Password Change")
        GUEST_HOTEL_BOOKING = "guest_hotel_booking", _("Guest Hotel Booking")
        GUEST_GUESTHOUSE_BOOKING = "guest_guesthouse_booking", _("Guest Guesthouse Booking")
        GUEST_EVENTSPACE_BOOKING = "guest_eventspace_booking", _("Guest Event Space Booking")
        GUEST_CAR_RENTAL_BOOKING = "guest_car_rental_booking", _("Guest Car Rental Booking")
        GUEST_PROPERTY_RENTAL_BOOKING = "guest_property_rental_booking", _("Guest Property Rental Booking")
        GUEST_CAR_SALE_REVEAL = "guest_car_sale_reveal", _("Guest Car Sale Reveal")
        GUEST_PROPERTY_SALE_REVEAL = "guest_property_sale_reveal", _("Guest Property Sale Reveal")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="otp_challenges",
        verbose_name=_("User"),
        null=True,
        blank=True,
    )
    phone = models.CharField(max_length=20, verbose_name=_("Phone Number"))
    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.LOGIN,
        verbose_name=_("Purpose"),
    )
    code_hash = models.CharField(max_length=128, verbose_name=_("Code Hash"))
    expires_at = models.DateTimeField(verbose_name=_("Expires At"))
    consumed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Consumed At"))
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name=_("Attempts"))
    max_attempts = models.PositiveSmallIntegerField(default=5, verbose_name=_("Max Attempts"))
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent At"))

    class Meta:
        verbose_name = _("OTP Challenge")
        verbose_name_plural = _("OTP Challenges")
        db_table = "otp_challenges"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["phone", "purpose", "created_at"]),
            models.Index(fields=["user", "purpose", "consumed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.phone} - {self.purpose}"

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at


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
    class SplitTypeChoice(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage")
        FLAT = "flat", _("Flat")

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

    license = models.FileField(verbose_name=_("License"), blank=True, null=True,upload_to="company_licenses/")

    category = models.CharField(
        max_length=100, choices=CategoryChoice.choices, verbose_name=_("Category")
    )
    tin=models.CharField(max_length=15,verbose_name=_("Tin"),blank=True, null=True)
    business_license_number=models.CharField(max_length=50,verbose_name=_("Business License Number"),blank=True, null=True)
    description = models.TextField(verbose_name=_("Description"), blank=True)

    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="company_profile",
        verbose_name=_("Address"),
        help_text=_("Company headquarters address")
    )

    class StatusChoice(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    status = models.CharField(
        max_length=20,
        choices=StatusChoice.choices,
        default=StatusChoice.PENDING,
        verbose_name=_("Status"),
    )

    approved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Approved At"))

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Approved By"),
    )

    rejection_reason = models.TextField(null=True, blank=True, verbose_name=_("Rejection Reason"))

    class Meta:
        verbose_name = _("Company Profile")
        verbose_name_plural = _("Company Profiles")
        db_table = "company_profiles"

    def __str__(self) -> str:
        return f"{self.name}::{self.category}"

    chapa_subaccount_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Chapa Subaccount ID"),
        help_text=_("The subaccount ID for split payments (e.g., specific to this company)."),
    )
    split_type = models.CharField(
        max_length=20,
        choices=SplitTypeChoice.choices,
        null=True,
        blank=True,
        verbose_name=_("Split Type"),
        help_text=_("Optional owner-specific platform commission split type."),
    )
    split_value = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Split Value"),
        help_text=_("Optional owner-specific platform commission value."),
    )
    split_config_active = models.BooleanField(
        default=False,
        verbose_name=_("Split Config Active"),
        help_text=_("Use this owner's split config when complete."),
    )

    @property
    def is_approved(self) -> bool:
        return self.status == CompanyProfile.StatusChoice.APPROVED


class IndividualOwnerProfile(AbstractBaseModel):
    """This Model is aimed only for handling individual property owners.
    We don't needed neither to give individuals the ability to add properties
    through dashboard like companies. We need our admin to verify them
    in-person and add their detail here than using the AUTH_USER_MODEL.
    """

    class SplitTypeChoice(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage")
        FLAT = "flat", _("Flat")

    # class PropertyCategoryChoice(models.TextChoices):
    #     GUEST_HOUSE = "guest_house", _("Guest House")
    #     APARTMENT = "apartment", _("Apartment")
    #     CONDOMINIUM = "condominium", _("Condominium")
    #     VILLA = "villa", _("Villa")
    #     VEHICLE = "vehicle", _("Vehicle")

    first_name = models.CharField(max_length=255, verbose_name=_("First Name"))

    last_name = models.CharField(max_length=255, verbose_name=_("Last Name"))

    address = models.OneToOneField(
        Address,
        on_delete=models.RESTRICT,
        related_name="individual_owner_profile",
        verbose_name=_("Address"),
        help_text=_("Individual owner primary address")
    )

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

    chapa_subaccount_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Chapa Subaccount ID"),
        help_text=_("The subaccount ID for split payments (e.g., specific to this owner)."),
    )
    split_type = models.CharField(
        max_length=20,
        choices=SplitTypeChoice.choices,
        null=True,
        blank=True,
        verbose_name=_("Split Type"),
        help_text=_("Optional owner-specific platform commission split type."),
    )
    split_value = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Split Value"),
        help_text=_("Optional owner-specific platform commission value."),
    )
    split_config_active = models.BooleanField(
        default=False,
        verbose_name=_("Split Config Active"),
        help_text=_("Use this owner's split config when complete."),
    )


class OwnerComplianceAgreement(AbstractBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SIGNED = "signed", _("Signed")
        REVOKED = "revoked", _("Revoked")

    owner = models.ForeignKey(
        "IndividualOwnerProfile",
        on_delete=models.PROTECT,
        related_name="compliance_agreements",
        verbose_name=_("Individual Owner"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Status"),
    )
    signed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Signed At"),
    )
    signed_by_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signed_owner_compliance_agreements",
        verbose_name=_("Signed By Admin"),
    )
    agreement_version = models.CharField(
        max_length=50,
        verbose_name=_("Agreement Version"),
    )
    note = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Note"),
    )

    class Meta:
        verbose_name = _("Owner Compliance Agreement")
        verbose_name_plural = _("Owner Compliance Agreements")
        db_table = "owner_compliance_agreements"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.owner}::{self.status}::{self.agreement_version}"


class HotelProfile(GeoLocatedModel):
    # class CategoryChoice(models.TextChoices):
    #     HOTEL = "hotel", _("Hotel")
    #     PENSION = "pension", _("Pension")

    company = models.ForeignKey(
        CompanyProfile, on_delete=models.CASCADE, related_name="hotels"
    )
    
    name = models.CharField(max_length=255, verbose_name=_("Hotel Name"), default="Hotel Name")
    description = models.TextField(verbose_name=_("Description"), blank=True)
    phone = models.CharField(max_length=20, verbose_name=_("Phone Number"), blank=True, null=True)
    website = models.URLField(verbose_name=_("Website"), blank=True, null=True)
    
    logo = models.ImageField(verbose_name=_("Logo"), upload_to="hotel/logos/", blank=True, null=True)
    
    license = models.FileField(verbose_name=_("Business License"), upload_to="hotel/licenses/", blank=True, null=True)
    
    address = models.OneToOneField(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hotel_profile",
        verbose_name=_("Address"),
    )

    images = GenericRelation(ListingImage, related_query_name="listings")

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Whether the hotel is active and visible."),
    )

    is_verified = models.BooleanField(
        default=False,
        verbose_name=_("Is Verified"),
        help_text=_("Whether the hotel has been verified by an administrator."),
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Verified At"),
        help_text=_("When the hotel was last verified by an administrator."),
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Verified By"),
        help_text=_("Administrator who last verified this hotel."),
    )

    verification_note = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name=_("Verification Note"),
        help_text=_("Optional note recorded by an administrator during verification."),
    )

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
