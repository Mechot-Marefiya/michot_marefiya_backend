from apps.core.views import CurrencyViewSet, FacilityViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

router.register("facilities", FacilityViewSet, basename="facilities")
router.register("currencies", CurrencyViewSet, "currencies")

urlpatterns = router.urls
