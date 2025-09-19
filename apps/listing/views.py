from rest_framework.permissions import AllowAny
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from apps.core.views import AbstractModelViewSet
from apps.listing.filters import RoomFilter
from apps.listing.models import (
    CarListing,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
)
from apps.listing.serializers import (
    CarListingResponseSerializer,
    CarListingSerializer,
    GuestHouseListingResponseSerializer,
    GuestHouseListingSerializer,
    PropertyListingResponseSerializer,
    PropertyListingSerializer,
    RoomListingResponseSerializer,
    RoomListingSerializer,
)


@extend_schema(responses=RoomListingResponseSerializer)
class RoomListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = RoomListingSerializer
    queryset = RoomListing.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = RoomFilter

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["request"] = self.request

        return context


@extend_schema(responses=GuestHouseListingResponseSerializer)
class GuestHouseListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = GuestHouseListingSerializer
    queryset = GuestHouseListing.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["request"] = self.request

        return context


@extend_schema(responses=CarListingResponseSerializer)
class CarListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = CarListingSerializer
    queryset = CarListing.objects.all()


@extend_schema(responses=PropertyListingResponseSerializer)
class PropertyListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PropertyListingSerializer
    queryset = PropertyListing.objects.all()
