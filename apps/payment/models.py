from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AbstractBaseModel
from apps.listing.models import Booking

class PaymentTransaction(AbstractBaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUCCESS = "success", _("Success")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="payment_transactions"
    )
    
    tx_ref = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ETB")
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )
    chapa_transaction_id = models.CharField(max_length=255, blank=True, null=True)
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = "payment_transactions"
        ordering = ["-created_at"]
        verbose_name = _("Payment Transaction")
        verbose_name_plural = _("Payment Transactions")

    def __str__(self):
        return f"Payment {self.tx_ref} - {self.status}"