from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from apps.core.views import AbstractModelViewSet
from apps.listing.filters import PropertyFilter, RoomFilter, BookingFilter
from apps.listing.models import (
    Amenity,
    CarListing,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
    Booking,
)
from apps.listing.serializers import (
    AmenityResponseSSerializer,
    BookingSerializer,
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
    # filter_backends = [DjangoFilterBackend]
    # filterset_class = CarFilter


@extend_schema(responses=PropertyListingResponseSerializer)
class PropertyListingViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PropertyListingSerializer
    queryset = PropertyListing.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter


class AmenityViewSet(AbstractModelViewSet):
    http_method_names = ["get"]
    permission_classes = [AllowAny]
    serializer_class = AmenityResponseSSerializer
    queryset = Amenity.objects.all()


class BookingViewSet(AbstractModelViewSet):
    http_method_names = ["get", "post"]
    serializer_class = BookingSerializer
    permission_classes = [AllowAny]
    queryset = Booking.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = BookingFilter

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
