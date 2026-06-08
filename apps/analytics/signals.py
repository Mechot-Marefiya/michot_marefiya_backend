from datetime import timedelta
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.listing.models import (
    Booking,
    BookingItem,
    CarRental,
    CarRentalItem,
    EventSpaceBooking,
    EventSpaceBookingItem,
    GuestHouseBooking,
    GuestHouseBookingItem,
)
from apps.analytics.models import AnalyticsDirtyDate


def _mark_dirty(company_id, dt):
    if not company_id or not dt:
        return
    AnalyticsDirtyDate.objects.update_or_create(
        company_id=company_id, date=dt, defaults={"processed": False}
    )


def _mark_date_range(company_ids, created_at=None, start_date=None, end_date=None):
    created_date = created_at.date() if created_at else None
    for company_id in company_ids:
        if created_date:
            _mark_dirty(company_id, created_date)
        if start_date:
            _mark_dirty(company_id, start_date)
        if end_date:
            try:
                _mark_dirty(company_id, end_date - timedelta(days=1))
            except Exception:
                pass


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

    _mark_date_range(
        company_ids,
        created_at=getattr(instance, "created_at", None),
        start_date=getattr(instance, "check_in_date", None),
        end_date=getattr(instance, "check_out_date", None),
    )


@receiver(post_save, sender=BookingItem)
@receiver(post_delete, sender=BookingItem)
def booking_item_changed(sender, instance, **kwargs):
    booking_changed(sender=Booking, instance=instance.booking, **kwargs)


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

    start_date = getattr(instance, "start_date", None)

    for cid in company_ids:
        _mark_date_range(
            [cid],
            created_at=getattr(instance, "created_at", None),
            start_date=start_date,
            end_date=getattr(instance, "end_date", None),
        )


@receiver(post_save, sender=CarRentalItem)
@receiver(post_delete, sender=CarRentalItem)
def car_rental_item_changed(sender, instance, **kwargs):
    car_rental_changed(sender=CarRental, instance=instance.car_rental, **kwargs)


@receiver(post_save, sender=GuestHouseBooking)
@receiver(post_delete, sender=GuestHouseBooking)
def guesthouse_booking_changed(sender, instance, **kwargs):
    company_ids = set()
    try:
        for item in instance.items.all():
            room = getattr(item, "room", None)
            guest_house = getattr(room, "guest_house", None)
            company = getattr(guest_house, "company", None)
            if company:
                company_ids.add(company.id)
    except Exception:
        pass

    _mark_date_range(
        company_ids,
        created_at=getattr(instance, "created_at", None),
        start_date=getattr(instance, "start_date", None),
        end_date=getattr(instance, "end_date", None),
    )


@receiver(post_save, sender=GuestHouseBookingItem)
@receiver(post_delete, sender=GuestHouseBookingItem)
def guesthouse_booking_item_changed(sender, instance, **kwargs):
    guesthouse_booking_changed(sender=GuestHouseBooking, instance=instance.booking, **kwargs)


@receiver(post_save, sender=EventSpaceBooking)
@receiver(post_delete, sender=EventSpaceBooking)
def eventspace_booking_changed(sender, instance, **kwargs):
    company_ids = set()
    try:
        for item in instance.items.all():
            event_space = getattr(item, "event_space", None)
            hotel = getattr(event_space, "hotel", None)
            company = getattr(hotel, "company", None)
            if company:
                company_ids.add(company.id)
    except Exception:
        pass

    _mark_date_range(
        company_ids,
        created_at=getattr(instance, "created_at", None),
        start_date=getattr(instance, "check_in_date", None),
        end_date=getattr(instance, "check_out_date", None),
    )


@receiver(post_save, sender=EventSpaceBookingItem)
@receiver(post_delete, sender=EventSpaceBookingItem)
def eventspace_booking_item_changed(sender, instance, **kwargs):
    eventspace_booking_changed(sender=EventSpaceBooking, instance=instance.booking, **kwargs)
