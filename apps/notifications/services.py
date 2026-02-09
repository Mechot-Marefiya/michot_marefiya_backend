from django.db import transaction
from django.utils import timezone
from .models import Notification, NotificationPreference, NotificationTemplate

class NotificationService:
    @staticmethod
    def create_notification(user, notification_type, title=None, message=None, 
                          metadata=None, action_url=None, priority=Notification.Priority.MEDIUM):
        if metadata is None:
            metadata = {}

        template = None
        try:
            template = NotificationTemplate.objects.get(notification_type=notification_type)
            
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
                pass 

        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title or "Notification",
            message=message or "",
            metadata=metadata,
            action_url=action_url,
            priority=priority,
            delivered_in_app=False
        )
        
        if template:
            try:
                prefs, _ = NotificationPreference.objects.get_or_create(user=user)
                if prefs.email_enabled:
                    email_subject = template.email_subject_template
                    email_body = template.email_body_template
                    email_html = template.email_html_template
                    
                    for key, value in metadata.items():
                        placeholder = f"{{{{{key}}}}}"
                        if value is not None:
                            email_subject = email_subject.replace(placeholder, str(value))
                            email_body = email_body.replace(placeholder, str(value))
                            if email_html:
                                email_html = email_html.replace(placeholder, str(value))
                    
                    from apps.notifications.tasks import send_notification_email_task
                    send_notification_email_task.delay(user.id, email_subject, email_body, email_html)
                    
                    notification.delivered_email = True  
                    notification.email_sent_at = timezone.now()
                    notification.save(update_fields=['delivered_email', 'email_sent_at'])

            except Exception:
                pass
        
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

    @staticmethod
    def notify_admins(notification_type, title, message, metadata=None, priority=Notification.Priority.MEDIUM):
        from django.contrib.auth import get_user_model
        from apps.account.enums import RoleCode
        User = get_user_model()
        
        admin_users = User.objects.filter(role__code=RoleCode.ADMIN.value, is_active=True)
        
        for admin in admin_users:
            try:
                NotificationService.create_notification(
                    user=admin,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    metadata=metadata,
                    priority=priority
                )
            except Exception:
                pass
