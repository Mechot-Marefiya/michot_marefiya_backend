from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
import logging
import uuid
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from apps.account.services import (
    GuestBookingConversionError,
    GuestBookingConversionService,
    ImageCreationService,
    OtpError,
    OtpService,
    get_latest_agreement,
)
from apps.account.enums import RoleCode
from apps.account.models import (
    Address,
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    ListingImage,
    OtpChallenge,
    OwnerComplianceAgreement,
    Role,
    normalize_phone_number,
)
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from apps.listing.services import ListingService
from apps.core.services.email_service import EmailService
from django.utils import timezone
from apps.account.utils import (
    generate_password,
    get_company_scope,
    get_individual_owner_scope,
    get_workspace_summary,
)
from rest_framework import serializers
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings
from services.maps import GeocodingError, get_place_detail

from apps.core.models import Facility
from apps.core.serializers import (
    AddressSerializer,
    FacilityResponseSerializer,
    FlexibleAddressField,
    JsonSerializerField,
)
from drf_spectacular.utils import extend_schema_field, inline_serializer
from services.sms import send_sms


User = get_user_model()


def build_placeholder_email(phone: str | None) -> str:
    normalized_phone = normalize_phone_number(phone)
    suffix = normalized_phone or uuid.uuid4().hex
    return f"{suffix}@phone.local"


class PlaceResolutionMixin(metaclass=serializers.SerializerMetaclass):
    place_id = serializers.CharField(required=False, allow_blank=True, write_only=True)
    session_token = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def _resolve_place_detail(self, data):
        place_id = (data.get("place_id") or "").strip()
        session_token = (data.get("session_token") or "").strip()

        if not place_id:
            return data

        if not session_token:
            raise serializers.ValidationError(
                {"session_token": "This field is required when place_id is provided."}
            )

        try:
            detail = get_place_detail(place_id, session_token)
        except GeocodingError as exc:
            raise serializers.ValidationError({"place_id": str(exc)}) from exc

        data["latitude"] = detail.get("lat")
        data["longitude"] = detail.get("lng")
        data["formatted_address"] = detail.get("formatted_address")
        data["place_id"] = detail.get("place_id") or place_id
        data["address_components"] = detail.get("components") or {}
        data["_skip_async_geocoding"] = True
        return data

    def _pop_session_token(self, validated_data):
        validated_data.pop("session_token", None)

    def _pop_skip_async_geocoding(self, validated_data) -> bool:
        return bool(validated_data.pop("_skip_async_geocoding", False))

class WorkspaceInfoSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    workspace_type = serializers.CharField(allow_null=True)


class LoginProfileSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


WORKSPACE_INFO_SCHEMA = WorkspaceInfoSerializer(allow_null=True)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        username_field = self.username_field
        if username_field in self.fields:
            self.fields[username_field].required = False
            self.fields[username_field].allow_blank = True

    def _get_authenticated_user(self, attrs):
        password = attrs.get("password")
        raw_phone = (attrs.get("phone") or "").strip()

        if not raw_phone:
            raise serializers.ValidationError(
                {"phone": "This field is required."}
            )

        phone = normalize_phone_number(raw_phone)
        user = (
            User.objects.select_related("role")
            .filter(phone=phone)
            .first()
        )
        if not user or not user.check_password(password):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )
        return user

    def validate(self, attrs):
        self.user = self._get_authenticated_user(attrs)
        refresh = self.get_token(self.user)
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
        
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
            elif self.user.role.code in [RoleCode.FRONT_DESK.value, "front_desk"]:
                if self.user.workspace:
                    data["workspace"] = get_workspace_summary(self.user.workspace)
            
            if hasattr(self.user, "individual_owner") and self.user.individual_owner and (
                self.user.role.code == RoleCode.INDIVIDUAL_OWNER.value or self.user.role.code == "individual_owner"
            ):
                 data["individual_owner"] = {
                    "id": self.user.individual_owner.id,
                    "name": f"{self.user.individual_owner.first_name} {self.user.individual_owner.last_name}",
                }
        else:
            data["role"] = None

        return data


class PhoneTokenObtainPairRequestSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)


class PhoneTokenObtainPairResponseSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()
    role = serializers.CharField(required=False, allow_null=True)
    company = LoginProfileSummarySerializer(required=False, allow_null=True)
    individual_owner = LoginProfileSummarySerializer(required=False, allow_null=True)
    workspace = WorkspaceInfoSerializer(required=False, allow_null=True)


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class StaffResponseSerializer(serializers.ModelSerializer):
    workspace = serializers.SerializerMethodField()
    role = serializers.CharField(source="role.name")

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "workspace", "created_at"]

    @extend_schema_field(WORKSPACE_INFO_SCHEMA)
    def get_workspace(self, instance):
        return get_workspace_summary(instance.workspace)


class StaffCreateSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(write_only=True)
    workspace_type = serializers.ChoiceField(
        choices=["hotel", "guesthouse", "car_rental", "event_space"],
        write_only=True
    )
    phone = serializers.CharField(required=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone", "workspace_id", "workspace_type"]

    def validate_phone(self, value):
        normalized_phone = normalize_phone_number(value)
        if not normalized_phone:
            raise serializers.ValidationError("This field may not be blank.")
        if User.objects.filter(phone=normalized_phone).exists():
            raise serializers.ValidationError("A user with this phone already exists.")
        return normalized_phone

    def validate(self, attrs):
        from django.apps import apps
        request = self.context.get("request")
        user = request.user
        
        company = get_company_scope(user)
        individual_owner = get_individual_owner_scope(user)

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
            if model_class is None:
                raise LookupError
        except LookupError:
            raise serializers.ValidationError({"workspace_type": "Workspace type configuration is invalid."})

        try:
            workspace = model_class.objects.get(id=workspace_id)
        except model_class.DoesNotExist:
            raise serializers.ValidationError({"workspace_id": f"{model_name} not found."})

        if (
            workspace_type == "car_rental"
            and getattr(workspace, "listing_type", None) != model_class.ListingTypeChoices.RENT
        ):
            raise serializers.ValidationError(
                {"workspace_id": "Only rent car listings can be assigned as car-rental workspaces."}
            )
              
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
        if not email:
            email = build_placeholder_email(validated_data.get("phone"))
            validated_data["email"] = email
        
        role, _ = Role.objects.get_or_create(
            code=RoleCode.FRONT_DESK.value,
            defaults={"name": "Front Desk"},
        )

        password = generate_password(email or validated_data.get("phone"))
        
        user = User(
            role=role,
            is_active=True,
            company=get_company_scope(self.context["request"].user),
            individual_owner=get_individual_owner_scope(self.context["request"].user),
            workspace=workspace,
            **validated_data
        )
        
        from django.contrib.contenttypes.models import ContentType
        user.workspace_content_type = ContentType.objects.get_for_model(workspace)
        user.workspace_object_id = workspace.id
        user.set_password(password)
        user.save()
        
        try:
            send_sms(
                user.phone,
                (
                    f"Michot Marefiya staff account created. "
                    f"Phone: {user.phone}. Password: {password}"
                ),
            )
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send staff credentials to {user.phone}: {str(e)}")
        
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
    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["email", "password", "confirm_password", "first_name", "last_name", "phone"]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        normalized_phone = OtpService.normalize_phone(value)
        if normalized_phone and User.objects.filter(phone=normalized_phone).exists():
            raise serializers.ValidationError("A user with this phone already exists.")
        return normalized_phone

    def validate(self, attrs):
        if not attrs.get("phone"):
            raise serializers.ValidationError({"phone": "This field is required."})
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
        validated_data["email"] = validated_data.get("email") or build_placeholder_email(
            validated_data.get("phone")
        )
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
            self.otp_challenge = OtpService.create_challenge(
                phone=user.phone,
                purpose=OtpChallenge.Purpose.SIGNUP,
            )
        except Exception as exc:
            user.delete()
            raise serializers.ValidationError(
                {"phone": "Could not send signup OTP. Please try again."}
            ) from exc

        return user

    def to_representation(self, instance):
        data = UserResponseSerializer(instance, self.context).to_representation(instance)
        data["verification_required"] = "phone"
        data["phone_verification_required"] = bool(instance.phone and not instance.phone_verified_at)
        challenge = getattr(self, "otp_challenge", None)
        if challenge:
            data["otp_challenge_id"] = str(challenge.id)
            data["otp_expires_at"] = challenge.expires_at
            data["otp_purpose"] = challenge.purpose
        return data



class UserResponseSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True, allow_null=True)
    workspace = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    individual_owner = serializers.SerializerMethodField()
    phone_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "phone_verified",
            "phone_verified_at",
            "last_known_lat",
            "last_known_lng",
            "location_updated_at",
            "location_permission_granted",
            "is_active",
            "role",
            "company",
            "individual_owner",
            "workspace",
        ]

    @extend_schema_field(LoginProfileSummarySerializer(allow_null=True))
    def get_company(self, instance):
        company = getattr(instance, "profile", None) or getattr(instance, "company", None)
        if not company:
            return None
        return {
            "id": str(company.id),
            "name": company.name,
        }

    @extend_schema_field(LoginProfileSummarySerializer(allow_null=True))
    def get_individual_owner(self, instance):
        owner = getattr(instance, "individual_owner", None)
        if not owner:
            return None
        name = f"{owner.first_name} {owner.last_name}".strip()
        return {
            "id": str(owner.id),
            "name": name,
        }

    @extend_schema_field(WORKSPACE_INFO_SCHEMA)
    def get_workspace(self, instance):
        """Return workspace data for front desk users."""
        return get_workspace_summary(instance.workspace)


class UserUpdateSerializer(serializers.ModelSerializer):
    current_password = serializers.CharField(write_only=True, required=False)
    phone_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "phone_verified",
            "phone_verified_at",
            "current_password",
        ]
        extra_kwargs = {
            "email": {"required": False},
            "first_name": {"required": False},
            "last_name": {"required": False},
            "phone": {"required": False},
        }

    def validate_phone(self, value):
        normalized_phone = normalize_phone_number(value)

        if not normalized_phone:
            return normalized_phone

        if self.instance and normalize_phone_number(self.instance.phone) == normalized_phone:
            return normalized_phone

        existing_queryset = User.objects.filter(phone=normalized_phone)
        if self.instance:
            existing_queryset = existing_queryset.exclude(pk=self.instance.pk)

        if existing_queryset.exists():
            raise serializers.ValidationError("A user with this phone already exists.")

        if self.instance:
            self.instance.can_change_phone(normalized_phone)

        return normalized_phone

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
            
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com').rstrip('/')
            # Link format: /verify-email-change?uid=...&token=...&email=...
            # We'll use a custom View to verify the signer and then update.
            verification_url = f"{frontend_url}/auth/verify-email-change?uid={uid}&email={signed_email}"
            
            # 1. Send verification to NEW email
            EmailService.send_email_change_verification(instance, new_email, verification_url)
            
            # 2. Send security alert to OLD email
            EmailService.send_email_change_notice(instance, instance.email, new_email)
            
            # We can add a message to the response via context or just return instance
            # The view can inspect and tell user "Verification sent"
            
        return instance


class UserLocationSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    permission_granted = serializers.BooleanField(write_only=True)
    location_updated_at = serializers.DateTimeField(read_only=True)
    location_permission_granted = serializers.BooleanField(read_only=True)

    def validate_lat(self, value):
        if value < -90 or value > 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_lng(self, value):
        if value < -180 or value > 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def save(self, **kwargs):
        user = kwargs["user"]
        user.last_known_lat = self.validated_data["lat"]
        user.last_known_lng = self.validated_data["lng"]
        user.location_permission_granted = self.validated_data["permission_granted"]
        user.location_updated_at = timezone.now()
        user.save(
            update_fields=[
                "last_known_lat",
                "last_known_lng",
                "location_permission_granted",
                "location_updated_at",
                "updated_at",
            ]
        )
        return user

    def to_representation(self, instance):
        return {
            "lat": instance.last_known_lat,
            "lng": instance.last_known_lng,
            "location_updated_at": instance.location_updated_at,
            "location_permission_granted": instance.location_permission_granted,
        }


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    otp_challenge_id = serializers.UUIDField(write_only=True, required=False)
    otp_code = serializers.CharField(write_only=True, required=False, max_length=12, trim_whitespace=True)
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
        otp_challenge_id = attrs.get("otp_challenge_id")
        otp_code = attrs.get("otp_code")
        user = self.context.get("user")

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

        if otp_challenge_id or otp_code:
            if not otp_challenge_id or not otp_code:
                raise serializers.ValidationError(
                    {"otp_code": "Both otp_challenge_id and otp_code are required for OTP verification."}
                )
            try:
                OtpService.verify_challenge(
                    challenge_id=otp_challenge_id,
                    code=otp_code,
                    purpose=OtpChallenge.Purpose.PASSWORD_CHANGE,
                    user=user,
                )
            except OtpError as exc:
                raise serializers.ValidationError({"otp_code": str(exc)})
            return attrs

        if not current_password and not self.context.get("skip_current_password_check", False):
            raise serializers.ValidationError(
                {"current_password": "Current password or phone OTP verification is required."}
            )

        return attrs

    def save(self):
        user = self.context.get("user")
        user.set_password(self.validated_data["new_password"])
        user.save()
        
        try:
            NotificationService.create_notification(
                user=user,
                notification_type=Notification.NotificationType.PASSWORD_CHANGED,
                title="Password Changed",
                message="Your password has been successfully changed.",
                priority=Notification.Priority.HIGH
            )
        except Exception:
            pass

        return user


class GuestBookingConversionSerializer(serializers.Serializer):
    otp_challenge_id = serializers.UUIDField(write_only=True, required=False)
    otp_code = serializers.CharField(write_only=True, required=False, max_length=12, trim_whitespace=True)

    def validate(self, attrs):
        otp_challenge_id = attrs.get("otp_challenge_id")
        otp_code = attrs.get("otp_code")
        if bool(otp_challenge_id) != bool(otp_code):
            raise serializers.ValidationError(
                {"detail": "Both otp_challenge_id and otp_code are required together."}
            )
        return attrs

    def save(self):
        user = self.context["user"]
        try:
            return GuestBookingConversionService.convert_for_user(
                user=user,
                otp_challenge_id=self.validated_data.get("otp_challenge_id"),
                otp_code=self.validated_data.get("otp_code"),
            )
        except (GuestBookingConversionError, OtpError) as exc:
            raise serializers.ValidationError({"detail": str(exc)})


class PasswordResetSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        normalized_phone = OtpService.normalize_phone(value)
        self.user = User.objects.filter(phone=normalized_phone, is_active=True).first()
        return normalized_phone

    def save(self):
        if not getattr(self, 'user', None):
            return

        self.challenge = OtpService.create_challenge(
            phone=self.user.phone,
            purpose=OtpChallenge.Purpose.PASSWORD_CHANGE,
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    code = serializers.CharField(max_length=12, trim_whitespace=True)
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
            result = OtpService.verify_challenge(
                challenge_id=attrs["challenge_id"],
                code=attrs["code"],
                purpose=OtpChallenge.Purpose.PASSWORD_CHANGE,
            )
        except OtpError as exc:
            raise serializers.ValidationError({"code": str(exc)}) from exc

        if not result.user:
            raise serializers.ValidationError({"code": "Invalid OTP challenge or code."})
        self.user = result.user

        return attrs

    def save(self):
        self.user.set_password(self.validated_data['new_password'])
        self.user.save()
        
        try:
            NotificationService.create_notification(
                user=self.user,
                notification_type=Notification.NotificationType.PASSWORD_CHANGED,
                title="Password Reset Successful",
                message="Your password has been successfully reset.",
                priority=Notification.Priority.HIGH
            )
        except Exception:
            pass

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
        
        try:
            NotificationService.create_notification(
                user=self.user,
                notification_type=Notification.NotificationType.EMAIL_VERIFIED,
                title="Email Verified",
                message="Your email address has been successfully verified.",
                priority=Notification.Priority.MEDIUM
            )
        except Exception:
            pass
            
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
        
        try:
            NotificationService.create_notification(
                user=self.user,
                notification_type=Notification.NotificationType.EMAIL_VERIFIED,
                title="Email Address Changed",
                message=f"Your email address has been updated to {self.new_email}.",
                priority=Notification.Priority.MEDIUM
            )
        except Exception:
            pass

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

        user = User(email=email, role=role, phone=validated_data.get("phone"))
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

        try:
            send_sms(
                user.phone,
                (
                    f"Michot Marefiya company account created. "
                    f"Phone: {user.phone}. Password: {password}"
                ),
            )
        except Exception as exc:
            logging.getLogger(__name__).error(
                "Failed to send company credentials by SMS to %s: %s",
                user.phone,
                exc,
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
    agreement_status = serializers.SerializerMethodField()

    class Meta:
        model = IndividualOwnerProfile
        fields = [
            "id",
            "national_id_number",
            "first_name",
            "last_name",
            "address",
            "phone",
            "agreement_status",
            # "category"
        ]

    @extend_schema_field(
        inline_serializer(
            "IndividualOwnerAgreementStatus",
            fields={
                "status": serializers.ChoiceField(choices=OwnerComplianceAgreement.Status.choices),
                "signed_at": serializers.DateTimeField(allow_null=True),
            },
        )
    )
    def get_agreement_status(self, instance):
        agreement = get_latest_agreement(instance)
        if not agreement:
            return None
        return AgreementStatusSerializer(agreement).data


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


class AgreementStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerComplianceAgreement
        fields = ["status", "signed_at"]
        read_only_fields = fields


class OwnerComplianceAgreementReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerComplianceAgreement
        fields = ["status", "signed_at", "agreement_version", "agreement_document"]
        read_only_fields = fields


class OwnerComplianceAgreementSerializer(serializers.ModelSerializer):
    signed_by_admin = serializers.UUIDField(source="signed_by_admin_id", read_only=True, allow_null=True)

    class Meta:
        model = OwnerComplianceAgreement
        fields = [
            "id",
            "status",
            "signed_at",
            "signed_by_admin",
            "agreement_version",
            "agreement_document",
            "note",
        ]
        read_only_fields = ["id", "signed_at", "signed_by_admin"]


class OwnerComplianceAgreementCreateSerializer(serializers.Serializer):
    agreement_version = serializers.CharField(max_length=50)
    agreement_document = serializers.FileField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)


class OwnerComplianceAgreementPatchSerializer(serializers.Serializer):
    agreement_version = serializers.CharField(max_length=50, required=False)
    agreement_document = serializers.FileField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)


class OwnerComplianceAgreementRevokeSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class HotelProfileResponseSerializer(serializers.ModelSerializer):
    company = CompanyProfileResponseSerializer()
    images = ListingImageSerializer(many=True)
    address = AddressSerializer(allow_null=True)
    facilities = FacilityResponseSerializer(many=True)
    is_favorite = serializers.SerializerMethodField()
    verified_by = serializers.UUIDField(source="verified_by_id", read_only=True, allow_null=True)

    class Meta:
        model = HotelProfile
        fields = [
            "id",
            "name",
            "description",
            "phone",
            "website",
            "address",
            "company",
            "images",
            "logo",
            "license",
            "latitude",
            "longitude",
            "formatted_address",
            "place_id",
            "stars",
            "featured",
            "is_active",
            "facilities",
            "is_favorite",
            "is_verified",
            "verified_at",
            "verified_by",
            "verification_note",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        company_data = rep.get("company", {}) or {}
        flattened_company = {
            key: value
            for key, value in company_data.items()
            if key not in {"id", "name", "phone", "description", "address"}
        }
        flattened_company.update(
            {
                "company_name": company_data.get("name"),
                "company_phone": company_data.get("phone"),
                "company_description": company_data.get("description"),
                "company_address": company_data.get("address"),
            }
        )
        return {**flattened_company, **rep}

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
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
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
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        normalized_phone = OtpService.normalize_phone(value)
        if normalized_phone and User.objects.filter(phone=normalized_phone).exists():
            raise serializers.ValidationError("A user with this phone already exists.")
        return normalized_phone

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, attrs):
        if not attrs.get("phone"):
            raise serializers.ValidationError({"phone": "This field is required."})
        if attrs.get("password") != attrs.get("confirm_password"):
             raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    @transaction.atomic()
    def create(self, validated_data):
        email = validated_data.pop("email", "") or build_placeholder_email(validated_data.get("phone"))
        first_name = validated_data.pop("first_name")
        last_name = validated_data.pop("last_name")
        password = validated_data.pop("password")
        validated_data.pop("confirm_password")
        phone = validated_data.get("phone")
        address_data = validated_data.pop("address")
        
        try:
            role = Role.objects.get(code=RoleCode.COMPANY.value)
        except Role.DoesNotExist:
             raise serializers.ValidationError({"error": "Role configuration error."})

        user = User.objects.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
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

        try:
            self.otp_challenge = OtpService.create_challenge(
                phone=user.phone,
                purpose=OtpChallenge.Purpose.SIGNUP,
            )
        except Exception as exc:
            user.delete()
            raise serializers.ValidationError(
                {"phone": "Could not send signup OTP. Please try again."}
            ) from exc
        
        return profile

    def _send_verification(self, user):
        try:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com').rstrip('/')
            activation_url = f"{frontend_url}/auth/verify-email?uid={uid}&token={token}"
            EmailService.send_verification_email(user, activation_url)
        except Exception:
            pass

    def to_representation(self, instance):
        data = CompanyProfileResponseSerializer(instance, context=self.context).to_representation(instance)
        data["verification_required"] = "phone"
        data["phone_verification_required"] = bool(
            instance.user.phone and not instance.user.phone_verified_at
        )
        challenge = getattr(self, "otp_challenge", None)
        if challenge:
            data["otp_challenge_id"] = str(challenge.id)
            data["otp_expires_at"] = challenge.expires_at
            data["otp_purpose"] = challenge.purpose
        return data


class IndividualOwnerRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
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
        if value and User.objects.filter(email=value).exists():
             raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
        
    def validate(self, attrs):
        if not attrs.get("phone"):
            raise serializers.ValidationError({"phone": "This field is required."})
        if attrs.get("password") != attrs.get("confirm_password"):
             raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    @transaction.atomic()
    def create(self, validated_data):
        email = validated_data.pop("email", "") or build_placeholder_email(validated_data.get("phone"))
        password = validated_data.pop("password")
        validated_data.pop("confirm_password")
        
        first_name = validated_data.get("first_name")
        last_name = validated_data.get("last_name")
        address_data = validated_data.pop("address")
        
        try:
            role = Role.objects.get(code=RoleCode.INDIVIDUAL_OWNER.value)
        except Role.DoesNotExist:
             raise serializers.ValidationError({"error": "Role configuration error."})

        user = User.objects.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=validated_data.get("phone"),
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
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com').rstrip('/')
            activation_url = f"{frontend_url}/auth/verify-email?uid={uid}&token={token}"
            EmailService.send_verification_email(user, activation_url)
        except Exception:
            pass

    def to_representation(self, instance):
        return IndividualOwnerProfileResponseSerializer(instance, context=self.context).to_representation(instance)


class HotelProfileSerializer(PlaceResolutionMixin, serializers.ModelSerializer):
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
            "place_id",
            "session_token",
        ]

    def validate_address(self, attr):
        serializer = AddressSerializer(data=attr)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, data):
        return self._resolve_place_detail(data)

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
        self._pop_session_token(validated_data)
        skip_async_geocoding = self._pop_skip_async_geocoding(validated_data)
        validated_data.setdefault("is_active", True)
        
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

        ListingService.schedule_geocoding(hotel, should_dispatch=not skip_async_geocoding)

        return hotel

    @transaction.atomic()
    def update(self, instance, validated_data):
        self._pop_session_token(validated_data)
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


class OtpRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    purpose = serializers.ChoiceField(
        choices=OtpChallenge.Purpose.choices,
        default=OtpChallenge.Purpose.LOGIN,
        required=False,
    )

    def validate(self, attrs):
        purpose = attrs.get("purpose", OtpChallenge.Purpose.LOGIN)
        allowed_purposes = {choice for choice, _label in OtpChallenge.Purpose.choices}
        if purpose not in allowed_purposes:
            raise serializers.ValidationError({"purpose": "Unsupported OTP purpose."})
        return attrs

    def save(self):
        try:
            self.challenge = OtpService.create_challenge(
                phone=self.validated_data["phone"],
                purpose=self.validated_data.get("purpose", OtpChallenge.Purpose.LOGIN),
            )
        except OtpError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        return self.challenge


class OtpResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    challenge_id = serializers.UUIDField()
    challenge_token = serializers.UUIDField()
    purpose = serializers.CharField()
    expires_at = serializers.DateTimeField()
    cooldown_seconds = serializers.IntegerField()
    phone = serializers.CharField()


class OtpVerifyResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    purpose = serializers.CharField()
    user = serializers.DictField(required=False, allow_null=True)
    access = serializers.CharField(required=False)
    refresh = serializers.CharField(required=False)
    role = serializers.CharField(required=False, allow_null=True)
    guest_verification_token = serializers.CharField(required=False)
    guest_history_transfer = serializers.DictField(required=False)


class OtpVerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField(required=False)
    challenge_token = serializers.UUIDField(required=False)
    code = serializers.CharField(max_length=12, trim_whitespace=True)
    purpose = serializers.ChoiceField(
        choices=OtpChallenge.Purpose.choices,
        default=OtpChallenge.Purpose.LOGIN,
        required=False,
    )

    def validate(self, attrs):
        challenge_id = attrs.get("challenge_id") or attrs.get("challenge_token")
        if not challenge_id:
            raise serializers.ValidationError({"challenge_token": "challenge_id or challenge_token is required."})
        purpose = attrs.get("purpose", OtpChallenge.Purpose.LOGIN)
        issue_tokens = purpose in {
            OtpChallenge.Purpose.LOGIN,
            OtpChallenge.Purpose.SIGNUP,
        }
        try:
            self.result = OtpService.verify_challenge(
                challenge_id=challenge_id,
                code=attrs["code"],
                purpose=purpose,
                issue_tokens=issue_tokens,
            )
        except OtpError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        attrs["challenge_id"] = challenge_id
        return attrs
