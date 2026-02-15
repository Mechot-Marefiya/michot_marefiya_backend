from rest_framework import serializers
from .models import Notification, NotificationPreference

class NotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(
        source='get_notification_type_display', 
        read_only=True,
        help_text="Human-readable notification type"
    )
    priority_display = serializers.CharField(
        source='get_priority_display', 
        read_only=True,
        help_text="Human-readable priority level"
    )
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'notification_type_display',
            'title', 'message', 'action_url', 'metadata',
            'is_read', 'read_at', 'priority', 'priority_display',
            'created_at', 'delivered_in_app', 'delivered_email', 'email_sent_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'read_at', 'action_url', 'metadata', 
            'priority', 'notification_type', 'notification_type_display',
            'priority_display', 'delivered_in_app', 'delivered_email', 'email_sent_at'
        ]
        extra_kwargs = {
            'id': {'help_text': 'Unique notification identifier (UUID)'},
            'notification_type': {'help_text': 'Type of notification (e.g., payment_success, booking_confirmed)'},
            'title': {'help_text': 'Notification title/headline'},
            'message': {'help_text': 'Detailed notification message'},
            'action_url': {'help_text': 'Optional URL for deep linking to related resource'},
            'metadata': {'help_text': 'Additional context data as JSON object'},
            'is_read': {'help_text': 'Whether the notification has been read'},
            'read_at': {'help_text': 'Timestamp when notification was marked as read'},
            'priority': {'help_text': 'Priority level: low, medium, high, or critical'},
            'created_at': {'help_text': 'Timestamp when notification was created'},
            'delivered_in_app': {'help_text': 'Whether notification was delivered in-app'},
            'delivered_email': {'help_text': 'Whether notification was sent via email'},
            'email_sent_at': {'help_text': 'Timestamp when email was sent'},
        }


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ['email_preferences', 'in_app_preferences', 'email_enabled']
<<<<<<< Updated upstream
=======
        extra_kwargs = {
            'email_preferences': {
                'help_text': 'JSON object mapping notification types to email delivery preferences. Example: {"payment_success": true, "booking_confirmed": false}'
            },
            'in_app_preferences': {
                'help_text': 'JSON object mapping notification types to in-app delivery preferences. Example: {"payment_success": true, "booking_confirmed": true}'
            },
            'email_enabled': {
                'help_text': 'Global toggle for all email notifications. When false, no emails will be sent regardless of individual preferences.'
            },
        }
>>>>>>> Stashed changes

    def update(self, instance, validated_data):
        if 'email_preferences' in validated_data:
            instance.email_preferences.update(validated_data.pop('email_preferences'))
        if 'in_app_preferences' in validated_data:
            instance.in_app_preferences.update(validated_data.pop('in_app_preferences'))
            
        return super().update(instance, validated_data)


class BulkDeleteSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
        help_text="List of notification IDs to delete (max 100)"
    )


class BatchMarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
        help_text="List of notification IDs to mark as read (max 100)"
    )
