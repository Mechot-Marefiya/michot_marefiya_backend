
from django.utils.dateparse import parse_date
from django.conf import settings
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status,filters
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from apps.account.serializers import HotelProfileResponseSerializer
from apps.listing.docs.schema import search_schema
from apps.core.views import AbstractModelViewSet
from apps.listing.filters import PropertyFilter, RoomFilter, BookingFilter
from apps.account.permissions import IsAuthenticatedOrReadOnly, IsAuthenticatedOrReadOnly
from apps.listing.models import (
    Amenity,
    CarListing,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
    Booking,StayAvailability,
    BookingItem,
    CarAvailability
)
from apps.account.models import(CompanyProfile,IndividualOwnerProfile)
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
    SearchResultSerializer,StayAvailabilityUpdateSerializer,
    CarAvailabilitySerializer,
    AvailabilityCheckSerializer,
    CarSearchSerializer,
    CarRentalSerializer,
    CarRental,
)
from apps.listing.services import StayAvailabilityService,BookingService,CarAvailabilityService
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


# @extend_schema(responses=CarListingResponseSerializer)
# class CarListingViewSet(AbstractModelViewSet):
#     permission_classes = [IsAuthenticatedOrReadOnly]
#     serializer_class = CarListingSerializer
#     queryset = CarListing.objects.all()
#     # filter_backends = [DjangoFilterBackend]
#     # filterset_class = CarFilter

# views.py
@extend_schema(responses=CarListingResponseSerializer)
class CarListingViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = CarListingSerializer
    queryset = CarListing.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'brand', 'car_class', 'fuel_type', 'transmission', 
        'condition', 'listing_type', 'is_active'
    ]
    search_fields = ['title', 'description', 'brand', 'model']
    ordering_fields = ['base_price', 'year', 'mileage', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CarListingSerializer
        return CarListingResponseSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active listings for non-staff users
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        # Additional filters
        min_year = self.request.query_params.get('min_year')
        max_year = self.request.query_params.get('max_year')
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        max_mileage = self.request.query_params.get('max_mileage')
        
        if min_year:
            queryset = queryset.filter(year__gte=min_year)
        if max_year:
            queryset = queryset.filter(year__lte=max_year)
        if min_price:
            queryset = queryset.filter(base_price__gte=min_price)
        if max_price:
            queryset = queryset.filter(base_price__lte=max_price)
        if max_mileage:
            queryset = queryset.filter(mileage__lte=max_mileage)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set the owner based on the current user if not provided"""
        user = self.request.user
        
        # If neither company nor individual_owner is provided, try to set based on user
        if not serializer.validated_data.get('company') and not serializer.validated_data.get('individual_owner'):
            # Try to get individual owner
            try:
                individual_owner = IndividualOwnerProfile.objects.get(user=user)
                serializer.save(individual_owner=individual_owner)
            except IndividualOwnerProfile.DoesNotExist:
                # Try to get company
                try:
                    company = CompanyProfile.objects.get(user=user)
                    serializer.save(company=company)
                except CompanyProfile.DoesNotExist:
                    # If user doesn't have either profile, let the validation error handle it
                    serializer.save()
        else:
            serializer.save()
    
    @extend_schema(
        request=AvailabilityCheckSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT
        }
    )
    @action(detail=True, methods=['post'], serializer_class=AvailabilityCheckSerializer)
    def check_availability(self, request, pk=None):
        """
        Check availability for a specific car listing for rental
        """
        car_listing = self.get_object()
        serializer = AvailabilityCheckSerializer(data=request.data)
        
        if serializer.is_valid():
            availability_check = CarAvailabilityService.check_availability_for_rent(
                car_listing=car_listing,
                start_date=serializer.validated_data['start_date'],
                end_date=serializer.validated_data['end_date'],
                quantity=serializer.validated_data['quantity']
            )
            
            return Response(availability_check)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, description='Start date for rental'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description='End date for rental'),
            OpenApiParameter('brand', OpenApiTypes.STR, description='Filter by brand'),
            OpenApiParameter('car_class', OpenApiTypes.STR, description='Filter by car class'),
            OpenApiParameter('max_daily_price', OpenApiTypes.FLOAT, description='Maximum daily price'),
        ]
    )
    @action(detail=False, methods=['get'], serializer_class=CarSearchSerializer)
    def available_for_rent(self, request):
        """
        Search for available cars for rent in a specific period
        """
        serializer = CarSearchSerializer(data=request.query_params)
        
        if serializer.is_valid():
            available_cars = CarAvailabilityService.get_available_cars_for_rent(
                start_date=serializer.validated_data['start_date'],
                end_date=serializer.validated_data['end_date'],
                brand=serializer.validated_data.get('brand'),
                car_class=serializer.validated_data.get('car_class')
            )
            
            # Filter by maximum daily price if provided
            max_daily_price = serializer.validated_data.get('max_daily_price')
            if max_daily_price is not None:
                available_cars = [car for car in available_cars if car.base_price <= max_daily_price]
            
            # Apply additional filters
            fuel_type = request.query_params.get('fuel_type')
            transmission = request.query_params.get('transmission')
            condition = request.query_params.get('condition')
            min_year = request.query_params.get('min_year')
            max_year = request.query_params.get('max_year')
            max_mileage = request.query_params.get('max_mileage')
            
            if fuel_type:
                available_cars = [car for car in available_cars if car.fuel_type == fuel_type]
            if transmission:
                available_cars = [car for car in available_cars if car.transmission == transmission]
            if condition:
                available_cars = [car for car in available_cars if car.condition == condition]
            if min_year:
                available_cars = [car for car in available_cars if car.year >= int(min_year)]
            if max_year:
                available_cars = [car for car in available_cars if car.year <= int(max_year)]
            if max_mileage:
                available_cars = [car for car in available_cars if car.mileage <= int(max_mileage)]
            
            # Apply ordering
            ordering = request.query_params.get('ordering', '-created_at')
            if ordering.lstrip('-') in ['base_price', 'year', 'mileage', 'created_at']:
                reverse = ordering.startswith('-')
                field = ordering.lstrip('-')
                available_cars.sort(key=lambda x: getattr(x, field), reverse=reverse)
            
            # Pagination
            page = self.paginate_queryset(available_cars)
            if page is not None:
                serializer = CarListingResponseSerializer(
                    page, 
                    many=True, 
                    context={'request': request}
                )
                return self.get_paginated_response(serializer.data)
            
            serializer = CarListingResponseSerializer(
                available_cars, 
                many=True, 
                context={'request': request}
            )
            
            return Response({
                'count': len(available_cars),
                'results': serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        parameters=[
            OpenApiParameter('brand', OpenApiTypes.STR, description='Filter by brand'),
            OpenApiParameter('car_class', OpenApiTypes.STR, description='Filter by car class'),
            OpenApiParameter('fuel_type', OpenApiTypes.STR, description='Filter by fuel type'),
            OpenApiParameter('transmission', OpenApiTypes.STR, description='Filter by transmission'),
            OpenApiParameter('condition', OpenApiTypes.STR, description='Filter by condition'),
            OpenApiParameter('listing_type', OpenApiTypes.STR, description='Filter by listing type'),
            OpenApiParameter('min_year', OpenApiTypes.INT, description='Minimum year'),
            OpenApiParameter('max_year', OpenApiTypes.INT, description='Maximum year'),
            OpenApiParameter('max_mileage', OpenApiTypes.INT, description='Maximum mileage'),
            OpenApiParameter('max_price', OpenApiTypes.FLOAT, description='Maximum price'),
        ]
    )
    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        General search for car listings with various filters
        """
        queryset = self.get_queryset()
        
        # Apply filters
        brand = request.query_params.get('brand')
        car_class = request.query_params.get('car_class')
        fuel_type = request.query_params.get('fuel_type')
        transmission = request.query_params.get('transmission')
        condition = request.query_params.get('condition')
        listing_type = request.query_params.get('listing_type')
        min_year = request.query_params.get('min_year')
        max_year = request.query_params.get('max_year')
        max_mileage = request.query_params.get('max_mileage')
        max_price = request.query_params.get('max_price')
        
        if brand:
            queryset = queryset.filter(brand=brand)
        if car_class:
            queryset = queryset.filter(car_class=car_class)
        if fuel_type:
            queryset = queryset.filter(fuel_type=fuel_type)
        if transmission:
            queryset = queryset.filter(transmission=transmission)
        if condition:
            queryset = queryset.filter(condition=condition)
        if listing_type:
            queryset = queryset.filter(listing_type=listing_type)
        if min_year:
            queryset = queryset.filter(year__gte=min_year)
        if max_year:
            queryset = queryset.filter(year__lte=max_year)
        if max_mileage:
            queryset = queryset.filter(mileage__lte=max_mileage)
        if max_price:
            queryset = queryset.filter(base_price__lte=max_price)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = CarListingResponseSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'])
    def my_listings(self, request):
        """
        Get current user's car listings
        """
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        user = request.user
        
        # Get listings where user is individual owner
        individual_listings = CarListing.objects.filter(
            individual_owner__user=user
        )
        
        # Get listings where user is company owner
        company_listings = CarListing.objects.filter(
            company__user=user
        )
        
        # Combine querysets
        queryset = individual_listings | company_listings
        queryset = queryset.distinct()
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = CarListingResponseSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
@extend_schema(responses=CarRentalSerializer)
class CarRentalViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CarRentalSerializer
    queryset = CarRental.objects.all()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['start_date', 'end_date', 'total_price', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        if not self.request.user.is_staff:
            queryset = queryset.filter(renter=self.request.user)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        start_date_from = self.request.query_params.get('start_date_from')
        start_date_to = self.request.query_params.get('start_date_to')
        end_date_from = self.request.query_params.get('end_date_from')
        end_date_to = self.request.query_params.get('end_date_to')
        
        if start_date_from:
            queryset = queryset.filter(start_date__gte=start_date_from)
        if start_date_to:
            queryset = queryset.filter(start_date__lte=start_date_to)
        if end_date_from:
            queryset = queryset.filter(end_date__gte=end_date_from)
        if end_date_to:
            queryset = queryset.filter(end_date__lte=end_date_to)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(renter=self.request.user)
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a rental and update availability
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        rental_items_data = request.data.get('rental_items', [])
        
        # Check availability for all rental items first
        for item_data in rental_items_data:
            car_listing_id = item_data.get('car_listing')
            quantity = item_data.get('units_rent', 1)
            start_date = serializer.validated_data.get('start_date')
            end_date = serializer.validated_data.get('end_date')
            
            try:
                car_listing = CarListing.objects.get(id=car_listing_id)
            except CarListing.DoesNotExist:
                return Response(
                    {"error": f"Car listing {car_listing_id} does not exist"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            availability_check = CarAvailabilityService.check_availability_for_rent(
                car_listing=car_listing,
                start_date=start_date,
                end_date=end_date,
                quantity=quantity
            )
            
            if not availability_check.get('available'):
                return Response(
                    {"error": f"Car {car_listing} is not available: {availability_check.get('reason')}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Create the rental
        rental = serializer.save()
        
        # Create rental items and update availability
        for item_data in rental_items_data:
            car_listing = CarListing.objects.get(id=item_data.get('car_listing'))
            
            rental_item = CarRentalItem.objects.create(
                car_rental=rental,
                car_listing=car_listing,
                units_rent=item_data.get('units_rent', 1),
                price_per_unit=item_data.get('price_per_unit')
            )
            
            # Update availability after rental creation
            availability_result = CarAvailabilityService.update_availability_after_rental(
                car_listing=car_listing,
                rental=rental,
                rental_item=rental_item,
                action="create"
            )
            
            if not availability_result.get('success'):
                # Rollback transaction if availability update fails
                raise serializers.ValidationError({
                    "error": f"Failed to update availability: {availability_result.get('error')}"
                })
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @extend_schema(responses=CarRentalSerializer)
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """
        Confirm a pending rental and finalize availability updates
        """
        rental = self.get_object()
        
        if not request.user.is_staff and rental.renter != request.user:
            return Response(
                {"error": "You do not have permission to confirm this rental."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if rental.status != CarRental.RentStatus.PENDING:
            return Response(
                {"error": "Only pending rentals can be confirmed."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if still available
        for rental_item in rental.rental_items.all():
            availability_check = CarAvailabilityService.check_availability_for_rent(
                car_listing=rental_item.car_listing,
                start_date=rental.start_date,
                end_date=rental.end_date,
                quantity=rental_item.units_rent
            )
            
            if not availability_check.get('available'):
                return Response(
                    {"error": f"Cannot confirm rental: {availability_check.get('reason')}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Update rental status
        rental.status = CarRental.RentStatus.CONFIRMED
        rental.save()
        
        # Finalize availability updates for confirmed rental
        for rental_item in rental.rental_items.all():
            CarAvailabilityService.update_availability_after_rental(
                car_listing=rental_item.car_listing,
                rental=rental,
                rental_item=rental_item,
                action="confirm"
            )
        
        serializer = self.get_serializer(rental)
        return Response(serializer.data)
    
    @extend_schema(responses=CarRentalSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a rental and restore availability
        """
        rental = self.get_object()
        
        if not request.user.is_staff and rental.renter != request.user:
            return Response(
                {"error": "You do not have permission to cancel this rental."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if rental.status == CarRental.RentStatus.CANCELLED:
            return Response(
                {"error": "Rental is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = rental.status
        rental.status = CarRental.RentStatus.CANCELLED
        rental.save()
        
        # Restore availability for cancelled rental
        for rental_item in rental.rental_items.all():
            CarAvailabilityService.update_availability_after_rental(
                car_listing=rental_item.car_listing,
                rental=rental,
                rental_item=rental_item,
                action="cancel"
            )
        
        serializer = self.get_serializer(rental)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_rentals(self, request):
        """
        Get current user's rentals
        """
        rentals = self.get_queryset().filter(renter=request.user)
        
        # Filter by active rentals (not cancelled)
        active_only = request.query_params.get('active_only')
        if active_only and active_only.lower() == 'true':
            rentals = rentals.exclude(status=CarRental.RentStatus.CANCELLED)
        
        # Filter by upcoming rentals
        upcoming_only = request.query_params.get('upcoming_only')
        if upcoming_only and upcoming_only.lower() == 'true':
            rentals = rentals.filter(start_date__gte=datetime.now().date())
        
        page = self.paginate_queryset(rentals)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(rentals, many=True)
        return Response(serializer.data)
    
    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'])
    def rental_stats(self, request):
        """
        Get rental statistics for current user
        """
        user = request.user
        
        total_rentals = CarRental.objects.filter(renter=user).count()
        confirmed_rentals = CarRental.objects.filter(renter=user, status=CarRental.RentStatus.CONFIRMED).count()
        pending_rentals = CarRental.objects.filter(renter=user, status=CarRental.RentStatus.PENDING).count()
        cancelled_rentals = CarRental.objects.filter(renter=user, status=CarRental.RentStatus.CANCELLED).count()
        
        # Total spent
        total_spent = CarRental.objects.filter(
            renter=user, 
            status=CarRental.RentStatus.CONFIRMED
        ).aggregate(total=Sum('total_price'))['total'] or 0
        
        # Upcoming rentals
        upcoming_rentals = CarRental.objects.filter(
            renter=user,
            start_date__gte=datetime.now().date(),
            status__in=[CarRental.RentStatus.PENDING, CarRental.RentStatus.CONFIRMED]
        ).count()
        
        return Response({
            'total_rentals': total_rentals,
            'confirmed_rentals': confirmed_rentals,
            'pending_rentals': pending_rentals,
            'cancelled_rentals': cancelled_rentals,
            'total_spent': float(total_spent),
            'upcoming_rentals': upcoming_rentals
        })

@extend_schema(responses=CarAvailabilitySerializer)
@extend_schema(
    parameters=[
        OpenApiParameter("car_listing", OpenApiTypes.UUID, description="Car listing ID", required=True),
        OpenApiParameter("start_date", OpenApiTypes.DATE, description="Rental start date", required=True),
        OpenApiParameter("end_date", OpenApiTypes.DATE, description="Rental end date", required=True),
        OpenApiParameter("quantity", OpenApiTypes.INT, description="Number of cars requested", required=False),
    ],
    responses=CarAvailabilitySerializer
)
class CarAvailabilitySearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        car_listing_id = request.query_params.get("car_listing")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        quantity = int(request.query_params.get("quantity", 1))

        # --- Required params check ---
        if not all([car_listing_id, start_date, end_date]):
            return Response(
                {"detail": "Missing required parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Parse dates ---
        start_date_obj = parse_date(start_date)
        end_date_obj = parse_date(end_date)

        if not start_date_obj or not end_date_obj:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if end_date_obj <= start_date_obj:
            return Response(
                {"detail": "end_date must be after start_date."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Lookup car listing ---
        try:
            car_listing = CarListing.objects.get(id=car_listing_id)
        except CarListing.DoesNotExist:
            return Response(
                {"detail": "Car listing not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # --- Business logic (unchanged) ---
        availability_data = CarAvailabilityService.check_availability_for_rent(
            car_listing=car_listing,
            start_date=start_date_obj,
            end_date=end_date_obj,
            quantity=quantity
        )

        # --- Build clean response (StaySearch style) ---
        response = {
            "car_listing": {
                "id": car_listing.id,
                "title": car_listing.title,
                "brand": car_listing.brand,
                "model": car_listing.model,
                "base_price": str(car_listing.base_price),
            },
            "search_period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "quantity_requested": quantity,
            "availability": availability_data,
        }

        return Response(response)
@extend_schema(
    parameters=[
        OpenApiParameter("start_date", OpenApiTypes.DATE, description="Rental start date", required=True),
        OpenApiParameter("end_date", OpenApiTypes.DATE, description="Rental end date", required=True),
        OpenApiParameter("quantity", OpenApiTypes.INT, description="Number of cars requested", required=False),
    ],
    summary="Search all available cars in a date range"
)
class CarAvailabilityByDateRangeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        quantity = int(request.query_params.get("quantity", 1))

        # --- Validate required params ---
        if not all([start_date, end_date]):
            return Response(
                {"detail": "start_date and end_date are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Parse dates ---
        start_date_obj = parse_date(start_date)
        end_date_obj = parse_date(end_date)

        if not start_date_obj or not end_date_obj:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if end_date_obj <= start_date_obj:
            return Response(
                {"detail": "end_date must be after start_date."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Fetch all car listings ---
        car_listings = CarListing.objects.all()

        results = []

        # --- Loop all listings and check availability ---
        for car_listing in car_listings:
            availability = CarAvailabilityService.check_availability_for_rent(
                car_listing=car_listing,
                start_date=start_date_obj,
                end_date=end_date_obj,
                quantity=quantity
            )

            if availability.get("is_available", False):
                results.append({
                    "car_listing_id": car_listing.id,
                    "title": car_listing.title,
                    "brand": car_listing.brand,
                    "model": car_listing.model,
                    "base_price": str(car_listing.base_price),
                    "availability": availability
                })

        return Response({
            "search_period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "quantity_requested": quantity,
            "available_cars_count": len(results),
            "available_cars": results
        })
@extend_schema(
    parameters=[
        OpenApiParameter("car_listing", OpenApiTypes.UUID, description="Car listing ID", required=True),
        OpenApiParameter("start_date", OpenApiTypes.DATE, description="Start date", required=True),
        OpenApiParameter("end_date", OpenApiTypes.DATE, description="End date", required=True),
        OpenApiParameter("quantity", OpenApiTypes.INT, description="Number of cars requested", required=False),
    ],
    summary="Get availability for a specific car listing within a date range"
)
class CarAvailabilityByCarAndDateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        car_listing_id = request.query_params.get("car_listing")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        quantity = int(request.query_params.get("quantity", 1))

        # --- Validate required parameters ---
        if not all([car_listing_id, start_date, end_date]):
            return Response(
                {"detail": "car_listing, start_date and end_date are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Parse dates ---
        start_date_obj = parse_date(start_date)
        end_date_obj = parse_date(end_date)

        if not start_date_obj or not end_date_obj:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if end_date_obj <= start_date_obj:
            return Response(
                {"detail": "end_date must be after start_date."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Lookup car listing ---
        try:
            car_listing = CarListing.objects.get(id=car_listing_id)
        except CarListing.DoesNotExist:
            return Response(
                {"detail": "Car listing not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # --- Business logic: Check availability ---
        availability_data = CarAvailabilityService.check_availability_for_rent(
            car_listing=car_listing,
            start_date=start_date_obj,
            end_date=end_date_obj,
            quantity=quantity
        )

        # --- Build clean response ---
        response = {
            "car_listing": {
                "id": car_listing.id,
                "title": car_listing.title,
                "brand": car_listing.brand,
                "model": car_listing.model,
                "base_price": str(car_listing.base_price),
            },
            "search_period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "quantity_requested": quantity,
            "availability": availability_data,
        }

        return Response(response)

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
class StayAvailabilityUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        """
        Update a StayAvailability instance.
        """
        stay_availability = get_object_or_404(StayAvailability, pk=pk)
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
