from django.db import transaction
from rest_framework import serializers
from datetime import timedelta
from django.utils.timezone import now
from datetime import datetime
from datetime import date
from rest_framework.exceptions import ValidationError
from apps.account.services import ImageCreationService
from apps.account.serializers import AddressSerializer, ListingImageSerializer
from apps.core.serializers import JsonSerializerField
from apps.listing.exceptions import BookingConflict
from apps.account.enums import RoleCode
from apps.listing.services import BookingService, ListingService

from apps.listing.models import (
    Amenity,
    Booking,BookingRating,
    BookingItem,StayAvailability,
    CarListing,CarAvailability,
    GuestHouseListing,
    PropertyListing,
    RoomListing,EventSpaceListing,
    CarRental,CarRentalItem,
)
from apps.listing.exceptions import RatingException
from .services import CarAvailabilityService
class AmenityResponseSSerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["id", "name", "icon"]


class RoomListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    amenities = AmenityResponseSSerializer(many=True)

    class Meta:
        model = RoomListing
        fields = [
            "id",
            "images",
            "title",
            "description",
            "base_price",
            "amenities",
            "number_of_guests",
            "total_units",
            "bed_type",
            "room_size_sqm",
            "smoking_allowed",
            "children_allowed",
            "refundable",
        ]


class RoomListingSerializer(serializers.ModelSerializer):
    # TODO: Handle HQ or branch address cases.
    # TODO: We only expect the address from the payload if it's for branch
    address = JsonSerializerField(required=False)
    images = serializers.ListField(child=serializers.ImageField())
    amenities = JsonSerializerField()
    # TODO: We need this to handle registration by michot admin
    # TODO: where the admin passes the hotel id.
    # hotel_id = serializers.UUIDField(required=False)
    company_id = serializers.UUIDField()

    class Meta:
        model = RoomListing
        fields = [
            "images",
            "title",
            "company_id",
            "description",
            "base_price",
            "address",
            "amenities",
            "number_of_guests",
            "total_units",
            "bed_type",
            "room_size_sqm",
            "smoking_allowed",
            "children_allowed",
            "refundable",
        ]

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @transaction.atomic()
    def create(self, validated_data):
        # TODO: Proper Error handling
        return ListingService.create_room_listing(validated_data)

    def to_representation(self, instance):
        return RoomListingResponseSerializer(instance, self.context).to_representation(
            instance
        )


class GuestHouseListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    address = AddressSerializer()
    amenities = AmenityResponseSSerializer(many=True)

    class Meta:
        model = GuestHouseListing
        fields = [
            "id",
            "title",
            "base_price",
            "description",
            "images",
            "total_rooms",
            "amenities",
            "address",
            "rating",
        ]


class GuestHouseListingSerializer(serializers.ModelSerializer):
    address = JsonSerializerField()
    images = serializers.ListField(child=serializers.ImageField())
    amenities = JsonSerializerField()

    class Meta:
        model = GuestHouseListing
        fields = [
            "title",
            "images",
            "base_price",
            "individual_owner",
            "company",
            "description",
            "total_rooms",
            "amenities",
            "address",
        ]

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, data):
        company_id = data.get("company")
        individual_id = data.get("individual_owner")

        if company_id and individual_id:
            raise serializers.ValidationError("Only one owner type allowed.")
        if not company_id and not individual_id:
            raise serializers.ValidationError("An owner is required.")
        return data

    def create(self, validated_data):
        # user = self.context["request"].user
        # individual_owner = validated_data.get("individual_owner")

        # ? Just for testing purpose
        # validated_data['individual_owner'] = "8393efcf-27c8-4408-bac1-cea75cccee96"

        # if not individual_owner:
        #     # ! Checking if the company is not doing this
        #     # ! but rather the Michot admin doing this and in some case the individual owner is missed.
        #     # ! Which means the logged in user is Michot admin (not another vendor)
        #     if user.role and user.role.code == RoleCode.ADMIN.value:
        #         raise serializers.ValidationError(
        #             "Valid Company or individual owner must exist."
        #         )
        #     company = get_object_or_404(CompanyProfile, user=user)
        #     validated_data["company"] = company

        # TODO: proper error handling
        return ListingService.create_guest_house_listing(validated_data)

    def to_representation(self, instance):
        return GuestHouseListingResponseSerializer(
            instance, self.context
        ).to_representation(instance)


# class CarListingResponseSerializer(serializers.ModelSerializer):
#     images = ListingImageSerializer(many=True)

#     class Meta:
#         model = CarListing
#         fields = [
#             "id",
#             "title",
#             "description",
#             "images",
#             "base_price",
#             "brand",
#             "model",
#             "year",
#             "mileage",
#             "fuel_type",
#             "transmission",
#             "condition",
#         ]


# class CarListingSerializer(serializers.ModelSerializer):
#     images = serializers.ListField(child=serializers.ImageField())

#     class Meta:
#         model = CarListing
#         fields = [
#             "title",
#             "description",
#             "images",
#             "base_price",
#             "individual_owner",
#             "company",
#             "brand",
#             "model",
#             "year",
#             "mileage",
#             "fuel_type",
#             "transmission",
#             "condition",
#         ]

#     def validate(self, data):
#         company_id = data.get("company")
#         individual_id = data.get("individual_owner")

#         if company_id and individual_id:
#             raise serializers.ValidationError("Only one owner type allowed.")
#         if not company_id and not individual_id:
#             raise serializers.ValidationError("An owner is required.")
#         return data

#     @transaction.atomic()
#     def create(self, validated_data):
#         # user = self.context["request"].user
#         # individual_owner = validated_data.get("individual_owner")
#         # # ? Just for testing purpose
#         # validated_data['individual_owner'] = "6ca9a7cf-44cc-4979-be3b-d49b8b484ef6"

#         # if not individual_owner:
#         #     # Checking if the company is not doing this but rather the Michot
#         #     # admin doing this and in some case the individual owner is missed.
#         #     # Which means the logged in user is Michot admin (not another vendor)
#         #     if user.role and user.role.code == RoleCode.ADMIN.value:
#         #         raise serializers.ValidationError(
#         #             "Valid Company or individual owner must exist."
#         #         )
#         #     company = get_object_or_404(CompanyProfile, user=user)
#         #     validated_data["company"] = company

#         images = validated_data.pop("images")

#         # individual_owner_id = validated_data.pop('individual_owner')

#         # individual_owner = get_object_or_404(
#         #     IndividualOwnerProfile,
#         #     id=individual_owner_id
#         # )

#         car_listing_instance = CarListing(
#             # individual_owner=individual_owner,
#             **validated_data
#         )

#         car_listing_instance.save()

#         ImageCreationService.create_images(car_listing_instance, images)

#         return car_listing_instance

#     def to_representation(self, instance):
#         return CarListingResponseSerializer(instance, self.context).to_representation(
#             instance
        #)
class CarAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CarAvailability
        fields = [
            'id', 'availability_type', 'is_available', 'available_from', 
            'available_to', 'quantity_available'
        ]
        read_only_fields = ['id']

class CarListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True, read_only=True)
    availabilities = CarAvailabilitySerializer(many=True, read_only=True)
    current_availability = serializers.SerializerMethodField()
    
    class Meta:
        model = CarListing
        fields = [
            "id",
            "title",
            "description",
            "images",
            "base_price",
            "is_active",
            "brand",
            "model",
            "year",
            "mileage",
            "fuel_type",
            "transmission",
            "condition",
            "listing_type",
            "car_class",
            "quantity",
            "company",
            "individual_owner",
            "availabilities",
            "current_availability",
            "created_at",
            "updated_at"
        ]
    
    def get_current_availability(self, obj):
        """Get current availability status for the car listing"""
        try:
            availability = CarAvailability.objects.get(
                car_listing=obj,
                availability_type=CarAvailability.CarAvailabilityType.RENT
            )
            return {
                'is_available': availability.is_available,
                'quantity_available': availability.quantity_available,
                'available_from': availability.available_from,
                'available_to': availability.available_to
            }
        except CarAvailability.DoesNotExist:
            return None

class CarListingSerializer(serializers.ModelSerializer):
    images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = CarListing
        fields = [
            "title",
            "description",
            "images",
            "base_price",
            "individual_owner",
            "company",
            "brand",
            "model",
            "year",
            "mileage",
            "fuel_type",
            "transmission",
            "condition",
            "listing_type",
            "car_class",
            "quantity"
        ]
    
    def validate(self, data):
        company = data.get("company")
        individual_owner = data.get("individual_owner")

        if company and individual_owner:
            raise serializers.ValidationError("Only one owner type allowed.")
        if not company and not individual_owner:
            raise serializers.ValidationError("An owner is required.")
        
        # Validate quantity for rental listings
        listing_type = data.get('listing_type', CarListing.ListingTypeChoices.RENT)
        quantity = data.get('quantity', 1)
        
        if listing_type == CarListing.ListingTypeChoices.RENT and quantity < 1:
            raise serializers.ValidationError("Quantity must be at least 1 for rental listings.")
        
        # Validate base_price
        base_price = data.get('base_price')
        if base_price and base_price <= 0:
            raise serializers.ValidationError("Base price must be greater than 0.")
        
        return data

    @transaction.atomic
    def create(self, validated_data):
        images = validated_data.pop("images", [])
        
        car_listing_instance = CarListing.objects.create(**validated_data)
        
        # Create images if provided
        if images:
            ImageCreationService.create_images(car_listing_instance, images)
        
        # Create availability record
        CarAvailabilityService.create_availability_for_car_listing(car_listing_instance)
        
        return car_listing_instance

    def to_representation(self, instance):
        return CarListingResponseSerializer(instance, context=self.context).data

class CarRentalItemSerializer(serializers.ModelSerializer):
    car_listing_details = serializers.SerializerMethodField()
    subtotal = serializers.ReadOnlyField()
    
    class Meta:
        model = CarRentalItem
        fields = [
            'id', 'car_listing', 'car_listing_details', 'units_rent', 
            'price_per_unit', 'subtotal', 'created_at'
        ]
        read_only_fields = ['id', 'subtotal', 'created_at']
    
    def get_car_listing_details(self, obj):
        return {
            'id': obj.car_listing.id,
            'title': obj.car_listing.title,
            'brand': obj.car_listing.brand,
            'model': obj.car_listing.model,
            'year': obj.car_listing.year,
            'base_price': obj.car_listing.base_price  # Include base price for reference
        }

class CarRentalSerializer(serializers.ModelSerializer):
    rental_items = CarRentalItemSerializer(many=True, write_only=True)
    items_details = CarRentalItemSerializer(
        source='rental_items', 
        many=True, 
        read_only=True
    )
    renter_name = serializers.CharField(source='renter.get_full_name', read_only=True)
    
    class Meta:
        model = CarRental
        fields = [
            'id', 'renter', 'renter_name', 'start_date', 'end_date', 
            'total_price', 'status', 'rental_items', 'items_details',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']
    
    def validate(self, data):
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        rental_items = data.get('rental_items', [])
        
        if start_date and end_date:
            if start_date >= end_date:
                raise serializers.ValidationError({
                    "end_date": "End date must be after start date."
                })
            
            if start_date < datetime.now().date():
                raise serializers.ValidationError({
                    "start_date": "Start date cannot be in the past."
                })
        
        if not rental_items:
            raise serializers.ValidationError({
                "rental_items": "At least one rental item is required."
            })
        
        # Validate each rental item
        for item in rental_items:
            car_listing = item.get('car_listing')
            units_rent = item.get('units_rent', 1)
            price_per_unit = item.get('price_per_unit')
            
            if not car_listing:
                raise serializers.ValidationError({
                    "rental_items": "Car listing is required for each item."
                })
            
            if car_listing.listing_type != CarListing.ListingTypeChoices.RENT:
                raise serializers.ValidationError({
                    "rental_items": f"Car {car_listing} is not available for rent."
                })
            
            # Check availability
            availability_check = CarAvailabilityService.check_availability_for_rent(
                car_listing=car_listing,
                start_date=start_date,
                end_date=end_date,
                quantity=units_rent
            )
            
            if not availability_check.get('available'):
                raise serializers.ValidationError({
                    "rental_items": f"Car {car_listing} is not available: {availability_check.get('reason')}"
                })
            
            if not price_per_unit or price_per_unit <= 0:
                raise serializers.ValidationError({
                    "rental_items": "Price per unit must be greater than 0."
                })
            
            # You can add validation to ensure price_per_unit is reasonable
            # compared to the car's base_price if needed
            base_price = car_listing.base_price
            if price_per_unit > base_price * 2:  # Example: prevent overcharging
                raise serializers.ValidationError({
                    "rental_items": f"Rental price seems too high compared to the car's base price."
                })
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        rental_items_data = validated_data.pop('rental_items')
        renter = self.context['request'].user
        
        # Calculate total price
        total_price = sum(
            item['units_rent'] * item['price_per_unit'] 
            for item in rental_items_data
        )
        
        # Create rental
        rental = CarRental.objects.create(
            renter=renter,
            total_price=total_price,
            **validated_data
        )
        
        # Create rental items and update availability
        for item_data in rental_items_data:
            car_listing = item_data['car_listing']
            units_rent = item_data['units_rent']
            
            CarRentalItem.objects.create(
                car_rental=rental,
                **item_data
            )
            
            # Update availability
            CarAvailabilityService.update_availability_after_rental(
                car_listing=car_listing,
                quantity=units_rent,
                action="decrement"
            )
        
        return rental
    
    def update(self, instance, validated_data):
        # Handle rental updates (like cancellation)
        if 'status' in validated_data:
            old_status = instance.status
            new_status = validated_data['status']
            
            # If cancelling a confirmed rental, return units to availability
            if (old_status == CarRental.RentStatus.CONFIRMED and 
                new_status == CarRental.RentStatus.CANCELLED):
                
                for rental_item in instance.rental_items.all():
                    CarAvailabilityService.update_availability_after_rental(
                        car_listing=rental_item.car_listing,
                        quantity=rental_item.units_rent,
                        action="increment"
                    )
            
            # If confirming a pending rental, ensure availability still exists
            elif (old_status == CarRental.RentStatus.PENDING and 
                  new_status == CarRental.RentStatus.CONFIRMED):
                
                for rental_item in instance.rental_items.all():
                    availability_check = CarAvailabilityService.check_availability_for_rent(
                        car_listing=rental_item.car_listing,
                        start_date=instance.start_date,
                        end_date=instance.end_date,
                        quantity=rental_item.units_rent
                    )
                    
                    if not availability_check.get('available'):
                        raise serializers.ValidationError({
                            "status": f"Cannot confirm rental: {availability_check.get('reason')}"
                        })
        
        return super().update(instance, validated_data)

class AvailabilityCheckSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    
    def validate(self, data):
        start_date = data['start_date']
        end_date = data['end_date']
        
        if start_date >= end_date:
            raise serializers.ValidationError({
                "end_date": "End date must be after start date."
            })
        
        if start_date < datetime.now().date():
            raise serializers.ValidationError({
                "start_date": "Start date cannot be in the past."
            })
        
        return data

class CarSearchSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    brand = serializers.CharField(required=False, allow_blank=True)
    car_class = serializers.CharField(required=False, allow_blank=True)
    max_daily_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0
    )
    
    def validate(self, data):
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise serializers.ValidationError({
                    "end_date": "End date must be after start date."
                })
        
        return data
class CarAvailabilityUpdateSerializer(serializers.Serializer):
    is_available = serializers.BooleanField(required=False)
    available_from = serializers.DateTimeField(required=False, allow_null=True)
    available_to = serializers.DateTimeField(required=False, allow_null=True)
    quantity_available = serializers.IntegerField(required=False, min_value=0)
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False) # Example field type

    def update(self, instance, validated_data):
        """
        Required method for saving updates when using serializers.Serializer.
        Includes logic to set is_available=False if quantity_available=0.
        """
        quantity = validated_data.get('quantity_available')
        if quantity == 0:
            validated_data['is_available'] = False
        elif quantity is not None and quantity > 0:
            if validated_data.get('is_available') is not False:
                 validated_data['is_available'] = True
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        instance.save()
        return instance
    
class PropertyListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    address = AddressSerializer()

    class Meta:
        model = PropertyListing
        fields = [
            "id",
            "title",
            "description",
            "images",
            "base_price",
            "address",
            "property_type",
            "bedrooms",
            "bathrooms",
            "square_meters",
            "is_furnished",
        ]


class PropertyListingSerializer(serializers.ModelSerializer):
    address = JsonSerializerField()
    images = serializers.ListField(child=serializers.ImageField())

    class Meta:
        model = PropertyListing
        fields = [
            "title",
            "description",
            "images",
            "base_price",
            "individual_owner",
            "company",
            "address",
            "property_type",
            "bedrooms",
            "bathrooms",
            "square_meters",
            "is_furnished",
        ]

    def validate(self, data):
        company_id = data.get("company")
        individual_id = data.get("individual_owner")

        if company_id and individual_id:
            raise serializers.ValidationError(
                {"owner": "Only one owner type allowed."}
            )
        if not company_id and not individual_id:
            raise serializers.ValidationError(
                {"owner": "An owner is required."}
            )
        return data

    def create(self, validated_data):
        # user = self.context["request"].user
        # individual_owner = validated_data.get("individual_owner")
        # company_owner = validated_data.get("company_owner")

        # ? Just for testing purpose
        # validated_data['individual_owner'] = "6ca9a7cf-44cc-4979-be3b-d49b8b484ef6"

        # if not individual_owner:
        #     # Checking if the company is not doing this
        #     # but rather the Michot admin doing this and in some case the individual owner is missed.
        #     # Which means the logged in user is Michot admin (not another vendor)
        #     if user.role and user.role.code == RoleCode.ADMIN.value:
        #         raise serializers.ValidationError(
        #             "Valid Company or individual owner must exist."
        #         )
        #     company = get_object_or_404(CompanyProfile, user=user)
        #     validated_data["company"] = company

        return ListingService.create_property_listing(validated_data)

    def to_representation(self, instance):
        return PropertyListingResponseSerializer(
            instance, self.context
        ).to_representation(instance)


class BookingItemResponseSerializer(serializers.ModelSerializer):
    room_id = serializers.UUIDField(source="room.id", read_only=True)
    room_title = serializers.CharField(source="room.title", read_only=True)
    room_description = serializers.CharField(source="room.description", read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = BookingItem
        fields = [
            "id",
            "room_id",
            "room_title",
            "room_description",
            "units_booked",
            "price_per_unit",
            "subtotal",
        ]

    def get_subtotal(self, obj):
        return obj.subtotal()


class BookingResponseSerializer(serializers.ModelSerializer):
    items = BookingItemResponseSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "user",
            "check_in_date",
            "check_out_date",
            "total_price",
            "status",
            "items",
        ]
class BookingRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingRating
        fields = ["rating", "comment"]

    def validate(self, attrs):
        booking = self.context["booking"]
        today = now().date()

        if today < booking.check_out_date:
            raise RatingException({"detail": "You can only rate after your stay is completed."})

        if today > booking.check_out_date + timedelta(days=15):
            raise RatingException({"detail": "Rating period has expired (15 days limit)."})

        if hasattr(booking, "rating"):
            raise RatingException({"detail": "This booking already has a rating."})

        return attrs

class BookingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingItem
        fields = ["room", "units_booked"]


class BookingSerializer(serializers.ModelSerializer):
    items = BookingItemSerializer(many=True)

    class Meta:
        model = Booking
        fields = ["items", "check_in_date", "check_out_date","status"]
        read_only_fields = ["status"]
    def validate(self, data):
        check_in = data.get("check_in_date")
        check_out = data.get("check_out_date")
        
        if check_in and check_out:
            if check_out <= check_in:
                raise serializers.ValidationError(
                    {"check_out_date": "Check-out date must be after check-in date."}
                )
        
        items = data.get("items", [])
        if not items:
            raise serializers.ValidationError(
                {"items": "At least one booking item is required."}
            )
        
        return data

    def create(self, validated_data):
        # 1. Determine the user
        user = validated_data.pop("user", None)
        request = self.context.get("request")
        if not user and request:
            user = request.user
        is_front_desk = False
        
        if user and user.is_authenticated and user.role and user.role.code == RoleCode.FRONT_DESK.value:
            is_front_desk = True
        if is_front_desk:
            validated_data["status"] = Booking.BookingStatus.WALK_IN
        return BookingService.create_booking(validated_data, user=user)

    def to_representation(self, instance):
        return BookingResponseSerializer(instance, self.context).to_representation(
            instance
        )
class PartialCancelSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    units_to_cancel = serializers.IntegerField(min_value=1)


class SearchRoomSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    number_of_guests = serializers.IntegerField()
    bed_type = serializers.CharField()
    room_size_sqm = serializers.IntegerField()
    available_units = serializers.IntegerField()
    # Optional seasonal preview fields populated by StaySearchView when enabled
    display_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    preview_min_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    preview_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    preview_has_discount = serializers.BooleanField(required=False)


class SearchResultSerializer(serializers.Serializer):
    hotel_id = serializers.UUIDField()
    hotel_name = serializers.CharField()
    city = serializers.CharField()
    stars = serializers.IntegerField(allow_null=True)
    rooms = SearchRoomSerializer(many=True)
class StayAvailabilityUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StayAvailability
        fields = [ "available_rooms"]

    def validate_available_rooms(self, value):
        if value < 0:
            raise serializers.ValidationError("available_rooms must be non-negative.")
        return value
class EventSpaceListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    amenities = AmenityResponseSSerializer(many=True)

    class Meta:
        model = EventSpaceListing
        fields = [
            "id",
            "images",
            "title",
            "description",
            "number_of_guests",
            "base_price",
            "amenities",
            "number_of_guests",
            "total_units",
            "space_type",
            "floor_area_sqm",
        ]

