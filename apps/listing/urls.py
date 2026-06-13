from django.urls import path
from rest_framework.routers import DefaultRouter
from apps.listing.views import (
    BookingViewSet,
    RoomListingViewSet,
    GuestHouseProfileViewSet, GuestHouseRoomViewSet,
    CarListingViewSet,
    CarSaleListingViewSet,
    PropertySaleListingViewSet,
    PropertyRentalBookingViewSet,
    PropertyListingViewSet,
    AmenityViewSet,
    StaySearchView,
    CarRentalViewSet,
    CarAvailabilityUpdateAPIView,
    CarAvailabilityByCarAndDateView,
    CarAvailabilityByDateRangeView, 
    StayAvailabilityUpdateView,
    EventSpaceListingViewSet,
    EventSpaceBookingViewSet,
    GuestHouseBookingViewSet,
    TermsAndConditionsViewSet,
    AddonOfferingViewSet,
    SeasonViewSet,
    SeasonalRateViewSet,
    InventoryGridView,
    NearbyListingsView,
    WithinBoundsListingsView,
    MapPinsView,
    FeedListingsView,
    ListingSearchView,
    ListingSearchSuggestionsView,
)

router = DefaultRouter()

router.register("rooms", RoomListingViewSet, basename="rooms")
router.register("guest-houses", GuestHouseProfileViewSet, basename="guest_houses")
router.register("guest-house-rooms", GuestHouseRoomViewSet, basename="guest_house_rooms")
router.register("cars", CarListingViewSet, basename="cars")
router.register("car-sales", CarSaleListingViewSet, basename="car-sales")
router.register("property-sales", PropertySaleListingViewSet, basename="property-sales")
router.register("property-rentals/bookings", PropertyRentalBookingViewSet, basename="property-rental-bookings")
router.register("properties", PropertyListingViewSet, basename="properties")
router.register("amenities", AmenityViewSet, basename="amenities")
router.register("bookings", BookingViewSet, basename="bookings")
router.register('car-rentals', CarRentalViewSet, basename='carrental')
router.register('event-spaces',EventSpaceListingViewSet,basename="event-spaces")
router.register('bookings-eventspaces',EventSpaceBookingViewSet,basename="bookings-eventspaces")
router.register('guesthouse-bookings', GuestHouseBookingViewSet, basename='guesthouse-bookings')
router.register('terms', TermsAndConditionsViewSet, basename='terms')
router.register('addon-offerings', AddonOfferingViewSet, basename='addon-offerings')
router.register('seasons', SeasonViewSet, basename='seasons')
router.register('seasonal-rates', SeasonalRateViewSet, basename='seasonal-rates')

urlpatterns = [
   path(
        "stays/availability/<uuid:pk>/update/", StayAvailabilityUpdateView.as_view(),name="stay-availability-update"),
   path("car-availabilities/<uuid:pk>/update/",CarAvailabilityUpdateAPIView.as_view(),name="car-availability-update"),
   
   # Stay search
    path("stays/search/", StaySearchView.as_view(), name="stay-search"),
    path("car-availabilities/by-car-and-date/", CarAvailabilityByCarAndDateView.as_view(),  name="car-availability-by-car-and-date"),
    path("car-availabilities/by-dates/", CarAvailabilityByDateRangeView.as_view(), name="car-availability-by-date-range"),
    path("inventory/grid/", InventoryGridView.as_view(), name="inventory-grid"),
    path("nearby/", NearbyListingsView.as_view(), name="listing-nearby"),
    path("within-bounds/", WithinBoundsListingsView.as_view(), name="listing-within-bounds"),
    path("map-pins/", MapPinsView.as_view(), name="listing-map-pins"),
    path("feed/", FeedListingsView.as_view(), name="listing-feed"),
    path("search/", ListingSearchView.as_view(), name="listing-search"),
    path("search/suggestions/", ListingSearchSuggestionsView.as_view(), name="listing-search-suggestions"),
]

urlpatterns += router.urls
