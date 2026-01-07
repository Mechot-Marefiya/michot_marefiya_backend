from rest_framework import serializers
from apps.core.models import Address, Facility, CurrencyRate
from decimal import Decimal

class AddressSerializer(serializers.ModelSerializer):
    
    street_line1 = serializers.CharField(
        max_length=255,
        label="Street Address",
        help_text="Street address, building name, or nearby landmark (e.g., 'Bole Road, near Edna Mall')",
        error_messages={
            'required': 'Street address is required to locate your listing',
            'blank': 'Street address cannot be empty',
            'max_length': 'Street address cannot exceed 255 characters'
        }
    )
    
    city = serializers.CharField(
        max_length=100,
        help_text="City name (e.g., 'Addis Ababa', 'Bahir Dar', 'Dire Dawa')",
        error_messages={
            'required': 'City is required to locate your listing',
            'blank': 'City name cannot be empty',
            'max_length': 'City name cannot exceed 100 characters'
        }
    )
    
    country = serializers.CharField(
        max_length=100,
        default="Ethiopia",
        help_text="Country name (defaults to Ethiopia)",
        error_messages={
            'max_length': 'Country name cannot exceed 100 characters'
        }
    )
    
    sub_city = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        help_text="Subcity or district (e.g., 'Bole', 'Kirkos', 'Arada')",
        error_messages={
            'max_length': 'Subcity name cannot exceed 100 characters'
        }
    )
    
    state = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        help_text="State or region (optional)",
        error_messages={
            'max_length': 'State name cannot exceed 100 characters'
        }
    )
    
    postal_code = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text="Postal code if available",
        error_messages={
            'max_length': 'Postal code cannot exceed 20 characters'
        }
    )
    
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        help_text="Latitude coordinate (between -90 and 90 degrees)",
        error_messages={
            'invalid': 'Latitude must be a valid decimal number',
            'max_digits': 'Latitude cannot have more than 9 total digits',
            'max_decimal_places': 'Latitude cannot have more than 6 decimal places'
        }
    )
    
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        help_text="Longitude coordinate (between -180 and 180 degrees)",
        error_messages={
            'invalid': 'Longitude must be a valid decimal number',
            'max_digits': 'Longitude cannot have more than 9 total digits',
            'max_decimal_places': 'Longitude cannot have more than 6 decimal places'
        }
    )
    
    class Meta:
        model = Address
        fields = [
            "city",
            "country",
            "sub_city",
            "street_line1",
            "latitude",
            "longitude",
            "state",
            "postal_code",
        ]
    
    def validate_latitude(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError(
                "Latitude must be between -90 and 90 degrees. "
                "Example: Addis Ababa is around 9.03°"
            )
        return value
    
    def validate_longitude(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError(
                "Longitude must be between -180 and 180 degrees. "
                "Example: Addis Ababa is around 38.74°"
            )
        return value
    
    def validate_city(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "City name cannot be empty or just whitespace"
            )
        normalized = value.strip().title()
        if len(normalized) < 2:
            raise serializers.ValidationError(
                "City name must be at least 2 characters long"
            )
        return normalized
    
    def validate_street_line1(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "Street address cannot be empty or just whitespace"
            )
        normalized = value.strip()
        if len(normalized) < 3:
            raise serializers.ValidationError(
                "Street address must be at least 3 characters long"
            )
        return normalized
    
    def validate_country(self, value):
        if value:
            return value.strip().title()
        return "Ethiopia"
    
    def validate_sub_city(self, value):
        if value:
            return value.strip().title()
        return value
    
    def validate_postal_code(self, value):
        if value:
            return value.strip().upper()
        return value
class FacilitySerializer(serializers.ModelSerializer):
 class Meta:
        model = Facility
        fields = [
            "icon",
            "name",
            
        ]
class FlexibleAddressField(serializers.Field):

    def to_internal_value(self, data):
        import json
        
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                raise serializers.ValidationError(
                    f"Invalid address format. Expected a JSON object or valid JSON string. "
                    f"Error at position {e.pos}: {e.msg}. "
                    f"Example: {{\"city\": \"Addis Ababa\", \"street_line1\": \"Bole Road\"}}"
                )
        
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                "Address must be an object with fields like 'city', 'street_line1', etc. "
                f"Received type: {type(data).__name__}. "
                "Example: {\"city\": \"Addis Ababa\", \"street_line1\": \"Bole Road\"}"
            )
        
        serializer = AddressSerializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
            raise serializers.ValidationError(
                {"address_fields": e.detail}
            )
        
        return serializer.validated_data
    
    def to_representation(self, value):
        if isinstance(value, Address):
            return AddressSerializer(value).data
        return value


class JsonSerializerField(serializers.Field):

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


class CurrencyRateSerializer(serializers.ModelSerializer):
    """Serializer for the CurrencyRate model."""
    class Meta:
        model = CurrencyRate
        fields = ["target", "rate"]