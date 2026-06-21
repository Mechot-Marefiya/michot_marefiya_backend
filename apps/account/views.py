from django.db.models import Sum, Q
from django.utils.dateparse import parse_date
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, serializers, viewsets
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from django.conf import settings
from django.utils import timezone
import logging
import traceback
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiExample, OpenApiResponse
from apps.listing.models import Booking, RoomListing, AddonOffering
from apps.listing.services import StayAvailabilityService, verify_listing, unverify_listing
from apps.account.docs.schemas import HotelProfileDocSerializer
from apps.account.filters import HotelFilter
from apps.core.views import AbstractModelViewSet
from apps.account.docs.schemas import check__room_availability_schema
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    OtpChallenge,
    OwnerComplianceAgreement,
    User,
)
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from django.contrib.contenttypes.models import ContentType
from apps.favorites.services import get_favorite_object_ids
from apps.account.models import Role
from apps.account.serializers import (
    CompanyProfileResponseSerializer,
    CustomTokenObtainPairSerializer,
    HotelProfileSerializer,
    HotelRoomAvailabilitySerializer,
    IndividualOwnerProfileResponseSerializer,
    IndividualOwnerProfileSerializer,
    UserSerializer,
    CompanyProfileSerializer,
    CompanyApplicationSerializer,
    UserResponseSerializer,
    UserUpdateSerializer,
    UserResponseSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    GuestBookingConversionSerializer,
    StaffCreateSerializer,
    ChangePasswordSerializer,
    StaffCreateSerializer,
    StaffResponseSerializer,
    PasswordResetSerializer,
    PasswordResetConfirmSerializer,
    VerifyEmailSerializer,
    VerifyEmailChangeSerializer,
    CompanyRegistrationSerializer,
    IndividualOwnerRegistrationSerializer,
    OtpRequestSerializer,
    OtpResponseSerializer,
    OtpVerifyResponseSerializer,
    OtpVerifySerializer,
    LogoutRequestSerializer,
    PhoneTokenObtainPairRequestSerializer,
    PhoneTokenObtainPairResponseSerializer,
    UserLocationSerializer,
    OwnerComplianceAgreementCreateSerializer,
    OwnerComplianceAgreementPatchSerializer,
    OwnerComplianceAgreementReadSerializer,
    OwnerComplianceAgreementRevokeSerializer,
    OwnerComplianceAgreementSerializer,
    RoleSerializer,
)
from apps.account.utils import get_workspace_catalog_entry
from apps.listing.serializers import AddonOfferingListSerializer, VerifyActionSerializer
from apps.account.enums import RoleCode
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.account.permissions import (
    IsAuthenticatedOrReadOnly,
    IsOwnerOrReadOnly,
    IsAdmin,
    IsCompanyOwner,
    IsCompanyOrIndividualOwner,
    IsPublicReadOnly,
)
from apps.account.services import (
    GuestBookingConversionError,
    GuestBookingConversionService,
    GuestPhoneVerificationService,
    create_agreement,
    get_latest_agreement,
    revoke_agreement,
    sign_agreement,
)
def _set_listing_activation(instance, *, active):
    instance.is_active = active
    instance.save(update_fields=["is_active", "updated_at"])


@extend_schema(tags=["Identity & Auth"])
class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_login'
    serializer_class = CustomTokenObtainPairSerializer

    @extend_schema(
        summary="Obtain JWT Token",
        description="Obtain JWT tokens with phone and password.",
        request=PhoneTokenObtainPairRequestSerializer,
        responses={
            200: PhoneTokenObtainPairResponseSerializer,
            401: OpenApiTypes.OBJECT
        }
    )
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except serializers.ValidationError:
            raise
        except Exception as exc:
            logging.exception("Error during token obtain")

            if getattr(settings, "DEBUG", False):
                return Response(
                    {
                        "detail": "Invalid phone or password.",
                        "error": str(exc),
                        "trace": traceback.format_exc(),
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            return Response({"detail": "Invalid phone or password."}, status=status.HTTP_401_UNAUTHORIZED)


@extend_schema(tags=["Identity & Auth"])
class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []
    serializer_class = OtpRequestSerializer

    @extend_schema(
        summary="Request phone OTP",
        description="Send a phone OTP for login or password-change verification.",
        request=OtpRequestSerializer,
        responses={200: OtpResponseSerializer, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = OtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        challenge = serializer.save()
        return Response(
            {
                "success": True,
                "challenge_id": str(challenge.id),
                "challenge_token": str(challenge.id),
                "purpose": challenge.purpose,
                "expires_at": challenge.expires_at,
                "cooldown_seconds": 0,
                "phone": challenge.phone,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Identity & Auth"])
class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_verify"
    serializer_class = OtpVerifySerializer

    @extend_schema(
        summary="Verify phone OTP",
        description="Verify a phone OTP. Login challenges return JWT access and refresh tokens.",
        request=OtpVerifySerializer,
        responses={200: OtpVerifyResponseSerializer, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.result
        data = {
            "success": True,
            "purpose": result.challenge.purpose,
            "user": (
                UserResponseSerializer(result.user, context={"request": request}).data
                if result.user
                else None
            ),
        }
        if result.tokens:
            data.update(result.tokens)
            if result.user.role:
                data["role"] = result.user.role.code
        if result.user and result.challenge.purpose == OtpChallenge.Purpose.SIGNUP:
            try:
                conversion = GuestBookingConversionService.convert_for_user(user=result.user)
                data["guest_history_transfer"] = {
                    "success": True,
                    "phone": conversion.phone,
                    "verified_via": conversion.verified_via,
                    "linked_counts": conversion.linked_counts,
                    "already_linked_counts": conversion.already_linked_counts,
                    "linked_total": conversion.linked_total,
                    "already_linked_total": conversion.already_linked_total,
                }
            except GuestBookingConversionError as exc:
                data["guest_history_transfer"] = {
                    "success": False,
                    "detail": str(exc),
                }
        if result.user is None:
            data["guest_verification_token"] = GuestPhoneVerificationService.create_token(
                result.challenge.phone
            )
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(tags=["Account"])
class UserLocationView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserLocationSerializer

    @extend_schema(
        summary="Store user location",
        description="Persist the latest client-reported location for proximity-aware experiences.",
        request=UserLocationSerializer,
        responses={200: UserLocationSerializer, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = UserLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save(user=request.user)
        return Response(UserLocationSerializer(user).data, status=status.HTTP_200_OK)


@extend_schema(tags=["Identity & Auth"])
class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token_refresh'



@extend_schema(tags=["Identity & Auth"])
class LogoutView(APIView):

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token_blacklist'

    @extend_schema(
        summary="Logout (Blacklist token)",
        description="Blacklist a refresh token to end the session.",
        request=LogoutRequestSerializer,
        responses={200: OpenApiResponse(description="Refresh token blacklisted."), 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_200_OK)
        except Exception:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Account Management"])
class StaffViewSet(viewsets.ModelViewSet):
    permission_classes = [IsCompanyOrIndividualOwner]
    serializer_class = StaffResponseSerializer
    http_method_names = ['get', 'post', 'delete']
    throttle_scope = 'token_blacklist'

    def get_queryset(self):
        qs = User.objects.filter(role__code=RoleCode.FRONT_DESK.value).select_related(
            'role', 'company', 'individual_owner', 'workspace_content_type'
        )

        if getattr(self, "swagger_fake_view", False):
            return qs.none()

        user = self.request.user
        if not getattr(user, "is_authenticated", False):
            return qs.none()
        
        if user.company:
            return qs.filter(company=user.company)
        elif user.individual_owner:
            return qs.filter(individual_owner=user.individual_owner)
            
        return qs.none() 

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffCreateSerializer
        return StaffResponseSerializer

    def perform_create(self, serializer):
        # Automated owner assignment happens in StaffCreateSerializer.create
        serializer.save()
    
    @action(detail=False, methods=['get'], url_path='available-workspaces')
    def available_workspaces(self, request):
        user = request.user
        workspaces = []
        from apps.listing.models import CarListing, EventSpaceListing, GuestHouseProfile
        
        if user.company:
            hotels = HotelProfile.objects.filter(company=user.company)
            for hotel in hotels:
                workspaces.append(get_workspace_catalog_entry(hotel))

            guesthouses = GuestHouseProfile.objects.filter(company=user.company)
            for gh in guesthouses:
                workspaces.append(get_workspace_catalog_entry(gh))

            cars = CarListing.objects.filter(
                company=user.company,
                listing_type=CarListing.ListingTypeChoices.RENT,
            )
            for car in cars:
                workspaces.append(get_workspace_catalog_entry(car))

            event_spaces = EventSpaceListing.objects.filter(hotel__company=user.company)
            for event_space in event_spaces:
                workspaces.append(get_workspace_catalog_entry(event_space))
        
        elif user.individual_owner:
            guesthouses = GuestHouseProfile.objects.filter(individual_owner=user.individual_owner)
            for gh in guesthouses:
                workspaces.append(get_workspace_catalog_entry(gh))
            
            cars = CarListing.objects.filter(
                individual_owner=user.individual_owner,
                listing_type=CarListing.ListingTypeChoices.RENT,
            )
            for car in cars:
                workspaces.append(get_workspace_catalog_entry(car))
        
        return Response([workspace for workspace in workspaces if workspace])


@extend_schema(tags=["Account Management"])
class RoleViewSet(AbstractModelViewSet):
    serializer_class = RoleSerializer
    queryset = Role.objects.all().order_by("name")
    permission_classes = [IsAdmin]



@extend_schema(tags=["Identity & Auth"])
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Current user profile (legacy)",
        description="Retrieve the profile of the currently authenticated user.",
        responses={200: UserResponseSerializer}
    )
    def get(self, request, *args, **kwargs):
        serializer = UserResponseSerializer(request.user)
        return Response(serializer.data)


@extend_schema(tags=["Identity & Auth"])
class UserViewSet(AbstractModelViewSet):
    queryset = User.objects.all()
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_register'

    def get_serializer_class(self):
        if self.action == 'create':
            return UserSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        elif self.action == 'change_password':
            return ChangePasswordSerializer
        elif self.action == 'convert_guest_bookings':
            return GuestBookingConversionSerializer
        return UserResponseSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['me', 'change_password', 'convert_guest_bookings']:
            return [IsAuthenticated()]
        else:
            return [IsOwnerOrReadOnly()]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.none()
        
        if self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and
            self.request.user.role and
            self.request.user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        return queryset.filter(id=self.request.user.id)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if request.user == instance:
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        if request.user.is_superuser or (
            hasattr(request.user, 'role') and
            request.user.role and
            request.user.role.code == RoleCode.ADMIN.value
        ):
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response({"detail": "Not allowed to delete this user."}, status=status.HTTP_403_FORBIDDEN)

    @extend_schema(
        summary="Current user profile",
        description=(
            "Retrieve or update the authenticated user's profile. "
            "Phone updates are rate-limited to three total changes with a seven-day cooldown between changes."
        ),
        request=UserUpdateSerializer,
        responses={200: UserResponseSerializer, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Phone cooldown error",
                value={"phone": ["Phone number can only be changed once every 7 days. Please try again later."]},
                status_codes=["400"],
            ),
            OpenApiExample(
                "Phone limit error",
                value={"phone": ["Phone number can only be changed three times. Please contact support if you need help."]},
                status_codes=["400"],
            ),
        ],
    )
    @action(detail=False, methods=['get', 'patch', 'put', 'delete'], url_path='me')
    def me(self, request):
        if request.method == 'GET':
            serializer = UserResponseSerializer(request.user, context=self.get_serializer_context())
            return Response(serializer.data)
        
        if request.method == 'DELETE':
            try:
                request.user.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except Exception as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=request.method == 'PATCH',
            context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='me/change-password')
    def change_password(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'user': request.user, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Convert guest bookings to the current account",
        description=(
            "Link historical guest bookings that match the authenticated user's phone number. "
            "If the user's phone is already verified, no OTP payload is required. "
            "Legacy accounts can provide a login OTP challenge and code to prove phone ownership."
        ),
        request=GuestBookingConversionSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['post'], url_path='me/convert-guest-bookings')
    def convert_guest_bookings(self, request):
        serializer = GuestBookingConversionSerializer(
            data=request.data,
            context={'user': request.user, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {
                "success": True,
                "phone": result.phone,
                "verified_via": result.verified_via,
                "linked_counts": result.linked_counts,
                "already_linked_counts": result.already_linked_counts,
                "linked_total": result.linked_total,
                "already_linked_total": result.already_linked_total,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='change-password')
    def change_password_for_user(self, request, pk=None):
        instance = self.get_object()
        
        is_admin = request.user.is_superuser or (
            hasattr(request.user, 'role') and
            request.user.role and
            request.user.role.code == RoleCode.ADMIN.value
        )
        
        if not is_admin:
            if request.user != instance:
                return Response(
                    {"detail": "You can only change your own password."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        skip_current_check = is_admin and request.user != instance
        
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={
                'user': instance,
                'request': request,
                'skip_current_password_check': skip_current_check
            }
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)


@extend_schema(responses=CompanyProfileResponseSerializer)
@extend_schema(tags=["Identity & Auth"])
class CompanyProfileViewSet(AbstractModelViewSet):
    serializer_class = CompanyProfileSerializer
    queryset = CompanyProfile.objects.all()
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_register'

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [AllowAny()]
        else:
            return [IsCompanyOwner()]

    def get_serializer_class(self):
        if self.action == 'create':
            return CompanyRegistrationSerializer
        return CompanyProfileSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        
        managed_only = self.request.query_params.get('managed') == 'true'
        user = self.request.user

        if managed_only and user and user.is_authenticated:
            if hasattr(user, 'profile'):
                queryset = queryset.filter(user=user)
            elif hasattr(user, 'company') and user.company:
                queryset = queryset.filter(id=user.company.id)
            else:
                queryset = queryset.none()
                
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # resolve favorites for hotel responses
        try:
            ct = ContentType.objects.get(app_label="account", model="hotelprofile")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(self.request.user, ct) if ct is not None else set()
        context["favorite_object_ids"] = fav_ids
        return context

    @action(detail=False, methods=["post"], url_path="apply", permission_classes=[IsAuthenticated])
    def apply(self, request):
        """Authenticated users apply to create a company profile (status=PENDING)."""
        serializer = CompanyApplicationSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        
        NotificationService.notify_admins(
            notification_type=Notification.NotificationType.NEW_COMPANY_REGISTRATION,
            title="New Company Registration",
            message=f"New company '{profile.name}' registered by {profile.user.email}.",
            metadata={
                'company_name': profile.name,
                'company_id': str(profile.id),
                'owner_email': profile.user.email
            },
            priority=Notification.Priority.MEDIUM
        )
            
        return Response(CompanyProfileResponseSerializer(profile).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="approve", permission_classes=[IsAdmin])
    def approve(self, request, pk=None):
        profile = self.get_object()
        if profile.status == CompanyProfile.StatusChoice.APPROVED:
            return Response({"detail": "Profile already approved."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            role = Role.objects.get(code=RoleCode.COMPANY.value)
        except Role.DoesNotExist:
            return Response({"detail": "Company role not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        profile.status = CompanyProfile.StatusChoice.APPROVED
        profile.approved_at = timezone.now()
        profile.approved_by = request.user
        profile.save()

        # Promote the user to company role
        profile.user.role = role
        profile.user.save()

        NotificationService.create_notification(
            user=profile.user,
            notification_type=Notification.NotificationType.COMPANY_APPROVED,
            title="Company Profile Approved",
            message=f"Your company profile '{profile.name}' has been approved. You can now start adding listings.",
            metadata={
                'company_name': profile.name,
                'approved_at': str(profile.approved_at)
            },
            priority=Notification.Priority.HIGH
        )

        return Response(CompanyProfileResponseSerializer(profile).data)

    @action(detail=True, methods=["post"], url_path="reject", permission_classes=[IsAdmin])
    def reject(self, request, pk=None):
        profile = self.get_object()
        if profile.status == CompanyProfile.StatusChoice.REJECTED:
            return Response({"detail": "Profile already rejected."}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("reason")
        profile.status = CompanyProfile.StatusChoice.REJECTED
        profile.rejection_reason = reason
        profile.approved_by = request.user
        profile.approved_at = timezone.now()
        profile.save()

        NotificationService.create_notification(
            user=profile.user,
            notification_type=Notification.NotificationType.COMPANY_REJECTED,
            title="Company Profile Rejected",
            message=f"Your company profile '{profile.name}' has been rejected. Reason: {reason}",
            metadata={
                'company_name': profile.name,
                'rejection_reason': reason
            },
            priority=Notification.Priority.HIGH
        )

        return Response(CompanyProfileResponseSerializer(profile).data)


@extend_schema(responses=IndividualOwnerProfileResponseSerializer)
@extend_schema(tags=["Identity & Auth"])
class IndividualOwnerProfileViewSet(AbstractModelViewSet):
    serializer_class = IndividualOwnerProfileSerializer
    queryset = IndividualOwnerProfile.objects.all()
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_register'

    def get_permissions(self):
        if self.action == 'create':
            return [IsAdmin()]
        elif self.action in ["agreement", "sign_agreement", "revoke_agreement"]:
            if self.request.method == "GET":
                return [IsAuthenticated()]
            return [IsAdmin()]
        elif self.action in ['list', 'retrieve']:
            return [AllowAny()]
        else:
            return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return IndividualOwnerProfileSerializer
        return IndividualOwnerProfileSerializer

    def get_queryset(self):
        return super().get_queryset()

    def _can_view_owner_agreement(self, request, owner):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or (hasattr(user, "role") and user.role and user.role.code == RoleCode.ADMIN.value):
            return True
        return getattr(user, "individual_owner_id", None) == owner.id

    @extend_schema(
        request=OwnerComplianceAgreementCreateSerializer,
        responses={200: OwnerComplianceAgreementSerializer, 201: OwnerComplianceAgreementSerializer},
    )
    @action(detail=True, methods=["get", "post", "patch"], url_path="agreement")
    def agreement(self, request, pk=None):
        owner = self.get_object()
        agreement = get_latest_agreement(owner)

        if request.method == "GET":
            if not self._can_view_owner_agreement(request, owner):
                return Response({"detail": "You do not have permission to view this agreement."}, status=status.HTTP_403_FORBIDDEN)
            if not agreement:
                return Response({"detail": "Compliance agreement not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer_class = (
                OwnerComplianceAgreementSerializer
                if (request.user.is_superuser or (hasattr(request.user, "role") and request.user.role and request.user.role.code == RoleCode.ADMIN.value))
                else OwnerComplianceAgreementReadSerializer
            )
            return Response(serializer_class(agreement).data, status=status.HTTP_200_OK)

        if request.method == "POST":
            serializer = OwnerComplianceAgreementCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            agreement = create_agreement(
                owner,
                request.user,
                serializer.validated_data["agreement_version"],
                note=serializer.validated_data.get("note"),
            )
            return Response(OwnerComplianceAgreementSerializer(agreement).data, status=status.HTTP_201_CREATED)

        if not agreement:
            return Response({"detail": "Compliance agreement not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = OwnerComplianceAgreementPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed_fields = []
        if "agreement_version" in serializer.validated_data:
            agreement.agreement_version = serializer.validated_data["agreement_version"]
            changed_fields.append("agreement_version")
        if "note" in serializer.validated_data:
            agreement.note = serializer.validated_data["note"]
            changed_fields.append("note")
        if changed_fields:
            changed_fields.append("updated_at")
            agreement.save(update_fields=changed_fields)
        return Response(OwnerComplianceAgreementSerializer(agreement).data, status=status.HTTP_200_OK)

    @extend_schema(
        responses={200: OwnerComplianceAgreementSerializer},
    )
    @action(detail=True, methods=["post"], url_path="agreement/sign", permission_classes=[IsAdmin])
    def sign_agreement(self, request, pk=None):
        owner = self.get_object()
        agreement = get_latest_agreement(owner)
        if not agreement:
            return Response({"detail": "Compliance agreement not found."}, status=status.HTTP_404_NOT_FOUND)
        agreement = sign_agreement(agreement, request.user)
        return Response(OwnerComplianceAgreementSerializer(agreement).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=OwnerComplianceAgreementRevokeSerializer,
        responses={200: OwnerComplianceAgreementSerializer},
    )
    @action(detail=True, methods=["post"], url_path="agreement/revoke", permission_classes=[IsAdmin])
    def revoke_agreement(self, request, pk=None):
        owner = self.get_object()
        agreement = get_latest_agreement(owner)
        if not agreement:
            return Response({"detail": "Compliance agreement not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = OwnerComplianceAgreementRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agreement = revoke_agreement(agreement, request.user, note=serializer.validated_data.get("note"))
        return Response(OwnerComplianceAgreementSerializer(agreement).data, status=status.HTTP_200_OK)


@extend_schema(tags=["Identity & Auth"])
class OwnerProfileAgreementView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OwnerComplianceAgreementReadSerializer, 404: OpenApiTypes.OBJECT})
    def get(self, request):
        owner = getattr(request.user, "individual_owner", None)
        if owner is None:
            return Response({"detail": "No associated individual owner profile found."}, status=status.HTTP_404_NOT_FOUND)
        agreement = get_latest_agreement(owner)
        if not agreement:
            return Response({"detail": "Compliance agreement not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OwnerComplianceAgreementReadSerializer(agreement).data, status=status.HTTP_200_OK)


@extend_schema(responses=HotelProfileDocSerializer)
@extend_schema(tags=["Accommodations"])
class HotelProfileViewSet(AbstractModelViewSet):
    serializer_class = HotelProfileSerializer
    queryset = HotelProfile.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = HotelFilter
    throttle_scope = None

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'check_availability', 'get_featured_hotels']:
            return [AllowAny()]
        if self.action in ["verify", "unverify", "activate", "deactivate"]:
            return [IsAdmin()]
        else:
            return [IsCompanyOwner()]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        notification_plan = NotificationService.prepare_saved_listing_deletion_notifications(
            instance,
            deleted_by=request.user,
        )
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == status.HTTP_204_NO_CONTENT:
            NotificationService.dispatch_saved_listing_deletion_notifications(notification_plan)
        return response

    def get_queryset(self):
        queryset = super().get_queryset()
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            pass
        elif managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            
            q = Q()
            if company:
                q |= Q(company=company)
            
            queryset = queryset.filter(q)

        if self.action in ['list', 'retrieve', 'get_featured_hotels']:
            if not managed_only and not (
                user
                and user.is_authenticated
                and (
                    user.is_superuser
                    or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)
                )
            ):
                queryset = queryset.filter(is_active=True)
            queryset = queryset.select_related(
                "company",
                "company__user",
                "company__user__role",
                "company__address",
                "company__approved_by",
            ).prefetch_related(
                "facilities",
                "images"
            )
            
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # resolve favorites for hotel responses
        try:
            ct = ContentType.objects.get(app_label="account", model="hotelprofile")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(self.request.user, ct) if ct is not None else set()
        context["favorite_object_ids"] = fav_ids
        return context

    @check__room_availability_schema
    @action(
        detail=True, 
        methods=["get"], 
        serializer_class=HotelRoomAvailabilitySerializer,
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def check_availability(self, request, pk=None):
        """
        Check room availability for a hotel between check-in and check-out dates.
        Expects check_in_date and check_out_date in the request params.
        """
        hotel = self.get_object()

        check_in_date = request.query_params.get("check_in_date")
        check_out_date = request.query_params.get("check_out_date")

        if not check_in_date or not check_out_date:
            return Response(
                {"detail": "check_in_date and check_out_date are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        check_in_date = parse_date(check_in_date)
        check_out_date = parse_date(check_out_date)

        if not check_in_date or not check_out_date:
            return Response(
                {"detail": "Invalid date format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if check_out_date <= check_in_date:
            return Response(
                {"detail": "Check-out date must be after check-in date."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rooms, availability_data = StayAvailabilityService.get_available_rooms(
            hotel, check_in_date, check_out_date
        )

        availability_map = {row["room"]: row["min_available"] for row in availability_data}

        results = []
        for room in rooms:
            available_units = availability_map.get(room.id, 0)
            results.append(
                {
                    "room_id": room.id,
                    "name": room.title,
                    "available_units": available_units,
                }
            )

        return Response(
            {
                "hotel_id": hotel.id,
                "check_in": check_in_date.isoformat(),
                "check_out": check_out_date.isoformat(),
                "rooms": results,
            }
        )
    @action(
        detail=False,
        methods=["get"],
        serializer_class=HotelProfileSerializer,
        url_path='featured',
    )
    def get_featured_hotels(self, request):
        featured_hotels = HotelProfile.objects.filter(featured=True, is_active=True)
        serializer = self.get_serializer(featured_hotels, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: HotelProfileSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        hotel = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            hotel,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = self.get_serializer(hotel)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: HotelProfileSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        hotel = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(hotel, request.user)
        serializer = self.get_serializer(hotel)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="activate", permission_classes=[IsAdmin])
    def activate(self, request, pk=None):
        hotel = self.get_object()
        _set_listing_activation(hotel, active=True)
        serializer = self.get_serializer(hotel)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="deactivate", permission_classes=[IsAdmin])
    def deactivate(self, request, pk=None):
        hotel = self.get_object()
        _set_listing_activation(hotel, active=False)
        serializer = self.get_serializer(hotel)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="List addons for this hotel",
        description="Returns all active addon offerings provided by this hotel.",
        responses={200: AddonOfferingListSerializer(many=True)}
    )
    @action(detail=True, methods=['get'], url_path='addons')
    def get_hotel_addons(self, request, pk=None):
        hotel = self.get_object()
        addons = AddonOffering.objects.filter(hotel=hotel, is_active=True)
        serializer = AddonOfferingListSerializer(addons, many=True, context=self.get_serializer_context())
        return Response(serializer.data)


@extend_schema(tags=["Identity & Auth"])
class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'
    serializer_class = PasswordResetSerializer

    @extend_schema(
        summary="Request Password Reset",
        description="Send a password reset OTP to the provided phone number.",
        request=PasswordResetSerializer,
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        challenge = getattr(serializer, "challenge", None)
        data = {"detail": "If an account with this phone exists, a reset code has been sent."}
        if challenge:
            data.update(
                {
                    "challenge_id": str(challenge.id),
                    "challenge_token": str(challenge.id),
                    "expires_at": challenge.expires_at,
                    "phone": challenge.phone,
                }
            )
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(tags=["Identity & Auth"])
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_login'
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(
        summary="Confirm Password Reset",
        description="Reset password using the OTP received by phone.",
        request=PasswordResetConfirmSerializer,
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password has been reset successfully."}, status=status.HTTP_200_OK)


@extend_schema(tags=["Identity & Auth"])
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'verify_email'
    serializer_class = VerifyEmailSerializer

    @extend_schema(
        summary="Verify Email Address",
        description="Activate user account using the token received in email.",
        request=VerifyEmailSerializer,
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Email verified successfully. You can now login."}, status=status.HTTP_200_OK)


@extend_schema(tags=["Identity & Auth"])
class VerifyEmailChangeView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'verify_email'
    serializer_class = VerifyEmailChangeSerializer

    @extend_schema(
        summary="Verify Email Change",
        description="Confirm email change request using signed token.",
        request=VerifyEmailChangeSerializer,
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        serializer = VerifyEmailChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Email address updated successfully."}, status=status.HTTP_200_OK)


