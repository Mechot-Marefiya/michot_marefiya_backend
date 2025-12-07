from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AbstractBaseModel


class CompanyDailyMetrics(AbstractBaseModel):
    company_id = models.UUIDField(db_index=True)
    date = models.DateField()

    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bookings_count = models.IntegerField(default=0)
    confirmed_count = models.IntegerField(default=0)
    cancelled_count = models.IntegerField(default=0)
    avg_booking_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # optional cached structures for quick UI use
    top_listings = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "company_daily_metrics"
        unique_together = ("company_id", "date")


class ListingDailyMetrics(AbstractBaseModel):
    listing_id = models.UUIDField(db_index=True)
    company_id = models.UUIDField(db_index=True)
    date = models.DateField()

    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bookings_count = models.IntegerField(default=0)
    avg_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "listing_daily_metrics"
        unique_together = ("listing_id", "date")
