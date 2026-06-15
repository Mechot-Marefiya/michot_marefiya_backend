from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from apps.core.models import AbstractBaseModel


class PaymentPlatformConfig(AbstractBaseModel):
    class SplitType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FLAT = "flat", "Flat"

    name = models.CharField(max_length=100, default="default", unique=True)
    is_active = models.BooleanField(default=True)
    default_split_type = models.CharField(
        max_length=20,
        choices=SplitType.choices,
        default=SplitType.PERCENTAGE,
        help_text="Default platform commission split type.",
    )
    default_split_value = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0200"),
        help_text="Default platform commission. For percentage, 0.02 means 2%.",
    )
    default_car_sale_reveal_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("100.00"),
        help_text="Default contact reveal fee for car sale listings.",
    )
    default_property_sale_reveal_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("100.00"),
        help_text="Default contact reveal fee for property sale listings.",
    )

    class Meta:
        verbose_name = "Payment Platform Config"
        verbose_name_plural = "Payment Platform Configs"
        db_table = "payment_platform_configs"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name="one_active_payment_platform_config",
            ),
        ]

    def clean(self):
        super().clean()
        if self.default_split_value < Decimal("0.0000"):
            raise ValidationError({"default_split_value": "Split value cannot be negative."})
        if (
            self.default_split_type == self.SplitType.PERCENTAGE
            and self.default_split_value > Decimal("1.0000")
        ):
            raise ValidationError(
                {"default_split_value": "Percentage split value must be between 0 and 1."}
            )
        if self.default_car_sale_reveal_fee <= Decimal("0.00"):
            raise ValidationError(
                {"default_car_sale_reveal_fee": "Car sale reveal fee must be greater than 0."}
            )
        if self.default_property_sale_reveal_fee <= Decimal("0.00"):
            raise ValidationError(
                {"default_property_sale_reveal_fee": "Property sale reveal fee must be greater than 0."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.name} payment config ({status})"


class PaymentTransaction(AbstractBaseModel):
#   supports Booking (hotel rooms), GuestHouseBooking, EventSpaceBooking, CarRental
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
    
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Type of booking (Booking, GuestHouseBooking, etc.)"
    )
    object_id = models.UUIDField(
        null=True, 
        blank=True,
        help_text="ID of the booking object"
    )
    booking_object = GenericForeignKey('content_type', 'object_id')
    
    booking_type = models.CharField(
        max_length=50,
        choices=[
            ('booking', 'Hotel Room'),
            ('guesthouse', 'Guesthouse'),
            ('eventspace', 'Event Space'),
            ('carrental', 'Car Rental'),
            ('carrental_extension', 'Car Rental Extension'),
            ('propertyrental', 'Property Rental'),
            ('contact_reveal', 'Contact Reveal'),
        ],
        default='booking',
        help_text="Discriminator for the type of booking"
    )
    
    booking = models.ForeignKey(
        'listing.Booking', 
        on_delete=models.CASCADE, 
        related_name='payment_transactions',
        null=True, 
        blank=True,
        help_text="Legacy field for hotel room bookings only - use booking_object instead"
    )
    
    tx_ref = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ETB")
    status = models.CharField(
        max_length=20, 
        choices=PaymentStatus.choices, 
        default=PaymentStatus.PENDING
    )
    chapa_transaction_id = models.CharField(max_length=255, null=True, blank=True)
    payment_method = models.CharField(max_length=100, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="The rate used for this transaction (e.g. 0.05)"
    )
    commission_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Amount taken as platform fee"
    )
    vendor_payout_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Amount sent to the vendor subaccount"
    )

    class TaxLiabilityStatus(models.TextChoices):
        APPLICABLE = "applicable", "Applicable"
        NOT_APPLICABLE = "not_applicable", "Not Applicable"

    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Tax amount collected for eligible property rental transactions"
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Tax rate used for eligible property rental transactions"
    )
    tax_liability_status = models.CharField(
        max_length=30,
        choices=TaxLiabilityStatus.choices,
        null=True,
        blank=True,
        help_text="Tax applicability status for this transaction"
    )

    class DisputeStatus(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under Review"
        ESCALATED = "escalated", "Escalated"
        RESOLVED = "resolved", "Resolved"

    dispute_status = models.CharField(
        max_length=30,
        choices=DisputeStatus.choices,
        null=True,
        blank=True,
        help_text="Admin dispute triage status for this transaction"
    )
    dispute_note = models.TextField(
        null=True,
        blank=True,
        help_text="Latest admin note for transaction dispute triage"
    )
    dispute_opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When dispute triage was opened"
    )
    dispute_resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When dispute triage was resolved"
    )
    dispute_handled_by = models.ForeignKey(
        'account.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handled_payment_disputes',
        help_text="Admin currently responsible for dispute triage"
    )
    
    class PayoutStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid (Split Success)"
        FAILED = "failed", "Failed (Split Error)"
        NOT_APPLICABLE = "na", "Not Applicable"

    payout_status = models.CharField(
        max_length=20,
        choices=PayoutStatus.choices,
        default=PayoutStatus.PENDING,
        help_text="Status of the vendor payout split"
    )

    vendor_company = models.ForeignKey(
        'account.CompanyProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
        help_text="Direct link to vendor company for ledger queries"
    )
    vendor_individual = models.ForeignKey(
        'account.IndividualOwnerProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
        help_text="Direct link to individual owner for ledger queries"
    )
    
    class Meta:
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions"
        db_table = "payment_transactions"
        ordering = ["-created_at"]
    
    @property
    def resolved_booking(self):
        """
        Return the bookingobject regardless of storage method (GFK or legacy FK).
        Prioritizes GenericForeignKey over legacy ForeignKey.
        """
        return self.booking_object or self.booking
    
    def __str__(self):
        return f"Payment {self.tx_ref} - {self.status}"
