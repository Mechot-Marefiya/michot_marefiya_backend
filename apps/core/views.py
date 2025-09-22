from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import AllowAny
from apps.core.models import Facility
from apps.core.serializers import FacilityResponseSerializer


class AbstractModelViewSet(ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]


class FacilityViewSet(AbstractModelViewSet):
    http_method_names = ['get']
    permission_classes = [AllowAny]
    serializer_class = FacilityResponseSerializer
    queryset = Facility.objects.all()
