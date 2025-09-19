from rest_framework.routers import DefaultRouter
from apps.account.views import (
    HotelProfileViewSet,
    UserViewSet,
    CompanyProfileViewSet
)

router = DefaultRouter()

router.register("users", UserViewSet, basename="users")
router.register("companies", CompanyProfileViewSet, basename="companies")
router.register('hotels', HotelProfileViewSet, basename='hotels')

urlpatterns = router.urls
