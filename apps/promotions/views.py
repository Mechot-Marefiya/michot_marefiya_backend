from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from apps.account.permissions import IsAdmin
from apps.promotions.models import PromotionCampaign, PromotionPlacement
from apps.promotions.serializers import (
    PromotionCampaignDetailSerializer,
    PromotionCampaignSerializer,
    PromotionPlacementSerializer,
    PublicPlacementSerializer,
    TrackingEventSerializer,
)
from apps.promotions.services import (
    get_active_placements,
    invalidate_active_placement_cache,
    record_click,
    record_impression,
)


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class PromotionCampaignViewSet(viewsets.ModelViewSet):
    queryset = PromotionCampaign.objects.all().select_related("advertiser").prefetch_related("placements")
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PromotionCampaignDetailSerializer
        return PromotionCampaignSerializer

    def perform_create(self, serializer):
        serializer.save()
        invalidate_active_placement_cache()

    def perform_update(self, serializer):
        serializer.save()
        invalidate_active_placement_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_active_placement_cache()

    @action(detail=True, methods=["get", "post"], url_path="placements", permission_classes=[IsAuthenticated, IsAdmin])
    def placements(self, request, pk=None):
        campaign = self.get_object()
        if request.method == "GET":
            serializer = PromotionPlacementSerializer(campaign.placements.all(), many=True)
            return Response(serializer.data)

        payload = request.data.copy()
        payload["campaign"] = str(campaign.id)
        serializer = PromotionPlacementSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        placement = serializer.save()
        invalidate_active_placement_cache()
        return Response(PromotionPlacementSerializer(placement).data, status=status.HTTP_201_CREATED)


class PublicPromotionPlacementViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]
    serializer_class = PublicPlacementSerializer

    @extend_schema(responses={200: PublicPlacementSerializer(many=True)})
    def list(self, request):
        placements = get_active_placements(
            slot_type=request.query_params.get("slot_type"),
            category=request.query_params.get("category"),
        )
        serializer = PublicPlacementSerializer(placements, many=True, context={"request": request})
        return Response(serializer.data)


class PromotionTrackingViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]
    serializer_class = TrackingEventSerializer

    @extend_schema(request=TrackingEventSerializer, responses={204: None})
    def create(self, request):
        serializer = TrackingEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        placement = serializer.placement
        if serializer.validated_data["event_type"] == "impression":
            record_impression(placement, request.user, _client_ip(request))
        else:
            record_click(placement, request.user, _client_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)
