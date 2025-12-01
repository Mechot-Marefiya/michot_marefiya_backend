from apps.core.views import CurrencyViewSet, FacilityViewSet,CurrencyConvertAPIView
from rest_framework.routers import DefaultRouter
from django.urls import path, include
router = DefaultRouter()

router.register("facilities", FacilityViewSet, basename="facilities")
router.register("currencies", CurrencyViewSet, "currencies")

urlpatterns = router.urls
urlpatterns = [
    path('currency/convert/', CurrencyConvertAPIView.as_view(), name='currency-convert'),
] + router.urls
