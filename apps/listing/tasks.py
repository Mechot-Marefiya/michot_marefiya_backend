import logging
from datetime import timedelta
from django.utils import timezone
from apps.listing.services import StayAvailabilityService
from django.db import transaction
from django.conf import settings
from config.celery import app
from apps.listing.models import Booking, GuestHouseBooking
from apps.listing.services import BookingService, GuestHouseBookingService

logger = logging.getLogger(__name__)

def track_availability(days_ahead=180):
    hotel_created = StayAvailabilityService.ensure_future_availability(days_ahead=days_ahead)
    from apps.listing.services import GuestHouseAvailabilityService
    gh_created = GuestHouseAvailabilityService.ensure_future_availability(days_ahead=days_ahead)
    return hotel_created + gh_created

@app.task
def auto_cancel_pending_booking(booking_id):
    """
    Task to cancel a booking if it is still in the PENDING status 
    15 minutes (or BOOKING_PENDING_TIMEOUT_MINUTES) after creation.
    """
    logger.info(f"Starting auto-cancellation check for booking {booking_id}")
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(id=booking_id)
            
            # Use the status from the object we just locked
            if booking.status != Booking.BookingStatus.PENDING:
                logger.info(f"Booking {booking_id} is no longer PENDING (status: {booking.status}), skipping.")
                return

            # Call the centralized cancellation service which handles inventory release
            BookingService.cancel_booking(booking)
            logger.info(f"Successfully auto-cancelled abandoned booking {booking_id}")
            
    except Booking.DoesNotExist:
        logger.warning(f"Booking {booking_id} not found for auto-cancellation.")
    except Exception as e:
        logger.exception(f"Unexpected error while auto-cancelling booking {booking_id}: {e}")

@app.task
def auto_cancel_pending_guesthouse_booking(booking_id):
    logger.info(f"Starting auto-cancellation check for GuestHouse booking {booking_id}")
    try:
        with transaction.atomic():
            booking = GuestHouseBooking.objects.select_for_update().get(id=booking_id)
            
            if booking.status != GuestHouseBooking.RentStatus.PENDING:
                logger.info(f"GuestHouseBooking {booking_id} is no longer PENDING (status: {booking.status}), skipping.")
                return

            GuestHouseBookingService.cancel_booking(booking)
            logger.info(f"Successfully auto-cancelled abandoned GuestHouse booking {booking_id}")
            
    except GuestHouseBooking.DoesNotExist:
        logger.warning(f"GuestHouseBooking {booking_id} not found for auto-cancellation.")
    except Exception as e:
        logger.exception(f"Unexpected error while auto-cancelling GuestHouse booking {booking_id}: {e}")

@app.task
def cancel_all_expired_bookings():
    """
    Periodic task to clean up all bookings that have been in PENDING 
    status longer than the allowed timeout. This acts as a safety net 
    for the signal-based individual tasks.
    """
    timeout_minutes = getattr(settings, 'BOOKING_PENDING_TIMEOUT_MINUTES', 15)
    threshold = timezone.now() - timedelta(minutes=timeout_minutes)
    
    expired_bookings = Booking.objects.filter(
        status=Booking.BookingStatus.PENDING,
        created_at__lte=threshold
    )
    
    count = expired_bookings.count()
    if count > 0:
        logger.info(f"Found {count} expired pending bookings. Starting mass cancellation...")
        for booking in expired_bookings:
            # We call the individual task asynchronously for each to reuse the locking logic
            auto_cancel_pending_booking.delay(booking.id)
    
    expired_gh_bookings = GuestHouseBooking.objects.filter(
        status=GuestHouseBooking.RentStatus.PENDING,
        created_at__lte=threshold
    )
    gh_count = expired_gh_bookings.count()
    if gh_count > 0:
        logger.info(f"Found {gh_count} expired pending guesthouse bookings. Starting mass cancellation...")
        for gh_booking in expired_gh_bookings:
            auto_cancel_pending_guesthouse_booking.delay(gh_booking.id)
    else:
        logger.debug("No expired pending guesthouse bookings found during periodic sweep.")