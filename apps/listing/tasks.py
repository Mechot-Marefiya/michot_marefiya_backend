from apps.listing.services import StayAvailabilityService
from datetime import timedelta
from django.utils import timezone
from django.db.models import F
from django.conf import settings
from django.db import transaction

from config.celery import app

from apps.listing.models import Booking 
from apps.listing.services import BookingService

def track_availability(days_ahead=180):
    return StayAvailabilityService.ensure_future_availability(days_ahead=days_ahead)
@app.task
def auto_cancel_pending_booking(booking_id):
    """
    Task to cancel a booking if it is still in the PENDING status 
    15 minutes after creation.
    """
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(id=booking_id)
            
            # Use the status from the object we just locked
            if booking.status != Booking.BookingStatus.PENDING:
                print(f"Booking {booking_id} is no longer PENDING (status: {booking.status}), skipping.")
                return

            # Call the centralized cancellation service which handles inventory release
            BookingService.cancel_booking(booking)
            print(f"Successfully auto-cancelled abandoned booking {booking_id}")
            
    except Booking.DoesNotExist:
            print(f"Booking {booking_id} status is {booking.status}, skipping auto-cancellation.")
            
    except Booking.DoesNotExist:
        print(f"Booking {booking_id} not found for auto-cancellation.")
    except Exception as e:
        print(f"An error occurred while auto-cancelling booking {booking_id}: {e}")