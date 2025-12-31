import logging
from apps.listing.services import StayAvailabilityService
from django.db import transaction
from config.celery import app
from apps.listing.models import Booking 
from apps.listing.services import BookingService

logger = logging.getLogger(__name__)

def track_availability(days_ahead=180):
    return StayAvailabilityService.ensure_future_availability(days_ahead=days_ahead)

@app.task
def auto_cancel_pending_booking(booking_id):
    """
    Task to cancel a booking if it is still in the PENDING status 
    15 minutes after creation.
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