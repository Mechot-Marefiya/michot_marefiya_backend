from rest_framework import viewsets, mixins, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import UserRateThrottle
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from .models import Notification, NotificationPreference, NotificationTemplate
from .serializers import (
    NotificationSerializer, 
    NotificationPreferenceSerializer,
    NotificationTemplateSerializer,
    BulkDeleteSerializer,
    BatchMarkReadSerializer
)
from .services import NotificationService
from apps.account.permissions import IsAdmin


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationThrottle(UserRateThrottle):
    rate = '300/hour'


class NotificationFilter(filters.FilterSet):
    created_after = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    
    class Meta:
        model = Notification
        fields = ['is_read', 'notification_type', 'priority']


@extend_schema(tags=['Notifications'])
class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    """
    ViewSet for managing user notifications.
    
    Provides endpoints for listing, retrieving, marking as read, and deleting notifications.
    All endpoints are scoped to the authenticated user - users can only access their own notifications.
    
    Features:
    - Pagination (20 per page, max 100)
    - Filtering by read status, type, priority, and date range
    - Ordering by created_at or priority
    - Batch operations (mark-read-batch, bulk-delete)
    - Unread count caching for performance
    - Rate limiting (300 requests/hour per user)
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination
    throttle_classes = [NotificationThrottle]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = NotificationFilter
    ordering_fields = ['created_at', 'priority']
    ordering = ['-created_at']

    @extend_schema(
        summary="List user notifications",
        description="Retrieve a paginated list of notifications for the authenticated user. Supports filtering by read status, notification type, priority, and date range.",
        parameters=[
            OpenApiParameter(
                name='is_read',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description='Filter by read status (true/false)'
            ),
            OpenApiParameter(
                name='notification_type',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by notification type (e.g., payment_success, booking_confirmed)'
            ),
            OpenApiParameter(
                name='priority',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by priority level (low, medium, high, critical)'
            ),
            OpenApiParameter(
                name='created_after',
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                description='Filter notifications created after this date (ISO 8601 format)'
            ),
            OpenApiParameter(
                name='created_before',
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                description='Filter notifications created before this date (ISO 8601 format)'
            ),
            OpenApiParameter(
                name='ordering',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Sort order: created_at, -created_at (newest first), priority, -priority (highest first)'
            ),
            OpenApiParameter(
                name='page',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Page number for pagination'
            ),
            OpenApiParameter(
                name='page_size',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Number of results per page (max 100)'
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Retrieve a single notification",
        description="Get details of a specific notification. Users can only access their own notifications."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        summary="Delete a notification",
        description="Permanently delete a specific notification. Users can only delete their own notifications."
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @extend_schema(
        summary="Mark notification as read",
        description="Marks a single notification as read and returns the updated notification.",
        responses={
            200: NotificationSerializer,
            404: OpenApiExample(
                'Not Found',
                value={'success': False, 'error_code': 'NOTIFICATION_NOT_FOUND', 'message': 'Notification not found or access denied'},
                response_only=True
            )
        }
    )
    @action(detail=True, methods=['patch'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        try:
            notification = self.get_object()
            NotificationService.mark_as_read(notification.id, request.user)
            notification.refresh_from_db()
            serializer = self.get_serializer(notification)
            return Response({
                'success': True,
                'message': 'Notification marked as read',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        except Notification.DoesNotExist:
            return Response({
                'success': False,
                'error_code': 'NOTIFICATION_NOT_FOUND',
                'message': 'Notification not found or you do not have access'
            }, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(
        summary="Mark all notifications as read",
        description="Marks all unread notifications for the current user as read.",
        responses={
            200: OpenApiExample(
                'Success',
                value={'success': True, 'message': 'Marked 5 notifications as read', 'data': {'count': 5}},
                response_only=True
            )
        }
    )
    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        count = NotificationService.mark_all_as_read(request.user)
        return Response({
            'success': True,
            'message': f'Marked {count} notifications as read',
            'data': {'count': count}
        }, status=status.HTTP_200_OK)
        
    @extend_schema(
        request=BulkDeleteSerializer,
        summary="Bulk delete notifications",
        description="Delete multiple notifications by ID (max 100).",
        responses={
            200: OpenApiExample(
                'Success',
                value={'success': True, 'message': 'Deleted 3 notifications', 'data': {'count': 3}},
                response_only=True
            ),
            400: OpenApiExample(
                'Validation Error',
                value={'success': False, 'error_code': 'VALIDATION_ERROR', 'message': 'Invalid input', 'errors': {}},
                response_only=True
            )
        }
    )
    @action(detail=False, methods=['delete'], url_path='bulk-delete')
    def bulk_delete(self, request):
        serializer = BulkDeleteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error_code': 'VALIDATION_ERROR',
                'message': 'Invalid input',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
             
        ids = serializer.validated_data['ids']
        deleted_count = NotificationService.bulk_delete(request.user, ids)
        return Response({
            'success': True,
            'message': f'Deleted {deleted_count} notifications',
            'data': {'count': deleted_count}
        }, status=status.HTTP_200_OK)


    @extend_schema(
        summary="Get unread notification count",
        description="Returns the total number of unread notifications for the current user.",
        responses={
            200: OpenApiExample(
                'Success',
                value={'success': True, 'data': {'unread_count': 5}},
                response_only=True
            )
        }
    )
    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = NotificationService.get_unread_count(request.user)
        return Response({
            'success': True,
            'data': {'unread_count': count}
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        request=BatchMarkReadSerializer,
        summary="Batch mark notifications as read",
        description="Mark multiple specific notifications as read by ID (max 100).",
        responses={
            200: OpenApiExample(
                'Success',
                value={'success': True, 'message': 'Marked 3 notifications as read', 'data': {'count': 3}},
                response_only=True
            )
        }
    )
    @action(detail=False, methods=['post'], url_path='mark-read-batch')
    def mark_read_batch(self, request):
        serializer = BatchMarkReadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error_code': 'VALIDATION_ERROR',
                'message': 'Invalid input',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        ids = serializer.validated_data['ids']
        updated_count = NotificationService.mark_read_batch(request.user, ids)
        
        return Response({
            'success': True,
            'message': f'Marked {updated_count} notifications as read',
            'data': {'count': updated_count}
        }, status=status.HTTP_200_OK)

    
    @extend_schema(
        summary="Get notification summary",
        description="Returns aggregated notification statistics by type and priority.",
        responses={
            200: OpenApiExample(
                'Success',
                value={
                    'success': True,
                    'data': {
                        'total_unread': 8,
                        'by_type': {'payment_success': 3, 'booking_confirmed': 5},
                        'by_priority': {'high': 2, 'medium': 6}
                    }
                },
                response_only=True
            )
        }
    )
    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        queryset = self.get_queryset()
        
        total_unread = queryset.filter(is_read=False).count()
        
        by_type = dict(
            queryset.filter(is_read=False)
            .values('notification_type')
            .annotate(count=Count('id'))
            .values_list('notification_type', 'count')
        )
        
        by_priority = dict(
            queryset.filter(is_read=False)
            .values('priority')
            .annotate(count=Count('id'))
            .values_list('priority', 'count')
        )
        
        return Response({
            'success': True,
            'data': {
                'total_unread': total_unread,
                'by_type': by_type,
                'by_priority': by_priority
            }
        }, status=status.HTTP_200_OK)


@extend_schema(tags=['Notifications'])
class NotificationPreferenceView(APIView):
    """
    API view for managing user notification preferences.
    
    Allows users to retrieve and update their notification delivery preferences
    for both email and in-app notifications. Preferences are stored as JSON objects
    allowing granular control over specific notification types.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        summary="Get notification preferences",
        description="Retrieve the current user's notification preferences.",
        responses={200: NotificationPreferenceSerializer}
    )
    def get(self, request):
        prefs, created = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(prefs)
        return Response({
            'success': True,
            'data': serializer.data
        })
    
    @extend_schema(
        request=NotificationPreferenceSerializer,
        summary="Update notification preferences",
        description="Update the current user's notification preferences.",
        responses={
            200: NotificationPreferenceSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={'success': False, 'error_code': 'VALIDATION_ERROR', 'message': 'Invalid input', 'errors': {}},
                response_only=True
            )
        }
    )
    def put(self, request):
        prefs, created = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(prefs, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Preferences updated successfully',
                'data': serializer.data
            })
        return Response({
            'success': False,
            'error_code': 'VALIDATION_ERROR',
            'message': 'Invalid input',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Notifications'])
class NotificationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationTemplateSerializer
    queryset = NotificationTemplate.objects.all().order_by("notification_type")
    permission_classes = [IsAdmin]
