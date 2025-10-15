# docs/schemas.py
from apps.core.serializers import AddressSerializer
from rest_framework import serializers

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
    facilities = serializers.ListField(child=serializers.CharField())
