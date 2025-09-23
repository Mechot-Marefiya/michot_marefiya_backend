from django.contrib import admin

from apps.listing.models import (
    CarListing,
    EventSpaceListing,
    PropertyListing,
    RoomListing,
)
from apps.listing.models import Amenity

admin.site.register(RoomListing)
admin.site.register(EventSpaceListing)
admin.site.register(CarListing)
admin.site.register(PropertyListing)
admin.site.register(Amenity)
