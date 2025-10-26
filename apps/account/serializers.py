from django.db import transaction
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from apps.account.services import ImageCreationService
from apps.account.enums import RoleCode
from apps.account.models import (
    Address,
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    ListingImage,
    Role,
)
from apps.account.utils import generate_password
from rest_framework import serializers

from apps.core.models import Facility
from apps.core.serializers import (
    AddressSerializer,
    FacilityResponseSerializer,
    JsonSerializerField,
)


User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["role"] = self.user.role.code

        if self.user.role.code == RoleCode.COMPANY.value and hasattr(
            self.user, "company_profile"
        ):
            data["company"] = {
                "id": self.user.company_profile.id,
                "name": self.user.company_profile.company_name,
            }

        return data


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ["image", "alt_text"]


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "code", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField()

    class Meta:
        model = User
        fields = ["email", "password", "confirm_password", "first_name", "last_name"]

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
        fields = ["id", "email", "first_name", "last_name", "is_active", "role"]


class CompanyProfileResponseSerializer(serializers.ModelSerializer):
    address = AddressSerializer()

    class Meta:
        model = CompanyProfile
        fields = [
            "id",
            "name",
            "phone",
            "category",
            "description",
            # "logo",
            "address",
        ]


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
    address = AddressSerializer()

    class Meta:
        model = IndividualOwnerProfile
        fields = [
            "id",
            "national_id_number",
            "first_name",
            "last_name",
            "address",
            "phone",
            # "category"
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
            # "category",
            "national_id_number",
        ]

    @transaction.atomic()
    def create(self, validated_data):
        address_data = validated_data.pop("address")

        address = Address.objects.create(**address_data)

        profile = IndividualOwnerProfile.objects.create(
            address=address, **validated_data
        )

        return profile

    def to_representation(self, instance):
        return IndividualOwnerProfileResponseSerializer(
            instance, self.context
        ).to_representation(instance)


class HotelProfileResponseSerializer(serializers.ModelSerializer):
    company = CompanyProfileResponseSerializer()
    images = ListingImageSerializer(many=True)
    facilities = FacilityResponseSerializer(many=True)

    class Meta:
        model = HotelProfile
        fields = ["id", "company", "images", "stars", "facilities"]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        company_data = rep.pop("company", {})
        # Avoiding the actual hotel id override by company id
        company_data.pop("id")
        return {**rep, **company_data}


class HotelProfileSerializer(serializers.Serializer):
    company = JsonSerializerField()
    logo = serializers.ImageField()
    license = serializers.FileField()
    facilities = JsonSerializerField()
    stars = serializers.IntegerField()
    images = serializers.ListField(child=serializers.ImageField())

    def validate(self, attrs):
        company_data = attrs.pop("company")
        address_data = company_data.pop("address")
        serializer = AddressSerializer(data=address_data)
        serializer.is_valid(raise_exception=True)
        attrs["address"] = serializer.validated_data
        attrs["company"] = company_data
        return attrs

    @transaction.atomic()
    def create(self, validated_data):
        company_info = validated_data.pop("company")
        email = company_info.pop("email")
        address_info = validated_data.pop("address")
        license = validated_data.pop("license")
        logo = validated_data.pop("logo")
        facilities = validated_data.pop("facilities")
        images = validated_data.pop("images")
        role = Role.objects.get(code=RoleCode.COMPANY.value)
        password = generate_password(email)
        user = User(email=email, role=role)
        user.set_password(password)
        user.save()
        address = Address.objects.create(**address_info)
        company = CompanyProfile.objects.create(
            user=user, logo=logo, license=license, **company_info, address=address
        )

        hotel = HotelProfile.objects.create(company=company, **validated_data)
        facility_instances = []
        for id in facilities:
            ins = get_object_or_404(Facility, id=id)
            facility_instances.append(ins)

        hotel.facilities.set(facility_instances)

        ImageCreationService.create_images(hotel, images)

        return hotel

    def to_representation(self, instance):
        return HotelProfileResponseSerializer(instance, self.context).to_representation(
            instance
        )


class HotelRoomAvailabilityResponseSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()
    room_name = serializers.CharField()
    available_units = serializers.IntegerField()


class HotelRoomAvailabilitySerializer(serializers.Serializer):
    check_in_date = serializers.DateField()
    check_out_date = serializers.DateField()

    def validate(self, data):
        """Ensure check-out date is after check-in date."""
        if data["check_out_date"] <= data["check_in_date"]:
            raise serializers.ValidationError(
                "Check-out date must be after check-in date."
            )
        return data
