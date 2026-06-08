from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import FavoriteViewSet, GuestFavoriteCollectionView, GuestFavoriteToggleView

router = DefaultRouter()
router.register("", FavoriteViewSet, basename="favorites")

urlpatterns = []
urlpatterns += [
    path("guest/", GuestFavoriteCollectionView.as_view(), name="guest-favorites"),
    path("guest/toggle/", GuestFavoriteToggleView.as_view(), name="guest-favorites-toggle"),
]
urlpatterns += router.urls
