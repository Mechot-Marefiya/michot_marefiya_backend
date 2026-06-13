import logging
from datetime import timedelta
from django.apps import apps
from django.utils import timezone
from apps.listing.services import StayAvailabilityService
from django.db import transaction
from django.conf import settings
from config.celery import app
from apps.listing.models import (
    Booking,
    ContactRevealRequest,
    GuestHouseBooking,
    PropertyContactRevealRequest,
    PropertyRentalBooking,
)
from apps.listing.services import BookingService, GuestHouseBookingService, PropertyRentalBookingService
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from services.sms import send_sms
from services.maps import GeocodingError, geocode_address

logger = logging.getLogger(__name__)
GEOCODING_RETRY_DELAYS = (30, 120, 300)


def _build_address_text(address) -> str:
    if not address:
        return ""

    parts = [
        getattr(address, "street_line1", None),
        getattr(address, "sub_city", None),
        getattr(address, "city", None),
        getattr(address, "state", None),
        getattr(address, "postal_code", None),
        getattr(address, "country", None),
    ]
    return ", ".join(str(part).strip() for part in parts if part and str(part).strip())


def _resolve_model(model_label: str):
    if not model_label or "." not in model_label:
        return None

    app_label, model_name = model_label.split(".", 1)
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None

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
def auto_cancel_pending_property_rental_booking(booking_id):
    logger.info(f"Starting auto-cancellation check for PropertyRental booking {booking_id}")
    try:
        with transaction.atomic():
            booking = PropertyRentalBooking.objects.select_for_update().get(id=booking_id)

            if booking.status != PropertyRentalBooking.RentStatus.PENDING:
                logger.info(
                    f"PropertyRentalBooking {booking_id} is no longer PENDING "
                    f"(status: {booking.status}), skipping."
                )
                return

            PropertyRentalBookingService.cancel_booking(booking)
            logger.info(f"Successfully auto-cancelled abandoned PropertyRental booking {booking_id}")

    except PropertyRentalBooking.DoesNotExist:
        logger.warning(f"PropertyRentalBooking {booking_id} not found for auto-cancellation.")
    except Exception as e:
        logger.exception(f"Unexpected error while auto-cancelling PropertyRental booking {booking_id}: {e}")


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

    expired_property_bookings = PropertyRentalBooking.objects.filter(
        status=PropertyRentalBooking.RentStatus.PENDING,
        created_at__lte=threshold
    )
    property_count = expired_property_bookings.count()
    if property_count > 0:
        logger.info(f"Found {property_count} expired pending property rental bookings. Starting mass cancellation...")
        for property_booking in expired_property_bookings:
            auto_cancel_pending_property_rental_booking.delay(property_booking.id)
    else:
        logger.debug("No expired pending property rental bookings found during periodic sweep.")


@app.task
def send_contact_reveal_unlocked_notification(reveal_request_id):
    reveal_request = None
    for request_model in (ContactRevealRequest, PropertyContactRevealRequest):
        try:
            reveal_request = request_model.objects.select_related("buyer", "listing").get(
                id=reveal_request_id
            )
            break
        except request_model.DoesNotExist:
            continue

    if reveal_request is None:
        logger.warning("Contact reveal request %s not found for notification.", reveal_request_id)
        return False

    if reveal_request.status != reveal_request.RevealStatus.PAID_REVEALED:
        logger.info(
            "Skipping contact reveal notification for %s in status %s.",
            reveal_request_id,
            reveal_request.status,
        )
        return False

    message = (
        f"Seller contact for {reveal_request.listing.title} is now unlocked. "
        "Open the listing contact screen to view details."
    )
    notification = NotificationService.create_notification(
        user=reveal_request.buyer,
        notification_type=Notification.NotificationType.CONTACT_REVEAL_UNLOCKED,
        title="Seller Contact Unlocked",
        message=message,
        metadata={
            "listing_id": str(reveal_request.listing_id),
            "reveal_request_id": str(reveal_request.id),
            "reveal_request_type": reveal_request.__class__.__name__,
            "tx_ref": reveal_request.tx_ref,
        },
        priority=Notification.Priority.HIGH,
    )

    phone = getattr(reveal_request.buyer, "phone", None)
    if phone:
        try:
            send_sms(phone, message)
            if notification:
                notification.delivered_sms = True
                notification.sms_sent_at = timezone.now()
                notification.save(update_fields=["delivered_sms", "sms_sent_at"])
        except Exception as exc:
            logger.error("Failed to send contact reveal SMS: %s", exc, exc_info=True)
            if notification:
                metadata = dict(notification.metadata or {})
                errors = dict(metadata.get("delivery_errors", {}))
                errors["sms"] = str(exc)
                metadata["delivery_errors"] = errors
                notification.metadata = metadata
                notification.save(update_fields=["metadata"])

    return True


@app.task(bind=True, max_retries=3)
def geocode_listing_async(self, listing_id, model_label):
    model = _resolve_model(model_label)
    if model is None:
        logger.warning("Geocoding skipped for unknown model label %s", model_label)
        return False

    queryset = model.objects.all()
    if any(field.name == "address" for field in model._meta.get_fields()):
        queryset = queryset.select_related("address")

    try:
        listing = queryset.get(id=listing_id)
    except model.DoesNotExist:
        logger.warning(
            "Geocoding skipped because listing %s was not found for %s.",
            listing_id,
            model_label,
        )
        return False

    if getattr(listing, "latitude", None) is not None:
        logger.debug("Skipping geocoding for %s because coordinates already exist.", listing_id)
        return False

    address_text = _build_address_text(getattr(listing, "address", None))
    if not address_text:
        logger.warning(
            "Geocoding skipped for %s because no address text could be built.",
            listing_id,
        )
        return False

    try:
        geocoded = geocode_address(address_text)
    except GeocodingError as exc:
        retry_count = getattr(self.request, "retries", 0)
        if retry_count < len(GEOCODING_RETRY_DELAYS):
            countdown = GEOCODING_RETRY_DELAYS[retry_count]
            logger.warning(
                "Geocoding retry scheduled for %s (%s) in %s seconds.",
                listing_id,
                model_label,
                countdown,
            )
            raise self.retry(exc=exc, countdown=countdown)

        logger.error(
            "Geocoding failed permanently for %s (%s): %s",
            listing_id,
            model_label,
            exc,
        )
        return False

    listing.latitude = geocoded.get("lat")
    listing.longitude = geocoded.get("lng")
    listing.formatted_address = geocoded.get("formatted_address")
    listing.place_id = geocoded.get("place_id")
    listing.address_components = geocoded.get("components")
    listing.save(
        update_fields=[
            "latitude",
            "longitude",
            "formatted_address",
            "place_id",
            "address_components",
        ]
    )
    return True
