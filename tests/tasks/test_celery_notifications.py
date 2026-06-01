# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest

from apps.notifications.tasks import send_notification_email_task

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
