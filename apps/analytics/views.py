from datetime import date, datetime, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.account.permissions import (
    IsAdmin,
    IsCompany, 
    IsCompanyOrIndividualOwner, 
    IsCompanyOrFrontDesk, 
    ORPermission
)
from apps.analytics import services
from apps.analytics.serializers import (
    DateRangeQuerySerializer,
    OverviewSerializer,
    OverviewMetricsSerializer,
    PayoutFailureMetricsSerializer,
    RevenueMetricsSerializer,
    TimeseriesItemSerializer,
    FrontDeskStatsSerializer,
    FrontDeskAvailabilityRowSerializer,
)
from apps.account.enums import RoleCode
from apps.account.models import HotelProfile
from apps.listing.models import GuestHouseProfile


def _parse_analytics_date_range(request, default_days=30):
    end = request.query_params.get("end_date")
    start = request.query_params.get("start_date")

    try:
        end_date = date.fromisoformat(end) if end else date.today()
        start_date = date.fromisoformat(start) if start else end_date - timedelta(days=default_days)
    except ValueError:
        return None, None, Response(
            {"detail": "Invalid date format. Use YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return start_date, end_date, None


def _validate_admin_metrics_query_params(request):
    serializer = DateRangeQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _resolve_company_target(user, company_id):
    if company_id:
        return str(company_id)
    if hasattr(user, "profile"):
        return str(user.profile.id)
    if hasattr(user, "company") and user.company:
        return str(user.company.id)
    return None


def _can_access_company_analytics(user, target_company_id):
    if user.is_superuser or (
        hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value
    ):
        return True

    if hasattr(user, "profile") and str(user.profile.id) == str(target_company_id):
        return True
    if hasattr(user, "company") and user.company and str(user.company.id) == str(target_company_id):
        return True

    return False


def _can_access_frontdesk_workspace(user, workspace_id, workspace_type):
    if user.is_superuser or (
        hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value
    ):
        return True

    workspace_type = str(workspace_type).lower()
    role_code = getattr(getattr(user, "role", None), "code", None)
    workspace = getattr(user, "workspace", None)

    if role_code == RoleCode.FRONT_DESK.value:
        if workspace is None:
            return False
        if str(getattr(workspace, "id", "")) != str(workspace_id):
            return False
        if workspace_type == "hotel" and isinstance(workspace, HotelProfile):
            return True
        if workspace_type == "guesthouse" and isinstance(workspace, GuestHouseProfile):
            return True
        return False

    company = getattr(user, "company", None) or getattr(user, "profile", None)
    if company and workspace_type == "hotel":
        return HotelProfile.objects.filter(id=workspace_id, company=company).exists()
    if company and workspace_type == "guesthouse":
        return GuestHouseProfile.objects.filter(id=workspace_id, company=company).exists()

    individual_owner = getattr(user, "individual_owner", None)
    if individual_owner and workspace_type == "guesthouse":
        return GuestHouseProfile.objects.filter(id=workspace_id, individual_owner=individual_owner).exists()

    return False


@extend_schema(tags=["Analytics"])
class CompanyOverviewView(APIView):
    permission_classes = [IsCompanyOrIndividualOwner]

    @extend_schema(responses=OverviewSerializer)
    def get(self, request):
        user = request.user
        
        company_id = request.query_params.get("company_id")

        if not company_id:
            company_id = _resolve_company_target(user, company_id)
        
        if company_id:
            if not _can_access_company_analytics(user, company_id):
                return Response({"detail": "Not authorized to view this company's analytics."}, status=status.HTTP_403_FORBIDDEN)

            start_date, end_date, error_response = _parse_analytics_date_range(request)
            if error_response:
                return error_response
            
            data = services.compute_company_overview(company_id, start_date, end_date)
            serializer = OverviewSerializer(data)
            return Response(serializer.data)

        individual_owner = getattr(user, "individual_owner", None)
        if individual_owner:
            owner_id = str(individual_owner.id)
            
            start_date, end_date, error_response = _parse_analytics_date_range(request)
            if error_response:
                return error_response

            data = services.compute_individual_owner_overview(owner_id, start_date, end_date)
            serializer = OverviewSerializer(data)
            return Response(serializer.data)

        return Response({"detail": "No associated company or individual owner profile found."}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(tags=["Analytics"])
class CompanyRevenueView(APIView):
    permission_classes = [IsCompanyOrIndividualOwner]

    @extend_schema(responses=TimeseriesItemSerializer(many=True))
    def get(self, request):
        user = request.user
        
        company_id = request.query_params.get("company_id")
        granularity = request.query_params.get("granularity", "day")
        if granularity not in {"day", "week", "month"}:
            return Response({"detail": "Invalid granularity. Use day, week, or month."}, status=status.HTTP_400_BAD_REQUEST)

        start_date, end_date, error_response = _parse_analytics_date_range(request)
        if error_response:
            return error_response

        target_company_id = _resolve_company_target(user, company_id)
             
        if target_company_id:
            if not _can_access_company_analytics(user, target_company_id):
                 return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
            
            items = services.revenue_timeseries(target_company_id, start_date, end_date, granularity=granularity)
            return Response(TimeseriesItemSerializer(items, many=True).data)

        if getattr(user, "individual_owner", None):
            owner_id = str(user.individual_owner.id)
            items = services.revenue_timeseries_individual(owner_id, start_date, end_date, granularity=granularity)
            return Response(TimeseriesItemSerializer(items, many=True).data)
            
        return Response({"detail": "No profile found."}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(tags=["Analytics"])
class CompanyActivityView(APIView):
    permission_classes = [IsCompanyOrIndividualOwner]

    @extend_schema(responses=TimeseriesItemSerializer(many=True))
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        
        company_id = request.query_params.get("company_id")

        target_company_id = _resolve_company_target(user, company_id)

        if target_company_id:
            if not _can_access_company_analytics(user, target_company_id):
                return Response({"detail": "Not authorized to view this company's analytics."}, status=status.HTTP_403_FORBIDDEN)

            activities = services.get_recent_activity(target_company_id)
            return Response(activities)
        
        if getattr(user, "individual_owner", None):
            owner_id = str(user.individual_owner.id)
            activities = services.get_recent_activity_individual(owner_id)
            return Response(activities)

        return Response({"detail": "No associated company or individual owner profile found."}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(tags=["Analytics"])
class FrontDeskStatsView(APIView):
    permission_classes = [IsCompanyOrFrontDesk]
    
    @extend_schema(responses=FrontDeskStatsSerializer)
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        workspace_id = request.query_params.get("workspace_id")
        workspace_type = request.query_params.get("workspace_type")
        
        if not workspace_id or not workspace_type:
            return Response({"detail": "workspace_id and workspace_type are required."}, status=status.HTTP_400_BAD_REQUEST)

        if not _can_access_frontdesk_workspace(user, workspace_id, workspace_type):
            return Response({"detail": "Not authorized to view this workspace."}, status=status.HTTP_403_FORBIDDEN)

        from apps.analytics.services_frontdesk import compute_front_desk_stats
        
        try:
            data = compute_front_desk_stats(workspace_id, workspace_type)
            serializer = FrontDeskStatsSerializer(data)
            return Response(serializer.data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Analytics"])
class FrontDeskAvailabilityView(APIView):
    permission_classes = [IsCompanyOrFrontDesk] 
    
    @extend_schema(
        parameters=[
            OpenApiParameter("workspace_id",  OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("workspace_type", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("start_date", OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("end_date", OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: FrontDeskAvailabilityRowSerializer(many=True)},
    )
    def get(self, request):
        user = request.user
        workspace_id = request.query_params.get("workspace_id")
        workspace_type = request.query_params.get("workspace_type")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        
        if not all([workspace_id, workspace_type, start_date_str, end_date_str]):
            return Response(
                {"detail": "workspace_id, workspace_type, start_date, and end_date are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if not _can_access_frontdesk_workspace(user, workspace_id, workspace_type):
            return Response({"detail": "Not authorized to view this workspace."}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
             return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
             
        if (end_date - start_date).days > 60:
             return Response({"detail": "Date range too large. Max 60 days."}, status=status.HTTP_400_BAD_REQUEST)

        from apps.analytics.services_frontdesk import get_availability_matrix
        
        try:
            data = get_availability_matrix(workspace_id, workspace_type, start_date, end_date)
            return Response(data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Analytics"])
class AdminOverviewMetricsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        parameters=[DateRangeQuerySerializer],
        responses=OverviewMetricsSerializer,
    )
    def get(self, request):
        params = _validate_admin_metrics_query_params(request)
        data = services.get_overview_metrics(
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
        )
        return Response(OverviewMetricsSerializer(data).data)


@extend_schema(tags=["Analytics"])
class AdminRevenueMetricsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        parameters=[DateRangeQuerySerializer],
        responses=RevenueMetricsSerializer,
    )
    def get(self, request):
        params = _validate_admin_metrics_query_params(request)
        data = services.get_revenue_metrics(
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
        )
        return Response(RevenueMetricsSerializer(data).data)


@extend_schema(tags=["Analytics"])
class AdminPayoutFailureMetricsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        parameters=[DateRangeQuerySerializer],
        responses=PayoutFailureMetricsSerializer,
    )
    def get(self, request):
        params = _validate_admin_metrics_query_params(request)
        data = services.get_payout_failure_metrics(
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
        )
        return Response(PayoutFailureMetricsSerializer(data).data)
