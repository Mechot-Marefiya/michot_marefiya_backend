from datetime import timedelta
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db import transaction, models
from django.conf import settings
from apps.listing.models import Booking, GuestHouseBooking
from apps.listing.tasks import auto_cancel_pending_booking, auto_cancel_pending_guesthouse_booking 

@receiver(post_save, sender=Booking)
def schedule_auto_cancel(sender, instance, created, **kwargs):

    if created and instance.status == Booking.BookingStatus.PENDING:
        timeout_minutes = getattr(settings, 'BOOKING_PENDING_TIMEOUT_MINUTES', 15)
        
        transaction.on_commit(
            lambda: auto_cancel_pending_booking.apply_async(
                args=[instance.id], 
                countdown=60 * timeout_minutes 
            )
        )

@receiver(post_save, sender=GuestHouseBooking)
def schedule_guesthouse_auto_cancel(sender, instance, created, **kwargs):
    if created and instance.status == GuestHouseBooking.RentStatus.PENDING:
        timeout_minutes = getattr(settings, 'BOOKING_PENDING_TIMEOUT_MINUTES', 15)
        
        transaction.on_commit(
            lambda: auto_cancel_pending_guesthouse_booking.apply_async(
                args=[instance.id], 
                countdown=60 * timeout_minutes 
            )
        )

@receiver(post_save, sender="listing.GuestHouseRoom")
def auto_create_guesthouse_inventory(sender, instance, created, **kwargs):
    if created:
        from apps.listing.services import GuestHouseAvailabilityService
        transaction.on_commit(
            lambda: GuestHouseAvailabilityService.create_availability(
                instance, instance.total_units
            )
        )

@receiver(post_save, sender="listing.GuestHouseRoom")
def sync_guesthouse_profile_price(sender, instance, **kwargs):
    profile = instance.guest_house
    min_price = profile.rooms.all().aggregate(models.Min('base_price'))['base_price__min']
    if min_price and profile.base_price != min_price:
        profile.base_price = min_price
        profile.save(update_fields=['base_price'])