from django.urls import path
from rest_framework.routers import DefaultRouter
from apps.listing.views import (
    BookingViewSet,
    # HotelRoomAvailabilityViewSet,
    RoomListingViewSet,
    GuestHouseListingViewSet,
    CarListingViewSet,
    PropertyListingViewSet,
    AmenityViewSet,
    StaySearchView,
    PricePreviewView,
)


urlpatterns = [
    path("stays/search/", StaySearchView.as_view(), name="stay-search")
]

urlpatterns += [
    path("rooms/<uuid:pk>/price-preview/", PricePreviewView.as_view(), name="price-preview"),
]

router = DefaultRouter()

router.register("rooms", RoomListingViewSet, basename="rooms")
router.register("guest-houses", GuestHouseListingViewSet,
                basename="guest_houses")
router.register("cars", CarListingViewSet, basename="cars")
router.register("properties", PropertyListingViewSet, basename="properties")
router.register("amenities", AmenityViewSet, basename="amenities")
router.register("bookings", BookingViewSet, basename="bookings")
# router.register('room-availability', HotelRoomAvailabilityViewSet,
#                 basename='room-availability')

urlpatterns += router.urls
