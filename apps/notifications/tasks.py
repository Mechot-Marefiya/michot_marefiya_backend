from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.services.email_service import EmailService
from services.sms import send_sms
import logging

logger = logging.getLogger(__name__)


def _mark_delivery(notification_id, channel, *, success=True, error=None):
    if not notification_id:
        return

    from apps.notifications.models import Notification

    try:
        notification = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        logger.warning("Notification %s not found while marking %s delivery.", notification_id, channel)
        return

    if success:
        setattr(notification, f"delivered_{channel}", True)
        setattr(notification, f"{channel}_sent_at", timezone.now())
        notification.save(update_fields=[f"delivered_{channel}", f"{channel}_sent_at"])
        return

    setattr(notification, f"delivered_{channel}", False)
    setattr(notification, f"{channel}_sent_at", None)
    metadata = dict(notification.metadata or {})
    delivery_errors = dict(metadata.get("delivery_errors", {}))
    delivery_errors[channel] = str(error)
    metadata["delivery_errors"] = delivery_errors
    notification.metadata = metadata
    notification.save(update_fields=[f"delivered_{channel}", f"{channel}_sent_at", "metadata"])


@shared_task
def send_notification_email_task(user_id, subject, body, html_body=None, notification_id=None):
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        EmailService.send_notification_email(user, subject, body, html_body)
        _mark_delivery(notification_id, "email")
    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found for notification email task.")
    except Exception as e:
        logger.error(f"Error in send_notification_email_task: {str(e)}", exc_info=True)
        _mark_delivery(notification_id, "email", success=False, error=e)


@shared_task
def send_notification_sms_task(user_id, message, notification_id=None):
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        phone = getattr(user, "phone", None)
        if not phone:
            raise ValueError("User has no phone number for SMS notification delivery.")
        send_sms(phone, message)
        _mark_delivery(notification_id, "sms")
        return True
    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found for notification SMS task.")
    except Exception as e:
        logger.error(f"Error in send_notification_sms_task: {str(e)}", exc_info=True)
        _mark_delivery(notification_id, "sms", success=False, error=e)
    return False


@shared_task
def send_notification_push_task(user_id, title, body, metadata=None, notification_id=None):
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        # Push provider/device-token storage is not wired yet. Keep a task boundary so
        # callers can honor push preferences without blocking current workflows.
        logger.info(
            "Push notification queued without provider for user %s: %s",
            user.id,
            title,
        )
        _mark_delivery(notification_id, "push")
        return True
    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found for notification push task.")
    except Exception as e:
        logger.error(f"Error in send_notification_push_task: {str(e)}", exc_info=True)
        _mark_delivery(notification_id, "push", success=False, error=e)
    return False
