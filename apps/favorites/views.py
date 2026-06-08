from django.contrib.contenttypes.models import ContentType
from apps.account.models import normalize_phone_number
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import Favorite, GuestFavorite
from .serializers import FavoriteSerializer, GuestFavoriteSerializer


@extend_schema(tags=["Favorites"])
class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user).select_related("content_type").order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        # allow deletion by id
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="toggle")
    def toggle(self, request):
        """Toggle favorite by providing content_type (app_label.model or id) and object_id"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ct = serializer.validated_data.get("content_type_obj")
        object_id = serializer.validated_data.get("object_id")
        user = request.user

        fav = Favorite.objects.filter(user=user, content_type=ct, object_id=str(object_id)).first()
        if fav:
            fav.delete()
            return Response({"detail": "removed"}, status=status.HTTP_200_OK)
        else:
            # use serializer to ensure snapshot persistence
            serializer = self.get_serializer(data={"content_type": request.data.get("content_type"), "object_id": object_id})
            serializer.is_valid(raise_exception=True)
            fav = serializer.save()
            data = FavoriteSerializer(fav, context={"request": request}).data
            return Response(data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Favorites"])
class GuestFavoriteCollectionView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: GuestFavoriteSerializer(many=True)},
        summary="List guest favorites by phone",
    )
    def get(self, request):
        guest_phone = request.query_params.get("guest_phone")
        if not guest_phone:
            return Response(
                {"guest_phone": ["This query parameter is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_phone = normalize_phone_number(guest_phone)
        if not normalized_phone:
            return Response(
                {"guest_phone": ["This query parameter is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = GuestFavorite.objects.filter(
            guest_phone=normalized_phone,
            linked_user__isnull=True,
        ).select_related("content_type").order_by("-created_at")
        data = GuestFavoriteSerializer(queryset, many=True, context={"request": request}).data
        return Response({"count": len(data), "results": data}, status=status.HTTP_200_OK)

    @extend_schema(
        request=GuestFavoriteSerializer,
        responses={201: GuestFavoriteSerializer},
        summary="Create a guest favorite by phone",
    )
    def post(self, request):
        serializer = GuestFavoriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        favorite = serializer.save()
        data = GuestFavoriteSerializer(favorite, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Favorites"])
class GuestFavoriteToggleView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=GuestFavoriteSerializer,
        responses={200: GuestFavoriteSerializer, 201: GuestFavoriteSerializer},
        summary="Toggle a guest favorite by phone",
    )
    def post(self, request):
        serializer = GuestFavoriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        ct = serializer.validated_data["content_type_obj"]
        object_id = serializer.validated_data["object_id"]
        guest_phone = serializer.validated_data["guest_phone"]

        favorite = GuestFavorite.objects.filter(
            guest_phone=guest_phone,
            linked_user__isnull=True,
            content_type=ct,
            object_id=str(object_id),
        ).first()
        if favorite:
            favorite.delete()
            return Response({"detail": "removed"}, status=status.HTTP_200_OK)

        favorite = serializer.save()
        data = GuestFavoriteSerializer(favorite, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)
