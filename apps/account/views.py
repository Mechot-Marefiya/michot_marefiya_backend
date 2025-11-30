from django.db.models import Sum, Q
from django.utils.dateparse import parse_date
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework_simplejwt.views import TokenObtainPairView
from django.conf import settings
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
from apps.account.serializers import (
    CompanyProfileResponseSerializer,
    CustomTokenObtainPairSerializer,
    HotelProfileSerializer,
    HotelRoomAvailabilitySerializer,
    IndividualOwnerProfileResponseSerializer,
    IndividualOwnerProfileSerializer,
    UserSerializer,
    CompanyProfileSerializer,
    UserResponseSerializer,
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
    serializer_class = UserSerializer
    queryset = User.objects.all()

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        else:
            return [IsOwnerOrReadOnly()]

    def get_queryset(self):
        """
        This is for Filtering queryset based on the user's role:
        - Regular & Company users: See only their own profile
        - Admin: See all users
        """
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



@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_me(request):
    try:
        user = request.user
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
        # Everyone can see all company profiles (public data)
        return super().get_queryset()


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
        # Everyone can see all individual owner profiles (public data)
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
        # Everyone can see all hotel profiles (public data)
        return super().get_queryset()

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
