
from django.utils.dateparse import parse_date
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
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
    BookingItem
)
from apps.listing.serializers import (
    AmenityResponseSSerializer,
    BookingSerializer,BookingResponseSerializer,
    CarListingResponseSerializer,
    CarListingSerializer,
    BookingRatingSerializer,
    GuestHouseListingResponseSerializer,
    GuestHouseListingSerializer,
    PropertyListingResponseSerializer,
    PropertyListingSerializer,
    RoomListingResponseSerializer,
    RoomListingSerializer,PartialCancelSerializer,
    SearchResultSerializer,
)
from apps.listing.services import StayAvailabilityService,BookingService


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
        if self.request.user.is_authenticated:
            return Booking.objects.filter(
                user=self.request.user
            ).prefetch_related("items", "items__room")
        return Booking.objects.none()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    @action(detail=True, methods=["post"],serializer_class=PartialCancelSerializer, url_path="partial-cancel")
    def partial_cancel(self, request, pk=None):
        serializer = PartialCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item_id = serializer.validated_data["item_id"]
        units_to_cancel = serializer.validated_data["units_to_cancel"]

        booking = self.get_object()

        try:
            booking_item = booking.items.get(id=item_id)
        except BookingItem.DoesNotExist:
            raise NotFound("Booking item not found")

        updated_booking = BookingService.partial_cancel_booking(
            booking_item,
            units_to_cancel
        )

        return Response(
            BookingResponseSerializer(
                updated_booking, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_200_OK
        )


    @action(detail=True, methods=["post"], url_path="rate",serializer_class=BookingRatingSerializer)
    def rate_booking(self, request, pk=None):
        booking = self.get_object()

        serializer = BookingRatingSerializer(
            data=request.data,
            context={"booking": booking}
        )
        serializer.is_valid(raise_exception=True)

        rating = serializer.save(booking=booking)

        return Response(
            BookingRatingSerializer(rating).data,
            status=status.HTTP_201_CREATED
        )
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

        if check_out_date <= check_in_date:
            return Response(
                {"detail": "Check-out date must be after check-in date."},
                status=status.HTTP_400_BAD_REQUEST
            )

        stays = StayAvailabilityService.search_stays(
            city,
            check_in_date,
            check_out_date,
            number_of_guests=int(guests),
        )

        results = []
        for stay_data in stays:
            hotel = stay_data["hotel"]
            hotel_result = {
                "hotel_id": hotel.id,
                "hotel_name": hotel.company.name,
                "city": hotel.company.address.city,
                "stars": hotel.stars,
                "rooms": []
            }
            
            for room_data in stay_data["rooms"]:
                room = room_data["room"]
                hotel_result["rooms"].append({
                    "id": room.id,
                    "title": room.title,
                    "description": room.description or "",
                    "base_price": str(room.base_price),
                    "number_of_guests": room.number_of_guests,
                    "bed_type": room.bed_type,
                    "room_size_sqm": room.room_size_sqm,
                    "available_units": room_data["available_units"]
                })
            
            results.append(hotel_result)

        serializer = SearchResultSerializer(results, many=True)
        return Response(serializer.data)
    