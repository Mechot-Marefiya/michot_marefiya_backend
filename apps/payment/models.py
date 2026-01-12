from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from apps.core.models import AbstractBaseModel


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
