from rest_framework.viewsets import ModelViewSet, ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ObjectDoesNotExist
from decimal import Decimal
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from apps.core.models import Facility
from apps.core.serializers import FacilityResponseSerializer,ConversionInputSerializer, CurrencyRateSerializer
from apps.core.utils import convert_currency
from apps.core.enums import CurrencyEnum
from apps.core.models import CurrencyRate

class AbstractModelViewSet(ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]


@extend_schema(tags=["Accommodations"])
class FacilityViewSet(AbstractModelViewSet):
    http_method_names = ["get"]
    permission_classes = [AllowAny]
    serializer_class = FacilityResponseSerializer
    queryset = Facility.objects.all()


@extend_schema(tags=["Debug & Utils"])
class CurrencyViewSet(ViewSet):
    permission_classes = [AllowAny]
    pagination_class = None

    def list(self, request):
        res = [{"code": c.name, "name": c.value} for c in CurrencyEnum]

        return Response(data=res, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def rates(self, request):
        """
        Returns the latest exchange rates for all currencies against USD.
        Format: {"USD": 1.0, "ETB": 152.9, ...}
        """
        from django.db.models import Max
        latest_date = CurrencyRate.objects.aggregate(Max('date'))['date__max']
        
        if not latest_date:
            return Response({"detail": "No rate data available."}, status=status.HTTP_404_NOT_FOUND)
            
        rates = CurrencyRate.objects.filter(base="USD", date=latest_date)
        rate_dict = {rate.target: float(rate.rate) for rate in rates}
        
        # Ensure USD is included as 1.0 if not explicitly in DB
        if "USD" not in rate_dict:
            rate_dict["USD"] = 1.0
            
        return Response(rate_dict, status=status.HTTP_200_OK)
@extend_schema(tags=["Debug & Utils"])
class CurrencyConvertAPIView(APIView):
    """
    API endpoint for performing currency conversion based on stored rates.
    """
    permission_classes = [] # Adjust permissions as needed

    def post(self, request, *args, **kwargs):
        serializer = ConversionInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        input_amount = data['amount']
        base_currency = data['base']
        target_currency = data['target']
        rate_date = data['date']
        
        try:
            converted_amount = convert_currency(
                amount=input_amount,
                source_currency=base_currency,
                target_currency=target_currency,
                rate_date=rate_date
            )
            

            effective_rate = converted_amount / input_amount
            
            response_data = {
                'status': 'success',
                'input_amount': input_amount,
                'base': base_currency,
                'target': target_currency,
                'converted_amount': converted_amount.quantize(Decimal('0.01')),
                'rate_date': rate_date,
                'rate_used': effective_rate.quantize(Decimal('0.000001')), 
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except ObjectDoesNotExist as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"Conversion failed: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )