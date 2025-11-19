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
from apps.account.permissions import IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly


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
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = UserSerializer
    queryset = User.objects.all()

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return super().get_permissions()


@extend_schema(responses=CompanyProfileResponseSerializer)
class CompanyProfileViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = CompanyProfileSerializer
    queryset = CompanyProfile.objects.all()

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return super().get_permissions()


@extend_schema(responses=IndividualOwnerProfileResponseSerializer)
class IndividualOwnerProfileViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = IndividualOwnerProfileSerializer
    queryset = IndividualOwnerProfile.objects.all()

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return super().get_permissions()


@extend_schema(responses=HotelProfileDocSerializer)
class HotelProfileViewSet(AbstractModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = HotelProfileSerializer
    queryset = HotelProfile.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = HotelFilter

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return super().get_permissions()

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
