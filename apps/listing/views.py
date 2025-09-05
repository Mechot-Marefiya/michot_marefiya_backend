from rest_framework.permissions import AllowAny
from apps.core.views import AbstractModelViewSet
from apps.listing.models import CarListing, PropertyListing, Room
from apps.listing.serializers import (
    CarListingSerializer,
    # HotelListingSerializer,
    PropertyListingSerializer,
)


class RoomListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = RoomListingSerializer
    queryset = Room.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["request"] = self.request

        return context


class CarListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = CarListingSerializer
    queryset = CarListing.objects.all()


class PropertyListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PropertyListingSerializer
    queryset = PropertyListing.objects.all()
