from django.conf import settings
from django.utils.dateparse import parse_date
from django.db import transaction
from rest_framework import serializers
from datetime import timedelta
from django.utils.timezone import now
from datetime import datetime
from datetime import date
from rest_framework.exceptions import ValidationError
from apps.account.services import ImageCreationService
from apps.account.models import CompanyProfile, HotelProfile
from django.shortcuts import get_object_or_404
from apps.account.serializers import AddressSerializer, ListingImageSerializer
from apps.core.serializers import (
    AddressSerializer,
    FacilityResponseSerializer,
    FlexibleAddressField,
    FacilitySerializer,
    JsonSerializerField,
)
from apps.listing.exceptions import BookingConflict
from apps.account.enums import RoleCode
from apps.core.models import Address
from apps.listing.services import BookingService, ListingService, EventSpaceAvailabilityService, GuestHouseAvailabilityService

from apps.listing.models import (
    Amenity,
    Booking,BookingRating,
    BookingItem,StayAvailability,GuestHouseAvailability,
    CarListing,CarAvailability,
    GuestHouseListing,
    PropertyListing,
    RoomListing,EventSpaceListing,
    CarRental,CarRentalItem,GuestHouseBookingItem,GuestHouseBooking,
    TermsAndConditions,
)
from apps.listing.exceptions import RatingException
from .services import CarAvailabilityService
from apps.core.utils import convert_currency
from apps.listing.services import CarRentalService
from apps.listing.services import GuestHouseBookingService

from django.utils.dateparse import parse_date
from apps.listing.services import PriceService
from apps.core.utils import get_display_currency, convert_currency
from decimal import Decimal
from datetime import timedelta 




class CurrencyConversionMixin(metaclass=serializers.SerializerMetaclass):
    converted_price = serializers.SerializerMethodField()
    converted_currency = serializers.SerializerMethodField()

    def get_converted_price(self, obj):
        target_currency = self.context.get("display_currency")
        if not target_currency:
            return None
        
        # Determine source price and currency
        # Supports both model instances (getattr) and dictionaries (bracket access)
        def get_val(o, attr, default=None):
            if isinstance(o, dict):
                return o.get(attr, default)
            return getattr(o, attr, default)

        source_price = get_val(obj, "base_price")
        if source_price is None:
            source_price = get_val(obj, "total_price")
            
        source_currency = get_val(obj, "currency", "ETB")

        if source_price is None:
            return None

        try:
            return convert_currency(source_price, source_currency, target_currency)
        except Exception:
            return None

    def get_converted_currency(self, obj):
        return self.context.get("display_currency")


class PriceQuoteMixin(metaclass=serializers.SerializerMetaclass):
    price_quote = serializers.SerializerMethodField(help_text="Complete pricing breakdown including platform fees. Populated only when check_in/check_out dates are provided.")

    def get_price_quote(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        units = request.query_params.get('units', '1')
        
        if not (check_in and check_out):
            return None
        
        try:
            check_in_date = parse_date(check_in)
            check_out_date = parse_date(check_out)
            units_int = int(units)
        except (ValueError, TypeError):
            return None
        
        if not check_in_date or not check_out_date or check_out_date <= check_in_date or units_int < 1:
            return None
        
        display_currency = get_display_currency(request)
        source_currency = getattr(obj, 'currency', 'ETB')
        
        try:
            if hasattr(PriceService, 'resolve_price_details_batch'):
                price_details_list = PriceService.resolve_price_details_batch(
                    obj, check_in_date, check_out_date
                )
            else:
                price_details_list = []
                date_cursor = check_in_date
                while date_cursor < check_out_date:
                    detail = PriceService.resolve_price_detail(obj, date_cursor)
                    detail['date'] = date_cursor
                    price_details_list.append(detail)
                    date_cursor += timedelta(days=1)
        except Exception:
            return None
        
        breakdown = []
        subtotal = Decimal('0.00')
        
        for detail in price_details_list:
            price_in_source = detail['price_per_unit']
            
            if display_currency and display_currency != source_currency:
                try:
                    price_converted = convert_currency(
                        price_in_source,
                        source_currency,
                        display_currency
                    )
                except Exception:
                    price_converted = price_in_source
                    display_currency = source_currency
            else:
                price_converted = price_in_source
            
            daily_total = price_converted * units_int
            subtotal += daily_total
            
            breakdown.append({
                'date': detail['date'].isoformat(),
                'price_per_unit': str(price_converted.quantize(Decimal('0.01'))),
                'units': units_int,
                'daily_total': str(daily_total.quantize(Decimal('0.01'))),
                'source': detail.get('source', 'base'),
                'is_discounted': detail.get('is_discounted', False)
            })
        
        # Centralized platform fee from settings
        fee_rate = Decimal(str(getattr(settings, 'PLATFORM_FEE_RATE', '0.05')))
        platform_fee = subtotal * fee_rate
        total = subtotal + platform_fee
        
        has_discount = any(item['is_discounted'] for item in breakdown)
        
        min_nightly_price = Decimal('0.00')
        if breakdown:
            min_nightly_price = min(Decimal(item['price_per_unit']) for item in breakdown)

        return {
            'breakdown': breakdown,
            'items_subtotal': str(subtotal.quantize(Decimal('0.01'))),
            'subtotal': str(subtotal.quantize(Decimal('0.01'))),       # legacy
            'base_total': str(subtotal.quantize(Decimal('0.01'))),
            'platform_fee': str(platform_fee.quantize(Decimal('0.01'))),
            'platform_fee_percentage': str(fee_rate * 100),
            'total': str(total.quantize(Decimal('0.01'))),
            'currency': display_currency or source_currency,
            'has_discount': has_discount,
            'min_price_per_unit': str(min_nightly_price.quantize(Decimal('0.01'))),
            'min_nightly_price': str(min_nightly_price.quantize(Decimal('0.01'))), # legacy
            'units_count': len(breakdown)
        }


class TermsAndConditionsSerializer(serializers.ModelSerializer):
    # Read-only serializer for displaying Terms & Conditions"
    
    class Meta:
        model = TermsAndConditions
        fields = [
            'id', 'version', 'title', 'content',
            'effective_date', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class AmenityResponseSSerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["id", "name", "icon"]


class RoomListingResponseSerializer(CurrencyConversionMixin, PriceQuoteMixin, serializers.ModelSerializer):
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
            "converted_price",
            "converted_currency",
            "price_quote",
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
        if ret.get("price_quote") is None:
            ret.pop("price_quote", None)
        return ret


class RoomListingSerializer(serializers.ModelSerializer):
    address = FlexibleAddressField(required=False)
    images = serializers.ListField(child=serializers.ImageField())
    amenities = JsonSerializerField()
    hotel_id = serializers.UUIDField()

    class Meta:
        model = RoomListing
        fields = [
            "images",
            "title",
            "hotel_id",
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

    def validate_hotel_id(self, value):
        """Ensure the hotel exists and belongs to an approved company."""
        try:
            hotel = HotelProfile.objects.select_related('company').get(id=value)
            if hotel.company.status != CompanyProfile.StatusChoice.APPROVED:
                raise serializers.ValidationError(
                    "Cannot create rooms for hotels with non-approved company profiles."
                )
            return value
        except HotelProfile.DoesNotExist:
            raise serializers.ValidationError(f"Hotel with id {value} does not exist.")

    @transaction.atomic()
    def create(self, validated_data):
        return ListingService.create_room_listing(validated_data)

    def to_representation(self, instance):
        return RoomListingResponseSerializer(instance, context=self.context).to_representation(
            instance
        )


class GuestHouseListingResponseSerializer(PriceQuoteMixin, CurrencyConversionMixin, serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    address = AddressSerializer()
    amenities = AmenityResponseSSerializer(many=True)
    facility=FacilitySerializer()
    is_favorite = serializers.SerializerMethodField()
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
            "is_favorite",
            "converted_price",
            "converted_currency",
            "price_quote",
        ]

    def get_is_favorite(self, obj):
        fav_ids = self.context.get("favorite_object_ids")
        if not fav_ids:
            return False
        return str(obj.id) in fav_ids


class GuestHouseListingSerializer(serializers.ModelSerializer):
    address = FlexibleAddressField()
    images = serializers.ListField(child=serializers.ImageField())
    amenities = JsonSerializerField()
    facility=FacilitySerializer()
    class Meta:
        model = GuestHouseListing
        fields = [
            "id",
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
            instance, context=self.context
        ).to_representation(instance)
class GuestHouseBookingItemSerializer(serializers.ModelSerializer):
    price_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    
    class Meta:
        model = GuestHouseBookingItem
        fields = [
            "room",
            "units_booked",
            "price_per_unit",
        ]
class GuestHouseBookingSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
    items = GuestHouseBookingItemSerializer(many=True, write_only=True)
    
    terms_accepted = serializers.BooleanField(required=True, write_only=True)
    terms_version = serializers.CharField(required=True, write_only=True)
    
    class Meta:
        model = GuestHouseBooking
        fields = [
            "id",
            "renter",
            "start_date",
            "end_date",
            "total_price",
            "currency",
            "items",
            "converted_price",
            "converted_currency",
            "terms_accepted",
            "terms_version",
            "terms_accepted_at",
            "terms_content_snapshot",
            "is_legacy",
        ]
        read_only_fields = ["id", "status", "renter", "total_price", "created_at", "updated_at"]
        
    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the terms and conditions to proceed with booking."
            )
        return value
        
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
        
        terms_version = data.get("terms_version")
        if terms_version and items:
            from django.contrib.contenttypes.models import ContentType
            first_guesthouse = items[0]["room"]
            
            ct = ContentType.objects.get_for_model(first_guesthouse)
            tc_exists = TermsAndConditions.objects.filter(
                content_type=ct,
                object_id=first_guesthouse.id,
                version=terms_version,
                is_active=True
            ).exists()
            
            if not tc_exists:
                raise serializers.ValidationError(
                    {"terms_version": f"Invalid or inactive T&C version: {terms_version}. Please refresh and accept the latest terms."}
                )

        return data

    @transaction.atomic
    def create(self, validated_data):
        return GuestHouseBookingService.create_booking(
            validated_data, 
            user=self.context["request"].user
        )

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


class CarListingResponseSerializer(PriceQuoteMixin, CurrencyConversionMixin, serializers.ModelSerializer):
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
            "updated_at",
            "converted_price",
            "converted_currency",
            "price_quote",
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


class CarRentalSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
    rental_items = CarRentalItemSerializer(many=True, write_only=True)
    items_details = CarRentalItemSerializer(
        source='rental_items', many=True, read_only=True
    )
    renter_name = serializers.CharField(
        source='renter.get_full_name', read_only=True
    )
    
    terms_accepted = serializers.BooleanField(required=True, write_only=True)
    terms_version = serializers.CharField(required=True, write_only=True)
    
    class Meta:
        model = CarRental
        fields = [
            'id', 'renter', 'renter_name', 'start_date', 'end_date', 
            'total_price', 'currency', 'status', 'rental_items', 'items_details',
            'created_at', 'updated_at', 'converted_price', 'converted_currency',
            'terms_accepted', 'terms_version', 'terms_accepted_at', 'terms_content_snapshot',
            'is_legacy',
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']
    
    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the terms and conditions to proceed with car rental."
            )
        return value
    
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
        
        # Validate T&C version for car rental company
        terms_version = data.get("terms_version")
        if terms_version and rental_items:
            from django.contrib.contenttypes.models import ContentType
            # Get company from first car listing
            first_car = rental_items[0]["car_listing"]
            company = first_car.company
            
            if company:
                ct = ContentType.objects.get_for_model(company)
                tc_exists = TermsAndConditions.objects.filter(
                    content_type=ct,
                    object_id=company.id,
                    version=terms_version,
                    is_active=True
                ).exists()
                
                if not tc_exists:
                    raise serializers.ValidationError(
                        {"terms_version": f"Invalid or inactive T&C version: {terms_version}. Please refresh and accept the latest terms."}
                    )

        return data
    
    @transaction.atomic
    def create(self, validated_data):
        return CarRentalService.create_booking(
            validated_data, 
            user=self.context["request"].user
        )
    
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
    
class PropertyListingResponseSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
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
            "converted_price",
            "converted_currency",
        ]


class PropertyListingSerializer(serializers.ModelSerializer):
    address = FlexibleAddressField()
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
            instance, context=self.context
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


class BookingResponseSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
    items = BookingItemResponseSerializer(many=True, read_only=True)
    snapshot = serializers.JSONField(read_only=True)

    is_resumable = serializers.SerializerMethodField()

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
            "converted_price",
            "converted_currency",
            "is_resumable",
            "terms_accepted",
            "terms_version",
            "terms_accepted_at",
            "terms_content_snapshot",
            "is_legacy",
        ]

    def get_is_resumable(self, obj):
        from django.conf import settings
        from django.utils.timezone import now
        from datetime import timedelta
        
        if obj.status != Booking.BookingStatus.PENDING:
            return False
            
        timeout = getattr(settings, 'BOOKING_PENDING_TIMEOUT_MINUTES', 15)
        return obj.created_at >= now() - timedelta(minutes=timeout)
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
    price_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    class Meta:
        model = BookingItem
        fields = ["room", "units_booked", "price_per_unit"]


class BookingSerializer(serializers.ModelSerializer):
    items = BookingItemSerializer(many=True, help_text="List of rooms and quantities to book.")
    
    # T&C fields (write_only, required for booking creation)
    terms_accepted = serializers.BooleanField(
        required=True, 
        write_only=True,
        help_text="Must be set to true to indicate agreement with the Terms and Conditions."
    )
    terms_version = serializers.CharField(
        required=True, 
        write_only=True,
        help_text="The version of the T&C document that was accepted (e.g., '1.0')."
    )

    class Meta:
        model = Booking
        fields = ["items", "check_in_date", "check_out_date", "currency", "status", 
                  "terms_accepted", "terms_version"]
        read_only_fields = ["status"]
        
    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the terms and conditions to proceed with booking."
            )
        return value
        
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
        
        terms_version = data.get("terms_version")
        if terms_version and items:
            from django.contrib.contenttypes.models import ContentType
            first_room = items[0]["room"]
            hotel = first_room.hotel
            
            if hotel:
                ct = ContentType.objects.get_for_model(hotel)
                tc_exists = TermsAndConditions.objects.filter(
                    content_type=ct,
                    object_id=hotel.id,
                    version=terms_version,
                    is_active=True
                ).exists()
                
                if not tc_exists:
                    raise serializers.ValidationError(
                        {"terms_version": f"Invalid or inactive T&C version: {terms_version}. Please refresh and accept the latest terms."}
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
        return BookingResponseSerializer(instance, context=self.context).to_representation(
            instance
        )
class PartialCancelSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    units_to_cancel = serializers.IntegerField(min_value=1)


class SearchRoomSerializer(CurrencyConversionMixin, serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(required=False, default="ETB")
    number_of_guests = serializers.IntegerField()
    bed_type = serializers.CharField()
    room_size_sqm = serializers.IntegerField()
    available_units = serializers.IntegerField()
    # Optional seasonal preview fields populated by StaySearchView when enabled
    display_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    preview_min_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    preview_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    preview_has_discount = serializers.BooleanField(required=False)


class SearchResultSerializer(CurrencyConversionMixin, serializers.Serializer):
    hotel_id = serializers.UUIDField()
    hotel_name = serializers.CharField()
    city = serializers.CharField()
    stars = serializers.IntegerField(allow_null=True)
    images = ListingImageSerializer(many=True)
    facilities = FacilityResponseSerializer(many=True)
    featured = serializers.BooleanField()
    is_favorite = serializers.SerializerMethodField()
    rooms = SearchRoomSerializer(many=True)

    def get_is_favorite(self, obj):
        # pure serializer logic; expects `favorite_object_ids` in context
        fav_ids = self.context.get("favorite_object_ids") if self.context is not None else None
        if not fav_ids:
            return False
            
        # obj is usually a dict here from StaySearchView
        hid = obj.get("hotel_id") if isinstance(obj, dict) else getattr(obj, "id", None)
        return str(hid) in fav_ids
class StayAvailabilityUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StayAvailability
        fields = [ "available_rooms"]

    def validate_available_rooms(self, value):
        if value < 0:
            raise serializers.ValidationError("available_rooms must be non-negative.")
        return value
class EventSpaceListingResponseSerializer(PriceQuoteMixin, CurrencyConversionMixin, serializers.ModelSerializer):
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
            "converted_price",
            "converted_currency",
            "price_quote",
        ]
class EventSpaceListingSerializer(serializers.ModelSerializer):
    """Serializer used for POST/PUT operations, relying on the service layer."""
    
    address = FlexibleAddressField(required=False)
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
        return ListingService.create_event_space_listing(validated_data)

    def to_representation(self, instance):
        """
        Uses the Response Serializer for the representation of the created/updated object.
        """
        return EventSpaceListingResponseSerializer(instance, context=self.context).to_representation(
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


class EventSpaceBookingResponseSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
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
            "event_type",
            "converted_price",
            "converted_currency",
            "terms_accepted",
            "terms_version",
            "terms_accepted_at",
            "terms_content_snapshot",
            "is_legacy",
        ]

# --- Write (Create) Serializers ---

class EventSpaceBookingItemSerializer(serializers.ModelSerializer):
    """Serializer for taking input on booking items."""
    price_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    
    class Meta:
        model = EventSpaceBookingItem
        fields = ["event_space", "units_booked", "price_per_unit"] 


class EventSpaceBookingSerializer(serializers.ModelSerializer):
    """Main serializer for creating a new Event Space Booking."""
    items = EventSpaceBookingItemSerializer(many=True) 
    
    terms_accepted = serializers.BooleanField(required=True, write_only=True)
    terms_version = serializers.CharField(required=True, write_only=True)

    class Meta:
        model = EventSpaceBooking # Mapped to the dedicated model
        fields = ["items", "check_in_date", "check_out_date", "currency", "event_type",
                  "terms_accepted", "terms_version"]
        read_only_fields = ["status"]

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the terms and conditions to proceed with booking."
            )
        return value

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
        
        terms_version = data.get("terms_version")
        if terms_version and items:
            from django.contrib.contenttypes.models import ContentType
            # Get hotel from first event space
            first_space = items[0]["event_space"]
            hotel = first_space.hotel
            
            if hotel:
                ct = ContentType.objects.get_for_model(hotel)
                tc_exists = TermsAndConditions.objects.filter(
                    content_type=ct,
                    object_id=hotel.id,
                    version=terms_version,
                    is_active=True
                ).exists()
                
                if not tc_exists:
                    raise serializers.ValidationError(
                        {"terms_version": f"Invalid or inactive T&C version: {terms_version}. Please refresh and accept the latest terms."}
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
        return EventSpaceBookingResponseSerializer(instance, context=self.context).to_representation(
            instance
        )


class PriceBreakdownItemSerializer(serializers.Serializer):
    date = serializers.DateField()
    price_per_unit = serializers.DecimalField(max_digits=10, decimal_places=2)
    source = serializers.CharField()
    note = serializers.CharField(required=False, allow_null=True)

class PricePreviewItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="ID of the room or event space listing")
    title = serializers.CharField(help_text="Title of the listing")
    units = serializers.IntegerField(help_text="Number of units selected")
    price_per_unit = serializers.CharField(required=False, help_text="Base price per unit (if applicable)")
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Calculated subtotal for this item over the date range")
    breakdown = PriceBreakdownItemSerializer(many=True, help_text="Detailed price breakdown for this item")

class PricePreviewTotalsSerializer(serializers.Serializer):
    items_subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Total price of all items excluding fees")
    platform_fee = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Consolidated platform fee")
    platform_fee_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, help_text="Platform fee percentage rate (e.g., 5.00)")
    grand_total = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Final price including all taxes and fees")
    currency = serializers.CharField(help_text="ISO currency code (e.g., ETB)")

class PricePreviewResponseSerializer(serializers.Serializer):
    items = PricePreviewItemSerializer(many=True, help_text="Breakdown of individual items in the selection")
    totals = PricePreviewTotalsSerializer(help_text="Consolidated cost summary in the base booking currency")
    converted_totals = PricePreviewTotalsSerializer(
        required=False, 
        allow_null=True, 
        help_text="Optional: Consolidated cost summary converted to requested display currency"
    )


class BookingPreviewSerializer(serializers.Serializer):
    check_in_date = serializers.DateField(help_text="First night of stay")
    check_out_date = serializers.DateField(help_text="Day of departure (non-inclusive for hotel stays)")
    items = BookingItemSerializer(many=True, help_text="List of rooms and quantities selected")

    def validate(self, data):
        check_in = data.get("check_in_date")
        check_out = data.get("check_out_date")
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError("Check-out date must be after check-in date.")
        
        items = data.get("items", [])
        if not items:
            raise serializers.ValidationError("At least one booking item is required.")
        return data

class GuestHouseBookingPreviewSerializer(serializers.Serializer):
    start_date = serializers.DateField(help_text="Arrival date")
    end_date = serializers.DateField(help_text="Departure date")
    items = GuestHouseBookingItemSerializer(many=True, help_text="List of guesthouse rooms and quantities selected")

    def validate(self, data):
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError("End date must be after start date.")
        
        items = data.get("items", [])
        if not items:
            raise serializers.ValidationError("At least one booking item is required.")
        return data

class EventSpaceBookingPreviewSerializer(serializers.Serializer):
    check_in_date = serializers.DateField(help_text="Event start date")
    check_out_date = serializers.DateField(help_text="Event end date")
    items = EventSpaceBookingItemSerializer(many=True, help_text="List of spaces and quantities selected")

    def validate(self, data):
        check_in = data.get("check_in_date")
        check_out = data.get("check_out_date")
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError("Check-out date must be after check-in date.")
        
        items = data.get("items", [])
        if not items:
            raise serializers.ValidationError("At least one booking item is required.")
        return data
