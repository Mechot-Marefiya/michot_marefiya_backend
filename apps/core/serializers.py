from rest_framework import serializers
from apps.core.models import Address, Facility


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "city",
            "country",
            "country",
            "sub_city",
            "street_line1",
            "latitude",
            "longitude",
            "state",
            "postal_code",
        ]


class JsonSerializerField(serializers.Field):
    """Used to convert JSON string to dict"""

    def to_internal_value(self, data):
        import json

        if isinstance(data, str):
            try:
                return json.loads(data)
            except Exception:
                raise serializers.ValidationError("Invalid JSON")
        elif isinstance(data, dict):
            return data
        raise serializers.ValidationError("Expected dict or JSON string")

    def to_representation(self, value):
        return value


class FacilityResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = [
            "id",
            "name",
            "icon"
        ]
