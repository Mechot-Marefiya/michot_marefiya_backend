from django_filters import rest_framework as filters

from apps.listing.models import CarListing, RoomListing


class RoomFilter(filters.FilterSet):
    hotel = filters.UUIDFilter('hotel')

    class Meta:
        model = RoomListing
        fields = ['hotel']


class CarFilter(filters.FilterSet):
    class Meta:
        model = CarListing
        fields = ['listing_type']
