from rest_framework.routers import DefaultRouter
from apps.account.views import (
    HotelProfileViewSet,
    IndividualOwnerProfileViewSet,
    UserViewSet,
    UserViewSet,
    CompanyProfileViewSet,
    StaffViewSet,
)

router = DefaultRouter()

router.register("users", UserViewSet, basename="users")
router.register("companies", CompanyProfileViewSet, basename="companies")
router.register("hotels", HotelProfileViewSet, basename="hotels")
router.register("individual-owners", IndividualOwnerProfileViewSet, "individual_owners")
router.register("staff", StaffViewSet, basename="staff")


urlpatterns = router.urls
