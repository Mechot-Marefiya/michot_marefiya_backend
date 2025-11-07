from datetime import timedelta
from django.dispatch import receiver
from django.db.models import F
from django.db.models.signals import post_save, post_delete
from apps.listing.models import Booking, StayAvailability


@receiver(post_save, sender=Booking)
def mark_room_unavailable(sender, instance, created, **kwargs):
    if created:
        StayAvailability.objects.filter(
            room=instance.room,
            date__gte=instance.check_in_date,
            date__lt=instance.check_out_date,
        ).update(available_rooms=F("available_rooms") - 1)


@receiver(post_delete, sender=Booking)
def restore_room_availability(sender, instance, **kwargs):
    StayAvailability.objects.filter(
        room=instance.room,
        date__gte=instance.check_in_date,
        date__lt=instance.check_out_date,
    ).update(available_rooms=F("available_rooms") - 1)


@receiver(post_save, sender=Booking)
def update_availability(sender, instance, **kwargs):
    room_type = instance.room_type
    date_cursor = instance.check_in_date
    while date_cursor < instance.check_out_date:
        StayAvailability.objects.filter(
            hotel=instance.hotel, room_type=room_type, date=date_cursor
        ).update(available_rooms=F("available_rooms") - 1)
        date_cursor += timedelta(days=1)
