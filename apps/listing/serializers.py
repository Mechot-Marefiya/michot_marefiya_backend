from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, IndividualOwnerProfile
from apps.account.serializers import AddressSerializer
from apps.core.models import Address
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


class AmenitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["name"]


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ["image", "alt_text"]


class RoomListingResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomListing
        fields = [
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
    address = JsonSerializerField()
    images = serializers.ListField(child=serializers.ImageField())

    class Meta:
        model = RoomListing
        fields = [
            "images",
            "title",
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
        validated_data["user"] = self.context["request"].user
        # TODO: Proper Error handling
        return ListingService.create_hotel_listing(validated_data)

    def to_representation(self, instance):
        return RoomListingResponseSerializer(instance, self.context).to_representation(
            instance
        )


class GuestHouseListingResponseSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True)

    class Meta:
        model = GuestHouseListing
        fields = [
            "title",
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
            "address",
            "rating"
        ]

        def validate_address(self, attr):
            serializer = AddressSerializer(data=attr)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data

        # def validate(self, attrs):
        #     print(attrs)
        #     # Enforce either individual_owner OR company.
        #     user = self.context["request"].user
        #     print("USER", user)
        #     individual_owner = attrs.get("individual_owner")

        #     if not individual_owner:
        #         company = get_object_or_404(CompanyProfile, user=user)
        #         attrs["company"] = company

        #     return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        print("USER", user)
        individual_owner = validated_data.get("individual_owner")

        if not individual_owner:
            # Checking if the company is not doing this
            # but rather the Michot admin doing this and in some case the individual owner is missed.
            # Which means the logged in user is Michot admin (not another vendor)
            if user.role and user.role.code == RoleCode.ADMIN.value:
                raise serializers.ValidationError(
                    "Valid Company or individual owner must exist")
            company = get_object_or_404(CompanyProfile, user=user)
            validated_data["company"] = company

        print("DAG", validated_data)
        # TODO: proper error handling
        return ListingService.create_guest_house_listing(validated_data)

    def to_representation(self, instance):
        return GuestHouseListingResponseSerializer(
            instance, self.context
        ).to_representation(instance)


class CarListingResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarListing
        fields = []


class CarListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarListing
        fields = []


class PropertyListingResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyListing
        fields = []


class PropertyListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyListing
        fields = []
