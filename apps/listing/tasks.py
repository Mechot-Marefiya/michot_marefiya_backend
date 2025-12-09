from apps.listing.services import StayAvailabilityService
from datetime import timedelta
from django.utils import timezone
from django.db.models import F
from django.conf import settings
# Import your Celery app instance from the new location
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
        booking = Booking.objects.get(id=booking_id)
        time_limit = getattr(settings, 'BOOKING_PENDING_TIMEOUT_MINUTES', 15)
        
        if booking.status == Booking.BookingStatus.PENDING and \
           booking.created_at < timezone.now() - timedelta(minutes=time_limit):
           
            # Update availability first (like in BookingService.cancel_booking)
            for item in booking.items.all():
                
                StayAvailabilityService.update_availability( 
                    hotel=item.room.hotel,
                    rooms_info=[
                        {"room": item.room, "quantity": item.units_booked}],
                    check_in_date=booking.check_in_date,
                    check_out_date=booking.check_out_date,
                    increment=True,
                )
            
            # Set status to CANCELLED and save
            booking.status = Booking.BookingStatus.CANCELLED
            booking.save()
            print(f"Auto-cancelled booking {booking_id}")
            
        else:
            print(f"Booking {booking_id} status is {booking.status}, skipping auto-cancellation.")
            
    except Booking.DoesNotExist:
        print(f"Booking {booking_id} not found for auto-cancellation.")
    except Exception as e:
        print(f"An error occurred while auto-cancelling booking {booking_id}: {e}")