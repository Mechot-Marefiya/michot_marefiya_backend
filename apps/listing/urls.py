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
    CarRentalViewSet,
    CarAvailabilityUpdateAPIView,
    CarAvailabilityByCarAndDateView,
    CarAvailabilityByDateRangeView, 
    StayAvailabilityUpdateView,
    EventSpaceListingViewSet,
    EventSpaceBookingViewSet,
    GuestHouseBookingAPIView,
    TermsAndConditionsViewSet,
)

router = DefaultRouter()

router.register("rooms", RoomListingViewSet, basename="rooms")
router.register("guest-houses", GuestHouseListingViewSet, basename="guest_houses")
router.register("cars", CarListingViewSet, basename="cars")
router.register("properties", PropertyListingViewSet, basename="properties")
router.register("amenities", AmenityViewSet, basename="amenities")
router.register("bookings", BookingViewSet, basename="bookings")
router.register('car-rentals', CarRentalViewSet, basename='carrental')
router.register('event-spaces',EventSpaceListingViewSet,basename="event-spaces")
router.register('bookings-eventspaces',EventSpaceBookingViewSet,basename="bookings-eventspaces")
router.register('terms', TermsAndConditionsViewSet, basename='terms')

urlpatterns = [
   path(
        "stays/availability/<uuid:pk>/update/", StayAvailabilityUpdateView.as_view(),name="stay-availability-update"),
   path("car-availabilities/<uuid:pk>/update/",CarAvailabilityUpdateAPIView.as_view(),name="car-availability-update"),
   
   # Stay search
    path("stays/search/", StaySearchView.as_view(), name="stay-search"),
    path("car-availabilities/by-car-and-date/", CarAvailabilityByCarAndDateView.as_view(),  name="car-availability-by-car-and-date"),
    path("car-availabilities/by-dates/", CarAvailabilityByDateRangeView.as_view(), name="car-availability-by-date-range"),
    path('guesthouse-bookings/', GuestHouseBookingAPIView.as_view(), name='guesthouse-bookings'),
]

urlpatterns += router.urls
