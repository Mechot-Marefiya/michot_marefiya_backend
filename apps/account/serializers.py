from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
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
        user = User(**validated_data, password=make_password(password))

        user.save()

        return user

    def to_representation(self, instance):
        return UserResponseSerializer(instance, self.context).to_representation(
            instance
        )


class UserResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active"]


class CompanyProfileSerializer(serializers.ModelSerializer):
    address = AddressSerializer()
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
        address = validated_data.pop('address')
        password = generate_password(email)

        user = User(email=email)
        user.set_password(password)
        user.save()

        address = Address.objects.create(**address)

        profile = CompanyProfile.objects.create(
            user, address, **validated_data)

        return profile
