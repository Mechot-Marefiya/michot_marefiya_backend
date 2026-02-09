from django.db import transaction
from django.utils import timezone
from .models import Notification, NotificationPreference, NotificationTemplate

class NotificationService:
    @staticmethod
    def create_notification(user, notification_type, title=None, message=None, 
                          metadata=None, action_url=None, priority=Notification.Priority.MEDIUM):
        if metadata is None:
            metadata = {}

        try:
            template = NotificationTemplate.objects.get(notification_type=notification_type)
            
            missing_vars = [var for var in template.required_variables if var not in metadata]
            if missing_vars:
                pass
                
            rendered_title = template.title_template
            rendered_message = template.message_template
            
            for key, value in metadata.items():
                placeholder = f"{{{{{key}}}}}"
                if value is not None:
                    rendered_title = rendered_title.replace(placeholder, str(value))
                    rendered_message = rendered_message.replace(placeholder, str(value))
            
            title = rendered_title
            message = rendered_message
            
        except NotificationTemplate.DoesNotExist:
            if not title or not message:
                raise ValueError("Title and message are required if no template exists for this type.")

        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            metadata=metadata,
            action_url=action_url,
            priority=priority,
            delivered_in_app=False
        )
        
        return notification

    @staticmethod
    def mark_as_read(notification_id, user):
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            if not notification.is_read:
                notification.is_read = True
                notification.read_at = timezone.now()
                notification.save(update_fields=['is_read', 'read_at'])
            return True
        except Notification.DoesNotExist:
            return False

    @staticmethod
    def mark_all_as_read(user):
        return Notification.objects.filter(user=user, is_read=False).update(
            is_read=True, 
            read_at=timezone.now()
        )

    @staticmethod
    def get_unread_count(user):
        return Notification.objects.filter(user=user, is_read=False).count()

    @staticmethod
    def get_user_notifications(user, limit=50):
        return Notification.objects.filter(user=user)[:limit]
