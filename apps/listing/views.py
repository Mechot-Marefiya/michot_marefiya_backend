
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
from rest_framework.throttling import ScopedRateThrottle
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
from apps.core.pagination import StandardResultsSetPagination
from apps.account.permissions import (
    IsAuthenticatedOrReadOnly,
    IsCompanyOwner,
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
    CarListing,
    GuestHouseProfile, GuestHouseRoom,
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
    GuestHouseBookingItem,
    AddonOffering,
    Season, SeasonalRate,
)
from apps.account.models import(CompanyProfile,IndividualOwnerProfile,HotelProfile)
from apps.listing.serializers import (
    AmenityResponseSSerializer,
    BookingPreviewSerializer,
    BookingSerializer,BookingResponseSerializer,
    CarListingResponseSerializer,
    CarListingSerializer,
    BookingRatingSerializer,
    
    CarAvailabilityUpdateSerializer,
    EventSpaceBookingPreviewSerializer,
    GuestHouseBookingPreviewSerializer,
    GuestHouseBookingPreviewSerializer,
    GuestHouseProfileResponseSerializer, GuestHouseRoomResponseSerializer,
    GuestHouseProfileSerializer, GuestHouseRoomSerializer,
    PricePreviewResponseSerializer,
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
    GuestHouseBookingSerializer,
    AddonOfferingSerializer,
    AddonOfferingListSerializer,
    BookingLookupSerializer,
    GuestCancellationSerializer,
    SeasonSerializer, SeasonalRateSerializer,
)
from apps.listing.services import (
    StayAvailabilityService, BookingService, CarAvailabilityService, 
    PriceService, GuestHouseAvailabilityService, EventSpaceAvailabilityService,
    PriceCalculationService
)
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
        queryset = super().get_queryset().select_related(
            'hotel', 
            'address'
        ).prefetch_related(
            'images', 
            'amenities'
        )
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        # Admin sees all
        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset

        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(hotel__company=company)
            if individual_owner:
                pass
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    @extend_schema(
        summary="Price Preview for specific dates",
        description=(
            "**DEPRECATED**: This endpoint is deprecated and will be removed in a future version. "
            "Use the main room detail endpoint with check_in/check_out query parameters instead: "
            "`GET /rooms/{id}/?check_in=YYYY-MM-DD&check_out=YYYY-MM-DD`. "
            "The response will include a complete `price_quote` field with platform fee and currency conversion."
        ),
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=True, description="Arrival date"),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=True, description="Departure date"),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        deprecated=True
    )
    @action(detail=True, methods=['get'], url_path='price-preview')
    def price_preview(self, request, pk=None):
        """
        DEPRECATED: Use room detail endpoint with check_in/check_out params instead.
        This endpoint does NOT include the 5% platform fee and lacks currency conversion.
        """
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

        lines = PriceService.resolve_price_details_batch(room, check_in_date, check_out_date)
        total = sum(Decimal(str(l['price_per_unit'])) for l in lines)
        has_discount = any(l.get('is_discounted') for l in lines)

        response = Response({
            'lines': lines,
            'total': f"{total:.2f}",
            'has_discount': bool(has_discount),
            'warning': (
                'DEPRECATED: This endpoint does not include platform fees. '
                'Use GET /rooms/{id}/?check_in=X&check_out=Y for accurate pricing.'
            )
        })
        
        response['Warning'] = (
            '299 - "Deprecated: Use ?check_in&check_out on main room endpoint instead. '
            'This endpoint will be removed in v2.0"'
        )
        return response

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

    @extend_schema(
        summary="Retrieve room details with accurate pricing",
        description="""
        Returns detailed information about a room listing. 
        Highly recommended: Provide `check_in` and `check_out` query parameters to receive a 
        comprehensive `price_quote` object including platform fees and daily breakdowns.
        """,
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=False, description="Arrival date (YYYY-MM-DD)"),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=False, description="Departure date (YYYY-MM-DD)"),
        ]
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = RoomListingResponseSerializer(instance, context=self.get_serializer_context())
        data = serializer.data

        quote = data.get('price_quote')
        if quote:
            prices = [Decimal(str(line['price_per_unit'])) for line in quote['breakdown']]
            if prices:
                preview_min = min(prices)
                data['preview_min_price'] = f"{preview_min:.2f}"
                data['preview_total'] = str(quote['items_subtotal'])
                data['preview_has_discount'] = quote['has_discount']
                data['display_price'] = f"{preview_min:.2f}" if quote['has_discount'] else f"{Decimal(str(data.get('base_price'))):.2f}"
        else:
            data['display_price'] = f"{Decimal(str(data.get('base_price'))):.2f}"

        return Response(data)

    @extend_schema(
        summary="List rooms with optional date-based pricing",
        description="""
        Returns a list of room listings. Provides `price_quote` and seasonal details 
        if `check_in` and `check_out` parameters are supplied.
        """,
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=False, description="Arrival date (YYYY-MM-DD)"),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=False, description="Departure date (YYYY-MM-DD)"),
            OpenApiParameter("hotel", OpenApiTypes.STR, required=False, description="Filter rooms by Hotel UUID"),
        ]
    )
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        rooms = page if page is not None else list(qs)

        serialized = []
        for room in rooms:
            serializer = RoomListingResponseSerializer(room, context=self.get_serializer_context())
            data = serializer.data
            
            quote = data.get('price_quote')
            if quote:
                prices = [Decimal(str(line['price_per_unit'])) for line in quote['breakdown']]
                if prices:
                    preview_min = min(prices)
                    data['preview_min_price'] = f"{preview_min:.2f}"
                    data['preview_total'] = str(quote['items_subtotal'])
                    data['preview_has_discount'] = quote['has_discount']
                    data['display_price'] = f"{preview_min:.2f}" if quote['has_discount'] else f"{Decimal(str(data.get('base_price'))):.2f}"
            else:
                data['display_price'] = f"{Decimal(str(data.get('base_price'))):.2f}"

            serialized.append(data)

        if page is not None:
            return self.get_paginated_response(serialized)
        return Response(serialized)

    @action(detail=False, methods=['get'], url_path='availability-matrix')
    def availability_matrix(self, request):
        workspace_id = request.query_params.get("workspace")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not workspace_id or not start_date_str or not end_date_str:
             return Response({"detail": "workspace, start_date, end_date required"}, status=400)
             
        try:
             start_date = date.fromisoformat(start_date_str)
             end_date = date.fromisoformat(end_date_str)
        except:
             return Response({"detail": "Invalid date format"}, status=400)
             
        room_qs = RoomListing.objects.filter(
            Q(hotel__id=workspace_id) | Q(hotel__company__id=workspace_id)
        ).select_related('hotel')
        
        if not room_qs.exists():
             return Response([])

        hotel_ids = room_qs.values_list('hotel_id', flat=True).distinct()
        
        full_matrix = {}
        for h_id in hotel_ids:
             matrix = StayAvailabilityService.get_availability_matrix(h_id, start_date, end_date)
             full_matrix.update(matrix)
             
        date_cursor = start_date
        dates = []
        while date_cursor <= end_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)

        results = []
        for room in room_qs:
            r_id = str(room.id)
            avail_map = full_matrix.get(r_id, {})
            
            availability_list = []
            for d in dates:
                d_str = d.isoformat()
                available_count = avail_map.get(d_str, room.total_units) 
                
                status_val = 'available'
                if available_count == 0:
                    status_val = 'full'
                elif available_count < room.total_units:
                    status_val = 'partial'
                
                availability_list.append({
                    "date": d_str,
                    "available": available_count,
                    "status": status_val
                })
            
            results.append({
                "room_id": r_id,
                "room_name": room.title,
                "total_units": room.total_units,
                "availability": availability_list
            })
            
        return Response(results)



@extend_schema(tags=["Guest House Rooms"])
class GuestHouseRoomViewSet(AbstractModelViewSet):
    serializer_class = GuestHouseRoomSerializer
    queryset = GuestHouseRoom.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["guest_house", "total_units", "number_of_guests"]

    def get_serializer_class(self):
        if self.action in ["list", "retrieve", "price_preview"]:
            return GuestHouseRoomResponseSerializer
        return GuestHouseRoomSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve', 'price_preview']:
            return [AllowAny()]
        else:
            return [IsListingOwner()]

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "guest_house", "guest_house__address"
        ).prefetch_related(
            "images", "amenities"
        )
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.filter(guest_house__is_active=True)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        request = self.request
        context["request"] = request
        context["display_currency"] = get_display_currency(request)
        
        check_in = request.query_params.get("check_in")
        check_out = request.query_params.get("check_out")
        
        if check_in and check_out:
             try:
                check_in_date = parse_date(check_in)
                check_out_date = parse_date(check_out)
                pass 
             except Exception:
                 pass
        return context

    @extend_schema(
        summary="Retrieve room details with accurate pricing",
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=False),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=False),
        ]
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = GuestHouseRoomResponseSerializer(instance, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='availability-matrix')
    def availability_matrix(self, request):
        workspace_id = request.query_params.get("workspace")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not workspace_id or not start_date_str or not end_date_str:
             return Response({"detail": "workspace, start_date, end_date required"}, status=400)
             
        try:
             start_date = date.fromisoformat(start_date_str)
             end_date = date.fromisoformat(end_date_str)
        except:
             return Response({"detail": "Invalid date format"}, status=400)
             
        room_qs = GuestHouseRoom.objects.filter(
            Q(guest_house__id=workspace_id) | 
            Q(guest_house__company__id=workspace_id) | 
            Q(guest_house__individual_owner__id=workspace_id)
        )
        
        if not room_qs.exists():
             return Response([])
             
        gh_ids = room_qs.values_list('guest_house_id', flat=True).distinct()
        
        full_matrix = {}
        for gh_id in gh_ids:
             matrix = GuestHouseAvailabilityService.get_availability_matrix(gh_id, start_date, end_date)
             full_matrix.update(matrix)
             
        date_cursor = start_date
        dates = []
        while date_cursor <= end_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)

        results = []
        for room in room_qs:
            r_id = str(room.id)
            avail_map = full_matrix.get(r_id, {})
            
            availability_list = []
            for d in dates:
                d_str = d.isoformat()
                available_count = avail_map.get(d_str, room.total_units)
                
                status_val = 'available'
                if available_count == 0:
                     status_val = 'full'
                elif available_count < room.total_units:
                     status_val = 'partial'
                     
                availability_list.append({
                    "date": d_str,
                    "available": available_count,
                    "status": status_val
                })
            results.append({
                "room_id": r_id,
                "room_name": room.title,
                "total_units": room.total_units,
                "availability": availability_list
            })
            
        return Response(results)


@extend_schema(tags=["Accommodations"])
class GuestHouseProfileViewSet(AbstractModelViewSet):
    serializer_class = GuestHouseProfileSerializer
    queryset = GuestHouseProfile.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['title', 'description', 'address__city', 'address__sub_city']
    throttle_scope = None

    def get_permissions(self):
        """
        - CREATE: Company users can create guest houses, admin can create all
        - READ: Public (all can read)
        - UPDATE/DELETE: Company can modify own guest houses, admin can modify all
        """
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve', 'check_availability']:
            return [AllowAny()]
        else:
            return [IsListingOwner()]

    def get_serializer_class(self):
        if self.action in ["list", "retrieve", "check_availability"]:
            return GuestHouseProfileResponseSerializer
        return GuestHouseProfileSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'company',
            'individual_owner'
        ).prefetch_related(
            'images',
            'amenities',
            'facility',
            'rooms'
        )
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset

        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(company=company)
            if individual_owner:
                q |= Q(individual_owner=individual_owner)
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        
        # resolve favorites
        try:
            ct = ContentType.objects.get(app_label="listing", model="guesthouseprofile")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(self.request.user, ct) if ct is not None else set()

        context["favorite_object_ids"] = fav_ids
        context["display_currency"] = get_display_currency(self.request)
        
        return context

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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
            responses=GuestHouseProfileResponseSerializer(many=True)
        )
    @action(
        detail=False, 
        methods=["get"], 
        url_path="check-availability",
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def check_availability(self, request):
            """
            Check availability across all guesthouses or a specific one.
            Returns PROFILES that have at least one room type meeting criteria.
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
                profile = GuestHouseProfile.objects.filter(id=guesthouse_id, is_active=True).first()
                if not profile:
                    return Response({"error": "Guest house not found."}, status=404)

                qs, meta = GuestHouseAvailabilityService.get_available_listings(
                    check_in, check_out, units, address_filters
                )
                qs = qs.filter(id=guesthouse_id)
            else:
                qs, meta = GuestHouseAvailabilityService.get_available_listings(
                    check_in, check_out, units, address_filters
                )
            
            context = self.get_serializer_context()
            availability_map = {row["guest_house_room"]: row["min_available"] for row in meta}
            context["availability_map"] = availability_map
            
            serializer = GuestHouseProfileResponseSerializer(qs, many=True, context=context)
            return Response({
                "count": qs.count(),
                "results": serializer.data
            })

@extend_schema(tags=["Accommodations"])
class GuestHouseBookingViewSet(AbstractModelViewSet):
    """
    ViewSet for GuestHouse Bookings with full CRUD operations.
    """
    serializer_class = GuestHouseBookingSerializer
    queryset = GuestHouseBooking.objects.all()
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = {
        'status': ['exact'],
        'start_date': ['gte', 'lte'],
        'end_date': ['gte', 'lte']
    }
    ordering_fields = ['start_date', 'end_date', 'total_price', 'created_at']
    ordering = ['-created_at']
    search_fields = [
        'booking_reference',
        'renter__email',
        'renter__first_name',
        'renter__last_name',
        'guest_email',
        'guest_first_name',
        'guest_last_name',
        'guest_phone'
    ]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        context["request"] = self.request
        return context

    def get_permissions(self):
        """
        - CREATE: Authenticated users can create bookings
        - READ: Authenticated users (see own + companies see their guesthouses)
        - UPDATE/DELETE: Booking owner or guesthouse owner
        """
        if self.action in ['create', 'lookup', 'price_preview']:
            return [AllowAny()]
        elif self.action in ['list', 'retrieve', 'my_bookings']:
            return [IsAuthenticated()]
        else:
            # For update/delete/cancel, require ownership
            from apps.account.permissions import IsGuestHouseBookingOwner
            return [IsGuestHouseBookingOwner()]

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()
    
    def get_queryset(self):
        """
        Filter queryset based on user role:
        - Admin: sees all bookings
        - Company (mode='host'): sees bookings for their guesthouses
        - User/Default: sees only own bookings as a guest
        """
        user = self.request.user
        if not user.is_authenticated:
            return GuestHouseBooking.objects.none()
            
        queryset = super().get_queryset()
        
        # Admin sees all
        if user.is_superuser or (
            hasattr(user, 'role') and 
            user.role and 
            user.role.code == RoleCode.ADMIN.value
        ):
            return queryset

        # Check for mode parameter
        mode = self.request.query_params.get('mode')

        # CASE 1: Host Mode (Extranet)
        if mode == 'host':
            # Company sees bookings for their guesthouses
            if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
                # Filter by company user
                return queryset.filter(items__room__guest_house__company__user=user).distinct()
            # Individual owner logic could go here if needed, but for now enforcing company/role check
             # If individual owner logic is needed:
            if hasattr(user, 'individual_owner') and user.individual_owner:
                 return queryset.filter(items__room__guest_house__individual_owner=user.individual_owner).distinct()

            return queryset.none()
        
        
        # Check for mode parameter (Feature branch logic)
        mode = self.request.query_params.get('mode')
        if mode == 'host':
            if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
                return queryset.filter(items__room__guest_house__company__user=user).distinct()
            if hasattr(user, 'individual_owner') and user.individual_owner:
                 return queryset.filter(items__room__guest_house__individual_owner=user.individual_owner).distinct()
            return queryset.none()

        # Base filter: User sees own bookings as renter
        query = Q(renter=user)
        
        if self.request.query_params.get('as_guest') == 'true':
            return queryset.filter(query).distinct()
        
        # Company sees bookings for their guesthouses
        if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
            query |= Q(items__room__guest_house__company__user=user)
        
        return queryset.filter(query).distinct()

    @extend_schema(
        summary="Lookup guest house booking status (Guest)",
        description="Retrieve booking details using reference and guest email. No login required.",
        parameters=[
            OpenApiParameter("reference", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("email", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: GuestHouseBookingSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = BookingLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        reference = serializer.validated_data['reference']
        email = serializer.validated_data['email']
        
        booking = get_object_or_404(
            GuestHouseBooking.objects.prefetch_related("items", "items__room"),
            booking_reference=reference,
            guest_email=email
        )
        
        response_serializer = GuestHouseBookingSerializer(booking, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @action(detail=False, methods=['get'], url_path='workspace-bookings')
    def workspace_bookings(self, request):
        user = request.user
        
        if not user.workspace:
             return Response(
                {"detail": "No workspace assigned to this user."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        workspace = user.workspace
        queryset = self.get_queryset()
        
        if hasattr(workspace, 'is_guesthouse') or workspace.__class__.__name__ == 'GuestHouseProfile':
            queryset = queryset.filter(items__room__guest_house=workspace).distinct()
        else:
             return Response([])

        return Response(GuestHouseBookingPreviewSerializer(queryset, many=True, context=self.get_serializer_context()).data)

    @extend_schema(request=GuestHouseBookingSerializer, responses=GuestHouseBookingSerializer)
    @action(detail=False, methods=['post'], url_path='walk-in', permission_classes=[IsAuthenticated])
    def walk_in(self, request, *args, **kwargs):
        """
        Create a walk-in booking. 
        Passes is_walk_in=True via context to trigger staff privileges check.
        Requires authentication.
        """
        # Default currency to ETB for walk-ins if not specified
        data = request.data.copy()
        if 'payment_currency' not in data:
            data['payment_currency'] = 'ETB'
        
        # Pass is_walk_in via context, not data
        context = {**self.get_serializer_context(), 'is_walk_in': True}
        serializer = self.get_serializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @extend_schema(
        summary="Create a new guesthouse booking (supports guest checkout)",
        description="""
        Initiates a booking for one or more rooms in a guest house.
        - Supports both authenticated users and guest checkout.
        - Required guest fields: `guest_email`, `guest_phone`, `guest_first_name`, `guest_last_name`.
        - `terms_accepted` and `terms_version` are mandatory.
        - Returns a pending booking with a `booking_reference` (prefix 'G').
        """,
        request=GuestHouseBookingSerializer,
        responses={201: GuestHouseBookingSerializer}
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a new booking.
        Serializer handles validation, availability checks, and T&C snapshot.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Serializer.create() calls GuestHouseBookingService.create_booking()
        booking = serializer.save()

        return Response(
            self.get_serializer(booking).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Cancel a guesthouse booking",
        description="Cancel a pending or confirmed booking and restore availability.",
        responses={200: GuestHouseBookingSerializer}
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a booking and restore availability.
        """
        booking = self.get_object()
        
        # Use service to cancel
        from apps.listing.services import GuestHouseBookingService
        try:
            GuestHouseBookingService.cancel_booking(booking)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(self.get_serializer(booking).data)
    
    @extend_schema(
        summary="Get my guesthouse bookings",
        description="Retrieve all bookings made by the authenticated user.",
        responses={200: GuestHouseBookingSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def my_bookings(self, request):
        """
        Get all bookings for the authenticated user.
        """
        bookings = GuestHouseBooking.objects.filter(renter=request.user).order_by('-created_at')
        
        page = self.paginate_queryset(bookings)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(bookings, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Price Preview for guesthouse selection",
        description="Get a consolidated price quote for a selection of guesthouses/rooms before booking.",
        request=GuestHouseBookingPreviewSerializer,
        parameters=[
            OpenApiParameter(
                name="display_currency",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional: Request price preview in a specific currency (e.g., USD) using triangulation."
            )
        ],
        responses={
            200: PricePreviewResponseSerializer,
            400: OpenApiTypes.OBJECT
        }
    )
    @action(
        detail=False, 
        methods=['post'], 
        url_path='price-preview',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def price_preview(self, request):
        serializer = GuestHouseBookingPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        start_date = data['start_date']
        end_date = data['end_date']
        items = data['items']
        
        # Validate availability (lock=False for previews)
        room_infos = [
            {"guesthouse_room": item["room"], "quantity": item["units_booked"]}
            for item in items
        ]
        try:
            GuestHouseAvailabilityService.validate_availability(room_infos, start_date, end_date, lock=False)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
            
        # Calculate totals
        nights = (end_date - start_date).days
        total_items = []
        item_subtotals = []
        
        currencies = {item["room"].currency for item in items}
        if len(currencies) > 1:
            return Response({"detail": "All selected items must have the same currency."}, status=400)
        currency = list(currencies)[0] if currencies else "ETB"
        display_currency = get_display_currency(request)
        
        for item in items:
            room = item["room"]
            units = item["units_booked"]
            
            price_details = PriceService.resolve_price_details_batch(room, start_date, end_date)
            item_base_total = sum(Decimal(str(d['price_per_unit'])) for d in price_details) * units
            
            item_subtotals.append(item_base_total)
            
            total_items.append({
                "id": str(room.id),
                "title": room.title,
                "units": units,
                "price_per_unit": f"{room.base_price:.2f}",
                "subtotal": f"{item_base_total:.2f}",
                "breakdown": price_details
            })
            
        return Response({
            "nights": nights,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(item_subtotals, currency, display_currency, items=total_items)
        })

# Car Listing ViewSet
@extend_schema(tags=["Car Rentals"])
class CarListingViewSet(AbstractModelViewSet):
    serializer_class = CarListingSerializer
    queryset = CarListing.objects.all()
    throttle_scope = None
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
        queryset = super().get_queryset().select_related(
            'company',
            'individual_owner'
        ).prefetch_related(
            'images',
            'daily_availabilities'
        )
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
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            if individual_owner:
                serializer.save(individual_owner=individual_owner)
                return

            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            if company:
                if company.status != CompanyProfile.StatusChoice.APPROVED:
                    raise PermissionDenied("Company profile is not approved.")
                serializer.save(company=company)
                return

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
    @action(
        detail=True, 
        methods=['post'], 
        serializer_class=AvailabilityCheckSerializer,
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
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
    @action(
        detail=False, 
        methods=['get'], 
        serializer_class=CarSearchSerializer,
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
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
        if self.action in ['create', 'lookup']:
            return [AllowAny()]
        elif self.action in ['list', 'retrieve', 'my_rentals', 'rental_stats']:
            return [IsAuthenticated()]
        else:
            return [IsCarRentalOwner()]

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

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
            return (user_rentals.distinct() | company_rentals).distinct()

        return user_rentals

    @extend_schema(
        summary="Lookup car rental status (Guest)",
        description="Retrieve rental details using reference and guest email. No login required.",
        parameters=[
            OpenApiParameter("reference", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("email", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: CarRentalSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = BookingLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        reference = serializer.validated_data['reference']
        email = serializer.validated_data['email']
        
        rental = get_object_or_404(
            CarRental.objects.prefetch_related("rental_items", "rental_items__car_listing"),
            booking_reference=reference,
            guest_email=email
        )
        
        response_serializer = CarRentalSerializer(rental, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @transaction.atomic
    @extend_schema(
        summary="Create a new car rental booking (supports guest checkout)",
        description="""
        Initiates a rental booking for one or more vehicles.
        - Supports both authenticated users and guest checkout.
        - If guest, provide renter details in `guest_*` fields.
        - Checks vehicle availability across the requested date range.
        - Returns a pending booking with a `booking_reference` (prefix 'C').
        """,
        request=CarRentalSerializer,
        responses={201: CarRentalSerializer}
    )
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

        user = request.user if request.user.is_authenticated else None
        rental = serializer.save(renter=user)

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
                quantity=rental_item.units_rent,
                start_date=rental.start_date,
                end_date=rental.end_date,
            )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        rental = self.get_object()
        if rental.status != CarRental.RentStatus.PENDING:
            return Response({"error": "Only pending rentals can be confirmed."}, status=status.HTTP_400_BAD_REQUEST)

        # Check daily availability again
        for item in rental.rental_items.all():
            try:
                CarAvailabilityService.validate_availability(
                    item.car_listing, item.units_rent, rental.start_date, rental.end_date
                )
            except Exception as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        rental.status = CarRental.RentStatus.CONFIRMED
        rental.save()
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
                item.car_listing,
                item.units_rent,
                rental.start_date,
                rental.end_date,
                increment=True,
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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

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
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = PropertyFilter
    search_fields = ['title', 'name', 'description', 'address']

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
        """Filter queryset - show all active to public, managed only to owners/admin."""
        queryset = super().get_queryset()
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset
        
        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(company=company)
            if individual_owner:
                q |= Q(individual_owner=individual_owner)
            return queryset.filter(q).order_by("-created_at")
        
        return queryset.filter(is_active=True).order_by("-created_at")


class AmenityViewSet(AbstractModelViewSet):
    http_method_names = ["get"]
    permission_classes = [AllowAny]
    serializer_class = AmenityResponseSSerializer
    queryset = Amenity.objects.all()


class BookingViewSet(AbstractModelViewSet):
    http_method_names = ["get", "post"]
    serializer_class = BookingSerializer
    queryset = Booking.objects.all()
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = BookingFilter
    ordering = ['-created_at']
    
    @extend_schema(request=BookingSerializer, responses=BookingSerializer)
    @action(detail=False, methods=['post'], url_path='walk-in', permission_classes=[IsAuthenticated])
    def walk_in(self, request, *args, **kwargs):
        """
        Create a walk-in booking. 
        Passes is_walk_in=True via context to trigger staff privileges check.
        Requires authentication.
        """
        # Default currency to ETB for walk-ins if not specified
        data = request.data.copy()
        if 'payment_currency' not in data:
            data['payment_currency'] = 'ETB'
        
        # Pass is_walk_in via context, not data
        context = {**self.get_serializer_context(), 'is_walk_in': True}
        serializer = self.get_serializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    search_fields = [
        'booking_reference',
        'user__email',
        'user__first_name',
        'user__last_name',
        'guest_email',
        'guest_first_name',
        'guest_last_name',
        'guest_phone'
    ]

    @extend_schema(
        summary="Create a new room booking (supports guest checkout)",
        description="""
        Initiates a booking for one or more hotel rooms. 
        - Supports both authenticated users and guest checkout.
        - If not logged in, `guest_email`, `guest_phone`, `guest_first_name`, and `guest_last_name` are required.
        - `terms_accepted` must be true.
        - `terms_version` must match the hotel's latest active T&C version.
        - Returns a pending booking with a human-readable `booking_reference` (e.g., H-X7Y2Z9).
        """,
        request=BookingSerializer,
        responses={201: BookingResponseSerializer}
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        """
        - CREATE/LOOKUP: Allow anyone (guests)
        - READ: Users see own bookings, companies see bookings for their listings, admin sees all
        - Special actions: partial_cancel, rate require ownership
        """
        if self.action in ['create', 'lookup', 'cancel', 'price_preview']:
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['partial_cancel', 'rate_booking']:
            return [IsBookingOwner()]
        else:
            return [IsAuthenticated()]

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        """
        Filter bookings based on user role:
        - Admin: See all bookings
        - Company (mode='host'): See bookings for their listings
        - User/Default: See only their own bookings
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
        
        # Check for mode parameter (Feature branch logic)
        mode = self.request.query_params.get('mode')
        if mode == 'host':
            if hasattr(self.request.user, 'role') and self.request.user.role:
                if self.request.user.role.code == RoleCode.COMPANY.value:
                    if hasattr(self.request.user, 'profile') and self.request.user.profile:
                        # Ensure HotelProfile is imported if needed, usually available via models
                        company = self.request.user.profile
                        try:
                            hotel = HotelProfile.objects.get(company=company)
                            return queryset.filter(
                                items__room__hotel=hotel
                            ).distinct()
                        except HotelProfile.DoesNotExist:
                            pass
            return queryset.none()

        # Users see only their own bookings
        user_bookings = queryset.filter(user=self.request.user).distinct()

        if self.request.query_params.get('as_guest') == 'true':
            return user_bookings

        # Company sees bookings for their hotels (Development branch logic)
        if hasattr(self.request.user, 'role') and self.request.user.role and self.request.user.role.code == RoleCode.COMPANY.value:
             if hasattr(self.request.user, 'profile') and self.request.user.profile:
                  company = self.request.user.profile
                  try:
                      hotel = HotelProfile.objects.get(company=company)
                      hotel_bookings = queryset.filter(items__room__hotel=hotel).distinct()
                      return (user_bookings | hotel_bookings).distinct()
                  except HotelProfile.DoesNotExist:
                      pass
        
        return user_bookings
    
    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)

    @extend_schema(
        summary="Lookup room booking status (Guest)",
        description="Retrieve booking details using reference and guest email. No login required.",
        parameters=[
            OpenApiParameter("reference", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("email", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: BookingResponseSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = BookingLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        reference = serializer.validated_data['reference']
        email = serializer.validated_data['email']
        
        booking = get_object_or_404(
            Booking.objects.prefetch_related("items", "items__room"),
            booking_reference=reference,
            guest_email=email
        )
        
        response_serializer = BookingResponseSerializer(booking, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @extend_schema(
        summary="Price Preview for room selection",
        description="Get a consolidated price quote for a selection of hotel rooms before booking.",
        request=BookingPreviewSerializer,
        parameters=[
            OpenApiParameter(
                name="display_currency",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional: Request price preview in a specific currency (e.g., USD) using triangulation."
            )
        ],
        responses={
            200: PricePreviewResponseSerializer,
            400: OpenApiTypes.OBJECT
        }
    )
    @action(
        detail=False, 
        methods=['post'], 
        url_path='price-preview',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def price_preview(self, request):
        serializer = BookingPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        check_in = data['check_in_date']
        check_out = data['check_out_date']
        items = data['items']
        
        # Validate availability (lock=False for previews)
        rooms_info = [{"room": item["room"], "quantity": item["units_booked"]} for item in items]
        hotel = items[0]["room"].hotel
        try:
            StayAvailabilityService.validate_availability(hotel, rooms_info, check_in, check_out, lock=False)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
            
        total_items = []
        item_subtotals = []
        
        currencies = {item["room"].currency for item in items}
        if len(currencies) > 1:
            return Response({"detail": "All selected items must have the same currency."}, status=400)
        currency = list(currencies)[0] if currencies else "ETB"
        display_currency = get_display_currency(request)
        
        for item in items:
            room = item["room"]
            units = item["units_booked"]
            
            price_details = PriceService.resolve_price_details_batch(room, check_in, check_out)
            item_base_total = sum(Decimal(str(d['price_per_unit'])) for d in price_details) * units
            
            item_subtotals.append(item_base_total)
            total_items.append({
                "id": str(room.id),
                "title": room.title,
                "units": units,
                "price_per_unit": str(price_details[0]['price_per_unit']) if price_details else str(room.base_price),
                "subtotal": str(item_base_total.quantize(Decimal('0.01'))),
                "breakdown": price_details
            })
            
        nights = (check_out - check_in).days
        return Response({
            "nights": nights,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(item_subtotals, currency, display_currency, items=total_items)
        })
    @extend_schema(
        summary="Cancel a booking (User or Guest)",
        description="""
        Cancel a booking.
        - **Authenticated**: User cancels their own booking.
        - **Guest**: Must provide `guest_email` matching the booking to verify ownership.
        """,
        request=GuestCancellationSerializer,
        responses={200: BookingResponseSerializer}
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Allows an authenticated user or verified guest to cancel their booking."""
        booking = self.get_object()
        
        # 1. Authenticated User Check
        if request.user.is_authenticated:
            pass # Permission class IsBookingOwner handles this? No, we might need manual check if permission is relaxed
            # If strictly using IsBookingOwner in get_permissions, this block is safe.
            # BUT: We are relaxing get_permissions to allow guests!
        
        # 2. Guest Verification Logic
        if not request.user.is_authenticated:
            if booking.user is not None:
                return Response(
                    {"detail": "This booking belongs to a registered user. Please log in to cancel."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = GuestCancellationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            email_input = serializer.validated_data['guest_email']
            if email_input.lower().strip() != booking.guest_email.lower().strip():
                return Response(
                    {"detail": "Email does not match the booking record."},
                    status=status.HTTP_403_FORBIDDEN
                )

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

    @action(detail=False, methods=['get'], url_path='workspace-bookings')
    def workspace_bookings(self, request):
        user = request.user
        
        if not user.workspace:
             return Response(
                {"detail": "No workspace assigned to this user."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        workspace = user.workspace
        queryset = self.get_queryset()
        
        if hasattr(workspace, 'is_hotel') or workspace.__class__.__name__ == 'HotelProfile':
            queryset = queryset.filter(items__room__hotel=workspace).distinct()
            
        elif hasattr(workspace, 'is_guesthouse') or workspace.__class__.__name__ == 'GuestHouseProfile':
             return Response([])
             
        return Response(
            BookingResponseSerializer(queryset, many=True).data
        )


@search_schema
class StaySearchView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

    def get(self, request):
        city = request.query_params.get("city")
        check_in_date = request.query_params.get("check_in_date")
        check_out_date = request.query_params.get("check_out_date")
        guests = request.query_params.get("guests")

        if not all([city, check_in_date, check_out_date, guests]):
            return Response({"detail": "Missing required parameters."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            guests_int = int(guests)
            if guests_int < 1:
                return Response({"detail": "Guest count must be at least 1."},
                                status=status.HTTP_400_BAD_REQUEST)
            if guests_int > 50:
                return Response({"detail": "Guest count cannot exceed 50."},
                                status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"detail": "Guest count must be a valid integer."},
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
                "images": hotel.images.all(),
                "facilities": hotel.facilities.all(),
                "rooms": []
            }
            
            duration = (check_out_date - check_in_date).days or 1
            for room_data in stay_data["rooms"]:
                room = room_data["room"]
                base_price = room.base_price
                
                preview_total = base_price * duration
                preview_min = base_price
                preview_has_discount = False
                display_price = base_price
                
                use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
                if use_seasonal:
                    room_lines = PriceService.resolve_price_details_batch(room, check_in_date, check_out_date)
                    room_prices = [Decimal(str(line['price_per_unit'])) for line in room_lines]

                    if room_prices:
                        preview_total = sum(room_prices)
                        preview_min = min(room_prices)
                        preview_has_discount = any(p < base_price for p in room_prices)
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
                    "nights": duration,
                    "number_of_guests": room.number_of_guests,
                    "bed_type": room.bed_type,
                    "room_size_sqm": room.room_size_sqm,
                    "available_units": room_data["available_units"]
                })
            
            # Use the stay total for the cheapest room as the hotel-level total
            if hotel_result["rooms"]:
                hotel_result["total_price"] = min(r["preview_total"] for r in hotel_result["rooms"])
                hotel_result["base_price"] = min(r["display_price"] for r in hotel_result["rooms"])
                first_room = stay_data["rooms"][0]["room"]
                hotel_result["currency"] = getattr(first_room, "currency", "ETB")
            
            results.append(hotel_result)

        paginator = StandardResultsSetPagination()
        paginated_results = paginator.paginate_queryset(results, request)
        
        # Resolve favorites once per request for hotel search results
        try:
            ct = ContentType.objects.get(app_label="account", model="hotelprofile")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(request.user, ct) if ct is not None else set()

        display_currency = get_display_currency(request)
        serializer = SearchResultSerializer(
            paginated_results, 
            many=True, 
            context={
                "request": request, 
                "favorite_object_ids": fav_ids,
                "display_currency": display_currency
            }
        )
        return paginator.get_paginated_response(serializer.data)
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

    def _can_update_availability(self, user, availability):
        if user.is_superuser or (
            hasattr(user, 'role') and
            user.role and
            user.role.code == RoleCode.ADMIN.value
        ):
            return True

        car = availability.car_listing
        company = getattr(car, 'company', None)
        if company:
            if getattr(company, 'user', None) == user:
                return True
            if getattr(user, 'company', None) == company:
                return True

        individual_owner = getattr(car, 'individual_owner', None)
        if individual_owner and getattr(user, 'individual_owner', None) == individual_owner:
            return True

        return False

    def patch(self, request, pk, format=None):
        """Update a CarAvailability instance (partial update)."""
        availability = get_object_or_404(
            CarAvailability.objects.select_related(
                'car_listing',
                'car_listing__company',
                'car_listing__individual_owner',
            ),
            pk=pk,
        )
        if not self._can_update_availability(request.user, availability):
            return Response(
                {"detail": "You do not have permission to update this availability."},
                status=status.HTTP_403_FORBIDDEN,
            )

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
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = EventSpaceFilter # Use the dedicated filter class
    search_fields = ['title', 'description', 'address__city', 'address__sub_city']

    # --- Permission Logic ---
    def get_permissions(self):
        """
        Applies access control based on the action and user role.
        """
        if self.action == 'create':
            # Only authenticated users (Company/Admin) can create listings
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve', 'search']:
            # Public access for reading listings
            return [AllowAny()]
        else:
            # Update/Delete requires the user to own the listing
            return [IsListingOwner()]

    # --- Queryset Logic ---
    def get_queryset(self):
        queryset = super().get_queryset()
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        # Admin sees all
        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset

        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(hotel__company=company)
            if individual_owner:
                 q |= Q(hotel__individual_owner=individual_owner) # Adjusting based on RoomListing pattern
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

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

        # Hydrate legacy pricing fields from price_quote for backward compatibility
        quote = data.get('price_quote')
        if quote:
            data['preview_min_price'] = quote['min_nightly_price']
            data['preview_total'] = quote['base_total']
            data['preview_has_discount'] = quote['has_discount']
            data['display_price'] = quote['min_nightly_price'] if quote['has_discount'] else data.get('base_price')
        else:
            data['display_price'] = data.get('base_price')

        return Response(data)

    # --- List Action ---
    def list(self, request, *args, **kwargs):
        """
        List event spaces; computes display_price and preview fields for each 
        listing if date params are provided.
        """
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        listings = page if page is not None else list(qs)

        serialized = []
        for listing in listings:
            serializer = EventSpaceListingResponseSerializer(listing, context=self.get_serializer_context())
            data = serializer.data
            
            # Hydrate legacy pricing fields from price_quote for backward compatibility
            quote = data.get('price_quote')
            if quote:
                data['preview_min_price'] = quote['min_nightly_price']
                data['preview_total'] = quote['base_total']
                data['preview_has_discount'] = quote['has_discount']
                data['display_price'] = quote['min_nightly_price'] if quote['has_discount'] else data.get('base_price')
            else:
                data['display_price'] = data.get('base_price')

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
@extend_schema(
    responses=EventSpaceBookingResponseSerializer,
)
@extend_schema(
    methods=['post'],
    summary="Create a new event space booking (supports guest checkout)",
    description="""
    Initiates a booking for an event space.
    - Supports both authenticated users and guest checkout.
    - If not logged in, guest details must be provided.
    - Captures additional fields for `event_type`.
    - Returns a pending booking with a `booking_reference`.
    """,
    request=EventSpaceBookingSerializer,
    responses={201: EventSpaceBookingResponseSerializer}
)
class EventSpaceBookingViewSet(AbstractModelViewSet):
    """
    ViewSet for viewing and managing Event Space Bookings (Create/List/Retrieve only).
    """
    # Only allow GET (list/retrieve) and POST (create)
    http_method_names = ["get", "post"] 
    serializer_class = EventSpaceBookingSerializer
    throttle_scope = None
    ordering = ['-created_at']

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
        if self.action in ['create', 'lookup', 'price_preview']:
            # Allow guests to create and lookup bookings
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            # All authenticated users can see their permitted list/detail
            return [IsAuthenticated()]
        # Removed: partial_cancel and rate_booking actions
        else:
            return [IsAuthenticated()]

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    # --- Queryset Filtering ---
    def get_queryset(self):
        """
        Filter bookings based on user role: User, Company, or Admin.
        
        Default: Returns only user's PERSONAL bookings (where they are the guest).
        Mode='host': Returns bookings for the user's PROPERTIES (where they are the host).
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
        
        
        # Check for mode parameter (Feature branch logic)
        mode = self.request.query_params.get('mode')
        if mode == 'host':
            if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
                if hasattr(user, 'profile') and user.profile:
                    company = user.profile
                    try:
                        hotel = HotelProfile.objects.get(company=company)
                        
                        return queryset.filter(
                            items__event_space__hotel=hotel
                        ).distinct()
                    except HotelProfile.DoesNotExist:
                        return queryset.none()
            return queryset.none()

        # Users see only their own bookings
        user_bookings = queryset.filter(user=user).distinct()
        
        if self.request.query_params.get('as_guest') == 'true':
            return user_bookings
        
        # Company sees bookings for their hotels (Development branch logic)
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
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)

    @extend_schema(request=EventSpaceBookingSerializer, responses=EventSpaceBookingSerializer)
    @action(detail=False, methods=['post'], url_path='walk-in', permission_classes=[IsAuthenticated])
    def walk_in(self, request, *args, **kwargs):
        """
        Create a walk-in booking. 
        Passes is_walk_in=True via context to trigger staff privileges check.
        Requires authentication.
        """
        # Default currency to ETB for walk-ins if not specified
        data = request.data.copy()
        if 'payment_currency' not in data:
            data['payment_currency'] = 'ETB'
        
        # Pass is_walk_in via context, not data
        context = {**self.get_serializer_context(), 'is_walk_in': True}
        serializer = self.get_serializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(
        summary="Lookup event space booking status (Guest)",
        description="Retrieve event space booking details using reference and guest email. No login required.",
        parameters=[
            OpenApiParameter("reference", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("email", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: EventSpaceBookingResponseSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = BookingLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        reference = serializer.validated_data['reference']
        email = serializer.validated_data['email']
        
        booking = get_object_or_404(
            EventSpaceBooking.objects.prefetch_related("items", "items__event_space"),
            booking_reference=reference,
            guest_email=email
        )
        
        response_serializer = EventSpaceBookingResponseSerializer(booking, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @extend_schema(
        summary="Price Preview for event space selection",
        description="Get a consolidated price quote for a selection of event spaces before booking.",
        request=EventSpaceBookingPreviewSerializer,
        parameters=[
            OpenApiParameter(
                name="display_currency",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional: Request price preview in a specific currency (e.g., USD) using triangulation."
            )
        ],
        responses={
            200: PricePreviewResponseSerializer,
            400: OpenApiTypes.OBJECT
        }
    )
    @action(detail=False, methods=['post'], url_path='price-preview')
    def price_preview(self, request):
        serializer = EventSpaceBookingPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        check_in = data['check_in_date']
        check_out = data['check_out_date']
        items = data['items']
        
        # validate availability (lock=False for previews)
        spaces_info = [{"space_listing": item["event_space"], "quantity": item["units_booked"]} for item in items]
        try:
            EventSpaceAvailabilityService.validate_availability(spaces_info, check_in, check_out, lock=False)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
            
        nights = (check_out - check_in).days
        total_items = []
        item_subtotals = []
        
        currencies = {item["event_space"].currency for item in items}
        if len(currencies) > 1:
            return Response({"detail": "All selected items must have the same currency."}, status=400)
        currency = list(currencies)[0] if currencies else "ETB"
        display_currency = get_display_currency(request)
        
        for item in items:
            space = item["event_space"]
            units = item["units_booked"]
            
            price_details = PriceService.resolve_price_details_batch(space, check_in, check_out)
            item_base_total = sum(Decimal(str(d['price_per_unit'])) for d in price_details) * units
            
            item_subtotals.append(item_base_total)
            
            total_items.append({
                "id": str(space.id),
                "title": space.title,
                "units": units,
                "price_per_unit": f"{(price_details[0]['price_per_unit'] if price_details else space.base_price):.2f}",
                "subtotal": f"{item_base_total:.2f}",
                "breakdown": price_details
            })
            
        return Response({
            "nights": nights,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(item_subtotals, currency, display_currency, items=total_items)
        })


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

    @extend_schema(
        summary="Get active Terms & Conditions for a guest house",
        description="Retrieve the currently active T&C for a specific guest house profile",
        responses={200: TermsAndConditionsSerializer, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='guesthouse/(?P<gh_id>[^/.]+)')
    def guesthouse_terms(self, request, gh_id=None):
        """Get active T&C for a guest house"""
        from apps.listing.models import GuestHouseProfile
        from apps.listing.services import TermsService
        
        gh = get_object_or_404(GuestHouseProfile, id=gh_id)
        terms = TermsService.get_active_terms(content_object=gh)
        
        if not terms:
            return Response(
                {"detail": "No terms and conditions available for this guest house."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.serializer_class(terms)
        return Response(serializer.data)

    @extend_schema(
        summary="Get active Terms & Conditions for a company (Car Rental)",
        description="Retrieve the currently active T&C for a specific company (Car Rental, etc.)",
        responses={200: TermsAndConditionsSerializer, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='company/(?P<company_id>[^/.]+)')
    def company_terms(self, request, company_id=None):
        """Get active T&C for a company"""
        from apps.account.models import CompanyProfile
        from apps.listing.services import TermsService
        
        company = get_object_or_404(CompanyProfile, id=company_id)
        terms = TermsService.get_active_terms(content_object=company)
        
        if not terms:
            return Response(
                {"detail": "No terms and conditions available for this company."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.serializer_class(terms)
        return Response(serializer.data)


@extend_schema(tags=["Accommodations"])
class AddonOfferingViewSet(AbstractModelViewSet):
    queryset = AddonOffering.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['hotel', 'category', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['display_order', 'price_per_unit', 'name']
    ordering = ['display_order', 'name']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if user.is_authenticated and (user.is_superuser or (
            hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value
        )):
            return queryset

        if user.is_authenticated and hasattr(user, 'role') and user.role:
            if user.role.code == RoleCode.COMPANY.value:
                return queryset.filter(hotel__company__user=user)

        return queryset.filter(is_active=True)

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return AddonOfferingListSerializer
        return AddonOfferingSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsListingOwner()]

    def perform_create(self, serializer):
        hotel = serializer.validated_data.get('hotel')
        
        is_admin = self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and 
            self.request.user.role and 
            self.request.user.role.code == RoleCode.ADMIN.value
        )
        
        if not is_admin:
            if not hotel.company or not hotel.company.user == self.request.user:
                raise PermissionDenied("You can only create addons for your own hotel.")
        
        serializer.save()

    @extend_schema(
        summary="List addons for a specific hotel",
        description="Filter offerings by hotel ID. Returns public-facing addon details.",
        parameters=[
            OpenApiParameter("hotel", OpenApiTypes.UUID, OpenApiParameter.QUERY, description="Filter by Hotel UUID"),
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Filter by Category"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


@extend_schema(tags=["Season Management"])
class SeasonViewSet(viewsets.ModelViewSet):
    """
    API for Owners to manage Seasons (e.g., Summer, Christmas).
    """
    serializer_class = SeasonSerializer
    permission_classes = [IsCompanyOwner]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Season.objects.none()

        if user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            return Season.objects.all()

        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        from django.db.models import Q
        q = Q(company=None, individual_owner=None) # Global seasons

        if company:
            q |= Q(company=company)
        if individual_owner:
            q |= Q(individual_owner=individual_owner)
            
        return Season.objects.filter(q).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
        
        # Only admins can create global seasons (both null)
        # For owners/staff, we MUST assign their profile
        kwargs = {}
        if not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            if company:
                kwargs['company'] = company
            if individual_owner:
                kwargs['individual_owner'] = individual_owner
                
        serializer.save(**kwargs)


@extend_schema(tags=["Season Management"])
class SeasonalRateViewSet(viewsets.ModelViewSet):
    """
    API for Owners to manage Rates associated with Seasons.
    """
    serializer_class = SeasonalRateSerializer
    permission_classes = [IsCompanyOwner]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return SeasonalRate.objects.none()

        if user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            return SeasonalRate.objects.all()

        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        from django.db.models import Q
        q = Q(company=None, individual_owner=None)

        if company:
            q |= Q(company=company)
        if individual_owner:
            q |= Q(individual_owner=individual_owner)
            
        return SeasonalRate.objects.filter(q).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
        
        kwargs = {}
        if not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            if company:
                kwargs['company'] = company
            if individual_owner:
                kwargs['individual_owner'] = individual_owner
                
        serializer.save(**kwargs)


class InventoryGridView(APIView):
    """
    Unified endpoint for the Owner Dashboard availability grid.
    Returns 30 days of availability and pricing for all units in a property.
    """
    permission_classes = [IsAuthenticated, IsListingOwner]

    @extend_schema(
        tags=["Inventory Management"],
        summary="Get 30-day availability and pricing grid",
        parameters=[
            OpenApiParameter("property_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("property_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True, enum=['hotel', 'guesthouse', 'eventspace']),
            OpenApiParameter("start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Default is today"),
            OpenApiParameter("days", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, default=30),
        ]
    )
    def get(self, request):
        property_id = request.query_params.get('property_id')
        property_type = request.query_params.get('property_type')
        start_date_str = request.query_params.get('start_date')
        days = int(request.query_params.get('days', 30))

        if not property_id or not property_type:
            return Response({"error": "property_id and property_type are required."}, status=400)

        from django.apps import apps
        try:
            if property_type == 'hotel':
                model = apps.get_model('account', 'HotelProfile')
            elif property_type == 'eventspace':
                 model = apps.get_model('listing', 'EventSpaceListing')
            elif property_type == 'guesthouse':
                model = apps.get_model('listing', 'GuestHouseProfile')
            else:
                return Response({"error": "Invalid property_type"}, status=400)
            
            prop_obj = model.objects.get(id=property_id)
            self.check_object_permissions(request, prop_obj)
        except Exception as e:
            return Response({"error": f"Access Denied or Property Not Found: {str(e)}"}, status=403)

        if start_date_str:
            start_date = parse_date(start_date_str)
        else:
            start_date = date.today()

        from apps.listing.services import InventoryGridService
        try:
            grid_data = InventoryGridService.get_availability_grid(
                property_id=property_id,
                property_type=property_type,
                start_date=start_date,
                days=days
            )
            return Response(grid_data)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


    
