from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import FavoriteViewSet

router = DefaultRouter()
router.register("", FavoriteViewSet, basename="favorites")

urlpatterns = []
urlpatterns += router.urls
