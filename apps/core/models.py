import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class AbstractBaseModel(models.Model):
    id = models.UUIDField(
        primary_key=True, editable=False, default=uuid.uuid4, verbose_name=_("Id")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated_at"))

    class Meta:
        abstract = True


class Address(AbstractBaseModel):
    street_line1 = models.CharField(max_length=255)

    country = models.TextField(
        max_length=100, verbose_name=_("Country"), default="Ethiopia"
    )

    city = models.CharField(max_length=100, verbose_name=_("City"))

    sub_city = models.CharField(max_length=100, verbose_name=_("Sub City"), blank=True)

    state = models.CharField(max_length=100, blank=True)

    postal_code = models.CharField(max_length=20, blank=True)

    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, blank=True, null=True
    )

    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, blank=True, null=True
    )

    class Meta:
        verbose_name = _("Address")
        verbose_name_plural = _("Addresses")
        db_table = "addresses"

    def __str__(self) -> str:
        return f"{self.city} - {self.street_line1}"


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


class CurrencyRate(AbstractBaseModel):
    """
    Stores the exchange rate between two currencies for a specific date.

    Typically updated once per day by a background task,
    and used across the application for consistent currency conversion.

    Example:
        1 USD = 151.68 ETB
        base="USD", target="ETB", rate=91.2534
    """

    base = models.CharField(
        max_length=3,
        verbose_name=_("base currency"),
        help_text=_(
            "The ISO 4217 currency code from which conversion starts, e.g., 'USD'."
        ),
    )

    target = models.CharField(
        verbose_name=_("target currency"),
        max_length=3,
        help_text=_(
            "The ISO 4217 currency code to which conversion applies, e.g., 'ETB'."
        ),
    )

    rate = models.DecimalField(
        verbose_name=_("exchange rate"),
        max_digits=12,
        decimal_places=6,
        help_text=_(
            "Exchange rate value for converting 1 unit of base currency into target currency."
        ),
    )

    date = models.DateField(
        verbose_name=_("rate date"),
        auto_now_add=True,
        help_text=_("The date when this rate was recorded."),
    )

    class Meta:
        verbose_name = _("Currency Rate")
        verbose_name_plural = _("Currency Rates")
        ordering = ["-date", "base", "target"]
        constraints = [
            models.UniqueConstraint(
                fields=["base", "target", "date"], name="base_target_date_idx"
            )
        ]
        indexes = [
            models.Index(fields=["base", "target", "date"]),
        ]

    def __str__(self):
        return f"1 {self.base} = {self.rate} {self.target} ({self.date})"


# class DataLookup(AbstractBaseModel):
#     lookup_type = models.CharField(max_length=50)
#     key = models.CharField(max_length=50)
#     value = models.CharField(max_length=255)
#     display_name = models.CharField(
#         max_length=100, blank=True
#     )
#     sort_order = models.PositiveIntegerField(default=0)
#     is_active = models.BooleanField(default=True)
#     is_default = models.BooleanField(default=False)
#     metadata = models.JSONField(default=dict, blank=True)

#     class Meta:
#         db_table = "data_lookups"
#         constraints = [
#             # Unique key within each lookup type
#             models.UniqueConstraint(
#                 fields=["lookup_type", "key"],
#                 name="unique_key_per_lookup_type"
#             ),
#             # Only one default per lookup type
#             models.UniqueConstraint(
#                 fields=["lookup_type"],
#                 condition=models.Q(is_default=True),
#                 name="one_default_per_lookup_type"
#             )
#         ]
#         indexes = [
#             models.Index(fields=["lookup_type", "is_active"]),
#             models.Index(fields=["lookup_type", "sort_order"]),
#         ]

#     def __str__(self):
#         return f"{self.lookup_type}: {self.display_name or self.key}"
