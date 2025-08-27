from rest_framework.permissions import AllowAny
# from rest_framework.viewsets import ViewSet
# from rest_framework.response import Response
# from rest_framework.status import HTTP_201_CREATED
from apps.core.views import AbstractModelViewSet
from apps.account.models import CompanyProfile, User
from apps.account.serializers import (
    UserSerializer,
    CompanyProfileSerializer
)


class UserViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = UserSerializer
    queryset = User.objects.all()


class CompanyProfileViewSet(AbstractModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = CompanyProfileSerializer
    queryset = CompanyProfile.objects.all()
