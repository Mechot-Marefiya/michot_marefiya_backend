from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, inline_serializer, OpenApiTypes
from apps.core.models import Address, Facility, CurrencyRate
from decimal import Decimal
import json
from services.maps import GeocodingError, get_place_detail

class StringArrayField(serializers.ListField):
    def to_internal_value(self, data):
        print(f"DEBUG: StringArrayField input: type={type(data)}, value={data}")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                raise serializers.ValidationError("Invalid JSON list")
        return super().to_internal_value(data)


class AddressSerializer(serializers.ModelSerializer):
    place_id = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Geoapify place identifier selected from autocomplete.",
    )

    session_token = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Geoapify autocomplete session token paired with place_id.",
    )
    
    street_line1 = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        label="Street Address",
        help_text="Street address, building name, or nearby landmark (e.g., 'Bole Road, near Edna Mall')",
        error_messages={
            'blank': 'Street address cannot be empty',
            'max_length': 'Street address cannot exceed 255 characters'
        }
    )
    
    city = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        help_text="City name (e.g., 'Addis Ababa', 'Bahir Dar', 'Dire Dawa')",
        error_messages={
            'blank': 'City name cannot be empty',
            'max_length': 'City name cannot exceed 100 characters'
        }
    )
    
    country = serializers.CharField(
        max_length=100,
        required=False,
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
            "place_id",
            "session_token",
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
        if value is None:
            return value
        if not str(value).strip():
            return ""
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
        if value is None:
            return value
        if not str(value).strip():
            return ""
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

    def _resolve_place_detail(self, attrs):
        place_id = (attrs.pop("place_id", "") or "").strip()
        session_token = (attrs.pop("session_token", "") or "").strip()

        if not place_id:
            return attrs

        if not session_token:
            raise serializers.ValidationError(
                {"session_token": "This field is required when place_id is provided."}
            )

        try:
            detail = get_place_detail(place_id, session_token)
        except GeocodingError as exc:
            raise serializers.ValidationError({"place_id": str(exc)}) from exc

        components = detail.get("components") or {}
        formatted_address = (detail.get("formatted_address") or "").strip()
        street_line1 = (attrs.get("street_line1") or "").strip()
        attrs["street_line1"] = street_line1 or formatted_address.split(",", 1)[0].strip() or formatted_address
        attrs["city"] = (attrs.get("city") or components.get("city") or "").strip()
        attrs["country"] = (attrs.get("country") or components.get("country") or "Ethiopia").strip()
        attrs["sub_city"] = (attrs.get("sub_city") or components.get("sub_city") or "").strip()
        attrs["state"] = (attrs.get("state") or components.get("region") or "").strip()
        attrs["postal_code"] = (attrs.get("postal_code") or components.get("postcode") or "").strip()
        attrs["latitude"] = attrs.get("latitude") or detail.get("lat")
        attrs["longitude"] = attrs.get("longitude") or detail.get("lng")
        attrs["google_place_id"] = detail.get("place_id") or place_id
        return attrs

    def validate(self, attrs):
        attrs = self._resolve_place_detail(attrs)

        errors = {}
        if not (attrs.get("street_line1") or "").strip():
            errors["street_line1"] = "Street address is required to locate your listing"
        if not (attrs.get("city") or "").strip():
            errors["city"] = "City is required to locate your listing"
        if errors:
            raise serializers.ValidationError(errors)

        return attrs
class FacilitySerializer(serializers.ModelSerializer):
 class Meta:
        model = Facility
        fields = [
            "icon",
            "name",
            
        ]
ADDRESS_SCHEMA = inline_serializer(
    name="AddressSchema",
    fields={
        "city": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        "country": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        "sub_city": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        "street_line1": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        "latitude": serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True),
        "longitude": serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True),
        "state": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        "postal_code": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        "place_id": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        "session_token": serializers.CharField(required=False, allow_blank=True, allow_null=True),
    },
)

@extend_schema_field(ADDRESS_SCHEMA)
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
                    f"Example: {{\"place_id\": \"...\", \"session_token\": \"...\"}}"
                )
        
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                "Address must be an object with Geoapify place fields or manual fields like 'city', 'street_line1'. "
                f"Received type: {type(data).__name__}. "
                "Example: {\"place_id\": \"...\", \"session_token\": \"...\"}"
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


@extend_schema_field(OpenApiTypes.OBJECT)
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


class CurrencyListItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class CurrencyConversionResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    input_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    base = serializers.CharField()
    target = serializers.CharField()
    converted_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    rate_date = serializers.DateField()
    rate_used = serializers.DecimalField(max_digits=18, decimal_places=6)
