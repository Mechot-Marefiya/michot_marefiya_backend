from apps.listing.services import StayAvailabilityService


def track_availability(days_ahead=180):
    return StayAvailabilityService.ensure_future_availability(days_ahead=days_ahead)
