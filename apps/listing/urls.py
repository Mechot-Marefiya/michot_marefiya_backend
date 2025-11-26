from django.urls import path
from rest_framework.routers import DefaultRouter
from apps.listing.views import (
    BookingViewSet,
    RoomListingViewSet,
    GuestHouseListingViewSet,
    CarListingViewSet,
    PropertyListingViewSet,
    AmenityViewSet,
    StaySearchView,
<<<<<<< HEAD
    CarRentalViewSet,
    CarAvailabilityByCarAndDateView,
    CarAvailabilityByDateRangeView, 
    StayAvailabilityUpdateView
)

=======
    PricePreviewView,
)


urlpatterns = [
    path("stays/search/", StaySearchView.as_view(), name="stay-search")
]

urlpatterns += [
    path("rooms/<uuid:pk>/price-preview/", PricePreviewView.as_view(), name="price-preview"),
]

>>>>>>> e22ab83f239a1015873c2fd69fa1ea72bf1ca62e
router = DefaultRouter()

router.register("rooms", RoomListingViewSet, basename="rooms")
router.register("guest-houses", GuestHouseListingViewSet, basename="guest_houses")
router.register("cars", CarListingViewSet, basename="cars")
router.register("properties", PropertyListingViewSet, basename="properties")
router.register("amenities", AmenityViewSet, basename="amenities")
router.register("bookings", BookingViewSet, basename="bookings")
router.register('car-rentals', CarRentalViewSet, basename='carrental')

urlpatterns = [
   path(
        "stays/availability/<uuid:pk>/update/", StayAvailabilityUpdateView.as_view(),name="stay-availability-update"),
   # Stay search
    path("stays/search/", StaySearchView.as_view(), name="stay-search"),
    path("car-availabilities/by-car-and-date/", CarAvailabilityByCarAndDateView.as_view(),  name="car-availability-by-car-and-date"),
    path("car-availabilities/by-dates/", CarAvailabilityByDateRangeView.as_view(), name="car-availability-by-date-range"),
]

urlpatterns += router.urls
