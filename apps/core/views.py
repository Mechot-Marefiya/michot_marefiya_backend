from rest_framework.viewsets import ModelViewSet, ViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from apps.core.models import Facility
from apps.core.serializers import FacilityResponseSerializer
from apps.core.enums import CurrencyEnum


class AbstractModelViewSet(ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]


class FacilityViewSet(AbstractModelViewSet):
    http_method_names = ["get"]
    permission_classes = [AllowAny]
    serializer_class = FacilityResponseSerializer
    queryset = Facility.objects.all()


class CurrencyViewSet(ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        res = [{"code": c.name, "name": c.value} for c in CurrencyEnum]

        return Response(data=res, status=status.HTTP_200_OK)
