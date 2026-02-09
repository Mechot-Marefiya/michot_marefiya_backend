from celery import shared_task
from django.contrib.auth import get_user_model
from apps.core.services.email_service import EmailService
import logging

logger = logging.getLogger(__name__)

@shared_task
def send_notification_email_task(user_id, subject, body, html_body=None):
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        EmailService.send_notification_email(user, subject, body, html_body)
    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found for notification email task.")
    except Exception as e:
        logger.error(f"Error in send_notification_email_task: {str(e)}", exc_info=True)
