from django.db import transaction
from rest_framework import serializers
from apps.account.services import ImageCreationService
from apps.account.serializers import AddressSerializer, ListingImageSerializer
from apps.core.serializers import JsonSerializerField
from apps.listing.services import BookingService, ListingService
from apps.listing.models import (
    Amenity,
    Booking,
    BookingItem,
    CarListing,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
)


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
                    "Only one owner type allowed.")
            if not company_id and not individual_id:
                raise serializers.ValidationError("An owner is required.")
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


class BookingResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            "id",
            "userroom",
            "units_booked",
            "check_in_date",
            "check_out_date",
            "total_price",
            "status",
        ]


class BookingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingItem
        fields = ["room", "units_booked"]


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ["items", "check_in_date", "check_out_date"]

    def create(self, validated_data):
        BookingService.create_booking(validated_data)

    def to_representation(self, instance):
        return BookingResponseSerializer(instance, self.context).to_representation(
            instance
        )
