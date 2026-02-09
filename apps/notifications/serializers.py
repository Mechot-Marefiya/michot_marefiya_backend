from rest_framework import serializers
from .models import Notification, NotificationPreference

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message', 
            'action_url', 'metadata', 'is_read', 'read_at',
            'priority', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'read_at', 'action_url', 'metadata', 'priority', 'notification_type']

class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ['email_preferences', 'in_app_preferences', 'email_enabled']

    def update(self, instance, validated_data):
        if 'email_preferences' in validated_data:
            instance.email_preferences.update(validated_data.pop('email_preferences'))
        if 'in_app_preferences' in validated_data:
            instance.in_app_preferences.update(validated_data.pop('in_app_preferences'))
            
        return super().update(instance, validated_data)
