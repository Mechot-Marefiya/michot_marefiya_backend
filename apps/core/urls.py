from apps.core.views import FacilityViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

router.register('facilities', FacilityViewSet, basename='facilities')


urlpatterns = router.urls
