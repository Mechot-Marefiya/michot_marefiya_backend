from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.promotions.views import (
    PromotionCampaignViewSet,
    PromotionTrackingViewSet,
    PublicPromotionPlacementViewSet,
)


router = DefaultRouter()
router.register("campaigns", PromotionCampaignViewSet, basename="promotion-campaigns")
router.register("placements", PublicPromotionPlacementViewSet, basename="promotion-placements")

urlpatterns = [
    path("track/", PromotionTrackingViewSet.as_view({"post": "create"}), name="promotion-track"),
]

urlpatterns += router.urls
