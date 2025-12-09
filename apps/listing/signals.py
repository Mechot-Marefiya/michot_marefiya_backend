from datetime import timedelta
from django.dispatch import receiver
from django.db.models import F
from django.db.models.signals import post_save, post_delete
from apps.listing.models import Booking, StayAvailability
from django.conf import settings
from datetime import timedelta

# Adjust imports based on your actual app structure
from apps.listing.models import Booking 
from apps.listing.tasks import auto_cancel_pending_booking 

# @receiver(post_save, sender=Booking)
# def mark_room_unavailable(sender, instance, created, **kwargs):
#     if created:
#         StayAvailability.objects.filter(
#             room=instance.room,
#             date__gte=instance.check_in_date,
#             date__lt=instance.check_out_date,
#         ).update(available_rooms=F("available_rooms") - 1)


# @receiver(post_delete, sender=Booking)
# def restore_room_availability(sender, instance, **kwargs):
#     StayAvailability.objects.filter(
#         room=instance.room,
#         date__gte=instance.check_in_date,
#         date__lt=instance.check_out_date,
#     ).update(available_rooms=F("available_rooms") - 1)


# @receiver(post_save, sender=Booking)
# def update_availability(sender, instance, **kwargs):
#     room_type = instance.room_type
#     date_cursor = instance.check_in_date
#     while date_cursor < instance.check_out_date:
#         StayAvailability.objects.filter(
#             hotel=instance.hotel, room_type=room_type, date=date_cursor
#         ).update(available_rooms=F("available_rooms") - 1)
#         date_cursor += timedelta(days=1)
@receiver(post_save, sender=Booking)
def schedule_auto_cancel(sender, instance, created, **kwargs):
    """
    Schedules an auto-cancellation task if a new Booking is created 
    with a PENDING status.
    """
    if created and instance.status == Booking.BookingStatus.PENDING:
        # Get timeout minutes from settings, default to 15 if not found
        timeout_minutes = getattr(settings, 'BOOKING_PENDING_TIMEOUT_MINUTES', 15)
        
        # Schedule the task to run 'timeout_minutes' seconds from now
        auto_cancel_pending_booking.apply_async(
            args=[instance.id], 
            countdown=60 * timeout_minutes 
        )