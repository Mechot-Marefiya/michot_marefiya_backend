from rest_framework.routers import DefaultRouter
from apps.account.views import UserViewSet, CompanyProfileViewSet

router = DefaultRouter()

router.register("users", UserViewSet, basename="users")
router.register("companies", CompanyProfileViewSet, basename="companies")

urlpatterns = router.urls
