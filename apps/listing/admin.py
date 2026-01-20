from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from apps.listing.models import (
    BookingItem,
    CarListing,
    CarAvailability,CarRental,CarRentalItem,
    EventSpaceListing,
    EventSpaceListing,
     GuestHouseProfile, GuestHouseRoom,
     GuestHouseInventory,
    GuestHouseBooking,
    GuestHouseBookingItem,
    EventSpaceBookingItem,
    EventSpaceBooking,
    EventSpaceAvailability,
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
from apps.listing.admin_terms import TermsAndConditionsAdmin


class ListingImageInline(GenericTabularInline):
    model = ListingImage
    extra = 1  # how many empty slots to show
    fields = ("image", "alt_text", "is_primary")

admin.site.register(CarAvailability)
admin.site.register(EventSpaceAvailability)
@admin.register(CarRental)
class CarRentalAdmin(admin.ModelAdmin):
    list_display = ("id", "renter", "start_date", "end_date", "total_price", "currency", "status", "is_legacy")
    list_filter = ("status",)
    search_fields = ("renter__email", "renter__first_name", "renter__last_name")

admin.site.register(CarRentalItem)
@admin.register(EventSpaceListing)
class EventSpaceListingAdmin(admin.ModelAdmin):
    list_display = ("title", "hotel", "space_type", "base_price", "currency", "is_active")
    search_fields = ("title", "description")
    list_filter = ("space_type", "is_active", "hotel")
    inlines = [ListingImageInline]
admin.site.register(EventSpaceBookingItem)

@admin.register(EventSpaceBooking)
class EventSpaceBookingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "check_in_date", "check_out_date", "total_price", "currency", "status", "is_legacy")
    list_filter = ("status",)
    search_fields = ("user__email",)
    search_fields = ("user__email",)
admin.site.register(GuestHouseInventory)

@admin.register(GuestHouseBooking)
class GuestHouseBookingAdmin(admin.ModelAdmin):
    list_display = ("id", "renter", "start_date", "end_date", "total_price", "currency", "status", "is_legacy")
    list_filter = ("status",)
    search_fields = ("renter__email",)
@admin.register(PropertyListing)
class PropertyListingAdmin(admin.ModelAdmin):
    list_display = (
        "property_type",
        "bedrooms",
        "bathrooms",
        "square_meters",
        "is_furnished",
        "currency",
        # "listing_type",
    )
    inlines = [ListingImageInline]


@admin.register(RoomListing)
class RoomListingAdmin(admin.ModelAdmin):
    list_display = ("title", "hotel", "base_price", "currency", "is_active")
    search_fields = ("title", "description")
    list_filter = ("is_active", "hotel")
    inlines=[ListingImageInline]
# admin.site.register(EventSpaceListing)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "check_in_date", "check_out_date", "total_price", "booking_currency", "status", "is_legacy")
    search_fields = ("user__email",)
    list_filter = ("status",)
    def booking_currency(self, obj):
        return getattr(obj, "currency", "ETB")
    booking_currency.short_description = "currency"
admin.site.register(BookingItem)
@admin.register(CarListing)
class CarListingModelAdmin(admin.ModelAdmin):
    list_display = ["brand", "company", "base_price", "currency"]
    inlines = [ListingImageInline]
# admin.site.register(PropertyListing)
@admin.register(GuestHouseProfile)
class GuestHouseProfileModelAdmin(admin.ModelAdmin):
    list_display=["company","title"]
    inlines=[ListingImageInline]

@admin.register(GuestHouseRoom)
class GuestHouseRoomModelAdmin(admin.ModelAdmin):
    list_display=["guest_house", "title", "base_price", "total_units"]
    inlines=[ListingImageInline]
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
@admin.register(GuestHouseBookingItem)
class GuestHouseBookingItemAdmin(admin.ModelAdmin):
    list_display = ("booking", "room", "units_booked", "price_per_unit")
