
from django.utils.dateparse import parse_date
from django.conf import settings
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from datetime import date
from datetime import datetime, timedelta
from decimal import Decimal
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status,filters
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework import serializers
from rest_framework.response import Response
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from apps.account.serializers import HotelProfileResponseSerializer, ListingImageSerializer
from apps.core.serializers import FacilityResponseSerializer
from django.contrib.contenttypes.models import ContentType
from apps.favorites.services import get_favorite_object_ids
from apps.listing.docs.schema import search_schema
from apps.core.views import AbstractModelViewSet
from apps.core.utils import get_display_currency
from rest_framework import viewsets
from apps.listing.utils import ParseDatesAndQuantity
from apps.listing.filters import PropertyFilter, RoomFilter, BookingFilter,EventSpaceFilter,EventSpaceBookingFilter
from apps.account.permissions import (
    IsAuthenticatedOrReadOnly,
    IsPublicReadOnly,
    IsAdmin,
    IsListingOwner,
    IsBookingOwner,
    IsCarRentalOwner,
    CanModifyBooking,
    ORPermission,
    IsCompanyOrFrontDesk,
)
from apps.account.enums import RoleCode
from apps.listing.models import (
    Amenity,
    CarListing,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
    Booking,StayAvailability,
    BookingItem,
    CarRentalItem,
    EventSpaceListing,
    CarAvailability,
    EventSpaceBooking,
    CarRental,
    GuestHouseBooking,
    GuestHouseBookingItem
    
)
from apps.account.models import(CompanyProfile,IndividualOwnerProfile,HotelProfile)
from apps.listing.serializers import (
    AmenityResponseSSerializer,
    BookingSerializer,BookingResponseSerializer,
    CarListingResponseSerializer,
    CarListingSerializer,
    BookingRatingSerializer,
    
    CarAvailabilityUpdateSerializer,
    GuestHouseListingResponseSerializer,
    GuestHouseListingSerializer,
    PropertyListingResponseSerializer,
    PropertyListingSerializer,
    RoomListingResponseSerializer,
    EventSpaceListingSerializer,
    EventSpaceListingResponseSerializer,
    RoomListingSerializer,PartialCancelSerializer,
    SearchResultSerializer,StayAvailabilityUpdateSerializer,
    CarAvailabilitySerializer,
    AvailabilityCheckSerializer,
    CarSearchSerializer,
    CarRentalSerializer,
    EventSpaceBookingResponseSerializer,
    EventSpaceBookingSerializer,
    GuestHouseBookingSerializer
)
from apps.listing.services import StayAvailabilityService,BookingService,CarAvailabilityService,PriceService,GuestHouseAvailabilityService,EventSpaceAvailabilityService
from rest_framework.exceptions import PermissionDenied

@extend_schema(tags=["Accommodations"])
class RoomListingViewSet(AbstractModelViewSet):
    serializer_class = RoomListingSerializer
    queryset = RoomListing.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = RoomFilter


    def get_permissions(self):
        """
        - CREATE: Company users can create rooms for their hotels, admin can create all
        - READ: Public (all can read)
        - UPDATE/DELETE: Company can modify own rooms, admin can modify all
        """
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve', 'price_preview']:
            return [AllowAny()]
        else:
            return [IsListingOwner()]

    def get_queryset(self):
        """
        Filter queryset based on user role:
        - Public/Users: See all active rooms
        - Company users: See all rooms (for their own, can modify)
        - Admin: See all rooms
        """
        queryset = super().get_queryset()
        
        # If user is not authenticated, show only active listings
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.filter(is_active=True)
        
        # Admin sees all
        if self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and
            self.request.user.role and
            self.request.user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        # For companies, show all but they can only modify their own (enforced by permission)
        # For regular users, show only active
        if hasattr(self.request.user, 'role') and self.request.user.role:
            if self.request.user.role.code == RoleCode.COMPANY.value:
                return queryset  # Companies see all for reference
            else:
                return queryset.filter(is_active=True)
        
        return queryset.filter(is_active=True)

    @extend_schema(
        summary="Price Preview for specific dates",
        description="Get a daily breakdown of prices for a room between check-in and check-out.",
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=True),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=True),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT}
    )
    @action(detail=True, methods=['get'], url_path='price-preview')
    def price_preview(self, request, pk=None):
        room = self.get_object()
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        if not check_in or not check_out:
            return Response({"detail": "check_in and check_out are required"}, status=400)
        try:
            check_in_date = parse_date(check_in)
            check_out_date = parse_date(check_out)
        except Exception:
            return Response({"detail": "invalid date format"}, status=400)
        if check_in_date >= check_out_date:
            return Response({"detail": "check_out must be after check_in"}, status=400)

        days = (check_out_date - check_in_date).days
        lines = []
        total = Decimal('0.00')
        for i in range(days):
            when = check_in_date + timedelta(days=i)
            info = PriceService.resolve_price_detail(room, when)
            price = info.get('price')
            lines.append({
                'date': when.isoformat(),
                'price': str(price),
                'source': info.get('source'),
                'rate_id': info.get('rate_id'),
                'note': info.get('note'),
                'is_discounted': bool(info.get('is_discounted', False)),
            })
            total += Decimal(str(price))

        has_discount = any(l.get('is_discounted') for l in lines)

        return Response({
            'lines': lines,
            'total': str(total.quantize(Decimal('0.01'))),
            'has_discount': bool(has_discount),
        })

    def get_serializer_context(self):
        context = super().get_serializer_context()

        request = self.request

        # Support both `check_in_date`/`check_out_date` (used by hotel availability)
        # and `check_in`/`check_out` (used elsewhere)
        check_in = request.query_params.get("check_in_date") or request.query_params.get("check_in")
        check_out = request.query_params.get("check_out_date") or request.query_params.get("check_out")
        hotel_id = request.query_params.get("hotel")

        if check_in and check_out and hotel_id:
            try:
                check_in_date = parse_date(check_in)
                check_out_date = parse_date(check_out)
            except Exception:
                check_in_date = None
                check_out_date = None

            if check_in_date and check_out_date and check_out_date > check_in_date:
                try:
                    hotel = get_object_or_404(HotelProfile, id=hotel_id)
                    _, availability_qs = StayAvailabilityService.get_available_rooms(
                        hotel, check_in_date, check_out_date
                    )
                    # availability_qs is a queryset of dicts with 'room' and 'min_available'
                    availability_map = {row['room']: row['min_available'] for row in availability_qs}
                    context['availability_map'] = availability_map
                except Exception:
                    # On any error, do not attach availability to avoid breaking existing responses
                    pass

        context["request"] = request
        context["display_currency"] = get_display_currency(request)

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


@extend_schema(tags=["Accommodations"])
class GuestHouseListingViewSet(AbstractModelViewSet):
    serializer_class = GuestHouseListingSerializer
    queryset = GuestHouseListing.objects.all()

    def get_permissions(self):
        """
        - CREATE: Company users can create guest houses, admin can create all
        - READ: Public (all can read)
        - UPDATE/DELETE: Company can modify own guest houses, admin can modify all
        """
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve']:
            return [AllowAny()]
        else:
            return [IsListingOwner()]

    def get_serializer_class(self):
        if self.action in ["list", "retrieve", "check_availability"]:
            return GuestHouseListingResponseSerializer
        return GuestHouseListingSerializer

    def get_queryset(self):
        """Filter queryset - show all active to public, all to companies/admin."""
        queryset = super().get_queryset()
        
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.filter(is_active=True)
        
        if self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and
            self.request.user.role and
            self.request.user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        if hasattr(self.request.user, 'role') and self.request.user.role:
            if self.request.user.role.code == RoleCode.COMPANY.value:
                return queryset
        
        return queryset.filter(is_active=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        
        # resolve favorites for guesthouse responses
        try:
            ct = ContentType.objects.get(app_label="listing", model="guesthouselisting")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(self.request.user, ct) if ct is not None else set()

        context["favorite_object_ids"] = fav_ids
        context["display_currency"] = get_display_currency(self.request)
        
        return context
    @extend_schema(
            parameters=[
                OpenApiParameter("check_in", OpenApiTypes.DATE, required=True),
                OpenApiParameter("check_out", OpenApiTypes.DATE, required=True),
                OpenApiParameter("units", OpenApiTypes.INT, required=False),
                OpenApiParameter("city", OpenApiTypes.STR, required=False),
                OpenApiParameter("country", OpenApiTypes.STR, required=False),
                OpenApiParameter("region", OpenApiTypes.STR, required=False),
                OpenApiParameter("sub_city", OpenApiTypes.STR, required=False),
                OpenApiParameter("guesthouse_id", OpenApiTypes.UUID, required=False),
            ],
            responses=GuestHouseListingResponseSerializer(many=True)
        )
    @action(detail=False, methods=["get"], url_path="check-availability")
    def check_availability(self, request):
            """
            Check availability across all guesthouses or a specific one.
            """
            try:
                check_in = datetime.strptime(request.query_params.get("check_in"), "%Y-%m-%d").date()
                check_out = datetime.strptime(request.query_params.get("check_out"), "%Y-%m-%d").date()
            except:
                return Response({"error": "Invalid check_in/check_out format (YYYY-MM-DD required)."},
                                status=status.HTTP_400_BAD_REQUEST)

            if check_in >= check_out:
                return Response({"error": "check_out must be after check_in."},
                                status=status.HTTP_400_BAD_REQUEST)

            units = int(request.query_params.get("units", 1))

            address_filters = {
                "city": request.query_params.get("city"),
                "country": request.query_params.get("country"),
                "region": request.query_params.get("region"),
                "sub_city": request.query_params.get("sub_city"),
            }

            guesthouse_id = request.query_params.get("guesthouse_id")

            if guesthouse_id:
                listing = GuestHouseListing.objects.filter(id=guesthouse_id, is_active=True).first()
                if not listing:
                    return Response({"error": "Guest house not found."}, status=404)

                qs, meta = GuestHouseAvailabilityService.get_available_listings(
                    check_in, check_out, units, address_filters
                )

                qs = qs.filter(id=guesthouse_id)

            else:
                qs, meta = GuestHouseAvailabilityService.get_available_listings(
                    check_in, check_out, units, address_filters
                )
            serializer = GuestHouseListingResponseSerializer(qs, many=True)
            return Response({
                "count": qs.count(),
                "results": serializer.data
            })

@extend_schema(tags=["Accommodations"])
class GuestHouseBookingAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List/Create Guest House Bookings",
        request=GuestHouseBookingSerializer,
        responses={200: GuestHouseBookingSerializer(many=True), 201: GuestHouseBookingSerializer}
    )

    def get(self, request):
        """
        List bookings:
        - Admins: all bookings
        - Users: own bookings
        """
        user = request.user
        if user.is_superuser:
            bookings = GuestHouseBooking.objects.all()
        else:
            bookings = GuestHouseBooking.objects.filter(renter=user)

        serializer = GuestHouseBookingSerializer(
            bookings, 
            many=True, 
            context={"display_currency": get_display_currency(request)}
        )
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        """
        Create a new booking.
        Validates availability and updates it.
        """
        serializer = GuestHouseBookingSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        items_data = serializer.validated_data.pop("items")
        renter = request.user
        start_date = serializer.validated_data["start_date"]
        end_date = serializer.validated_data["end_date"]

        # Prepare room infos for availability service
        room_infos = [
            {"guesthouse_listing": item["room"], "quantity": item["units_booked"]}
            for item in items_data
        ]

        # Validate availability
        GuestHouseAvailabilityService.validate_availability(
            room_infos, start_date, end_date
        )

        # Calculate total price
        total_price = sum(item["units_booked"] * item["price_per_unit"] for item in items_data)

        # Create booking
        booking = GuestHouseBooking.objects.create(
            renter=renter,
            total_price=total_price,
            **serializer.validated_data
        )

        # Create booking items
        for item in items_data:
            GuestHouseBookingItem.objects.create(
                booking=booking,
                **item
            )

        # Decrement availability
        GuestHouseAvailabilityService.update_availability(
            room_infos, start_date, end_date, increment=False
        )

        return Response(
            GuestHouseBookingSerializer(
                booking, 
                context={"display_currency": get_display_currency(request)}
            ).data,
            status=status.HTTP_201_CREATED
        )
# Car Listing ViewSet
@extend_schema(tags=["Car Rentals"])
class CarListingViewSet(AbstractModelViewSet):
    serializer_class = CarListingSerializer
    queryset = CarListing.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['brand', 'car_class', 'fuel_type', 'transmission', 'condition', 'listing_type', 'is_active']
    search_fields = ['title', 'description', 'brand', 'model']
    ordering_fields = ['base_price', 'year', 'mileage', 'created_at']
    ordering = ['-created_at']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        # 'list' is the action for GET /api/v1/listing/cars/
        elif self.action in ['list', 'retrieve', 'check_availability', 'available_for_rent', 'search']:
            return [AllowAny()]
        elif self.action == 'my_listings':
            return [IsAuthenticated()]
        else:
            return [IsListingOwner()]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CarListingSerializer
        return CarListingResponseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Admin sees all
        if user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) and user.role.code == RoleCode.ADMIN.value):
            pass
        # Company sees all
        elif user.is_authenticated and getattr(user, 'role', None) and user.role.code == RoleCode.COMPANY.value:
            pass
        # Others see only active
        else:
            queryset = queryset.filter(is_active=True)

        # --- Apply extra filters from query params ---
        min_year = self.request.query_params.get('min_year')
        max_year = self.request.query_params.get('max_year')
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        max_mileage = self.request.query_params.get('max_mileage')

        if min_year: queryset = queryset.filter(year__gte=int(min_year))
        if max_year: queryset = queryset.filter(year__lte=int(max_year))
        if min_price: queryset = queryset.filter(base_price__gte=float(min_price))
        if max_price: queryset = queryset.filter(base_price__lte=float(max_price))
        if max_mileage: queryset = queryset.filter(mileage__lte=int(max_mileage))

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        if not serializer.validated_data.get('company') and not serializer.validated_data.get('individual_owner'):
            try:
                individual_owner = IndividualOwnerProfile.objects.get(user=user)
                serializer.save(individual_owner=individual_owner)
            except IndividualOwnerProfile.DoesNotExist:
                try:
                    company = CompanyProfile.objects.get(user=user)
                    if company.status != CompanyProfile.StatusChoice.APPROVED:
                        raise PermissionDenied("Company profile is not approved.")
                    serializer.save(company=company)
                except CompanyProfile.DoesNotExist:
                    serializer.save()
        else:
            serializer.save()
    @extend_schema(responses=CarListingResponseSerializer)
    def list(self, request):
        """
        Handles GET /api/v1/listing/cars/ - the default endpoint.
        Applies queryset logic (active/all) and then filters/paginates.
        """
        queryset = self.get_queryset()
        
        # Apply DRF's default filtering/searching/ordering (from filter_backends)
        queryset = self.filter_queryset(queryset)
        
        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        # No pagination
        serializer = CarListingResponseSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    # --- Availability Actions ---
    @extend_schema(request=AvailabilityCheckSerializer)
    @action(detail=True, methods=['post'], serializer_class=AvailabilityCheckSerializer)
    def check_availability(self, request, pk=None):
        car_listing = self.get_object()
        serializer = AvailabilityCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        availability = CarAvailabilityService.validate_availability(
            car_listing,
            serializer.validated_data['quantity'],
            serializer.validated_data['start_date'],
            serializer.validated_data['end_date'],
        )
        
        return Response(availability)

    @extend_schema(parameters=[
        OpenApiParameter('start_date', OpenApiTypes.DATE),
        OpenApiParameter('end_date', OpenApiTypes.DATE),
        OpenApiParameter('brand', OpenApiTypes.STR),
        OpenApiParameter('car_class', OpenApiTypes.STR),
        OpenApiParameter('max_daily_price', OpenApiTypes.FLOAT),
    ])
    @action(detail=False, methods=['get'], serializer_class=CarSearchSerializer)
    def available_for_rent(self, request):
        serializer = CarSearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        cars = CarAvailabilityService.search_available_cars(
            start_date=serializer.validated_data['start_date'],
            end_date=serializer.validated_data['end_date'],
            brand=serializer.validated_data.get('brand'),
            car_class=serializer.validated_data.get('car_class')
        )

        # Filter max_daily_price
        max_price = serializer.validated_data.get('max_daily_price')
        if max_price:
            cars = [c for c in cars if c.base_price <= max_price]

        page = self.paginate_queryset(cars)
        if page is not None:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = CarListingResponseSerializer(cars, many=True, context={'request': request})
        return Response({'count': len(cars), 'results': serializer.data})

    @extend_schema(responses=CarListingResponseSerializer)
    @action(detail=False, methods=['get'])
    def my_listings(self, request):
        user = request.user
        if user.is_authenticated:
            if user.is_superuser or getattr(user, 'role', None) and user.role.code == RoleCode.ADMIN.value:
                # The get_queryset method handles filtering by role/active status already
                queryset = self.get_queryset() 
            else:
                # Fetch only listings belonging to the user's company/profile
                # NOTE: Depending on your model relationships, you might need to adjust this filter
                queryset = CarListing.objects.filter(company__user=user).distinct()
        else:
            return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        page = self.paginate_queryset(queryset)
        if page:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = CarListingResponseSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
# Car Rental ViewSet
@extend_schema(tags=["Car Rentals"])
class CarRentalViewSet(AbstractModelViewSet):
    serializer_class = CarRentalSerializer
    queryset = CarRental.objects.all()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['start_date', 'end_date', 'total_price', 'created_at']
    ordering = ['-created_at']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve', 'my_rentals', 'rental_stats']:
            return [IsAuthenticated()]
        else:
            return [IsCarRentalOwner()]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return CarRental.objects.none()
        queryset = super().get_queryset()

        # Admin sees all
        if user.is_superuser or getattr(user, 'role', None) and user.role.code == RoleCode.ADMIN.value:
            return queryset

        # User sees own rentals
        user_rentals = queryset.filter(renter=user)

        # Company sees rentals for their cars + own rentals
        if getattr(user, 'role', None) and user.role.code == RoleCode.COMPANY.value:
            company_rentals = queryset.filter(rental_items__car_listing__company=user.profile).distinct()
            return (user_rentals | company_rentals).distinct()

        return user_rentals

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rental_items_data = request.data.get('rental_items', [])

        # --- Check availability for all rental items ---
        for item_data in rental_items_data:
            car_listing = CarListing.objects.get(id=item_data['car_listing'])
            availability = CarAvailabilityService.validate_availability(
                car_listing,
                serializer.validated_data['start_date'],
                serializer.validated_data['end_date'],
                item_data.get('units_rent', 1)
            )
            if not availability.get('available'):
                return Response({"error": availability.get('reason')}, status=status.HTTP_400_BAD_REQUEST)

        rental = serializer.save(renter=request.user)

        # --- Create rental items & update availability ---
        for item_data in rental_items_data:
            car_listing = CarListing.objects.get(id=item_data['car_listing'])
            rental_item = CarRentalItem.objects.create(
                car_rental=rental,
                car_listing=car_listing,
                units_rent=item_data['units_rent'],
                price_per_unit=item_data['price_per_unit']
            )
            CarAvailabilityService.update_availability(
                car_listing=car_listing,
                rental=rental,
                rental_item=rental_item,
                action="create"
            )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        rental = self.get_object()
        if rental.status != CarRental.RentStatus.PENDING:
            return Response({"error": "Only pending rentals can be confirmed."}, status=status.HTTP_400_BAD_REQUEST)

        # Check daily availability again
        for item in rental.rental_items.all():
            availability = CarAvailabilityService.validate_availability(
                item.car_listing, rental.start_date, rental.end_date, item.units_rent
            )
            if not availability.get('available'):
                return Response({"error": availability.get('reason')}, status=status.HTTP_400_BAD_REQUEST)

        rental.status = CarRental.RentStatus.CONFIRMED
        rental.save()

        for item in rental.rental_items.all():
            CarAvailabilityService.update_availability(
                item.car_listing, rental, item, action="confirm"
            )
        return Response(self.get_serializer(rental).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        rental = self.get_object()
        if rental.status == CarRental.RentStatus.CANCELLED:
            return Response({"error": "Rental is already cancelled."}, status=status.HTTP_400_BAD_REQUEST)

        rental.status = CarRental.RentStatus.CANCELLED
        rental.save()

        for item in rental.rental_items.all():
            CarAvailabilityService.update_availability(
                item.car_listing, rental, item, action="cancel"
            )
        return Response(self.get_serializer(rental).data)

    @action(detail=False, methods=['get'])
    def my_rentals(self, request):
        rentals = self.get_queryset().filter(renter=request.user)
        page = self.paginate_queryset(rentals)
        if page:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(rentals, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def rental_stats(self, request):
        user = request.user
        queryset = CarRental.objects.filter(renter=user)
        total_spent = queryset.filter(status=CarRental.RentStatus.CONFIRMED).aggregate(total=Sum('total_price'))['total'] or 0
        return Response({
            "total_rentals": queryset.count(),
            "confirmed_rentals": queryset.filter(status=CarRental.RentStatus.CONFIRMED).count(),
            "pending_rentals": queryset.filter(status=CarRental.RentStatus.PENDING).count(),
            "cancelled_rentals": queryset.filter(status=CarRental.RentStatus.CANCELLED).count(),
            "total_spent": float(total_spent)
        })

# Availability APIViews
class CarAvailabilitySearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=CarAvailabilitySerializer)
    def get(self, request):
        car_listing_id, start_date, end_date, quantity_or_resp = ParseDatesAndQuantity.parse_dates_and_quantity(request, require_car=True)
        if isinstance(quantity_or_resp, Response):
            return quantity_or_resp
        car_listing = CarListing.objects.get(id=car_listing_id)
        availability = CarAvailabilityService.validate_availability(car_listing, start_date, end_date, quantity_or_resp)
        return Response({
            "car_listing": {
                "id": car_listing.id, "title": car_listing.title, "brand": car_listing.brand,
                "model": car_listing.model, "base_price": str(car_listing.base_price)
            },
            "search_period": {"start_date": start_date, "end_date": end_date},
            "quantity_requested": quantity_or_resp,
            "availability": availability
        })

class CarAvailabilityByDateRangeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="Search all available cars in a date range")
    def get(self, request):
        _, start_date, end_date, quantity_or_resp = ParseDatesAndQuantity.parse_dates_and_quantity(request)
        if isinstance(quantity_or_resp, Response):
            return quantity_or_resp

        results = []
        for car in CarListing.objects.all():
            availability = CarAvailabilityService.get_available_cars(car, start_date, end_date, quantity_or_resp)
            if availability.get("is_available"):
                results.append({
                    "car_listing_id": car.id,
                    "title": car.title,
                    "brand": car.brand,
                    "model": car.model,
                    "base_price": str(car.base_price),
                    "availability": availability
                })
        return Response({
            "search_period": {"start_date": start_date, "end_date": end_date},
            "quantity_requested": quantity_or_resp,
            "available_cars_count": len(results),
            "available_cars": results
        })

class CarAvailabilityByCarAndDateView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="Get availability for a specific car listing within a date range")
    def get(self, request):
        car_listing_id, start_date, end_date, quantity_or_resp = ParseDatesAndQuantity.parse_dates_and_quantity(request, require_car=True)
        if isinstance(quantity_or_resp, Response):
            return quantity_or_resp
        car_listing = CarListing.objects.get(id=car_listing_id)
        availability = CarAvailabilityService.validate_availability(car_listing, start_date, end_date, quantity_or_resp)
        return Response({
            "car_listing": {
                "id": car_listing.id, "title": car_listing.title, "brand": car_listing.brand,
                "model": car_listing.model, "base_price": str(car_listing.base_price)
            },
            "search_period": {"start_date": start_date, "end_date": end_date},
            "quantity_requested": quantity_or_resp,
            "availability": availability
        })

@extend_schema(responses=PropertyListingResponseSerializer)
class PropertyListingViewSet(AbstractModelViewSet):
    serializer_class = PropertyListingSerializer
    queryset = PropertyListing.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        """
        - CREATE: Company users can create properties, admin can create all
        - READ: Public (all can read)
        - UPDATE/DELETE: Company can modify own properties, admin can modify all
        """
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve']:
            return [AllowAny()]
        else:
            return [IsListingOwner()]

    def get_queryset(self):
        """Filter queryset - show all active to public, all to companies/admin."""
        queryset = super().get_queryset()
        
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.filter(is_active=True)
        
        if self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and
            self.request.user.role and
            self.request.user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        if hasattr(self.request.user, 'role') and self.request.user.role:
            if self.request.user.role.code == RoleCode.COMPANY.value:
                return queryset
        
        return queryset.filter(is_active=True)


class AmenityViewSet(AbstractModelViewSet):
    http_method_names = ["get"]
    permission_classes = [AllowAny]
    serializer_class = AmenityResponseSSerializer
    queryset = Amenity.objects.all()


class BookingViewSet(AbstractModelViewSet):
    http_method_names = ["get", "post"]
    serializer_class = BookingSerializer
    queryset = Booking.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = BookingFilter

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        """
        - CREATE: Authenticated users can create bookings
        - READ: Users see own bookings, companies see bookings for their listings, admin sees all
        - Special actions: partial_cancel, rate require ownership
        """
        if self.action == 'create':
            return [ORPermission(IsAuthenticated, IsCompanyOrFrontDesk)]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['partial_cancel', 'cancel','rate_booking']:
            return [IsBookingOwner()]
        else:
            return [IsAuthenticated()]

    def get_queryset(self):
        """
        Filter bookings based on user role:
        - Users: See only their own bookings
        - Companies: See bookings for their listings + own bookings (as customers)
        - Admin: See all bookings
        """
        if not self.request.user or not self.request.user.is_authenticated:
            return Booking.objects.none()
        
        queryset = Booking.objects.prefetch_related("items", "items__room")
        
        # Admin sees all
        if self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and
            self.request.user.role and
            self.request.user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        # Users see only their own bookings
        user_bookings = queryset.filter(user=self.request.user).distinct()
        
        # Companies see bookings for their listings + own bookings
        if hasattr(self.request.user, 'role') and self.request.user.role:
            if self.request.user.role.code == RoleCode.COMPANY.value:
                # Get company's hotels
                if hasattr(self.request.user, 'profile') and self.request.user.profile:
                    from apps.account.models import HotelProfile
                    company = self.request.user.profile
                    try:
                        hotel = HotelProfile.objects.get(company=company)
                        # Get bookings for rooms in this hotel
                        hotel_bookings = queryset.filter(
                            items__room__hotel=hotel
                        ).distinct()
                        # Combine with user's own bookings (if they booked as customer)
                        return (user_bookings | hotel_bookings).distinct()
                    except HotelProfile.DoesNotExist:
                        pass
        
        return user_bookings

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Allows an authenticated user to cancel their booking."""
        booking = self.get_object()
        
        try:
            cancelled_booking = BookingService.cancel_booking(booking)
        except BookingConflict as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        return Response(
            BookingResponseSerializer(
                cancelled_booking, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_200_OK
        )
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
                "featured": hotel.featured,
                "images": ListingImageSerializer(hotel.images.all(), many=True).data,
                "facilities": FacilityResponseSerializer(hotel.facilities.all(), many=True).data,
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

            # Populate hotel-level base_price using the cheapest room's display_price or base_price
            # to enable converted_price calculation in SearchResultSerializer
            if hotel_result["rooms"]:
                hotel_result["base_price"] = min(r["display_price"] for r in hotel_result["rooms"])
                # We assume currency is consistent across rooms of the same hotel
                # or we default to the first room's currency.
                first_room = stay_data["rooms"][0]["room"]
                hotel_result["currency"] = getattr(first_room, "currency", "ETB")
            
            results.append(hotel_result)

        # Resolve favorites once per request for hotel search results
        try:
            ct = ContentType.objects.get(app_label="account", model="hotelprofile")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(request.user, ct) if ct is not None else set()

        display_currency = get_display_currency(request)
        serializer = SearchResultSerializer(
            results, 
            many=True, 
            context={
                "request": request, 
                "favorite_object_ids": fav_ids,
                "display_currency": display_currency
            }
        )
        return Response(serializer.data)
class StayAvailabilityUpdateView(APIView):
    def get_permissions(self):
        """
        Only company owners of the hotel or admin can update availability.
        """
        return [IsAuthenticated()]

    def put(self, request, pk):
        """
        Update a StayAvailability instance.
        Only the hotel owner (company) or admin can update.
        """
        stay_availability = get_object_or_404(StayAvailability, pk=pk)
        
        # Check if user has permission to update this availability
        user = request.user
        
        # Admin can always update
        is_admin = user.is_superuser or (
            hasattr(user, 'role') and
            user.role and
            user.role.code == RoleCode.ADMIN.value
        )
        
        if not is_admin:
            # Check if user owns the hotel
            hotel = stay_availability.hotel
            if hasattr(hotel, 'company') and hotel.company:
                if not (hasattr(hotel.company, 'user') and hotel.company.user == user):
                    return Response(
                        {"detail": "You do not have permission to update this availability."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                return Response(
                    {"detail": "You do not have permission to update this availability."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        serializer = StayAvailabilityUpdateSerializer(
            instance=stay_availability,
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "id": str(stay_availability.id),
                **serializer.data,
                "detail": "Stay availability updated successfully."
            },
            status=status.HTTP_200_OK
        )
class CarAvailabilityUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def patch(self, request, pk, format=None):
        """Update a CarAvailability instance (partial update)."""
        availability = get_object_or_404(CarAvailability, pk=pk)
        # Set partial=True to allow missing fields
        serializer = CarAvailabilityUpdateSerializer(availability, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
@extend_schema(responses=EventSpaceListingResponseSerializer)
class EventSpaceListingViewSet(AbstractModelViewSet):
    """
    ViewSet for viewing and managing Event Space Listings, including 
    handling seasonal pricing display.
    """
    serializer_class = EventSpaceListingSerializer
    # Pre-fetch related data for efficient retrieval
    queryset = EventSpaceListing.objects.all().select_related(
        "hotel", "address"
    ).prefetch_related(
        "images", "amenities", "availability" 
    )
    filter_backends = [DjangoFilterBackend]
    filterset_class = EventSpaceFilter # Use the dedicated filter class

    # --- Permission Logic ---
    def get_permissions(self):
        """
        Applies access control based on the action and user role.
        """
        if self.action == 'create':
            # Only authenticated users (Company/Admin) can create listings
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve']:
            # Public access for reading listings
            return [AllowAny()]
        else:
            # Update/Delete requires the user to own the listing
            return [IsListingOwner()]

    # --- Queryset Logic ---
    def get_queryset(self):
        """
        Filters queryset based on user role, matching the logic of RoomListing.
        """
        queryset = super().get_queryset()
        
        # If user is not authenticated, show only active listings (assuming an 'is_active' field)
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.filter(is_active=True)
        
        if self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and
            self.request.user.role and
            self.request.user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        # Company/Other user roles logic
        if hasattr(self.request.user, 'role') and self.request.user.role:
            if self.request.user.role.code == RoleCode.COMPANY.value:
                # Companies see all listings for reference
                return queryset
            else:
                # Regular users see only active listings
                return queryset.filter(is_active=True)
        
        return queryset.filter(is_active=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        context["display_currency"] = get_display_currency(self.request)
        return context

    # --- Retrieve (Detail) Action ---
    def retrieve(self, request, *args, **kwargs):
        """
        Return event space detail with optional seasonal display price 
        when date query params are provided.
        """
        instance = self.get_object()
        serializer = EventSpaceListingResponseSerializer(instance, context=self.get_serializer_context())
        data = serializer.data

        # Price calculation logic
        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')

        # default values
        data['display_price'] = data.get('base_price')

        if use_seasonal and check_in and check_out:
            check_in_date = parse_date(check_in)
            check_out_date = parse_date(check_out)
            
            if check_in_date and check_out_date and check_out_date > check_in_date:
                cursor = check_in_date
                prices = []
                while cursor < check_out_date:
                    # Assumes PriceService can resolve price for an EventSpaceListing instance
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

    # --- List Action ---
    def list(self, request, *args, **kwargs):
        """
        List event spaces; computes display_price and preview fields for each 
        listing if date params are provided.
        """
        qs = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(qs)
        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        check_in = request.query_params.get('check_in') or request.query_params.get('check_in_date')
        check_out = request.query_params.get('check_out') or request.query_params.get('check_out_date')

        listings = page if page is not None else list(qs)

        serialized = []
        for listing in listings:
            serializer = EventSpaceListingResponseSerializer(listing, context=self.get_serializer_context())
            data = serializer.data
            
            # default
            data['display_price'] = data.get('base_price')

            if use_seasonal and check_in and check_out:
                check_in_date = parse_date(check_in)
                check_out_date = parse_date(check_out)
                
                if check_in_date and check_out_date and check_out_date > check_in_date:
                    cursor = check_in_date
                    prices = []
                    while cursor < check_out_date:
                        # Assumes PriceService can resolve price for an EventSpaceListing instance
                        p = PriceService.resolve_price(listing, cursor) 
                        prices.append(p)
                        cursor += timedelta(days=1)
                        
                    if prices:
                        preview_total = sum(prices)
                        preview_min = min(prices)
                        preview_has_discount = any(p < listing.base_price for p in prices)
                        
                        data['preview_min_price'] = preview_min
                        data['preview_total'] = preview_total
                        data['preview_has_discount'] = preview_has_discount
                        data['display_price'] = preview_min if preview_has_discount else listing.base_price

            serialized.append(data)

        if page is not None:
            return self.get_paginated_response(serialized)

        return Response(serialized)
    @extend_schema(
    summary="Search available event spaces",
    description="Searches available event spaces by date, quantity, and optional address.",
    parameters=[
        OpenApiParameter(
            name="quantity",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Required number of units"
        ),
        OpenApiParameter(
            name="check_in",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Check-in date (YYYY-MM-DD)"
        ),
        OpenApiParameter(
            name="check_out",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Check-out date (YYYY-MM-DD)"
        ),
        OpenApiParameter(
            name="address",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Optional address search term"
        ),
    ],
    responses={200: EventSpaceListingSerializer(many=True)}
)
    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Searches available event spaces by date, quantity, and address.
        """
        try:
            quantity_str = request.query_params.get('quantity')
            check_in_str = request.query_params.get('check_in')
            check_out_str = request.query_params.get('check_out')
            address_query = request.query_params.get('address')

            if not all([quantity_str, check_in_str, check_out_str]):
                return Response(
                    {"error": "Missing required query parameters: quantity, check_in, check_out."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            required_quantity = int(quantity_str)
            check_in_date = date.fromisoformat(check_in_str)
            check_out_date = date.fromisoformat(check_out_str)

        except (ValueError, TypeError) as e:
            return Response(
                {"error": f"Invalid parameter format: {e}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        available_listings = EventSpaceAvailabilityService.search_available_listings(
            check_in_date,
            check_out_date,
            required_quantity,
            address_query=address_query,
        )

        serializer = self.get_serializer(available_listings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
@extend_schema(responses=EventSpaceBookingResponseSerializer)
class EventSpaceBookingViewSet(AbstractModelViewSet):
    """
    ViewSet for viewing and managing Event Space Bookings (Create/List/Retrieve only).
    """
    # Only allow GET (list/retrieve) and POST (create)
    http_method_names = ["get", "post"] 
    serializer_class = EventSpaceBookingSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context
    
    # Prefetch related data for efficiency
    queryset = EventSpaceBooking.objects.prefetch_related(
        "items", 
        "items__event_space"
    )
    filter_backends = [DjangoFilterBackend]
    # Use the dedicated filter class (must be implemented)
    filterset_class = EventSpaceBookingFilter 

    # --- Permissions ---
    def get_permissions(self):
        """
        Applies access control based on the action and user role.
        """
        if self.action == 'create':
            # Only authenticated users (and potentially company/front desk) can create
            return [ORPermission(IsAuthenticated, IsCompanyOrFrontDesk)]
        elif self.action in ['list', 'retrieve']:
            # All authenticated users can see their permitted list/detail
            return [IsAuthenticated()]
        # Removed: partial_cancel and rate_booking actions
        else:
            return [IsAuthenticated()]

    # --- Queryset Filtering ---
    def get_queryset(self):
        """
        Filter bookings based on user role: User, Company, or Admin.
        """
        user = self.request.user
        if not user or not user.is_authenticated:
            return EventSpaceBooking.objects.none()
        
        queryset = super().get_queryset() # Starts with the prefetched queryset
        
        # Admin sees all
        if user.is_superuser or (
            hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        user_bookings = queryset.filter(user=user)
        
        if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
            if hasattr(user, 'profile') and user.profile:
                company = user.profile
                try:
                    hotel = HotelProfile.objects.get(company=company)
                    
                    hotel_bookings = queryset.filter(
                        items__event_space__hotel=hotel
                    ).distinct()
                    
                    return (user_bookings | hotel_bookings).distinct()
                except HotelProfile.DoesNotExist:
                    pass
        
        # Default: Return only the user's own bookings
        return user_bookings

    def perform_create(self, serializer):
        """Passes the request user to the serializer's create method."""
        serializer.save(user=self.request.user)


@extend_schema(tags=["Terms & Conditions"])
class TermsAndConditionsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for retrieving Terms & Conditions.
    
    - list: Get all T&C (admin only)
    - retrieve: Get specific T&C by ID  
    - hotel/{hotel_id}: Get active T&C for a hotel
    """
    from apps.listing.serializers import TermsAndConditionsSerializer
    from apps.listing.models import TermsAndConditions
    
    serializer_class = TermsAndConditionsSerializer
    permission_classes = [AllowAny]
    queryset = TermsAndConditions.objects.filter(is_active=True)
    
    @extend_schema(
        summary="Get active Terms & Conditions for a hotel",
        description="Retrieve the currently active T&C for a specific hotel",
        responses={200: TermsAndConditionsSerializer, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='hotel/(?P<hotel_id>[^/.]+)')
    def hotel_terms(self, request, hotel_id=None):
        """Get active T&C for a hotel"""
        from apps.account.models import HotelProfile
        from apps.listing.services import TermsService
        
        hotel = get_object_or_404(HotelProfile, id=hotel_id)
        terms = TermsService.get_active_terms(content_object=hotel)
        
        if not terms:
            return Response(
                {"detail": "No terms and conditions available for this hotel."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.serializer_class(terms)
        return Response(serializer.data)

    