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

from .models import Notification, NotificationPreference
from .serializers import (
    NotificationSerializer, 
    NotificationPreferenceSerializer,
    BulkDeleteSerializer,
    BatchMarkReadSerializer
)
from .services import NotificationService


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


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination
    throttle_classes = [NotificationThrottle]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = NotificationFilter
    ordering_fields = ['created_at', 'priority']
    ordering = ['-created_at']

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


class NotificationPreferenceView(APIView):
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
