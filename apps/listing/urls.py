from apps.listing.views import (
    RoomListingViewSet,
    GuestHouseListingViewSet,
    CarListingViewSet,
    PropertyListingViewSet,
)
from rest_framework.routers import DefaultRouter


router = DefaultRouter()

router.register("rooms", RoomListingViewSet, basename="rooms")
router.register("guest-houses", GuestHouseListingViewSet,
                basename="guest_houses")
router.register("cars", CarListingViewSet, basename="cars")
router.register("properties", PropertyListingViewSet, basename="properties")

urlpatterns = router.urls
