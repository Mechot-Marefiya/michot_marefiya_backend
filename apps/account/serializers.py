from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from rest_framework.serializers import ModelSerializer, ValidationError, CharField

User = get_user_model()


class UserSerializer(ModelSerializer):
    confirm_password = CharField()

    class Meta:
        model = User
        fields = ["email", "password", "confirm_password", "first_name", "last_name"]

    def validate(self, attrs):
        # TODO: Add password strength validtion here

        confirm_password = attrs.pop("confirm_password")
        if confirm_password != attrs["password"]:
            raise ValidationError("Password does not match")
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


class UserResponseSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active"]
