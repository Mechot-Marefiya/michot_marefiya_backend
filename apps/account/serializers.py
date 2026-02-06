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
from apps.listing.services import ListingService
from apps.core.services.email_service import EmailService
from django.utils import timezone
from apps.account.utils import generate_password
from rest_framework import serializers
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings

from apps.core.models import Facility
from apps.core.serializers import (
    AddressSerializer,
    FacilityResponseSerializer,
    FlexibleAddressField,
    JsonSerializerField,
)


User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):

        data = super().validate(attrs)
        
        if not self.user.is_active:
            raise serializers.ValidationError(
                "User account is disabled. Please contact the admin."
            )
        
        if self.user.role:
            data["role"] = self.user.role.code

            if self.user.role.code == RoleCode.COMPANY.value:
                if hasattr(self.user, "profile"):
                    data["company"] = {
                        "id": self.user.profile.id,
                        "name": self.user.profile.name,
                    }
                elif hasattr(self.user, "individual_owner") and self.user.individual_owner:
                     data["individual_owner"] = {
                        "id": self.user.individual_owner.id,
                        "name": f"{self.user.individual_owner.first_name} {self.user.individual_owner.last_name}",
                    }
        else:
            data["role"] = None

        return data


class StaffResponseSerializer(serializers.ModelSerializer):
    workspace = serializers.SerializerMethodField()
    role = serializers.CharField(source="role.name")

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "workspace", "created_at"]

    def get_workspace(self, instance):
        if instance.workspace:
            return str(instance.workspace)
        return None


class StaffCreateSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(write_only=True)
    workspace_type = serializers.ChoiceField(
        choices=["hotel", "guesthouse", "car_rental", "event_space"],
        write_only=True
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "workspace_id", "workspace_type"]

    def validate(self, attrs):
        from django.apps import apps
        request = self.context.get("request")
        user = request.user
        
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        if not (company or individual_owner):
             raise serializers.ValidationError("Only company or individual owners can create staff.")

        workspace_id = attrs.get("workspace_id")
        workspace_type = attrs.get("workspace_type")
        
        model_map = {
            "hotel": ("account", "HotelProfile"),
            "guesthouse": ("listing", "GuestHouseProfile"),
            "car_rental": ("listing", "CarListing"),
            "event_space": ("listing", "EventSpaceListing")
        }
        
        if workspace_type not in model_map:
             raise serializers.ValidationError({"workspace_type": "Invalid workspace type."})
             
        app_label, model_name = model_map[workspace_type]
        try:
            model_class = apps.get_model(app_label, model_name)
            workspace = model_class.objects.get(id=workspace_id)
        except (LookupError, model_class.DoesNotExist):
              raise serializers.ValidationError({"workspace_id": f"{model_name} not found."})
              
        is_owner = False
        if company:
             if hasattr(workspace, "company") and workspace.company == company:
                 is_owner = True
             elif hasattr(workspace, "hotel") and workspace.hotel.company == company:
                 is_owner = True
        
        if not is_owner and individual_owner:
             if hasattr(workspace, "individual_owner") and workspace.individual_owner == individual_owner:
                 is_owner = True
                  
        if not is_owner and not user.is_superuser:
            raise serializers.ValidationError({"workspace_id": "You do not have permission to add staff to this workspace."})
            
        attrs["workspace_instance"] = workspace
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        workspace = validated_data.pop("workspace_instance")
        validated_data.pop("workspace_id")
        validated_data.pop("workspace_type")
        
        email = validated_data.get("email")
        
        try:
            role = Role.objects.get(code=RoleCode.FRONT_DESK.value)
        except Role.DoesNotExist:
            raise serializers.ValidationError({"error": "Front Desk role configuration missing."})

        password = generate_password(email)
        
        user = User(
            role=role,
            is_active=True,
            company=self.context["request"].user.company,
            individual_owner=self.context["request"].user.individual_owner,
            workspace=workspace,
            **validated_data
        )
        user.set_password(password)
        user.save()
        
        EmailService.send_account_credentials(user, password)
        
        return user


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ["image", "alt_text"]


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "code", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "password", "confirm_password", "first_name", "last_name"]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        confirm_password = attrs.pop("confirm_password")
        
        if password != confirm_password:
            raise serializers.ValidationError({"password": "Passwords do not match"})
        
        if len(password) < 8:
            raise serializers.ValidationError(
                {"password": "Password must be at least 8 characters long."}
            )
        
        if not any(char.isdigit() for char in password):
            raise serializers.ValidationError(
                {"password": "Password must contain at least one digit."}
            )
        
        if not any(char.isalpha() for char in password):
            raise serializers.ValidationError(
                {"password": "Password must contain at least one letter."}
            )
        
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        try:
            role = Role.objects.get(code=RoleCode.USER.value)
        except Role.DoesNotExist:
            raise serializers.ValidationError(
                {"error": "User role does not exist in the system"}
            )
        
        user = User(**validated_data, role=role, is_active=False)
        user.set_password(password)
        user.save()

        try:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com')
            activation_url = f"{frontend_url}auth/verify-email?uid={uid}&token={token}"
            
            EmailService.send_verification_email(user, activation_url)
        except Exception as e:
            # log error but don't rollback user creation? 
            # maybe it's better to perhaps rollback or inform user.
            # for now, i will log and proceed, but user won't be able to login.
            # ideally this should be robust.
            pass

        return user

    def to_representation(self, instance):
        return UserResponseSerializer(instance, self.context).to_representation(
            instance
        )


class UserResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active", "role"]

    role = RoleSerializer(read_only=True)


class UserUpdateSerializer(serializers.ModelSerializer):
    current_password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "current_password"]
        extra_kwargs = {
            "email": {"required": False},
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def validate_email(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Email cannot be empty.")
        
        value = value.strip().lower()
        
        if self.instance and self.instance.email == value:
            return value

        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
            
        return value

    def validate(self, attrs):
        if 'email' in attrs and attrs['email'] != self.instance.email:
            if 'current_password' not in attrs:
                raise serializers.ValidationError({"current_password": "Current password is required to change email."})
            
            if not self.instance.check_password(attrs['current_password']):
                raise serializers.ValidationError({"current_password": "Incorrect password."})
        
        return attrs

    def update(self, instance, validated_data):
        new_email = validated_data.pop('email', None)
        validated_data.pop('current_password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        if new_email and new_email != instance.email:
            uid = urlsafe_base64_encode(force_bytes(instance.pk))
            token = default_token_generator.make_token(instance)
            
            from django.core.signing import TimestampSigner
            signer = TimestampSigner()
            signed_email = signer.sign(new_email)
            
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com')
            # Link format: /verify-email-change?uid=...&token=...&email=...
            # We'll use a custom View to verify the signer and then update.
            verification_url = f"{frontend_url}auth/verify-email-change?uid={uid}&email={signed_email}"
            
            # 1. Send verification to NEW email
            EmailService.send_email_change_verification(instance, new_email, verification_url)
            
            # 2. Send security alert to OLD email
            EmailService.send_email_change_notice(instance, instance.email, new_email)
            
            # We can add a message to the response via context or just return instance
            # The view can inspect and tell user "Verification sent"
            
        return instance

    def to_representation(self, instance):
        return UserResponseSerializer(instance, self.context).to_representation(instance)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True, required=True)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate_current_password(self, value):
        user = self.context.get("user")
        request = self.context.get("request")
        skip_verification = self.context.get("skip_current_password_check", False)
        
        if skip_verification:
            return value
        
        if not value:
            raise serializers.ValidationError("Current password is required.")
        
        if user and not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")
        current_password = attrs.get("current_password")

        if new_password != confirm_password:
            raise serializers.ValidationError({"new_password": "New passwords do not match."})

        if current_password and new_password == current_password:
            raise serializers.ValidationError(
                {"new_password": "New password must be different from current password."}
            )

        if len(new_password) < 8:
            raise serializers.ValidationError(
                {"new_password": "Password must be at least 8 characters long."}
            )

        if not any(char.isdigit() for char in new_password):
            raise serializers.ValidationError(
                {"new_password": "Password must contain at least one digit."}
            )

        if not any(char.isalpha() for char in new_password):
            raise serializers.ValidationError(
                {"new_password": "Password must contain at least one letter."}
            )

        return attrs

    def save(self):
        user = self.context.get("user")
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user
        return user


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        self.user = User.objects.filter(email=value).first()
        return value

    def save(self):
        if not getattr(self, 'user', None):
            return

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com')
        reset_url = f"{frontend_url}auth/reset-password?uid={uid}&token={token}"
        
        EmailService.send_password_reset(self.user, reset_url)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"new_password": "Passwords do not match."})

        password = attrs['new_password']
        if len(password) < 8:
            raise serializers.ValidationError({"new_password": "Password must be at least 8 characters long."})
        if not any(char.isdigit() for char in password):
            raise serializers.ValidationError({"new_password": "Password must contain at least one digit."})
        if not any(char.isalpha() for char in password):
            raise serializers.ValidationError({"new_password": "Password must contain at least one letter."})

        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            self.user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"token": "Invalid reset link."})

        if not default_token_generator.check_token(self.user, attrs['token']):
            raise serializers.ValidationError({"token": "Invalid or expired reset link."})

        return attrs

    def save(self):
        self.user.set_password(self.validated_data['new_password'])
        self.user.save()
        return self.user
class CompanyProfileResponseSerializer(serializers.ModelSerializer):
    address = AddressSerializer()
    user = UserResponseSerializer()
    approved_by = UserResponseSerializer(read_only=True)

    class Meta:
        model = CompanyProfile
        fields = [
            "id",
            "user",
            "status",
            "approved_at",
            "approved_by",
            "name",
            "phone",
            "category",
            "description",
            # "logo",
            "address",
            "tin",
            "business_license_number",
        ]


class VerifyEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            self.user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"token": "Invalid activation link."})

        if not default_token_generator.check_token(self.user, attrs['token']):
            raise serializers.ValidationError({"token": "Invalid or expired activation link."})
        
        if self.user.is_active:
             raise serializers.ValidationError({"detail": "User is already active."})

        return attrs

    def save(self):
        self.user.is_active = True
        self.user.save()
        return self.user


class VerifyEmailChangeSerializer(serializers.Serializer):
    uid = serializers.CharField()
    email = serializers.CharField()

    def validate(self, attrs):
        from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
        
        signer = TimestampSigner()
        try:
            self.new_email = signer.unsign(attrs['email'], max_age=60 * 60 * 24)
        except SignatureExpired:
            raise serializers.ValidationError({"email": "Verification link has expired."})
        except BadSignature:
             raise serializers.ValidationError({"email": "Invalid verification link."})

        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            self.user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Invalid user link."})

        if User.objects.filter(email=self.new_email).exclude(pk=self.user.pk).exists():
             raise serializers.ValidationError({"email": "This email is already in use."})

        return attrs

    def save(self):
        self.user.email = self.new_email
        self.user.save()
        return self.user


class CompanyProfileSerializer(serializers.ModelSerializer):
    # * We created this custom field because our payload for address is a JSOn string not a dict.
    # * We made it JSOn string cause we sent the form as a multipart not a JSON and multipart doesn't allow nesting
    # * And we made it multipart cause we need to send both file and JSON.
    address = FlexibleAddressField()
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
            "tin",
            "description",
            "business_license_number",
        ]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

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
        
        try:
            role = Role.objects.get(code=RoleCode.COMPANY.value)
        except Role.DoesNotExist:
            raise serializers.ValidationError(
                {"error": "Company role does not exist in the system"}
            )

        password = generate_password(email)

        user = User(email=email, role=role)
        user.set_password(password)
        user.save()
        address = ListingService.get_or_create_address(address_data)
        profile = CompanyProfile.objects.create(
            user=user,
            address=address,
            status=CompanyProfile.StatusChoice.APPROVED,
            approved_at=timezone.now(),
            **validated_data,
        )

        EmailService.send_account_credentials(user, password)

        return profile

    def to_representation(self, instance):
        return CompanyProfileResponseSerializer(
            instance, self.context
        ).to_representation(instance)


class CompanyApplicationSerializer(serializers.ModelSerializer):
    address = FlexibleAddressField()

    class Meta:
        model = CompanyProfile
        fields = [
            "name",
            "license",
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

    def validate(self, attrs):
        user = self.context["request"].user
        if hasattr(user, "profile") and user.profile:
            raise serializers.ValidationError("User already has a company profile.")
        return attrs

    @transaction.atomic()
    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user
        address_data = validated_data.pop("address")
        address = ListingService.get_or_create_address(address_data)

        profile = CompanyProfile.objects.create(
            user=user, address=address, status=CompanyProfile.StatusChoice.PENDING, **validated_data
        )

        return profile

    def to_representation(self, instance):
        return CompanyProfileResponseSerializer(instance, self.context).to_representation(instance)


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

        address = ListingService.get_or_create_address(address_data)

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
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = HotelProfile
    class Meta:
        model = HotelProfile
        fields = ["id", "company", "images", "logo", "stars", "featured","facilities", "is_favorite"]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        company_data = rep.pop("company", {})
        # Avoiding the actual hotel id override by company id
        company_data.pop("id")
        return {**rep, **company_data}

    def get_is_favorite(self, instance):
        """
        Pure serializer logic: uses only `self.context` and does not perform DB queries.
        Expects `favorite_object_ids` in context as a set of string ids. Defaults to False.
        """
        fav_ids = self.context.get("favorite_object_ids")
        if not fav_ids:
            return False
        try:
            return str(instance.id) in fav_ids
        except Exception:
            return False





class CompanyRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    
    address = FlexibleAddressField()

    class Meta:
        model = CompanyProfile
        fields = [
            "email", "first_name", "last_name", "password", "confirm_password",
            "name", "license", "logo", "category", "description", 
            "phone", "tin", "business_license_number", "address"
        ]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("confirm_password"):
             raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    @transaction.atomic()
    def create(self, validated_data):
        email = validated_data.pop("email")
        first_name = validated_data.pop("first_name")
        last_name = validated_data.pop("last_name")
        password = validated_data.pop("password")
        validated_data.pop("confirm_password")
        
        address_data = validated_data.pop("address")
        
        try:
            role = Role.objects.get(code=RoleCode.COMPANY.value)
        except Role.DoesNotExist:
             raise serializers.ValidationError({"error": "Role configuration error."})

        user = User.objects.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=False
        )
        user.set_password(password)
        user.save()
        
        address = ListingService.get_or_create_address(address_data)
        
        profile = CompanyProfile.objects.create(
            user=user,
            address=address,
            status=CompanyProfile.StatusChoice.PENDING,
            **validated_data
        )
        
        self._send_verification(user)
        
        return profile

    def _send_verification(self, user):
        try:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com')
            activation_url = f"{frontend_url}auth/verify-email?uid={uid}&token={token}"
            EmailService.send_verification_email(user, activation_url)
        except Exception:
            pass

    def to_representation(self, instance):
        return CompanyProfileResponseSerializer(instance, context=self.context).to_representation(instance)


class IndividualOwnerRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    
    address = FlexibleAddressField()

    class Meta:
        model = IndividualOwnerProfile
        fields = [
            "email", "password", "confirm_password",
            "first_name", "last_name", "phone", "national_id_number", "address"
        ]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
             raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
        
    def validate(self, attrs):
        if attrs.get("password") != attrs.get("confirm_password"):
             raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    @transaction.atomic()
    def create(self, validated_data):
        email = validated_data.pop("email")
        password = validated_data.pop("password")
        validated_data.pop("confirm_password")
        
        first_name = validated_data.get("first_name")
        last_name = validated_data.get("last_name")
        address_data = validated_data.pop("address")
        
        try:
            role = Role.objects.get(code=RoleCode.COMPANY.value) 
        except Role.DoesNotExist:
             raise serializers.ValidationError({"error": "Role configuration error."})

        user = User.objects.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=False
        )
        user.set_password(password)
        
        address = ListingService.get_or_create_address(address_data)
        
        profile = IndividualOwnerProfile.objects.create(
            address=address,
            **validated_data
        )
        
        user.individual_owner = profile
        user.save()
        
        self._send_verification(user)
        
        return profile

    def _send_verification(self, user):
        try:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com')
            activation_url = f"{frontend_url}auth/verify-email?uid={uid}&token={token}"
            EmailService.send_verification_email(user, activation_url)
        except Exception:
            pass

    def to_representation(self, instance):
        return IndividualOwnerProfileResponseSerializer(instance, context=self.context).to_representation(instance)


class HotelProfileSerializer(serializers.ModelSerializer):
    facilities = JsonSerializerField()
    images = serializers.ListField(child=serializers.ImageField(), required=False) 
    address = FlexibleAddressField()
    license = serializers.FileField(required=False)
    logo = serializers.ImageField(required=False)

    class Meta:
        model = HotelProfile
        fields = [
            "name",
            "description",
            "phone",
            "website",
            "address", 
            "license",
            "logo",
            "stars",
            "featured",
            "facilities",
            "images", 
        ]

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @transaction.atomic()
    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user
        
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        if not company:
            raise serializers.ValidationError({"detail": "User does not have an active company profile."})

        if company.status != CompanyProfile.StatusChoice.APPROVED:
             raise serializers.ValidationError({"detail": "Your company profile is not approved yet."})

        address_data = validated_data.pop("address")
        facilities = validated_data.pop("facilities", [])
        images = validated_data.pop("images", [])
        
        address = ListingService.get_or_create_address(address_data)
        
        hotel = HotelProfile.objects.create(
            company=company,
            address=address,
            **validated_data
        )

        if facilities:
            hotel.facilities.set(facilities)

        if images:
            ImageCreationService.create_images(hotel, images)

        return hotel

    @transaction.atomic()
    def update(self, instance, validated_data):
        kept_image_ids = self.initial_data.getlist("kept_image_ids") if "kept_image_ids" in self.initial_data else None
        
        if kept_image_ids is None and "kept_image_ids" in self.initial_data:
             kept_image_ids = self.initial_data["kept_image_ids"]
             
        return ListingService.update_hotel_profile(instance, validated_data, kept_image_ids)

    def to_representation(self, instance):
        return HotelProfileResponseSerializer(instance, context=self.context).to_representation(
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