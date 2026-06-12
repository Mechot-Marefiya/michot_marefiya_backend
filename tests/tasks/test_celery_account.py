# BASELINE: written from CODEBASE_MAP.md
# PRD status: needs modification
# Flutter contract: no
# Last updated: 2026-06-11

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.account.models import OtpChallenge
from apps.account.tasks import OtpChallengeCache, cleanup_expired_otp_challenges, send_otp_sms_task

pytestmark = pytest.mark.django_db


def test_send_otp_sms_task_executes_successfully(monkeypatch, user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash="hashed",
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
    )
    cache.set(
        OtpChallengeCache.pending_key(challenge.id),
        {"phone": user.phone, "message": "OTP body"},
        timeout=300,
    )
    called = {"value": False}

    def fake_send_sms(phone, message):
        called["value"] = phone == user.phone and message == "OTP body"
        return True

    monkeypatch.setattr("services.sms.send_sms", fake_send_sms)

    assert send_otp_sms_task(str(challenge.id)) is True
    challenge.refresh_from_db()
    assert called["value"] is True
    assert challenge.sent_at is not None
    assert cache.get(OtpChallengeCache.pending_key(challenge.id)) is None


def test_send_otp_sms_task_failure_does_not_raise(monkeypatch, user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash="hashed",
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
    )
    cache.set(
        OtpChallengeCache.pending_key(challenge.id),
        {"phone": user.phone, "message": "OTP body"},
        timeout=300,
    )
    cache.set(OtpChallengeCache.cooldown_key(user.phone, challenge.purpose), str(challenge.id), timeout=60)

    def fail_send_sms(phone, message):
        raise RuntimeError("provider down")

    monkeypatch.setattr("services.sms.send_sms", fail_send_sms)

    assert send_otp_sms_task(str(challenge.id)) is False
    assert OtpChallenge.objects.filter(id=challenge.id).exists() is False


def test_cleanup_expired_otp_challenges_removes_expired_consumed(user):
    challenge = OtpChallenge.objects.create(
        user=user,
        phone=user.phone,
        purpose=OtpChallenge.Purpose.LOGIN,
        code_hash="hashed",
        expires_at=timezone.now() - timezone.timedelta(minutes=1),
        consumed_at=timezone.now() - timezone.timedelta(seconds=30),
        sent_at=timezone.now() - timezone.timedelta(minutes=2),
    )
    cache.set(
        OtpChallengeCache.pending_key(challenge.id),
        {"phone": user.phone, "message": "OTP body"},
        timeout=300,
    )
    cache.set(OtpChallengeCache.cooldown_key(user.phone, challenge.purpose), str(challenge.id), timeout=60)

    assert cleanup_expired_otp_challenges() == 1
    assert OtpChallenge.objects.filter(id=challenge.id).exists() is False
    assert cache.get(OtpChallengeCache.pending_key(challenge.id)) is None
    assert cache.get(OtpChallengeCache.cooldown_key(user.phone, challenge.purpose)) is None


def test_cleanup_expired_otp_challenges_beat_schedule_registered(settings):
    schedule = settings.CELERY_BEAT_SCHEDULE["cleanup-expired-otp-challenges-every-5-minutes"]

    assert schedule["task"] == "apps.account.tasks.cleanup_expired_otp_challenges"
    assert schedule["schedule"] == 60.0 * 5
    assert schedule["args"] == ()
