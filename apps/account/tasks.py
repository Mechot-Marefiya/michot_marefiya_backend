import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.account.models import OtpChallenge

logger = logging.getLogger(__name__)


@shared_task
def send_otp_sms_task(challenge_id):
    challenge = OtpChallenge.objects.filter(id=challenge_id).first()
    if not challenge:
        logger.warning("OTP challenge %s not found for SMS delivery.", challenge_id)
        return False

    payload = cache.get(OtpChallengeCache.pending_key(challenge.id))
    if not payload:
        logger.warning("OTP payload missing from cache for challenge %s.", challenge_id)
        return False

    try:
        from services.sms import send_sms

        send_sms(payload["phone"], payload["message"])
    except Exception as exc:
        logger.exception("Failed to send OTP SMS for challenge %s", challenge_id)
        cache.delete(OtpChallengeCache.pending_key(challenge.id))
        challenge.delete()
        return False

    cache.delete(OtpChallengeCache.pending_key(challenge.id))
    challenge.sent_at = timezone.now()
    challenge.save(update_fields=["sent_at", "updated_at"])
    return True


@shared_task
def cleanup_expired_otp_challenges():
    expired = list(
        OtpChallenge.objects.filter(expires_at__lte=timezone.now()).only("id", "phone", "purpose")
    )
    deleted_count = 0
    for challenge in expired:
        cache.delete(OtpChallengeCache.pending_key(challenge.id))
        deleted_count += 1
    OtpChallenge.objects.filter(id__in=[challenge.id for challenge in expired]).delete()
    return deleted_count


class OtpChallengeCache:
    @staticmethod
    def prefix():
        from django.conf import settings

        return getattr(settings, "OTP_REDIS_KEY_PREFIX", "otp")

    @classmethod
    def pending_key(cls, challenge_id):
        return f"{cls.prefix()}:pending:{challenge_id}"
