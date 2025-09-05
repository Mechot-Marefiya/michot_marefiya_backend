from django.db import transaction
from rest_framework import serializers

from apps.account.serializers import AddressSerializer
from apps.core.serializers import JsonSerializerField
from apps.listing.models import CarListing, PropertyListing, RoomListing
from apps.listing.services import ListingService


class RoomListingResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomListing
        fields = [
            "images",
            "title",
            "description",
            "price",
            "amenities",
            "number_of_guests",
            "total_units",
            "bed_type",
            "room_size_sqm",
            "smoking_allowed",
            "children_allowed",
            "refundable",
            "check_in_time",
            "check_out_time"
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
            "price",
            "address",
            "amenities",
            "number_of_guests",
            "total_units",
            "bed_type",
            "room_size_sqm",
            "smoking_allowed",
            "children_allowed",
            "refundable",
            "check_in_time",
            "check_out_time"
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
