from django_filters import rest_framework as filters

from apps.listing.models import Booking, PropertyListing, RoomListing,EventSpaceListing,EventSpaceBooking


class RoomFilter(filters.FilterSet):
    hotel = filters.UUIDFilter("hotel")

    class Meta:
        model = RoomListing
        fields = ["hotel"]

class EventSpaceFilter(filters.FilterSet):
    hotel = filters.UUIDFilter("hotel")
    company = filters.UUIDFilter("hotel__company")

    class Meta:
        model = EventSpaceListing
        fields = ["hotel", "company"]
# class CarFilter(filters.FilterSet):
#     class Meta:
#         model = CarListing
#         fields = ["listing_type", "car_class"]


class PropertyFilter(filters.FilterSet):
    company = filters.UUIDFilter("company")
    individual_owner = filters.UUIDFilter("individual_owner")

    class Meta:
        model = PropertyListing
        fields = ["property_type", "company", "individual_owner"]


class BookingFilter(filters.FilterSet):
    check_in_date = filters.DateFromToRangeFilter()
    
    class Meta:
        model = Booking
        fields = ["status", "check_in_date"]
class EventSpaceBookingFilter(filters.FilterSet):
    """
    Dedicated FilterSet for EventSpaceBooking objects.
    """
    class Meta:
        model = EventSpaceBooking
        fields = ["status", "check_in_date", "check_out_date"]