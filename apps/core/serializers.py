from rest_framework import serializers
from apps.core.models import Address, Facility
from decimal import Decimal

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
class FacilitySerializer(serializers.ModelSerializer):
 class Meta:
        model = Facility
        fields = [
            "icon",
            "name",
            
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
        fields = ["id", "name", "icon"]

class ConversionInputSerializer(serializers.Serializer):
    """Serializer for validating currency conversion input."""
    date = serializers.DateField(
        required=True, 
        help_text="The date for which the exchange rate should be used (YYYY-MM-DD)."
    )
    base = serializers.CharField(
        max_length=3, 
        required=True,
        help_text="The source (base) currency code (e.g., 'USD')."
    )
    target = serializers.CharField(
        max_length=3, 
        required=True,
        help_text="The destination (target) currency code (e.g., 'ETB')."
    )
    amount = serializers.DecimalField(
        max_digits=18, 
        decimal_places=2, 
        required=True,
        help_text="The amount to be converted."
    )