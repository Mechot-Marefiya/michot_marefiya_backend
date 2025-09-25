from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile
from apps.account.serializers import AddressSerializer
from apps.core.serializers import JsonSerializerField
from apps.listing.models import (
    Amenity,
    CarListing,
    GuestHouseListing,
    ListingImage,
    PropertyListing,
    RoomListing,
)
from apps.listing.services import ListingService


class AmenityResponseSSerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["id", "name", "icon"]


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ["image", "alt_text"]


class RoomListingResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomListing
        fields = [
            "id",
            # "hotel",
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
    hotel_id = serializers.UUIDField(required=False)

    class Meta:
        model = RoomListing
        fields = [
            "images",
            "title",
            "hotel_id",
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
        hotel_id = validated_data.get('hotel_id', None)
        if not hotel_id:
            validated_data["user"] = self.context["request"].user
        validated_data['hotel_id'] = hotel_id
        # TODO: Proper Error handling
        return ListingService.create_hotel_listing(validated_data)

    def to_representation(self, instance):
        return RoomListingResponseSerializer(
            instance,
            self.context
        ).to_representation(
            instance
        )


class GuestHouseListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)
    address = AddressSerializer()

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
            "rating"
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
            "description",
            "total_rooms",
            "amenities",
            "address"
        ]

        def validate_address(self, attr):
            serializer = AddressSerializer(data=attr)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data

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
            "listing_type",
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
            "brand",
            "model",
            "year",
            "mileage",
            "fuel_type",
            "transmission",
            "listing_type",
            "condition",
        ]

    @transaction.atomic()
    def create(self, validated_data):
        user = self.context["request"].user
        individual_owner = validated_data.get("individual_owner")

        if not individual_owner:
            # Checking if the company is not doing this but rather the Michot
            # admin doing this and in some case the individual owner is missed.
            # Which means the logged in user is Michot admin (not another vendor)
            if user.role and user.role.code == RoleCode.ADMIN.value:
                raise serializers.ValidationError(
                    "Valid Company or individual owner must exist."
                )
            company = get_object_or_404(CompanyProfile, user=user)
            validated_data["company"] = company

        images = validated_data.pop("images")

        car_listing_instance = CarListing(**validated_data)

        car_listing_instance.save()

        ListingService.create_images(car_listing_instance, images)

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
            "listing_type",
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
            # "individual_owner",
            "address",
            "property_type",
            "bedrooms",
            "bathrooms",
            "square_meters",
            "is_furnished",
            "listing_type",
        ]

    def create(self, validated_data):
        # user = self.context["request"].user
        # individual_owner = validated_data.get("individual_owner")

        # ? Just for testing purpose
        # validated_data['individual_owner'] = "8393efcf-27c8-4408-bac1-cea75cccee96"

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
