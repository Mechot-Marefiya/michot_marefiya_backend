from datetime import timedelta
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db import transaction
from django.conf import settings
from apps.listing.models import Booking 
from apps.listing.tasks import auto_cancel_pending_booking 

@receiver(post_save, sender=Booking)
def schedule_auto_cancel(sender, instance, created, **kwargs):
    """
    Schedules an auto-cancellation task if a new Booking is created 
    with a PENDING status.
    """
    if created and instance.status == Booking.BookingStatus.PENDING:
        # Get timeout minutes from settings, default to 15 if not found
        timeout_minutes = getattr(settings, 'BOOKING_PENDING_TIMEOUT_MINUTES', 15)
        
        # We use on_commit to ensure the task is only scheduled AFTER the 
        # booking has been safely written to the database. This prevents
        # the task from starting and not finding the record yet.
        transaction.on_commit(
            lambda: auto_cancel_pending_booking.apply_async(
                args=[instance.id], 
                countdown=60 * timeout_minutes 
            )
        )