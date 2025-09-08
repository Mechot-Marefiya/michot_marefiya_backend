from rest_framework.permissions import AllowAny
from apps.core.views import AbstractModelViewSet
from apps.listing.models import (
    CarListing,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
)
from apps.listing.serializers import (
    CarListingSerializer,
    GuestHouseListingSerializer,
    PropertyListingSerializer,
    RoomListingSerializer,
)


class RoomListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = RoomListingSerializer
    queryset = RoomListing.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["request"] = self.request

        return context


class GuestHouseListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = GuestHouseListingSerializer
    queryset = GuestHouseListing.objects.all()

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
