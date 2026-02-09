from django.contrib import admin
from .models import Notification, NotificationPreference, NotificationTemplate

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'notification_type', 'title', 'is_read', 'priority', 'created_at']
    list_filter = ['notification_type', 'is_read', 'priority', 'delivered_in_app', 'delivered_email']
    search_fields = ['user__email', 'title', 'message']
    readonly_fields = ['created_at', 'updated_at', 'read_at', 'email_sent_at']
    date_hierarchy = 'created_at'

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_enabled']
    search_fields = ['user__email']
    list_filter = ['email_enabled']

@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['notification_type', 'title_template', 'created_at']
    search_fields = ['notification_type', 'title_template']
