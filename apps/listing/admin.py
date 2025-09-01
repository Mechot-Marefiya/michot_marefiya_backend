from django.contrib import admin

from apps.listing.models import CarListing, HotelListing, PropertyListing

admin.site.register(HotelListing)
admin.site.register(CarListing)
admin.site.register(PropertyListing)
