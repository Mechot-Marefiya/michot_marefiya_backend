
from django.utils.dateparse import parse_date
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from apps.account.serializers import HotelProfileResponseSerializer
from apps.listing.docs.schema import search_schema
from apps.core.views import AbstractModelViewSet
from apps.listing.filters import PropertyFilter, RoomFilter, BookingFilter
from apps.account.permissions import IsAuthenticatedOrReadOnly
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
from apps.listing.services import StayAvailabilityService


@extend_schema(responses=RoomListingResponseSerializer)
class RoomListingViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
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
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = GuestHouseListingSerializer
    queryset = GuestHouseListing.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["request"] = self.request

        return context


@extend_schema(responses=CarListingResponseSerializer)
class CarListingViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = CarListingSerializer
    queryset = CarListing.objects.all()
    # filter_backends = [DjangoFilterBackend]
    # filterset_class = CarFilter


@extend_schema(responses=PropertyListingResponseSerializer)
class PropertyListingViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
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
    permission_classes = [IsAuthenticated]
    queryset = Booking.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = BookingFilter

    def get_queryset(self):
        """
        Users can only see their own bookings.
        Returns empty queryset if user is not authenticated (shouldn't happen due to IsAuthenticated).
        """
        if self.request.user.is_authenticated:
            return Booking.objects.filter(user=self.request.user)
        return Booking.objects.none()

    def perform_create(self, serializer):
        """
        Automatically assign the booking to the authenticated user.
        This ensures users can only create bookings for themselves.
        """
        if not self.request.user.is_authenticated:
            from rest_framework import serializers as drf_serializers
            raise drf_serializers.ValidationError(
                "Authentication required to create a booking."
            )
        serializer.save(user=self.request.user)


@search_schema
class StaySearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        city = request.query_params.get("city")
        check_in_date = request.query_params.get("check_in_date")
        check_out_date = request.query_params.get("check_out_date")
        guests = request.query_params.get("guests")

        if not all([city, check_in_date, check_out_date, guests]):
            return Response({"detail": "Missing required parameters."},
                            status=status.HTTP_400_BAD_REQUEST)

        check_in_date = parse_date(check_in_date)
        check_out_date = parse_date(check_out_date)

        if not check_in_date or not check_out_date:
            return Response({"detail": "Invalid date format."},
                            status=status.HTTP_400_BAD_REQUEST)

        stays = StayAvailabilityService.search_stays(
            city,
            check_in_date,
            check_out_date,
            number_of_guests=int(guests),
        )

        # TODO: If we also gonna handle guest houses here,
        # TODO: this serialization will fail.
        serializer = HotelProfileResponseSerializer(stays, many=True)

        return Response(serializer.data)
