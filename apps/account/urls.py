from rest_framework.routers import DefaultRouter
from apps.account.views import (
    HotelProfileViewSet,
    IndividualOwnerProfileViewSet,
    UserViewSet,
    delete_me,
    CompanyProfileViewSet,
)
from django.urls import path

router = DefaultRouter()

router.register("users", UserViewSet, basename="users")
router.register("companies", CompanyProfileViewSet, basename="companies")
router.register("hotels", HotelProfileViewSet, basename="hotels")
router.register("individual-owners", IndividualOwnerProfileViewSet, "individual_owners")


urlpatterns = router.urls + [
    path('users/me/', delete_me, name='user-delete-me'),
]
