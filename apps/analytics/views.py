from datetime import date, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from apps.account.permissions import IsCompany
from apps.analytics import services
from apps.analytics.serializers import OverviewSerializer, TimeseriesItemSerializer


class CompanyOverviewView(APIView):
    permission_classes = [IsCompany]

    @extend_schema(responses=OverviewSerializer)
    def get(self, request):
        # Determine company id: admin may pass company_id, otherwise use request.user.profile
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        # parse dates
        end = request.query_params.get("end_date")
        start = request.query_params.get("start_date")

        if end:
            end_date = date.fromisoformat(end)
        else:
            end_date = date.today()

        if start:
            start_date = date.fromisoformat(start)
        else:
            start_date = end_date - timedelta(days=30)

        # admin may query other companies via company_id
        company_id = request.query_params.get("company_id")
        if not company_id:
            # try to resolve company profile id from user.profile
            profile = getattr(user, "profile", None)
            if not profile:
                return Response({"detail": "Company profile not found."}, status=status.HTTP_403_FORBIDDEN)
            company_id = str(profile.id)

        data = services.compute_company_overview(company_id, start_date, end_date)

        serializer = OverviewSerializer(data)
        return Response(serializer.data)


class CompanyRevenueView(APIView):
    permission_classes = [IsCompany]

    @extend_schema(responses=TimeseriesItemSerializer(many=True))
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        end = request.query_params.get("end_date")
        start = request.query_params.get("start_date")
        granularity = request.query_params.get("granularity", "day")

        if end:
            end_date = date.fromisoformat(end)
        else:
            end_date = date.today()

        if start:
            start_date = date.fromisoformat(start)
        else:
            start_date = end_date - timedelta(days=30)

        company_id = request.query_params.get("company_id")
        if not company_id:
            profile = getattr(user, "profile", None)
            if not profile:
                return Response({"detail": "Company profile not found."}, status=status.HTTP_403_FORBIDDEN)
            company_id = str(profile.id)

        items = services.revenue_timeseries(company_id, start_date, end_date, granularity=granularity)
        serializer = TimeseriesItemSerializer(items, many=True)
        return Response(serializer.data)
