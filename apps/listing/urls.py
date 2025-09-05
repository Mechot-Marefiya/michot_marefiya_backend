from apps.listing.views import RoomListingViewSet
from rest_framework.routers import DefaultRouter


router = DefaultRouter()

router.register("rooms", RoomListingViewSet, basename="rooms")

urlpatterns = router.urls
