from django.db import transaction
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from apps.account.enums import RoleCode
from apps.account.models import (
    Address,
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    Role
)
from apps.account.utils import generate_password
from rest_framework import serializers

from apps.core.serializers import AddressSerializer, JsonSerializerField


User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        # Add custom data
        data["role"] = self.user.role.code  # e.g., "company" or "user"

        if self.user.role.code == RoleCode.COMPANY.value and hasattr(
            self.user, "company_profile"
        ):
            data["company"] = {
                "id": self.user.company_profile.id,
                "name": self.user.company_profile.company_name,
            }

        return data


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
        fields = ["name", "phone", "category", "description", "logo"]


class CompanyProfileSerializer(serializers.ModelSerializer):
    # * We created this custom field because our payload for address is a JSOn string not a dict.
    # * We made it JSOn string cause we sent the form as a multipart not a JSON and multipart doesn't allow nesting
    # * And we made it multipart cause we need to send both file and JSON.
    address = JsonSerializerField()
    email = serializers.EmailField()

    class Meta:
        model = CompanyProfile
        fields = [
            "email",
            "license",
            "name",
            "address",
            "phone",
            "logo",
            "category",
            "description",
        ]

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, attr):
        return attr

    @transaction.atomic()
    def create(self, validated_data):
        email = validated_data.pop("email")
        address_data = validated_data.pop("address")
        role = Role.objects.get(code=RoleCode.COMPANY.value)

        password = generate_password(email)

        user = User(email=email, role=role)
        user.set_password(password)
        user.save()
        address = Address.objects.create(**address_data)
        profile = CompanyProfile.objects.create(
            user=user, address=address, **validated_data
        )

        return profile

    def to_representation(self, instance):
        return CompanyProfileResponseSerializer(
            instance, self.context
        ).to_representation(instance)


class IndividualOwnerProfileResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndividualOwnerProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "address",
            "phone",
            "category"
        ]


class IndividualOwnerProfileSerializer(serializers.ModelSerializer):
    address = AddressSerializer()

    class Meta:
        model = IndividualOwnerProfile
        fields = [
            "first_name",
            "last_name",
            "address",
            "phone",
            "category",
            "national_id_number"
        ]

    @transaction.atomic()
    def create(self, validated_data):
        address_data = validated_data.pop("address")

        address = Address.objects.create(**address_data)

        profile = IndividualOwnerProfile.objects.create(
            address=address,
            **validated_data
        )

        return profile

    def to_representation(self, instance):
        return IndividualOwnerProfileResponseSerializer(
            instance, self.context
        ).to_representation(instance)


class HotelProfileResponseSerializer(serializers.ModelSerializer):
    company = CompanyProfileResponseSerializer()

    class Meta:
        model = HotelProfile
        fields = [
            'id',
            'company',
            'stars',
            'facilities'
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        company_data = rep.pop("company", {})
        return {**rep, **company_data}


class HotelProfileSerializer(serializers.ModelSerializer):
    company = CompanyProfileResponseSerializer()

    class Meta:
        model = HotelProfile
        fields = [
            'company',
            'stars',
            'facilities'
        ]

    @transaction.atomic()
    def create(self, validated_data):
        company_info = validated_data.pop('company')

        company = CompanyProfile.objects.create(**company_info)

        hotel = HotelProfile.objects.create(company=company, **validated_data)

        return hotel
