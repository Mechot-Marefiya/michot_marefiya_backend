from django.contrib.contenttypes.models import ContentType
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from .models import Favorite
from .serializers import FavoriteSerializer


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
