from datetime import timedelta
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.listing.models import Booking, CarRental
from apps.analytics.models import AnalyticsDirtyDate


def _mark_dirty(company_id, dt):
    if not company_id or not dt:
        return
    AnalyticsDirtyDate.objects.update_or_create(
        company_id=company_id, date=dt, defaults={"processed": False}
    )


@receiver(post_save, sender=Booking)
@receiver(post_delete, sender=Booking)
def booking_changed(sender, instance, **kwargs):
    # mark created_at and stay range days as dirty for the owning company
    try:
        items = instance.items.all()
    except Exception:
        items = []

    company_ids = set()
    for item in items:
        room = getattr(item, "room", None)
        if room and getattr(room, "hotel", None) and getattr(room.hotel, "company", None):
            company_ids.add(room.hotel.company.id)

    # also try to infer from booking items
    created_date = getattr(instance, "created_at", None)
    if created_date:
        created_date = created_date.date()

    # mark booking check-in/check-out dates
    check_in = getattr(instance, "check_in_date", None)
    check_out = getattr(instance, "check_out_date", None)

    for cid in company_ids:
        if created_date:
            _mark_dirty(cid, created_date)
        if check_in:
            _mark_dirty(cid, check_in)
        if check_out:
            # also mark the last night (check_out - 1)
            try:
                last_night = check_out - timedelta(days=1)
                _mark_dirty(cid, last_night)
            except Exception:
                pass


@receiver(post_save, sender=CarRental)
@receiver(post_delete, sender=CarRental)
def car_rental_changed(sender, instance, **kwargs):
    # mark created_at and start_date for car rentals affecting company
    company_ids = set()
    try:
        for item in instance.rental_items.all():
            car = getattr(item, "car_listing", None)
            if car and getattr(car, "company", None):
                company_ids.add(car.company.id)
    except Exception:
        pass

    created_date = getattr(instance, "created_at", None)
    if created_date:
        created_date = created_date.date()

    start_date = getattr(instance, "start_date", None)

    for cid in company_ids:
        if created_date:
            _mark_dirty(cid, created_date)
        if start_date:
            _mark_dirty(cid, start_date)
