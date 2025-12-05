from django_filters import rest_framework as filters

from apps.listing.models import Booking, PropertyListing, RoomListing,EventSpaceListing,EventSpaceBooking


class RoomFilter(filters.FilterSet):
    hotel = filters.UUIDFilter("hotel")

    class Meta:
        model = RoomListing
        fields = ["hotel"]

class EventSpaceFilter(filters.FilterSet):
    hotel = filters.UUIDFilter("hotel")

    class Meta:
        model = EventSpaceListing
        fields = ["hotel"]
# class CarFilter(filters.FilterSet):
#     class Meta:
#         model = CarListing
#         fields = ["listing_type", "car_class"]


class PropertyFilter(filters.FilterSet):
    class Meta:
        model = PropertyListing
        fields = ["property_type"]


class BookingFilter(filters.FilterSet):
    class Meta:
        model = Booking
        fields = ["status"]
class EventSpaceBookingFilter(filters.FilterSet):
    """
    Dedicated FilterSet for EventSpaceBooking objects.
    """
    class Meta:
        model = EventSpaceBooking
        fields = ["status", "check_in_date", "check_out_date"]