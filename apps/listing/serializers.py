from django.db import transaction
from rest_framework import serializers
from datetime import timedelta
from django.utils.timezone import now
from datetime import datetime
from datetime import date
from rest_framework.exceptions import ValidationError
from apps.account.services import ImageCreationService
from apps.account.models import CompanyProfile
from django.shortcuts import get_object_or_404
from apps.account.serializers import AddressSerializer, ListingImageSerializer
from apps.core.serializers import JsonSerializerField,FacilitySerializer
from apps.listing.exceptions import BookingConflict
from apps.account.enums import RoleCode
from apps.core.models import Address
from apps.listing.services import BookingService, ListingService,EventSpaceAvailabilityService,EventSpaceAvailabilityService,GuestHouseAvailabilityService

from apps.listing.models import (
    Amenity,
    Booking,BookingRating,
    BookingItem,StayAvailability,GuestHouseAvailability,
    CarListing,CarAvailability,
    GuestHouseListing,
    PropertyListing,
    RoomListing,EventSpaceListing,
    CarRental,CarRentalItem,GuestHouseBookingItem,GuestHouseBooking
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
    available_units = serializers.SerializerMethodField()

    class Meta:
        model = RoomListing
        fields = [
            "id",
            "images",
            "title",
            "description",
            "base_price",
            "currency",
            "amenities",
            "number_of_guests",
            "total_units",
            "bed_type",
            "room_size_sqm",
            "smoking_allowed",
            "children_allowed",
            "refundable",
            "available_units",
        ]

    def get_available_units(self, obj):
        availability_map = self.context.get("availability_map")
        if availability_map is None:
            return None
        return availability_map.get(obj.id, 0)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if "availability_map" not in self.context:
            ret.pop("available_units", None)
        return ret


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
            "currency",
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

    def validate_currency(self, value):
        if not value:
            return value
        value = value.upper()
        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
        return value

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
    facility=FacilitySerializer()
    class Meta:
        model = GuestHouseListing
        fields = [
            "id",
            "title",
            "base_price",
            "currency",
            "description",
            "images",
            "total_rooms",
            "amenities",
            "address",
            "rating",
            "facility",
        ]


class GuestHouseListingSerializer(serializers.ModelSerializer):
    address = JsonSerializerField()
    images = serializers.ListField(child=serializers.ImageField())
    amenities = JsonSerializerField()
    facility=FacilitySerializer()
    class Meta:
        model = GuestHouseListing
        fields = [
            "title",
            "images",
            "base_price",
            "currency",
            "individual_owner",
            "company",
            "description",
            "total_rooms",
            "amenities",
            "address",
            "facility"
        ]

    def validate_currency(self, value):
        if not value:
            return value
        value = value.upper()
        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
        return value

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
        if company_id:
            company_obj = company_id if isinstance(company_id, CompanyProfile) else get_object_or_404(CompanyProfile, id=company_id)
            if company_obj.status != CompanyProfile.StatusChoice.APPROVED:
                raise serializers.ValidationError({"company": "Company profile is not approved."})
        return data

    # def create(self, validated_data):
    #     # user = self.context["request"].user
    #     # individual_owner = validated_data.get("individual_owner")

    #     # ? Just for testing purpose
    #     # validated_data['individual_owner'] = "8393efcf-27c8-4408-bac1-cea75cccee96"

    #     # if not individual_owner:
    #     #     # ! Checking if the company is not doing this
    #     #     # ! but rather the Michot admin doing this and in some case the individual owner is missed.
    #     #     # ! Which means the logged in user is Michot admin (not another vendor)
    #     #     if user.role and user.role.code == RoleCode.ADMIN.value:
    #     #         raise serializers.ValidationError(
    #     #             "Valid Company or individual owner must exist."
    #     #         )
    #     #     company = get_object_or_404(CompanyProfile, user=user)
    #     #     validated_data["company"] = company

    #     # TODO: proper error handling
    #     return ListingService.create_guest_house_listing(validated_data)
    @transaction.atomic
    def create(self, validated_data):
        images = validated_data.pop("images", [])
        amenities = validated_data.pop("amenities", [])
        facilities = validated_data.pop("facility", [])
        address_data = validated_data.pop("address")

        address = Address.objects.create(**address_data)
        validated_data["address"] = address

        instance = GuestHouseListing.objects.create(**validated_data)

        if isinstance(amenities, list):
            instance.amenities.set(amenities)

        if isinstance(facilities, list):
            instance.facility.set(facilities)

        if images:
            ImageCreationService.create_images(instance, images)

        # FIX: use correct service method
        GuestHouseAvailabilityService.create_availability(
            instance,
            units_quantity=instance.total_rooms
        )

        return instance

    def to_representation(self, instance):
        return GuestHouseListingResponseSerializer(
            instance, self.context
        ).to_representation(instance)
class GuestHouseBookingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestHouseBookingItem
        fields = [
            "room",
            "units_booked",
        ]
class GuestHouseBookingSerializer(serializers.ModelSerializer):
    items = GuestHouseBookingItemSerializer(many=True, write_only=True)
    class Meta:
        model = GuestHouseBooking
        fields = [
            "id",
            "renter",
            "start_date",
            "end_date",
            "total_price",
            "items",
            
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]
    def validate(self, data):
        start = data["start_date"]
        end = data["end_date"]
        items = data.get("items", [])

        if start >= end:
            raise serializers.ValidationError("End date must be after start date.")

        if start < datetime.now().date():
            raise serializers.ValidationError("Start date cannot be in the past.")

        if not items:
            raise serializers.ValidationError("At least one room booking item is required.")

        # Build space_infos list expected by availability service
        room_infos = [
            {"guesthouse_listing": item["room"], "quantity": item["units_booked"]}
            for item in items
        ]

        # Centralized availability validation
        GuestHouseAvailabilityService.validate_availability(
            room_infos, start, end
        )

        return data

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        renter = self.context["request"].user

        # Calculate total price
        total_price = sum([
            item["units_booked"] * item["price_per_unit"]
            for item in items_data
        ])

        booking = GuestHouseBooking.objects.create(
            renter=renter,
            total_price=total_price,
            **validated_data
        )

        # Build space_infos for update
        room_infos = []

        for item in items_data:
            obj = GuestHouseBookingItem.objects.create(
                booking=booking,
                **item
            )

            room_infos.append({
                "guesthouse_listing": obj.room,
                "quantity": obj.units_booked
            })

        # Decrement availability
        GuestHouseAvailabilityService.update_availability(
            room_infos,
            booking.start_date,
            booking.end_date,
            increment=False
        )

        return booking

    @transaction.atomic
    def update(self, instance, validated_data):
        new_status = validated_data.get("status")
        old_status = instance.status

        # CANCELLED → add back availability
        if old_status == GuestHouseBooking.RentStatus.CONFIRMED and new_status == GuestHouseBooking.RentStatus.CANCELLED:

            room_infos = [{
                "guesthouse_listing": item.room,
                "quantity": item.units_booked
            } for item in instance.items.all()]

            GuestHouseAvailabilityService.update_availability(
                room_infos,
                instance.start_date,
                instance.end_date,
                increment=True
            )

        # CONFIRMATION → revalidate
        if old_status == GuestHouseBooking.RentStatus.PENDING and new_status == GuestHouseBooking.RentStatus.CONFIRMED:

            room_infos = [{
                "guesthouse_listing": item.room,
                "quantity": item.units_booked
            } for item in instance.items.all()]

            GuestHouseAvailabilityService.validate_availability(
                room_infos,
                instance.start_date,
                instance.end_date
            )

        return super().update(instance, validated_data)


class GuestHouseAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestHouseAvailability
        fields = ["id", "date", "available_rooms"]
        read_only_fields = ["id"]

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
            'id',
            'date',
            'available_units',
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
            "seats",
            "individual_owner",
            "availabilities",
            "current_availability",
            "created_at",
            "updated_at"
        ]
    
    def get_current_availability(self, obj):
        """
        Return today's available units if exists.
        """
        today = date.today()
        availability = CarAvailability.objects.filter(
            car_listing=obj, date=today
        ).first()

        if not availability:
            return None
        
        return {
            "date": availability.date,
            "available_units": availability.available_units
        }

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
            "currency",
            "individual_owner",
            "company",
            "brand",
            "model",
            "year",
            "mileage",
            "fuel_type",
            "transmission",
            "condition",
            "seats",
            "listing_type",
            "car_class",
            "quantity"
        ]

    def validate_currency(self, value):
        if not value:
            return value
        value = value.upper()
        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
        return value
    
    def validate(self, data):
        company = data.get("company")
        individual_owner = data.get("individual_owner")

        if company and individual_owner:
            raise serializers.ValidationError("Only one owner type allowed.")
        if not company and not individual_owner:
            raise serializers.ValidationError("An owner is required.")
        
        listing_type = data.get('listing_type', CarListing.ListingTypeChoices.RENT)
        quantity = data.get('quantity', 1)
        
        if listing_type == CarListing.ListingTypeChoices.RENT and quantity < 1:
            raise serializers.ValidationError("Quantity must be at least 1 for rental listings.")
        
        base_price = data.get('base_price')
        if base_price and base_price <= 0:
            raise serializers.ValidationError("Base price must be greater than 0.")
        # Ensure provided company profile (if any) is approved
        if company:
            company_obj = company if isinstance(company, CompanyProfile) else get_object_or_404(CompanyProfile, id=company)
            if company_obj.status != CompanyProfile.StatusChoice.APPROVED:
                raise serializers.ValidationError({"company": "Company profile is not approved."})
        
        return data

    @transaction.atomic
    def create(self, validated_data):
        images = validated_data.pop("images", [])
        
        car_listing_instance = CarListing.objects.create(**validated_data)
        
        if images:
            ImageCreationService.create_images(car_listing_instance, images)
        
        # Creates daily availability records
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
            'base_price': obj.car_listing.base_price
        }


class CarRentalSerializer(serializers.ModelSerializer):
    rental_items = CarRentalItemSerializer(many=True, write_only=True)
    items_details = CarRentalItemSerializer(
        source='rental_items', many=True, read_only=True
    )
    renter_name = serializers.CharField(
        source='renter.get_full_name', read_only=True
    )
    
    class Meta:
        model = CarRental
        fields = [
            'id', 'renter', 'renter_name', 'start_date', 'end_date', 
            'total_price', 'currency', 'status', 'rental_items', 'items_details',
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
        else:
            raise serializers.ValidationError({
                "start_date": "Start date and end date are required."
            })

        if start_date < date.today():
            raise serializers.ValidationError({
                "start_date": "Start date cannot be in the past."
            })

        if not rental_items:
            raise serializers.ValidationError({
                "rental_items": "At least one rental item is required."
            })

        # ========== DAILY AVAILABILITY CHECK ==========
        for item in rental_items:
            listing = item["car_listing"]
            units = item["units_rent"]

            result = CarAvailabilityService.check_daily_availability(
                car_listing=listing,
                start_date=start_date,
                end_date=end_date,
                quantity=units,
            )

            if not result.get("available", False):
                raise serializers.ValidationError({
                    "rental_items": f"{listing.title} is not available: {result.get('reason', 'unavailable')}"
                })

            if item.get("price_per_unit", 0) <= 0:
                raise serializers.ValidationError({
                    "rental_items": "Price per unit must be greater than 0."
                })

        return data
    
    @transaction.atomic
    def create(self, validated_data):
        rental_items_data = validated_data.pop('rental_items')
        renter = self.context['request'].user
        
        total_price = sum(
            item['units_rent'] * item['price_per_unit'] 
            for item in rental_items_data
        )
        
        rental = CarRental.objects.create(
            renter=renter,
            total_price=total_price,
            **validated_data
        )
        
        for item in rental_items_data:
            listing = item["car_listing"]
            units = item["units_rent"]

            CarRentalItem.objects.create(
                car_rental=rental, **item
            )

            # decrement daily availability
            CarAvailabilityService.reserve_daily_units(
                listing, rental.start_date, rental.end_date, units
            )
        
        return rental
    
    @transaction.atomic
    def update(self, instance, validated_data):
        old_status = instance.status
        new_status = validated_data.get("status")

        # cancellation
        if old_status == CarRental.RentStatus.CONFIRMED and new_status == CarRental.RentStatus.CANCELLED:
            for item in instance.rental_items.all():
                CarAvailabilityService.release_daily_units(
                    item.car_listing,
                    instance.start_date,
                    instance.end_date,
                    item.units_rent
                )

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
            "currency",
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
            "currency",
            "individual_owner",
            "company",
            "address",
            "property_type",
            "bedrooms",
            "bathrooms",
            "square_meters",
            "is_furnished",
        ]

    def validate_currency(self, value):
        if not value:
            return value
        value = value.upper()
        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
        return value

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
    snapshot = serializers.JSONField(read_only=True)

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
            "snapshot",
        ]

    def get_subtotal(self, obj):
        return obj.subtotal()


class BookingResponseSerializer(serializers.ModelSerializer):
    items = BookingItemResponseSerializer(many=True, read_only=True)
    snapshot = serializers.JSONField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "user",
            "check_in_date",
            "check_out_date",
            "total_price",
            "currency",
            "status",
            "items",
            "snapshot",
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
    is_favorite = serializers.SerializerMethodField()
    rooms = SearchRoomSerializer(many=True)

    def get_is_favorite(self, obj):
        # pure serializer logic; expects `favorite_object_ids` in context
        fav_ids = self.context.get("favorite_object_ids") if self.context is not None else None
        if not fav_ids:
            return False
        try:
            return str(obj.get("hotel_id")) in fav_ids
        except Exception:
            return False
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
            "currency",
            "amenities",
            "number_of_guests",
            "total_units",
            "space_type",
            "floor_area_sqm",
        ]
class EventSpaceListingSerializer(serializers.ModelSerializer):
    """Serializer used for POST/PUT operations, relying on the service layer."""
    
    address = AddressSerializer(required=False)
    images = serializers.ListField(child=serializers.ImageField(), required=False) 
    amenities = JsonSerializerField(required=False) 

    company_id = serializers.UUIDField()

    class Meta:
        model = EventSpaceListing
        fields = [
            "images",
            "title",
            "company_id",
            "description",
            "base_price",
            "currency",
            "address",
            "amenities",
            "number_of_guests",
            "total_units",
            "space_type",
            "floor_area_sqm",
            # Add other fields as needed for creation
        ]

    def validate_currency(self, value):
        if not value:
            return value
        value = value.upper()
        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
        return value

    # The Address validation is handled by the nested AddressSerializer
    # if you use the standard nested serializer structure (as shown above).
    # If using JsonSerializerField for Address, you must re-implement the validate_address:
    # def validate_address(self, attr):
    #     serializer = AddressSerializer(data=attr)
    #     serializer.is_valid(raise_exception=True)
    #     return serializer.validated_data

    @transaction.atomic()
    def create(self, validated_data):
        """
        Delegates the complex creation process (including availability) 
        to the service layer.
        """
        return EventSpaceAvailabilityService.create_event_space_listing(validated_data)

    def to_representation(self, instance):
        """
        Uses the Response Serializer for the representation of the created/updated object.
        """
        return EventSpaceListingResponseSerializer(instance, self.context).to_representation(
            instance
        )
from rest_framework import serializers
from .models import EventSpaceBooking, EventSpaceBookingItem
from .services import EventSpaceBookingService 
# Assuming imports for other required classes (RoleCode, serializers, etc.)

# --- Response Serializers ---

class EventSpaceBookingItemResponseSerializer(serializers.ModelSerializer):
    event_space_id = serializers.UUIDField(source="event_space.id", read_only=True)
    event_space_title = serializers.CharField(source="event_space.title", read_only=True)
    event_space_description = serializers.CharField(source="event_space.description", read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = EventSpaceBookingItem
        fields = [
            "id",
            "event_space_id",
            "event_space_title",
            "event_space_description",
            "units_booked",
            "price_per_unit",
            "subtotal",
        ]

    def get_subtotal(self, obj):
        return obj.subtotal()


class EventSpaceBookingResponseSerializer(serializers.ModelSerializer):
    """Serializer for reading/outputting a complete Event Space Booking."""
    # Related_name is simply 'items' on EventSpaceBooking
    items = EventSpaceBookingItemResponseSerializer(many=True, read_only=True) 

    class Meta:
        model = EventSpaceBooking
        fields = [
            "id",
            "user",
            "check_in_date",
            "check_out_date",
            "total_price",
            "status",
            "items",
            "event_type"
        ]

# --- Write (Create) Serializers ---

class EventSpaceBookingItemSerializer(serializers.ModelSerializer):
    """Serializer for taking input on booking items."""
    class Meta:
        model = EventSpaceBookingItem
        fields = ["event_space", "units_booked"] 


class EventSpaceBookingSerializer(serializers.ModelSerializer):
    """Main serializer for creating a new Event Space Booking."""
    items = EventSpaceBookingItemSerializer(many=True) 

    class Meta:
        model = EventSpaceBooking # Mapped to the dedicated model
        fields = ["items", "check_in_date", "check_out_date","event_type"]
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
        
        # !To Do: You may want to add validation here to ensure all event spaces
        # belong to the same hotel, if that is a business rule.
        
        return data

    def create(self, validated_data):
        # Determine the user and status logic (copied from your original)
        user = validated_data.pop("user", None)
        request = self.context.get("request")
        if not user and request:
            user = request.user
            
        is_front_desk = False
        if user and user.is_authenticated and hasattr(user, 'role') and user.role and user.role.code == RoleCode.FRONT_DESK.value:
            is_front_desk = True
        
        if is_front_desk:
            validated_data["status"] = EventSpaceBooking.BookingStatus.WALK_IN 
            
        return EventSpaceBookingService.create_booking(validated_data, user=user)

    def to_representation(self, instance):
        return EventSpaceBookingResponseSerializer(instance, self.context).to_representation(
            instance
        )