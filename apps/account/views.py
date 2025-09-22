from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView

# from rest_framework.parsers import MultiPartParser, JSONParser

# from rest_framework.viewsets import ViewSet
# from rest_framework.response import Response
# from rest_framework.status import HTTP_201_CREATED
from apps.core.views import AbstractModelViewSet
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    User
)
from apps.account.serializers import (
    CustomTokenObtainPairSerializer,
    # HotelProfileResponseSerializer,
    HotelProfileSerializer,
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


class CompanyProfileViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = CompanyProfileSerializer
    queryset = CompanyProfile.objects.all()


class IndividualOwnerProfileViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = IndividualOwnerProfileSerializer
    queryset = IndividualOwnerProfile.objects.all()


class HotelProfileViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = HotelProfileSerializer
    queryset = HotelProfile.objects.all()
