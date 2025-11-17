from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from apps.listing.models import (
    BookingItem,
    CarListing,
    # EventSpaceListing,
    GuestHouseListing,
    ListingImage,
    PropertyListing,
    RoomListing,
    Booking,
    StayAvailability
)
from apps.listing.models import Amenity


class ListingImageInline(GenericTabularInline):
    model = ListingImage
    extra = 1  # how many empty slots to show
    fields = ("image", "alt_text", "is_primary")


@admin.register(PropertyListing)
class PropertyListingAdmin(admin.ModelAdmin):
    list_display = (
        "property_type",
        "bedrooms",
        "bathrooms",
        "square_meters",
        "is_furnished",
        # "listing_type",
    )
    inlines = [ListingImageInline]


admin.site.register(RoomListing)
# admin.site.register(EventSpaceListing)
admin.site.register(Booking)
admin.site.register(BookingItem)
# admin.site.register(StayAvailability)
admin.site.register(CarListing)
# admin.site.register(PropertyListing)
admin.site.register(GuestHouseListing)
admin.site.register(Amenity)


@admin.register(StayAvailability)
class StayAvailabilityAdmin(admin.ModelAdmin):
    # list_display = ["hotel", "room"]
    ordering = ["date"]
