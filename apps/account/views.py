from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
# from rest_framework.parsers import MultiPartParser, JSONParser

# from rest_framework.viewsets import ViewSet
# from rest_framework.response import Response
# from rest_framework.status import HTTP_201_CREATED
from apps.account.filters import HotelFilter
from apps.core.views import AbstractModelViewSet
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    User
)
from apps.account.serializers import (
    CompanyProfileResponseSerializer,
    CustomTokenObtainPairSerializer,
    HotelProfileResponseSerializer,
    # HotelProfileResponseSerializer,
    HotelProfileSerializer,
    IndividualOwnerProfileResponseSerializer,
    IndividualOwnerProfileSerializer,
    UserSerializer,
    CompanyProfileSerializer
)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class UserViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = UserSerializer
    queryset = User.objects.all()


@extend_schema(responses=CompanyProfileResponseSerializer)
class CompanyProfileViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = CompanyProfileSerializer
    queryset = CompanyProfile.objects.all()


@extend_schema(responses=IndividualOwnerProfileResponseSerializer)
class IndividualOwnerProfileViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = IndividualOwnerProfileSerializer
    queryset = IndividualOwnerProfile.objects.all()


@extend_schema(responses=HotelProfileResponseSerializer)
class HotelProfileViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = HotelProfileSerializer
    queryset = HotelProfile.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = HotelFilter
