from django.conf import settings
from django.utils.dateparse import parse_date
from django.utils.html import strip_tags
from django.db import transaction
from rest_framework import serializers
from datetime import timedelta
from django.utils.timezone import now
from datetime import datetime
from datetime import date
from rest_framework.exceptions import ValidationError, PermissionDenied
from drf_spectacular.utils import extend_schema_field, inline_serializer, OpenApiTypes
from apps.account.services import ImageCreationService
from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile
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
from apps.core.models import Address, Facility
from apps.listing.services import BookingService, ListingService, EventSpaceAvailabilityService, GuestHouseAvailabilityService

from apps.listing.models import (
    Amenity,
    Booking,BookingRating,
    BookingItem,StayAvailability,GuestHouseInventory,BookingAddon,AddonOffering,
    CarListing,CarAvailability,
    GuestHouseProfile, GuestHouseRoom,
    PropertyListing,
    RoomListing,EventSpaceListing,
    CarRental,CarRentalItem,GuestHouseBookingItem,GuestHouseBooking,
    TermsAndConditions,
    Season, SeasonalRate,
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
    conversion = serializers.SerializerMethodField(help_text="Metadata about currency conversion if requested")

    @extend_schema_field(inline_serializer(
        name='CurrencyConversionMetadata',
        fields={
            'from': serializers.CharField(help_text="Original currency code (e.g., ETB)"),
            'to': serializers.CharField(help_text="Target display currency code (e.g., USD)"),
            'rate': serializers.CharField(help_text="Exchange rate used for calculation (as string)"),
            'total': serializers.CharField(help_text="Total price converted to target currency (fixed 2 decimals)"),
            'calculated_at': serializers.DateTimeField(help_text="ISO timestamp of when this rate was calculated")
        }
    ))
    def get_conversion(self, obj):
        target_currency = self.context.get("display_currency")
        if not target_currency:
            return None
        
        # Determine source price and currency
        def get_val(o, attr, default=None):
            if isinstance(o, dict):
                return o.get(attr, default)
            return getattr(o, attr, default)

        source_price = get_val(obj, "total_price") or get_val(obj, "base_price") or get_val(obj, "price_per_unit")
        
        if source_price is not None:
            source_price = Decimal(str(source_price))
            
        source_currency = get_val(obj, "currency", "ETB")

        if source_price is None:
            return None

        from apps.core.utils import convert_currency
        from django.utils.timezone import now
        try:
            converted_amount, rate = convert_currency(
                source_price, 
                source_currency, 
                target_currency, 
                return_rate=True
            )
            return {
                "from": source_currency,
                "to": target_currency,
                "rate": f"{rate:.8g}",
                "total": f"{converted_amount:.2f}",
                "calculated_at": now().isoformat()
            }
        except Exception:
            return None


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
            price_in_source = Decimal(str(detail['price_per_unit']))
            
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


class SanitizeGuestDetailsMixin:

    def validate_guest_first_name(self, value):
        return strip_tags(value) if value else value

    def validate_guest_last_name(self, value):
        return strip_tags(value) if value else value

    def validate_special_requests(self, value):
        return strip_tags(value) if value else value

    def validate_guest_phone(self, value):
        return strip_tags(value) if value else value


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
            "conversion",
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
        """Ensure the hotel exists, belongs to an approved company, and is owned by the user."""
        try:
            hotel = HotelProfile.objects.select_related('company').get(id=value)
            
            if hotel.company.status != CompanyProfile.StatusChoice.APPROVED:
                raise serializers.ValidationError(
                    "Cannot create rooms for hotels with non-approved company profiles."
                )
            
            user = self.context['request'].user
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            
            if not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
                if hotel.company != company:
                    raise serializers.ValidationError("You do not have permission to manage this hotel.")
                    
            return value
        except HotelProfile.DoesNotExist:
            raise serializers.ValidationError(f"Hotel with id {value} does not exist.")

    @transaction.atomic()
    def create(self, validated_data):
        return ListingService.create_room_listing(validated_data)

    @transaction.atomic()
    def update(self, instance, validated_data):
        kept_image_ids = self.initial_data.getlist("kept_image_ids") if "kept_image_ids" in self.initial_data else None
        if kept_image_ids is None and "kept_image_ids" in self.initial_data:
             kept_image_ids = self.initial_data["kept_image_ids"]
        return ListingService.update_room_listing(instance, validated_data, kept_image_ids)

    def to_representation(self, instance):
        return RoomListingResponseSerializer(instance, context=self.context).to_representation(
            instance
        )


class GuestHouseRoomResponseSerializer(CurrencyConversionMixin, PriceQuoteMixin, serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    available_units = serializers.SerializerMethodField()
    amenities = AmenityResponseSSerializer(many=True)
    
    class Meta:
        model = GuestHouseRoom
        fields = [
            "id",
            "title",
            "images",
            "base_price",
            "currency",
            "amenities",
            "number_of_guests",
            "total_units",
            "available_units",
            "bed_type",
            "room_size_sqm",
            "conversion",
            "price_quote",
        ]
        
    def get_available_units(self, obj):
        availability_map = self.context.get("availability_map")
        if availability_map:
            return availability_map.get(obj.id, 0)
        return obj.total_units

class GuestHouseProfileResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    address = AddressSerializer(allow_null=True)
    amenities = AmenityResponseSSerializer(many=True)
    facility = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    rooms = GuestHouseRoomResponseSerializer(many=True, read_only=True)
    
    class Meta:
        model = GuestHouseProfile
        fields = [
            "id",
            "title",
            "description",
            "images",
            "amenities",
            "address",
            "rating",
            "facility",
            "rating",
            "facility",
            "is_favorite",
            "rooms",
            "phone",
            "website",
            "license",
            "logo",
        ]

    def get_is_favorite(self, obj):
        fav_ids = self.context.get("favorite_object_ids")
        if not fav_ids:
            return False
        return str(obj.id) in fav_ids
    
    def get_facility(self, obj):
        try:
            facilities = obj.facility.all()
            return [{"name": f.name} for f in facilities]
        except:
            return []


class GuestHouseRoomSerializer(serializers.ModelSerializer):
    images = serializers.ListField(child=serializers.ImageField(), required=False)
    amenities = JsonSerializerField(required=False)
    guest_house_id = serializers.UUIDField()

    class Meta:
        model = GuestHouseRoom
        fields = [
            "id",
            "guest_house_id",
            "title",
            "images",
            "base_price",
            "currency",
            "amenities",
            "number_of_guests",
            "total_units",
            "bed_type",
            "room_size_sqm",
        ]
        
    def validate_currency(self, value):
        if not value:
            return value
        value = value.upper()
        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
        return value
        
    def validate_guest_house_id(self, value):
        if not GuestHouseProfile.objects.filter(id=value).exists():
             raise serializers.ValidationError(f"Guest House with id {value} does not exist.")
        return value

    @transaction.atomic
    def create(self, validated_data):
         images = validated_data.pop("images", [])
         amenities = validated_data.pop("amenities", [])
         
         guest_house_id = validated_data.pop("guest_house_id")
         validated_data["guest_house"] = GuestHouseProfile.objects.get(id=guest_house_id)
         
         instance = GuestHouseRoom.objects.create(**validated_data)
         
         if isinstance(amenities, list):
             instance.amenities.set(amenities)
             
         if images:
            ImageCreationService.create_images(instance, images)
            
         return instance

    @transaction.atomic()
    def update(self, instance, validated_data):
        kept_image_ids = self.initial_data.getlist("kept_image_ids") if "kept_image_ids" in self.initial_data else None
        if kept_image_ids is None and "kept_image_ids" in self.initial_data:
             kept_image_ids = self.initial_data["kept_image_ids"]
        return ListingService.update_guest_house_room(instance, validated_data, kept_image_ids)

class GuestHouseProfileSerializer(serializers.ModelSerializer):
    address = FlexibleAddressField()
    images = serializers.ListField(child=serializers.ImageField())
    amenities = JsonSerializerField()
    facility = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=Facility.objects.all(),
        required=False
    )
    logo = serializers.ImageField(required=False)

    class Meta:
        model = GuestHouseProfile
        fields = [
            "id",
            "title",
            "images",
            "individual_owner",
            "company",
            "description",
            "amenities",
            "address",
            "facility",
            "phone",
            "website",
            "license",
            "logo",
        ]

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, data):
        user = self.context['request'].user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        company_id = data.get("company")
        individual_id = data.get("individual_owner")

        if company_id and individual_id:
            raise serializers.ValidationError("Only one owner type allowed.")
        
        # If both are missing, we'll auto-assign in create based on context
        # But if they ARE provided, they must match the user
        if not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            if company_id:
                company_obj = company_id if isinstance(company_id, CompanyProfile) else get_object_or_404(CompanyProfile, id=company_id)
                if company_obj != company:
                    raise serializers.ValidationError({"company": "You do not have permission to manage this company."})
                if company_obj.status != CompanyProfile.StatusChoice.APPROVED:
                    raise serializers.ValidationError({"company": "Company profile is not approved."})
            
            if individual_id:
                indiv_obj = individual_id if isinstance(individual_id, IndividualOwnerProfile) else get_object_or_404(IndividualOwnerProfile, id=individual_id)
                if indiv_obj != individual_owner:
                    raise serializers.ValidationError({"individual_owner": "You do not have permission to manage this profile."})
        
        return data



    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        # Auto-assign if missing
        if not validated_data.get('company') and not validated_data.get('individual_owner'):
            if company:
                validated_data['company'] = company
            elif individual_owner:
                validated_data['individual_owner'] = individual_owner
        
        if 'facility' in validated_data:
            validated_data['facilities'] = validated_data.pop('facility')
            
            
        return ListingService.create_guest_house_listing(validated_data)

    @transaction.atomic()
    def update(self, instance, validated_data):
        kept_image_ids = self.initial_data.getlist("kept_image_ids") if "kept_image_ids" in self.initial_data else None
        if kept_image_ids is None and "kept_image_ids" in self.initial_data:
             kept_image_ids = self.initial_data["kept_image_ids"]
        return ListingService.update_guest_house_profile(instance, validated_data, kept_image_ids)

    def to_representation(self, instance):
        return GuestHouseProfileResponseSerializer(
            instance, context=self.context
        ).to_representation(instance)
class GuestHouseBookingItemSerializer(serializers.ModelSerializer):
    stay_total = serializers.SerializerMethodField()
    nightly_rate = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = GuestHouseBookingItem
        fields = [
            "id",
            "room",
            "units_booked",
            "nightly_rate",
            "stay_total",
            "subtotal",
        ]

    def get_nightly_rate(self, obj):
        return f"{obj.price_per_unit:.2f}"

    def get_stay_total(self, obj):
        return f"{obj.subtotal():.2f}"

    def get_subtotal(self, obj):
        return self.get_stay_total(obj)
class GuestHouseBookingSerializer(SanitizeGuestDetailsMixin, CurrencyConversionMixin, serializers.ModelSerializer):
    items = GuestHouseBookingItemSerializer(many=True, write_only=True)
    
    terms_accepted = serializers.BooleanField(required=False, write_only=True)
    terms_version = serializers.CharField(required=False, write_only=True)
    
    guest_first_name = serializers.CharField(max_length=100, required=False, help_text="First name of the guest (Required if not logged in)")
    guest_last_name = serializers.CharField(max_length=100, required=False, help_text="Last name of the guest (Required if not logged in)")
    guest_email = serializers.EmailField(required=False, help_text="Contact email for confirmations (Required if not logged in)")
    guest_phone = serializers.CharField(max_length=20, required=False, help_text="Contact phone number (Required if not logged in)")
    special_requests = serializers.CharField(required=False, allow_blank=True, help_text="Special requests for the guesthouse stay")
    
    payment_currency = serializers.ChoiceField(
        choices=["USD", "ETB"],
        required=False,
        write_only=True,
        help_text="Preferred currency for payment (USD or ETB). Defaults to ETB if not specified."
    )
    is_walk_in = serializers.BooleanField(
        required=False, 
        write_only=True, 
        default=False, 
        help_text="Set to true if this is a walk-in booking by staff."
    )

    class Meta:
        model = GuestHouseBooking
        fields = [
            "id",
            "renter",
            "booking_reference",
            "start_date",
            "end_date",
            "total_price",
            "total_item_cost",
            "currency",
            "status",
            "items",
            "conversion",
            "terms_accepted",
            "terms_version",
            "terms_accepted_at",
            "terms_content_snapshot",
            "terms_url",
            "is_legacy",
            "stay_total",
            "guest_first_name", "guest_last_name", "guest_email", "guest_phone", "special_requests", "payment_currency",
        ]

        read_only_fields = ["id", "status", "renter", "total_price", "created_at", "updated_at", "booking_reference", "currency"]

    total_price = serializers.SerializerMethodField(help_text="Grand total in base currency")
    total_item_cost = serializers.SerializerMethodField(help_text="Total cost of all guesthouse units")
    stay_total = serializers.SerializerMethodField(help_text="Alias for total_item_cost")
    terms_url = serializers.SerializerMethodField(help_text="Link to view the latest terms for the guesthouse")

    @extend_schema_field(OpenApiTypes.STR)
    def get_stay_total(self, obj):
        return self.get_total_item_cost(obj)

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_price(self, obj):
        return f"{obj.total_price:.2f}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_terms_url(self, obj):
        try:
            gh_id = obj.items.first().room.guest_house_id
            return f"/api/v1/listing/terms/guesthouse/{gh_id}/"
        except Exception:
            return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_item_cost(self, obj):
        total = sum(item.subtotal() for item in obj.items.all())
        return f"{total:.2f}"

    booking_reference = serializers.CharField(read_only=True, help_text="Unique human-readable reference code (e.g., G-X7Y2Z9)")
    terms_accepted_at = serializers.DateTimeField(read_only=True, help_text="Timestamp when the T&C were accepted")
    terms_content_snapshot = serializers.CharField(read_only=True, help_text="Full text of the T&C at the time of booking")
    is_legacy = serializers.BooleanField(read_only=True, help_text="Indicates if this booking was created before the T&C/Guest details update")
        

        
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

        user = self.context['request'].user
        guest_email = data.get('guest_email')
        if (not user or not user.is_authenticated) and not guest_email:
             raise serializers.ValidationError("Either log in or provide guest email.")

        room_infos = [
            {"guesthouse_room": item["room"], "quantity": item["units_booked"]}
            for item in items
        ]

        # Centralized availability validation
        GuestHouseAvailabilityService.validate_availability(
            room_infos, start, end
        )
        
        is_privileged = False
        if user and user.is_authenticated:
            is_walk_in = self.context.get("is_walk_in", False)
            
            if items:
                 from apps.listing.utils import is_user_staff_of_listing
                 first_room = items[0]["room"]
                 listing_obj = first_room.guest_house
                 
                 if is_walk_in:
                     if not is_user_staff_of_listing(user, listing_obj):
                         raise PermissionDenied("You do not have permission to perform a walk-in booking for this listing.")
                     is_privileged = True
        
        if not is_privileged:
            if not data.get("terms_accepted"):
                raise serializers.ValidationError({"terms_accepted": "You must accept the terms and conditions."})
            
            terms_version = data.get("terms_version")
            if not terms_version:
                 raise serializers.ValidationError({"terms_version": "Terms version is required."})

            if terms_version and items:
                from django.contrib.contenttypes.models import ContentType
                first_room = items[0]["room"]
                first_guesthouse_profile = first_room.guest_house
                
                ct = ContentType.objects.get_for_model(first_guesthouse_profile)
                tc_exists = TermsAndConditions.objects.filter(
                    content_type=ct,
                    object_id=first_guesthouse_profile.id,
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
        user = self.context["request"].user
        if not user.is_authenticated:
            user = None
            
        is_walk_in = self.context.get("is_walk_in", False)
        return GuestHouseBookingService.create_booking(
            validated_data, 
            user=user,
            is_walk_in=is_walk_in
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        new_status = validated_data.get("status")
        old_status = instance.status

        # CANCELLED → add back availability
        if old_status == GuestHouseBooking.RentStatus.CONFIRMED and new_status == GuestHouseBooking.RentStatus.CANCELLED:

            room_infos = [{
                "guesthouse_room": item.room,
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
                "guesthouse_room": item.room,
                "quantity": item.units_booked
            } for item in instance.items.all()]

            GuestHouseAvailabilityService.validate_availability(
                room_infos,
                instance.start_date,
                instance.end_date
            )

        return super().update(instance, validated_data)


class GuestHouseInventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestHouseInventory
        fields = ["id", "date", "available_rooms", "price"]
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
            "conversion",
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
    stay_total = serializers.SerializerMethodField()
    nightly_rate = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CarRentalItem
        fields = [
            'id', 'car_listing', 'car_listing_details', 'units_rent', 
            'nightly_rate', 'stay_total', 'subtotal', 'created_at'
        ]
        read_only_fields = ['id', 'stay_total', 'subtotal', 'created_at']

    def get_nightly_rate(self, obj):
        return f"{obj.price_per_unit:.2f}"

    def get_stay_total(self, obj):
        total = obj.units_rent * obj.price_per_unit
        return f"{total:.2f}"

    def get_subtotal(self, obj):
        return self.get_stay_total(obj)
    
    def get_car_listing_details(self, obj):
        return {
            'id': obj.car_listing.id,
            'title': obj.car_listing.title,
            'brand': obj.car_listing.brand,
            'model': obj.car_listing.model,
            'year': obj.car_listing.year,
            'base_price': obj.car_listing.base_price
        }


class CarRentalSerializer(SanitizeGuestDetailsMixin, CurrencyConversionMixin, serializers.ModelSerializer):
    rental_items = CarRentalItemSerializer(many=True, write_only=True)
    items_details = CarRentalItemSerializer(
        source='rental_items', many=True, read_only=True
    )
    renter_name = serializers.CharField(
        source='renter.get_full_name', read_only=True
    )
    
    terms_accepted = serializers.BooleanField(required=True, write_only=True)
    terms_version = serializers.CharField(required=True, write_only=True)
    
    guest_first_name = serializers.CharField(max_length=100, required=False, help_text="First name of the renter (Required if not logged in)")
    guest_last_name = serializers.CharField(max_length=100, required=False, help_text="Last name of the renter (Required if not logged in)")
    guest_email = serializers.EmailField(required=False, help_text="Contact email for confirmations (Required if not logged in)")
    guest_phone = serializers.CharField(max_length=20, required=False, help_text="Contact phone number (Required if not logged in)")
    special_requests = serializers.CharField(required=False, allow_blank=True, help_text="Special requests for the rental")
    
    payment_currency = serializers.ChoiceField(
        choices=["USD", "ETB"],
        required=False,
        write_only=True,
        help_text="Preferred currency for payment (USD or ETB). Defaults to ETB if not specified."
    )


    class Meta:
        model = CarRental
        fields = [
            'id', 'renter', 'renter_name', 'booking_reference', 'start_date', 'end_date', 
            'total_price', 'total_rental_cost', 'currency', 'status', 'rental_items', 'items_details',
            'created_at', 'updated_at', 'conversion',
            'terms_accepted', 'terms_version', 'terms_accepted_at', 'terms_content_snapshot', 'terms_url',
            'is_legacy',
            'stay_total',
            'guest_first_name', 'guest_last_name', 'guest_email', 'guest_phone', 'special_requests', 'payment_currency',
        ]

        read_only_fields = ['id', 'status', 'created_at', 'updated_at', 'booking_reference']
    
    total_price = serializers.SerializerMethodField(help_text="Grand total in base currency")
    total_rental_cost = serializers.SerializerMethodField(help_text="Total cost of all rental units")
    stay_total = serializers.SerializerMethodField(help_text="Alias for total_rental_cost")
    terms_url = serializers.SerializerMethodField(help_text="Link to view the latest terms for the car rental company")

    @extend_schema_field(OpenApiTypes.STR)
    def get_stay_total(self, obj):
        return self.get_total_rental_cost(obj)

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_price(self, obj):
        return f"{obj.total_price:.2f}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_terms_url(self, obj):
        try:
            company = obj.rental_items.first().car_listing.company
            if company:
                return f"/api/v1/listing/terms/company/{company.id}/"
            return None
        except Exception:
            return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_rental_cost(self, obj):
        total = sum(item.units_rent * item.price_per_unit for item in obj.rental_items.all())
        return f"{total:.2f}"
    
    booking_reference = serializers.CharField(read_only=True, help_text="Unique human-readable reference code (e.g., C-X7Y2Z9)")
    terms_accepted_at = serializers.DateTimeField(read_only=True, help_text="Timestamp when the T&C were accepted")
    terms_content_snapshot = serializers.CharField(read_only=True, help_text="Full text of the T&C at the time of booking")
    is_legacy = serializers.BooleanField(read_only=True, help_text="Indicates if this booking was created before the T&C/Guest details update")
    
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

        user = self.context['request'].user
        guest_email = data.get('guest_email')
        if (not user or not user.is_authenticated) and not guest_email:
             raise serializers.ValidationError("Either log in or provide guest email.")

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
        user = self.context["request"].user
        if not user.is_authenticated:
            user = None
            
        return CarRentalService.create_booking(
            validated_data, 
            user=user
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
            "conversion",
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

    @transaction.atomic()
    def update(self, instance, validated_data):
        kept_image_ids = self.initial_data.getlist("kept_image_ids") if "kept_image_ids" in self.initial_data else None
        if kept_image_ids is None and "kept_image_ids" in self.initial_data:
             kept_image_ids = self.initial_data["kept_image_ids"]
        return ListingService.update_property_listing(instance, validated_data, kept_image_ids)

    def to_representation(self, instance):
        return PropertyListingResponseSerializer(
            instance, context=self.context
        ).to_representation(instance)


class AddonOfferingSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
    class Meta:
        model = AddonOffering
        fields = [
            'id', 'hotel', 'name', 'description', 'category', 
            'price_per_unit', 'currency', 'pricing_type',
            'is_active', 'max_quantity_per_booking',
            'requires_inventory', 'daily_capacity',
            'icon', 'display_order',
            'created_at', 'updated_at', 'conversion'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        requires_inventory = data.get('requires_inventory', False)
        daily_capacity = data.get('daily_capacity')
        
        if requires_inventory and not daily_capacity:
            raise serializers.ValidationError({
                'daily_capacity': 'Daily capacity is required when inventory tracking is enabled'
            })
        
        price_per_unit = data.get('price_per_unit')
        if price_per_unit and price_per_unit <= 0:
            raise serializers.ValidationError({
                'price_per_unit': 'Price must be greater than zero'
            })
        
        return data


class AddonOfferingListSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    
    class Meta:
        model = AddonOffering
        fields = [
            'id', 'hotel', 'hotel_name', 'name', 'description', 'category',
            'price_per_unit', 'currency', 'pricing_type',
            'max_quantity_per_booking', 'icon', 'conversion'
        ]
        read_only_fields = fields


class BookingAddonInputSerializer(serializers.Serializer):
    offering_id = serializers.UUIDField(
        help_text="UUID of the addon offering to book"
    )
    quantity = serializers.IntegerField(
        min_value=1,
        default=1,
        help_text="Number of units to book"
    )
    
    def validate(self, data):
        offering_id = data.get('offering_id')
        quantity = data.get('quantity', 1)
        
        try:
            offering = AddonOffering.objects.get(id=offering_id)
        except AddonOffering.DoesNotExist:
            raise serializers.ValidationError({
                'offering_id': f'Addon offering {offering_id} not found'
            })
        
        if not offering.is_active:
            raise serializers.ValidationError({
                'offering_id': f'{offering.name} is currently unavailable'
            })
        
        if offering.max_quantity_per_booking and quantity > offering.max_quantity_per_booking:
            raise serializers.ValidationError({
                'quantity': f'{offering.name}: Maximum {offering.max_quantity_per_booking} units allowed per booking'
            })
        
        data['_offering'] = offering
        
        return data


class BookingAddonSerializer(serializers.ModelSerializer):
    subtotal = serializers.ReadOnlyField(help_text="Quantity x Price per unit (as string)")
    offering_name = serializers.CharField(source='offering.name', read_only=True, allow_null=True)
    offering_id = serializers.UUIDField(source='offering.id', read_only=True, allow_null=True)
    
    class Meta:
        model = BookingAddon
        fields = [
            'id', 'booking_item', 'offering_id', 'offering_name',
            'name', 'description', 'category', 'quantity', 
            'price_per_unit', 'currency', 'subtotal'
        ]
        read_only_fields = ['id', 'subtotal']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['price_per_unit'] = f"{instance.price_per_unit:.2f}"
        data['subtotal'] = f"{instance.subtotal():.2f}"
        return data


class BookingItemResponseSerializer(serializers.ModelSerializer):
    room = serializers.SerializerMethodField(help_text="Nested room identification")
    stay_total = serializers.SerializerMethodField(help_text="Total cost for this item for the entire stay duration (Units x Rate x Nights)")
    nightly_rate = serializers.SerializerMethodField(help_text="The price per unit per night at the time of booking")
    nights = serializers.SerializerMethodField(help_text="Number of nights for this stay")
    snapshot = serializers.JSONField(read_only=True, help_text="Immutable JSON snapshot of room details at booking time")
    addons = BookingAddonSerializer(many=True, read_only=True, help_text="Additional services selected for this room.")

    class Meta:
        model = BookingItem
        fields = [
            "id",
            "room",
            "units_booked",
            "nights",
            "nightly_rate",
            "stay_total",
            "snapshot",
            "addons",
        ]

    @extend_schema_field(inline_serializer(
        name='BookingItemRoomInfo',
        fields={
            'id': serializers.UUIDField(),
            'title': serializers.CharField(),
            'description': serializers.CharField()
        }
    ))
    def get_room(self, obj):
        return {
            "id": str(obj.room.id),
            "title": obj.room.title,
            "description": obj.room.description
        }

    @extend_schema_field(OpenApiTypes.INT)
    def get_nights(self, obj):
        return (obj.booking.check_out_date - obj.booking.check_in_date).days

    @extend_schema_field(OpenApiTypes.STR)
    def get_nightly_rate(self, obj):
        return f"{obj.price_per_unit:.2f}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_stay_total(self, obj):
        nights = self.get_nights(obj)
        sub = obj.subtotal(nights=nights)
        return f"{sub:.2f}"


class BookingResponseSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
    items = BookingItemResponseSerializer(many=True, read_only=True)
    snapshot = serializers.JSONField(read_only=True)

    is_resumable = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "user",
            "booking_reference",
            "check_in_date",
            "check_out_date",
            "total_price",
            "total_room_cost",
            "total_addon_cost",
            "currency",
            "status",
            "items",
            "snapshot",
            "conversion",
            "is_resumable",
            "terms_accepted",
            "terms_version",
            "terms_accepted_at",
            "terms_content_snapshot",
            "terms_url",
            "is_legacy",
            "stay_total",
            "guest_first_name", "guest_last_name", "guest_email", "guest_phone", "special_requests",
        ]

    total_price = serializers.SerializerMethodField(help_text="Grand total (Rooms + Addons + Fees) in base currency")
    total_room_cost = serializers.SerializerMethodField(help_text="Total cost of all rooms in the booking")
    stay_total = serializers.SerializerMethodField(help_text="Alias for total_room_cost for consistency")
    total_addon_cost = serializers.SerializerMethodField(help_text="Total cost of all selected addons")
    terms_url = serializers.SerializerMethodField(help_text="Link to view the latest terms for this hotel")

    @extend_schema_field(OpenApiTypes.STR)
    def get_stay_total(self, obj):
        return self.get_total_room_cost(obj)

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_price(self, obj):
        return f"{obj.total_price:.2f}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_terms_url(self, obj):
        try:
            hotel_id = obj.items.first().room.hotel_id
            return f"/api/v1/listing/terms/hotel/{hotel_id}/"
        except Exception:
            return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_room_cost(self, obj):
        nights = (obj.check_out_date - obj.check_in_date).days
        total = sum(item.subtotal(nights=nights) for item in obj.items.all())
        return f"{total:.2f}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_addon_cost(self, obj):
        from apps.listing.models import BookingAddon
        addons = BookingAddon.objects.filter(booking_item__booking=obj)
        total = sum(addon.subtotal() for addon in addons)
        return f"{total:.2f}"

    booking_reference = serializers.CharField(read_only=True, help_text="Unique human-readable reference code (e.g., H-X7Y2Z9)")
    terms_accepted_at = serializers.DateTimeField(read_only=True, help_text="Timestamp when the T&C were accepted")
    terms_content_snapshot = serializers.CharField(read_only=True, help_text="Full text of the T&C at the time of booking")
    is_legacy = serializers.BooleanField(read_only=True, help_text="Indicates if this booking was created before the T&C/Guest details update")

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


class BookingLookupSerializer(serializers.Serializer):
    reference = serializers.CharField(
        required=True,
        help_text="The unique booking reference (e.g., H-X7Y2Z9)"
    )
    email = serializers.EmailField(
        required=True,
        help_text="The guest email associated with the booking"
    )

class BookingItemSerializer(serializers.ModelSerializer):
    price_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    units_booked = serializers.IntegerField(min_value=1)
    addons = BookingAddonInputSerializer(
        many=True, 
        required=False,
        help_text="List of addon offerings to include with this room booking"
    )

    class Meta:
        model = BookingItem
        fields = ["room", "units_booked", "price_per_unit", "addons"]
    
    def validate_addons(self, addons_data):
        if not addons_data:
            return addons_data
        
        return addons_data


class BookingSerializer(SanitizeGuestDetailsMixin, serializers.ModelSerializer):
    items = BookingItemSerializer(many=True, help_text="List of rooms and quantities to book.")
    
    # T&C fields (write_only, required for booking creation)
    terms_accepted = serializers.BooleanField(
        required=False, 
        write_only=True,
        help_text="Must be set to true to indicate agreement with the Terms and Conditions."
    )
    terms_version = serializers.CharField(
        required=False, 
        write_only=True,
        help_text="The version of the T&C document that was accepted (e.g., '1.0')."
    )

    guest_first_name = serializers.CharField(max_length=100, required=False, help_text="First name of the person staying (Required if not logged in)")
    guest_last_name = serializers.CharField(max_length=100, required=False, help_text="Last name of the person staying (Required if not logged in)")
    guest_email = serializers.EmailField(required=False, help_text="Contact email for confirmations (Required if not logged in)")
    guest_phone = serializers.CharField(max_length=20, required=False, help_text="Contact phone number (Required if not logged in)")
    guest_phone = serializers.CharField(max_length=20, required=False, help_text="Contact phone number (Required if not logged in)")
    special_requests = serializers.CharField(required=False, allow_blank=True, help_text="Special requests (e.g., late check-in, room preferences)")

    payment_currency = serializers.ChoiceField(
        choices=["USD", "ETB"],
        required=False,
        write_only=True,
        help_text="Preferred currency for payment (USD or ETB). Defaults to ETB if not specified."
    )


    class Meta:
        model = Booking
        fields = ["items", "check_in_date", "check_out_date", "currency", "status", 
                   "terms_accepted", "terms_version",
                  "guest_first_name", "guest_last_name", "guest_email", "guest_phone", "special_requests", "payment_currency"]
        read_only_fields = ["status", "currency"]
        

        
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

        user = self.context['request'].user
        guest_email = data.get('guest_email')
        if (not user or not user.is_authenticated) and not guest_email:
             raise serializers.ValidationError("Either log in or provide guest email.")
        
        is_privileged = False
        if user and user.is_authenticated:
            is_walk_in = self.context.get("is_walk_in", False)
            
            if items:
                 from apps.listing.utils import is_user_staff_of_listing
                 first_room = items[0]["room"]
                 listing_obj = first_room.hotel
                 
                 if is_walk_in:
                     if not is_user_staff_of_listing(user, listing_obj):
                         raise PermissionDenied("You do not have permission to perform a walk-in booking for this listing.")
                     is_privileged = True

        if not is_privileged:
            terms_accepted = data.get("terms_accepted")
            if not terms_accepted:
                 raise serializers.ValidationError({"terms_accepted": "You must accept the terms and conditions."})
            
            terms_version = data.get("terms_version")
            if not terms_version:
                 raise serializers.ValidationError({"terms_version": "Terms version is required."})

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
            if not user.is_authenticated:
                user = None
        is_front_desk = False
        
        if user and user.is_authenticated and user.role and user.role.code == RoleCode.FRONT_DESK.value:
            is_front_desk = True
        if is_front_desk:
            validated_data["status"] = Booking.BookingStatus.WALK_IN
            
        is_walk_in = self.context.get("is_walk_in", False)
        return BookingService.create_booking(validated_data, user=user, is_walk_in=is_walk_in)

    def to_representation(self, instance):
        return BookingResponseSerializer(instance, context=self.context).to_representation(
            instance
        )
class PartialCancelSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    units_to_cancel = serializers.IntegerField(min_value=1)


class GuestCancellationSerializer(serializers.Serializer):
    guest_email = serializers.EmailField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class SearchRoomSerializer(CurrencyConversionMixin, serializers.Serializer):
    id = serializers.UUIDField(help_text="Unique identifier for the room type")
    title = serializers.CharField(help_text="Display title of the room (e.g., Deluxe Suite)")
    description = serializers.CharField(help_text="Detailed description of room features")
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Starting nightly rate in base currency")
    currency = serializers.CharField(required=False, default="ETB", help_text="ISO currency code")
    number_of_guests = serializers.IntegerField(help_text="Maximum occupancy allowed")
    bed_type = serializers.CharField(help_text="Bed configuration (e.g., King, Twin)")
    room_size_sqm = serializers.IntegerField(help_text="Room area in square meters")
    available_units = serializers.IntegerField(help_text="Total units remained for the selected dates")
    
    display_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, help_text="The price to show the user (takes into account seasonal discounts)")
    preview_min_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, help_text="The lowest nightly rate found in the date range")
    preview_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, help_text="The grand total for the entire duration of the stay")
    preview_has_discount = serializers.BooleanField(required=False, help_text="True if any night in the range has a seasonal discount")
    nights = serializers.IntegerField(required=False, help_text="Number of nights for the stay duration")


class SearchResultSerializer(CurrencyConversionMixin, serializers.Serializer):
    hotel_id = serializers.UUIDField(help_text="Unique ID of the hotel")
    hotel_name = serializers.CharField(help_text="Name of the hotel / property")
    city = serializers.CharField(help_text="City location")
    stars = serializers.IntegerField(allow_null=True, help_text="Star rating (1-5)")
    images = ListingImageSerializer(many=True, help_text="Gallery of hotel images")
    facilities = FacilityResponseSerializer(many=True, help_text="Hotel facilities (Pool, Spa, etc.)")
    featured = serializers.BooleanField(help_text="True if this is a sponsored or featured property")
    is_favorite = serializers.SerializerMethodField(help_text="True if the current user has favorited this hotel")
    rooms = SearchRoomSerializer(many=True, help_text="Available room types in this hotel for the period")

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
            "conversion",
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

    def validate_company_id(self, value):
        user = self.context['request'].user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)

        if not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            if str(value) != str(getattr(company, 'id', '')):
                raise serializers.ValidationError("You do not have permission to manage this company.")
                
        return value

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

    @transaction.atomic()
    def update(self, instance, validated_data):
        kept_image_ids = self.initial_data.getlist("kept_image_ids") if "kept_image_ids" in self.initial_data else None
        if kept_image_ids is None and "kept_image_ids" in self.initial_data:
             kept_image_ids = self.initial_data["kept_image_ids"]
        return ListingService.update_event_space_listing(instance, validated_data, kept_image_ids)

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
    stay_total = serializers.SerializerMethodField()
    nightly_rate = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = EventSpaceBookingItem
        fields = [
            "id",
            "event_space_id",
            "event_space_title",
            "event_space_description",
            "units_booked",
            "nightly_rate",
            "stay_total",
            "subtotal",
        ]

    def get_nightly_rate(self, obj):
        return f"{obj.price_per_unit:.2f}"

    def get_stay_total(self, obj):
        return f"{obj.subtotal():.2f}"

    def get_subtotal(self, obj):
        return self.get_stay_total(obj)


class EventSpaceBookingResponseSerializer(CurrencyConversionMixin, serializers.ModelSerializer):
    """Serializer for reading/outputting a complete Event Space Booking."""
    # Related_name is simply 'items' on EventSpaceBooking
    items = EventSpaceBookingItemResponseSerializer(many=True, read_only=True) 

    class Meta:
        model = EventSpaceBooking
        fields = [
            "id",
            "user",
            "booking_reference",
            "check_in_date",
            "check_out_date",
            "total_price",
            "total_item_cost",
            "status",
            "items",
            "event_type",
            "conversion",
            "terms_accepted",
            "terms_version",
            "terms_accepted_at",
            "terms_content_snapshot",
            "terms_url",
            "is_legacy",
            "stay_total",
            "guest_first_name", "guest_last_name", "guest_email", "guest_phone", "special_requests",
        ]

    total_price = serializers.SerializerMethodField(help_text="Grand total in base currency")
    total_item_cost = serializers.SerializerMethodField(help_text="Total cost of all event space units")
    stay_total = serializers.SerializerMethodField(help_text="Alias for total_item_cost")
    terms_url = serializers.SerializerMethodField(help_text="Link to view the latest terms for the hotel")

    @extend_schema_field(OpenApiTypes.STR)
    def get_stay_total(self, obj):
        return self.get_total_item_cost(obj)

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_price(self, obj):
        return f"{obj.total_price:.2f}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_terms_url(self, obj):
        try:
            hotel_id = obj.items.first().event_space.hotel_id
            return f"/api/v1/listing/terms/hotel/{hotel_id}/"
        except Exception:
            return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_item_cost(self, obj):
        total = sum(item.units_booked * item.price_per_unit for item in obj.items.all())
        return f"{total:.2f}"

    booking_reference = serializers.CharField(read_only=True, help_text="Unique human-readable reference code (e.g., E-X7Y2Z9)")
    terms_accepted_at = serializers.DateTimeField(read_only=True, help_text="Timestamp when the T&C were accepted")
    terms_content_snapshot = serializers.CharField(read_only=True, help_text="Full text of the T&C at the time of booking")
    is_legacy = serializers.BooleanField(read_only=True, help_text="Indicates if this booking was created before the T&C/Guest details update")

# --- Write (Create) Serializers ---

class EventSpaceBookingItemSerializer(serializers.ModelSerializer):
    """Serializer for taking input on booking items."""
    price_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    units_booked = serializers.IntegerField(min_value=1)
    
    class Meta:
        model = EventSpaceBookingItem
        fields = ["event_space", "units_booked", "price_per_unit"] 


class EventSpaceBookingSerializer(SanitizeGuestDetailsMixin, serializers.ModelSerializer):
    """Main serializer for creating a new Event Space Booking."""
    items = EventSpaceBookingItemSerializer(many=True) 
    
    terms_accepted = serializers.BooleanField(required=True, write_only=True)
    terms_version = serializers.CharField(required=True, write_only=True)

    guest_first_name = serializers.CharField(max_length=100, required=False, help_text="First name of the guest (Required if not logged in)")
    guest_last_name = serializers.CharField(max_length=100, required=False, help_text="Last name of the guest (Required if not logged in)")
    guest_email = serializers.EmailField(required=False, help_text="Contact email for confirmations (Required if not logged in)")
    guest_phone = serializers.CharField(max_length=20, required=False, help_text="Contact phone number (Required if not logged in)")
    guest_phone = serializers.CharField(max_length=20, required=False, help_text="Contact phone number (Required if not logged in)")
    special_requests = serializers.CharField(required=False, allow_blank=True, help_text="Special requests for the event")

    payment_currency = serializers.ChoiceField(
        choices=["USD", "ETB"],
        required=False,
        write_only=True,
        help_text="Preferred currency for payment (USD or ETB). Defaults to ETB if not specified."
    )


    class Meta:
        model = EventSpaceBooking # Mapped to the dedicated model
        fields = ["items", "check_in_date", "check_out_date", "currency", "event_type",
                  "terms_accepted", "terms_version",
                  "guest_first_name", "guest_last_name", "guest_email", "guest_phone", "special_requests", "payment_currency"]
        read_only_fields = ["status", "currency"]

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

        user = self.context['request'].user
        guest_email = data.get('guest_email')
        if (not user or not user.is_authenticated) and not guest_email:
             raise serializers.ValidationError("Either log in or provide guest email.")
        
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

        is_privileged = False
        if user and user.is_authenticated:
            is_walk_in = self.context.get("is_walk_in", False)
            
            if items:
                 from apps.listing.utils import is_user_staff_of_listing
                 first_space = items[0]["event_space"]
                 hotel = first_space.hotel
                 
                 if is_walk_in:
                     if not is_user_staff_of_listing(user, hotel):
                         raise PermissionDenied("You do not have permission to perform a walk-in booking for this listing.")
                     is_privileged = True
        
        return data

    def create(self, validated_data):
        # Determine the user and status logic (copied from your original)
        user = validated_data.pop("user", None)
        request = self.context.get("request")
        if not user and request:
            user = request.user
            if not user.is_authenticated:
                user = None
            
        is_front_desk = False
        if user and user.is_authenticated and hasattr(user, 'role') and user.role and user.role.code == RoleCode.FRONT_DESK.value:
            is_front_desk = True
        
        if is_front_desk:
            validated_data["status"] = EventSpaceBooking.BookingStatus.WALK_IN 
            
        is_walk_in = self.context.get("is_walk_in", False)
        return EventSpaceBookingService.create_booking(validated_data, user=user, is_walk_in=is_walk_in)

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
    nights = serializers.IntegerField(help_text="Total number of nights for the stay")
    items = PricePreviewItemSerializer(many=True, help_text="Breakdown of individual items in the selection")
    totals = PricePreviewTotalsSerializer(help_text="Consolidated cost summary in the base booking currency")
    conversion = serializers.JSONField(
        required=False, 
        allow_null=True, 
        help_text="Metadata and converted totals in the requested display currency"
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

class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = [
            'id', 'name', 'start_date', 'end_date', 'recurring', 
            'active', 'notes', 'company', 'individual_owner'
        ]
        read_only_fields = ['company', 'individual_owner']

    def validate(self, attrs):
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        
        if self.instance:
            start_date = start_date or self.instance.start_date
            end_date = end_date or self.instance.end_date
            
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})
            
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
        
        if company:
            validated_data['company'] = company
        elif individual_owner:
            validated_data['individual_owner'] = individual_owner
        elif not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            raise serializers.ValidationError("User must be an owner to create a season.")
            
        return super().create(validated_data)


class SeasonalRateSerializer(serializers.ModelSerializer):
    season_name = serializers.CharField(source='season.name', read_only=True)
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = SeasonalRate
        fields = [
            'id', 'season', 'season_name', 'hotel', 'company', 'room', 
            'individual_owner', 'price_override', 'multiplier', 'priority', 'active', 
            'days_of_week', 'min_stay', 'target_name'
        ]
        read_only_fields = ['company', 'hotel', 'individual_owner'] 

    def get_target_name(self, obj):
        if obj.room:
            return f"Room: {obj.room.title}"
        if obj.hotel:
            return f"Hotel: {obj.hotel.company.name}" # HotelProfile doesn't have a name directly usually, accessing company name or specific hotel field
        if obj.company:
             return "Entire Company"
        return "Global"

    def validate(self, attrs):
        user = self.context['request'].user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        multiplier = attrs.get('multiplier')
        price_override = attrs.get('price_override')
        if not multiplier and not price_override:
            if not self.instance or (not self.instance.multiplier and not self.instance.price_override):
                 raise serializers.ValidationError("Either a Multiplier or a Price Override must be set.")

        season = attrs.get('season')
        if season:
            is_global = season.company is None and season.individual_owner is None
            is_owner = (company and season.company == company) or \
                       (individual_owner and season.individual_owner == individual_owner)
            
            if not user.is_superuser and not is_global and not is_owner:
                raise serializers.ValidationError({"season": "You do not have permission to use this season."})

        room = attrs.get('room')
        hotel = attrs.get('hotel')

        if room:
            if hasattr(room, 'hotel') and room.hotel:
                if not user.is_superuser and room.hotel.company != company:
                    raise serializers.ValidationError({"room": "This room does not belong to your company."})
            
        if hotel:
            if not user.is_superuser and hotel.company != company:
                 raise serializers.ValidationError({"hotel": "This hotel does not belong to your company."})
                 
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
        
        if company:
             validated_data['company'] = company
        if individual_owner:
             validated_data['individual_owner'] = individual_owner
             
        room = validated_data.get('room')
        if room and hasattr(room, 'hotel') and room.hotel:
            validated_data['hotel'] = room.hotel
            validated_data['company'] = room.hotel.company
        
        return super().create(validated_data)
