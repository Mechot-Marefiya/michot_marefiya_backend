from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import AbstractBaseModel


class PromotionCampaign(AbstractBaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SCHEDULED = "scheduled", _("Scheduled")
        ACTIVE = "active", _("Active")
        PAUSED = "paused", _("Paused")
        EXPIRED = "expired", _("Expired")

    name = models.CharField(max_length=255)
    advertiser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="promotion_campaigns",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class PromotionPlacement(AbstractBaseModel):
    class SlotType(models.TextChoices):
        FEATURED_LISTING = "featured_listing", _("Featured Listing")
        CATEGORY_BANNER = "category_banner", _("Category Banner")
        SEARCH_TOP = "search_top", _("Top of Search Results")
        HOME_BANNER = "home_banner", _("Home Banner")

    campaign = models.ForeignKey(
        PromotionCampaign,
        on_delete=models.CASCADE,
        related_name="placements",
    )
    slot_type = models.CharField(max_length=40, choices=SlotType.choices)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")
    target_category = models.CharField(max_length=100, null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        target = self.content_object or self.target_category or "untargeted"
        return f"{self.campaign.name} - {self.slot_type} - {target}"


class PromotionImpression(AbstractBaseModel):
    placement = models.ForeignKey(
        PromotionPlacement,
        on_delete=models.CASCADE,
        related_name="impressions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_impressions",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]


class PromotionClick(AbstractBaseModel):
    placement = models.ForeignKey(
        PromotionPlacement,
        on_delete=models.CASCADE,
        related_name="clicks",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_clicks",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
