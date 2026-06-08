# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest

from apps.notifications.models import Notification
from apps.notifications.tasks import (
    send_notification_email_task,
    send_notification_push_task,
    send_notification_sms_task,
)

pytestmark = pytest.mark.django_db


def test_send_notification_email_task_executes_successfully(monkeypatch, user):
    called = {"value": False}

    def fake_send(target_user, subject, body, html_body=None):
        called["value"] = target_user.id == user.id and subject == "Subject"

    monkeypatch.setattr("apps.notifications.tasks.EmailService.send_notification_email", fake_send)

    assert send_notification_email_task(user.id, "Subject", "Body") is None
    assert called["value"] is True


def test_send_notification_email_task_handles_missing_object_gracefully():
    assert send_notification_email_task("00000000-0000-0000-0000-000000000000", "Subject", "Body") is None


def test_send_notification_sms_task_executes_successfully(monkeypatch, user):
    user.phone = "0911111111"
    user.save(update_fields=["phone"])
    notification = Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="SMS",
        message="Message",
    )
    called = {"value": False}

    def fake_send_sms(phone, message):
        called["value"] = phone == user.phone and message == "SMS body"
        return True

    monkeypatch.setattr("apps.notifications.tasks.send_sms", fake_send_sms)

    assert send_notification_sms_task(user.id, "SMS body", str(notification.id)) is True
    notification.refresh_from_db()
    assert called["value"] is True
    assert notification.delivered_sms is True
    assert notification.sms_sent_at is not None


def test_send_notification_sms_task_records_missing_phone(user):
    notification = Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="SMS",
        message="Message",
    )

    assert send_notification_sms_task(user.id, "SMS body", str(notification.id)) is False
    notification.refresh_from_db()
    assert notification.delivered_sms is False
    assert "sms" in notification.metadata["delivery_errors"]


def test_send_notification_push_task_marks_delivery(user):
    notification = Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Push",
        message="Message",
    )

    assert send_notification_push_task(user.id, "Title", "Body", {"booking_reference": "BK-1"}, str(notification.id)) is True
    notification.refresh_from_db()
    assert notification.delivered_push is True
    assert notification.push_sent_at is not None
