from django.db.models import Sum, Q
from django.utils.dateparse import parse_date
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework_simplejwt.views import TokenObtainPairView
from django.conf import settings
from django.utils import timezone
import logging
import traceback
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from apps.listing.models import Booking, RoomListing
from apps.listing.services import StayAvailabilityService
from apps.account.docs.schemas import HotelProfileDocSerializer
from apps.account.filters import HotelFilter
from apps.core.views import AbstractModelViewSet
from apps.account.docs.schemas import check__room_availability_schema
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    User,
)
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
    ChangePasswordSerializer,
)
from apps.account.enums import RoleCode
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.account.permissions import (
    IsAuthenticatedOrReadOnly,
    IsOwnerOrReadOnly,
    IsAdmin,
    IsCompanyOwner,
    IsPublicReadOnly,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

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
                        "detail": "Invalid email or password.",
                        "error": str(exc),
                        "trace": traceback.format_exc(),
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)
        except AttributeError:
            return Response(
                {"detail": "Token blacklisting not enabled on server."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        except Exception:
            return Response({"detail": "Failed to blacklist token."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserResponseSerializer(request.user)
        return Response(serializer.data)


class UserViewSet(AbstractModelViewSet):
    queryset = User.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return UserSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        elif self.action == 'change_password':
            return ChangePasswordSerializer
        return UserResponseSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['me', 'change_password']:
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
class CompanyProfileViewSet(AbstractModelViewSet):
    serializer_class = CompanyProfileSerializer
    queryset = CompanyProfile.objects.all()

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [AllowAny()]
        else:
            return [IsCompanyOwner()]

    def get_queryset(self):
        return super().get_queryset()

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

        return Response(CompanyProfileResponseSerializer(profile).data)


@extend_schema(responses=IndividualOwnerProfileResponseSerializer)
class IndividualOwnerProfileViewSet(AbstractModelViewSet):
    serializer_class = IndividualOwnerProfileSerializer
    queryset = IndividualOwnerProfile.objects.all()

    def get_permissions(self):
        if self.action == 'create':
            return [IsAdmin()]
        elif self.action in ['list', 'retrieve']:
            return [AllowAny()]
        else:
            return [IsAdmin()]

    def get_queryset(self):
        return super().get_queryset()


@extend_schema(responses=HotelProfileDocSerializer)
class HotelProfileViewSet(AbstractModelViewSet):
    serializer_class = HotelProfileSerializer
    queryset = HotelProfile.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = HotelFilter

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['list', 'retrieve', 'check_availability', 'get_featured_hotels']:
            return [AllowAny()]
        else:
            return [IsCompanyOwner()]

    def get_queryset(self):
        return super().get_queryset()

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
        detail=True, methods=["get"], serializer_class=HotelRoomAvailabilitySerializer
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
        featured_hotels = HotelProfile.objects.filter(featured=True)
        serializer = self.get_serializer(featured_hotels, many=True)
        return Response(serializer.data)
