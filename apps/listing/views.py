
from django.utils.dateparse import parse_date
from datetime import timedelta
from django.conf import settings
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
from apps.listing.services import PriceService
from apps.listing.serializers import PricePreviewResponseSerializer
from apps.listing.models import RoomListing


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

    def retrieve(self, request, *args, **kwargs):
        """Return room detail with optional seasonal display price when
        `check_in` and `check_out` query params are provided and the
        `FEATURE_SEASONAL_PRICING` flag is enabled.
        """
        instance = self.get_object()
        # base serialized data
        serializer = RoomListingResponseSerializer(instance, context=self.get_serializer_context())
        data = serializer.data

        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')

        # default values
        data['display_price'] = data.get('base_price')

        if use_seasonal and check_in and check_out:
            from django.utils.dateparse import parse_date
            from datetime import timedelta
            check_in_date = parse_date(check_in)
            check_out_date = parse_date(check_out)
            if check_in_date and check_out_date and check_out_date > check_in_date:
                cursor = check_in_date
                prices = []
                while cursor < check_out_date:
                    p = PriceService.resolve_price(instance, cursor)
                    prices.append(p)
                    cursor += timedelta(days=1)

                if prices:
                    preview_total = sum(prices)
                    preview_min = min(prices)
                    preview_has_discount = any(p < instance.base_price for p in prices)
                    data['preview_min_price'] = preview_min
                    data['preview_total'] = preview_total
                    data['preview_has_discount'] = preview_has_discount
                    data['display_price'] = preview_min if preview_has_discount else instance.base_price

        return Response(data)

    def list(self, request, *args, **kwargs):
        """List rooms; when `check_in` and `check_out` are provided and
        `FEATURE_SEASONAL_PRICING` is enabled, compute `display_price` and
        preview fields for each room.
        """
        qs = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(qs)
        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        check_in = request.query_params.get('check_in') or request.query_params.get('check_in_date')
        check_out = request.query_params.get('check_out') or request.query_params.get('check_out_date')

        rooms = page if page is not None else list(qs)

        serialized = []
        for room in rooms:
            serializer = RoomListingResponseSerializer(room, context=self.get_serializer_context())
            data = serializer.data
            # default
            data['display_price'] = data.get('base_price')

            if use_seasonal and check_in and check_out:
                from django.utils.dateparse import parse_date
                from datetime import timedelta
                check_in_date = parse_date(check_in)
                check_out_date = parse_date(check_out)
                if check_in_date and check_out_date and check_out_date > check_in_date:
                    cursor = check_in_date
                    prices = []
                    while cursor < check_out_date:
                        p = PriceService.resolve_price(room, cursor)
                        prices.append(p)
                        cursor += timedelta(days=1)
                    if prices:
                        preview_total = sum(prices)
                        preview_min = min(prices)
                        preview_has_discount = any(p < room.base_price for p in prices)
                        data['preview_min_price'] = preview_min
                        data['preview_total'] = preview_total
                        data['preview_has_discount'] = preview_has_discount
                        data['display_price'] = preview_min if preview_has_discount else room.base_price

            serialized.append(data)

        if page is not None:
            return self.get_paginated_response(serialized)

        return Response(serialized)


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
                # compute seasonal preview if feature enabled
                base_price = room.base_price
                use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
                display_price = base_price
                preview_min = None
                preview_total = None
                preview_has_discount = False

                if use_seasonal:
                    cursor = check_in_date
                    prices = []
                    while cursor < check_out_date:
                        p = PriceService.resolve_price(room, cursor)
                        prices.append(p)
                        cursor += timedelta(days=1)

                    if prices:
                        # prices are Decimal
                        preview_total = sum(prices)
                        preview_min = min(prices)
                        preview_has_discount = any(p < base_price for p in prices)
                        display_price = preview_min if preview_has_discount else base_price

                hotel_result["rooms"].append({
                    "id": room.id,
                    "title": room.title,
                    "description": room.description or "",
                    "base_price": base_price,
                    "display_price": display_price,
                    "preview_min_price": preview_min,
                    "preview_total": preview_total,
                    "preview_has_discount": preview_has_discount,
                    "number_of_guests": room.number_of_guests,
                    "bed_type": room.bed_type,
                    "room_size_sqm": room.room_size_sqm,
                    "available_units": room_data["available_units"]
                })
            
            results.append(hotel_result)

        serializer = SearchResultSerializer(results, many=True)
        return Response(serializer.data)


class PricePreviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        check_in = request.query_params.get("check_in")
        check_out = request.query_params.get("check_out")

        if not check_in or not check_out:
            return Response({"detail": "Missing check_in or check_out."}, status=status.HTTP_400_BAD_REQUEST)

        check_in_date = parse_date(check_in)
        check_out_date = parse_date(check_out)

        if not check_in_date or not check_out_date or check_out_date <= check_in_date:
            return Response({"detail": "Invalid date range."}, status=status.HTTP_400_BAD_REQUEST)

        # fetch room
        try:
            room = RoomListing.objects.get(id=pk)
        except RoomListing.DoesNotExist:
            raise NotFound("Room not found")

        # iterate dates and resolve price
        lines = []
        cursor = check_in_date
        total = 0
        base_price = room.base_price
        has_discount = False

        while cursor < check_out_date:
            price = PriceService.resolve_price(room, cursor)
            # determine source: inventory / seasonal / base
            source = "base"
            inv = None
            try:
                from apps.listing.models import RoomInventory
                inv = RoomInventory.objects.filter(room_listing=room, date=cursor).first()
            except Exception:
                inv = None

            if inv and inv.price is not None:
                source = "inventory"
            else:
                # if different from base, assume seasonal
                from decimal import Decimal
                if Decimal(price) != Decimal(room.base_price):
                    source = "seasonal"

            lines.append({"date": cursor, "price": price, "source": source})
            total += price
            if price < room.base_price:
                has_discount = True
            cursor += timedelta(days=1)

        serializer = PricePreviewResponseSerializer({
            "lines": lines,
            "total": total,
            "has_discount": has_discount,
            "base_price": base_price,
        })

        return Response(serializer.data)
    