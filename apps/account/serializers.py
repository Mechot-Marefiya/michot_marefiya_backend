from django.db import transaction
from django.contrib.auth import get_user_model
from apps.account.enums import RoleCode
from apps.account.models import Address, CompanyProfile, Role
from apps.account.utils import generate_password
from rest_framework import serializers

User = get_user_model()


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'city', 'country', 'country', 'sub_city', 'street_line1',
            'street_line2', 'latitude', 'longitude', 'state', 'postal_code']


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


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "code", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField()

    class Meta:
        model = User
        fields = ["email", "password",
                  "confirm_password", "first_name", "last_name"]

    def validate(self, attrs):
        # TODO: Add password strength validtion here

        confirm_password = attrs.pop("confirm_password")
        if confirm_password != attrs["password"]:
            raise serializers.ValidationError("Password does not match")
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = Role.objects.get(code=RoleCode.USER.value)
        user = User(**validated_data, role=role)
        user.set_password(password)

        user.save()

        return user

    def to_representation(self, instance):
        return UserResponseSerializer(instance, self.context).to_representation(
            instance
        )


class UserResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name",
                  "last_name", "is_active", "role"]


class CompanyProfileResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile
        fields = ['name', 'phone', 'industry', 'description']


class CompanyProfileSerializer(serializers.ModelSerializer):
    # * We created this custom field because our payload for address is a JSOn string not a dict.
    # * We made it JSOn string cause we sent the form as a multipart not a JSON and multipart doesn't allow nesting
    # * And we made it multipart cause we need to send both file and JSON.
    address = JsonSerializerField()
    email = serializers.EmailField()

    class Meta:
        model = CompanyProfile
        fields = ['email', 'license', 'name', 'address',
                  'phone', 'logo', 'industry', 'description']

    def validate(self, attr):
        # TODO: Do validation
        return attr

    @transaction.atomic()
    def create(self, validated_data):
        email = validated_data.pop('email')
        address_data = validated_data.pop('address')
        role = Role.objects.get(code=RoleCode.COMPANY.value)

        password = generate_password(email)

        user = User(email=email, role=role)
        user.set_password(password)
        user.save()
        address = Address.objects.create(**address_data)
        profile = CompanyProfile.objects.create(
            user=user, address=address, **validated_data)

        return profile

    def to_representation(self, instance):
        return CompanyProfileResponseSerializer(
            instance,
            self.context
        ).to_representation(instance)
