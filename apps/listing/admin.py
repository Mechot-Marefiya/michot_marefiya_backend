from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from apps.listing.models import (
    BookingItem,
    CarListing,
    CarAvailability,CarRental,CarRentalItem,
    # EventSpaceListing,
    GuestHouseListing,
    ListingImage,
    PropertyListing,
    RoomListing,
    Booking,
    RoomInventory,
    BookingRating,
    Transaction,
    StayAvailability
)
from apps.listing.models import Amenity
from apps.listing.models import Season, SeasonalRate, BookingItemPrice


class ListingImageInline(GenericTabularInline):
    model = ListingImage
    extra = 1  # how many empty slots to show
    fields = ("image", "alt_text", "is_primary")

admin.site.register(CarAvailability)
admin.site.register(CarRental)
admin.site.register(CarRentalItem)
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


@admin.register(RoomListing)
class RoomListingAdmin(admin.ModelAdmin):
    list_display = ("title", "hotel", "base_price", "is_active")
    search_fields = ("title", "description")
    list_filter = ("is_active", "hotel")
# admin.site.register(EventSpaceListing)
admin.site.register(Booking)
admin.site.register(BookingItem)
admin.site.register(CarListing)
# admin.site.register(PropertyListing)
admin.site.register(GuestHouseListing)
admin.site.register(Amenity)


@admin.register(RoomInventory)
class RoomInventoryAdmin(admin.ModelAdmin):
    list_display = ("room_listing", "date", "price")


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "recurring", "active")


@admin.register(SeasonalRate)
class SeasonalRateAdmin(admin.ModelAdmin):
    list_display = ("season", "room", "hotel", "company", "price_override", "multiplier", "priority", "active")
    list_filter = ("active", "priority")


@admin.register(BookingItemPrice)
class BookingItemPriceAdmin(admin.ModelAdmin):
    list_display = ("booking_item", "date", "price_per_unit", "units")


@admin.register(BookingRating)
class BookingRatingAdmin(admin.ModelAdmin):
    list_display = ("booking", "rating", "created_at")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("booking", "provider", "provider_payment_id", "amount", "currency", "status", "created_at")


@admin.register(StayAvailability)
class StayAvailabilityAdmin(admin.ModelAdmin):
    # list_display = ["hotel", "room"]
    ordering = ["date"]
