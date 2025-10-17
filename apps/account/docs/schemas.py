# docs/schemas.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, OpenApiParameter
from apps.account.serializers import (
    HotelRoomAvailabilityResponseSerializer,
    HotelRoomAvailabilitySerializer
)
from apps.core.serializers import AddressSerializer

# * This is a custom schema since the default
# * serializers didn't gamme what I wanted


class HotelProfileDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    phone = serializers.CharField()
    category = serializers.CharField()
    description = serializers.CharField()
    stars = serializers.IntegerField()
    address = AddressSerializer()
    images = serializers.ListField(child=serializers.ImageField())
    facilities = serializers.ListField(child=serializers.CharField())


check__room_availability_schema = extend_schema(
    request=HotelRoomAvailabilitySerializer,
    responses={200: HotelRoomAvailabilityResponseSerializer(many=True)},
    parameters=[
        OpenApiParameter(
            name='check_in_date',
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description='Check-in date (YYYY-MM-DD)',
        ),
        OpenApiParameter(
            name='check_out_date',
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description='Check-out date (YYYY-MM-DD)',
        ),
    ]
)
