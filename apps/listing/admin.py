from django.contrib import admin

from apps.listing.models import CarListing, EventSpace, PropertyListing, Room

admin.site.register(Room)
admin.site.register(EventSpace)
admin.site.register(CarListing)
admin.site.register(PropertyListing)
