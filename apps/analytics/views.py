from datetime import date, datetime, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.account.permissions import IsCompany, IsCompanyOrIndividualOwner
from apps.analytics import services
from apps.analytics.serializers import OverviewSerializer, TimeseriesItemSerializer, FrontDeskStatsSerializer
from apps.account.enums import RoleCode


@extend_schema(tags=["Analytics"])
class CompanyOverviewView(APIView):
    permission_classes = [IsCompanyOrIndividualOwner]

    @extend_schema(responses=OverviewSerializer)
    def get(self, request):
        user = request.user
        
        is_admin = False
        if request.user.is_superuser:
            is_admin = True
        elif hasattr(request.user, 'role') and request.user.role:
            try:
                is_admin = request.user.role.code == RoleCode.ADMIN.value
            except Exception:
                is_admin = False

        company_id = request.query_params.get("company_id")
        
        if not company_id:
            if hasattr(user, "profile"):
                company_id = str(user.profile.id)
            elif hasattr(user, "company") and user.company:
                company_id = str(user.company.id)
        
        if company_id:
            if not is_admin:
                allowed = False
                if hasattr(user, "profile") and str(user.profile.id) == str(company_id): allowed = True
                if hasattr(user, "company") and user.company and str(user.company.id) == str(company_id): allowed = True
                
                if not allowed:
                    return Response({"detail": "Not authorized to view this company's analytics."}, status=status.HTTP_403_FORBIDDEN)
            
            end = request.query_params.get("end_date")
            start = request.query_params.get("start_date")
            end_date = date.fromisoformat(end) if end else date.today()
            start_date = date.fromisoformat(start) if start else end_date - timedelta(days=30)
            
            data = services.compute_company_overview(company_id, start_date, end_date)
            serializer = OverviewSerializer(data)
            return Response(serializer.data)

        individual_owner = getattr(user, "individual_owner", None)
        if individual_owner:
            owner_id = str(individual_owner.id)
            
            end = request.query_params.get("end_date")
            start = request.query_params.get("start_date")
            end_date = date.fromisoformat(end) if end else date.today()
            start_date = date.fromisoformat(start) if start else end_date - timedelta(days=30)

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
        
        is_admin = request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role and request.user.role.code == RoleCode.ADMIN.value)
        company_id = request.query_params.get("company_id")

        end = request.query_params.get("end_date")
        start = request.query_params.get("start_date")
        granularity = request.query_params.get("granularity", "day")
        end_date = date.fromisoformat(end) if end else date.today()
        start_date = date.fromisoformat(start) if start else end_date - timedelta(days=30)

        target_company_id = None
        if company_id:
             target_company_id = company_id
        elif hasattr(user, "profile"):
             target_company_id = str(user.profile.id)
        elif hasattr(user, "company") and user.company:
             target_company_id = str(user.company.id)
             
        if target_company_id:
            if not is_admin:
                allowed = False
                if hasattr(user, "profile") and str(user.profile.id) == str(target_company_id): allowed = True
                if hasattr(user, "company") and user.company and str(user.company.id) == str(target_company_id): allowed = True
                if not allowed:
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
        
        is_admin = False
        if request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role and request.user.role.code == RoleCode.ADMIN.value):
            is_admin = True

        target_company_id = None
        if company_id:
             target_company_id = company_id
        elif hasattr(user, "profile"):
             target_company_id = str(user.profile.id)
        elif hasattr(user, "company") and user.company:
             target_company_id = str(user.company.id)

        if target_company_id:
            if not is_admin:
                allowed = False
                if hasattr(user, "profile") and str(user.profile.id) == str(target_company_id): allowed = True
                if hasattr(user, "company") and user.company and str(user.company.id) == str(target_company_id): allowed = True
                if not allowed:
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
    permission_classes = [IsCompanyOrIndividualOwner]
    
    @extend_schema(responses=FrontDeskStatsSerializer)
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        
        workspace_id = request.query_params.get("workspace_id")
        workspace_type = request.query_params.get("workspace_type")
        
        if not workspace_id or not workspace_type:
            return Response({"detail": "workspace_id and workspace_type are required."}, status=status.HTTP_400_BAD_REQUEST)

        from apps.analytics.services_frontdesk import compute_front_desk_stats
        
        try:
            data = compute_front_desk_stats(workspace_id, workspace_type)
            serializer = FrontDeskStatsSerializer(data)
            return Response(serializer.data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Analytics"])
class FrontDeskAvailabilityView(APIView):
    permission_classes = [IsCompanyOrIndividualOwner] 
    
    @extend_schema(
        parameters=[
            OpenApiParameter("workspace_id",  OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("workspace_type", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("start_date", OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("end_date", OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=True),
        ]
    )
    def get(self, request):
        workspace_id = request.query_params.get("workspace_id")
        workspace_type = request.query_params.get("workspace_type")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        
        if not all([workspace_id, workspace_type, start_date_str, end_date_str]):
            return Response(
                {"detail": "workspace_id, workspace_type, start_date, and end_date are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
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

