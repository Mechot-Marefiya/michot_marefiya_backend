from django.db import transaction
from rest_framework import serializers
from datetime import timedelta
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError
from apps.account.services import ImageCreationService
from apps.account.serializers import AddressSerializer, ListingImageSerializer
from apps.core.serializers import JsonSerializerField
from apps.listing.exceptions import BookingConflict
from apps.listing.services import BookingService, ListingService

from apps.listing.models import (
    Amenity,
    Booking,BookingRating,
    BookingItem,
    CarListing,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
)
from apps.listing.exceptions import RatingException

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


class CarListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)

    class Meta:
        model = CarListing
        fields = [
            "id",
            "title",
            "description",
            "images",
            "base_price",
            "brand",
            "model",
            "year",
            "mileage",
            "fuel_type",
            "transmission",
            "condition",
        ]


class CarListingSerializer(serializers.ModelSerializer):
    images = serializers.ListField(child=serializers.ImageField())

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
        ]

    def validate(self, data):
        company_id = data.get("company")
        individual_id = data.get("individual_owner")

        if company_id and individual_id:
            raise serializers.ValidationError("Only one owner type allowed.")
        if not company_id and not individual_id:
            raise serializers.ValidationError("An owner is required.")
        return data

    @transaction.atomic()
    def create(self, validated_data):
        # user = self.context["request"].user
        # individual_owner = validated_data.get("individual_owner")
        # # ? Just for testing purpose
        # validated_data['individual_owner'] = "6ca9a7cf-44cc-4979-be3b-d49b8b484ef6"

        # if not individual_owner:
        #     # Checking if the company is not doing this but rather the Michot
        #     # admin doing this and in some case the individual owner is missed.
        #     # Which means the logged in user is Michot admin (not another vendor)
        #     if user.role and user.role.code == RoleCode.ADMIN.value:
        #         raise serializers.ValidationError(
        #             "Valid Company or individual owner must exist."
        #         )
        #     company = get_object_or_404(CompanyProfile, user=user)
        #     validated_data["company"] = company

        images = validated_data.pop("images")

        # individual_owner_id = validated_data.pop('individual_owner')

        # individual_owner = get_object_or_404(
        #     IndividualOwnerProfile,
        #     id=individual_owner_id
        # )

        car_listing_instance = CarListing(
            # individual_owner=individual_owner,
            **validated_data
        )

        car_listing_instance.save()

        ImageCreationService.create_images(car_listing_instance, images)

        return car_listing_instance

    def to_representation(self, instance):
        return CarListingResponseSerializer(instance, self.context).to_representation(
            instance
        )


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
        fields = ["items", "check_in_date", "check_out_date"]

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
        user = validated_data.pop("user", None)
        if not user and self.context.get("request"):
            user = self.context["request"].user
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


class SearchResultSerializer(serializers.Serializer):
    hotel_id = serializers.UUIDField()
    hotel_name = serializers.CharField()
    city = serializers.CharField()
    stars = serializers.IntegerField(allow_null=True)
    rooms = SearchRoomSerializer(many=True)