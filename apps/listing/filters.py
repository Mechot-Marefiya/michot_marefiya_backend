from django_filters import rest_framework as filters

from apps.listing.models import Booking, CarListing, PropertyListing, RoomListing


class RoomFilter(filters.FilterSet):
    hotel = filters.UUIDFilter("hotel")

    class Meta:
        model = RoomListing
        fields = ["hotel"]


class CarFilter(filters.FilterSet):
    class Meta:
        model = CarListing
        fields = ["listing_type", "car_class"]


class PropertyFilter(filters.FilterSet):
    class Meta:
        model = PropertyListing
        fields = ["property_type", "listing_type"]


class BookingFilter(filters.FilterSet):
    class Meta:
        model = Booking
        fields = ["status"]
