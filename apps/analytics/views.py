from datetime import date, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from apps.account.permissions import IsCompany
from apps.analytics import services
from apps.analytics.serializers import OverviewSerializer, TimeseriesItemSerializer
from apps.account.enums import RoleCode


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

        # determine if current user is admin-like
        is_admin = False
        if request.user.is_superuser:
            is_admin = True
        elif hasattr(request.user, 'role') and request.user.role:
            try:
                is_admin = request.user.role.code == RoleCode.ADMIN.value
            except Exception:
                is_admin = False

        if not company_id:
            # try to resolve company profile id from user.profile
            profile = getattr(user, "profile", None)
            if not profile:
                return Response({"detail": "Company profile not found."}, status=status.HTTP_403_FORBIDDEN)
            company_id = str(profile.id)
        else:
            # if a company_id was provided, only allow it for admin users
            if not is_admin:
                profile = getattr(user, "profile", None)
                if not profile or str(profile.id) != str(company_id):
                    return Response({"detail": "Not authorized to view this company's analytics."}, status=status.HTTP_403_FORBIDDEN)

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

        is_admin = False
        if request.user.is_superuser:
            is_admin = True
        elif hasattr(request.user, 'role') and request.user.role:
            try:
                is_admin = request.user.role.code == RoleCode.ADMIN.value
            except Exception:
                is_admin = False

        if not company_id:
            profile = getattr(user, "profile", None)
            if not profile:
                return Response({"detail": "Company profile not found."}, status=status.HTTP_403_FORBIDDEN)
            company_id = str(profile.id)
        else:
            if not is_admin:
                profile = getattr(user, "profile", None)
                if not profile or str(profile.id) != str(company_id):
                    return Response({"detail": "Not authorized to view this company's analytics."}, status=status.HTTP_403_FORBIDDEN)

        items = services.revenue_timeseries(company_id, start_date, end_date, granularity=granularity)
        serializer = TimeseriesItemSerializer(items, many=True)
        return Response(serializer.data)
