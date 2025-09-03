from apps.listing.views import HotelListingViewSet
from rest_framework.routers import DefaultRouter


router = DefaultRouter()

router.register("hotel-listings", HotelListingViewSet, basename="hotel_listings")

urlpatterns = router.urls
