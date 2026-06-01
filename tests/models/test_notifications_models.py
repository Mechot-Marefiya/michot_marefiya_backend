# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest

from apps.notifications.models import Notification, NotificationPreference, NotificationTemplate

pytestmark = pytest.mark.django_db


def test_notification_str_representation(notification):
    assert str(notification) == f"{notification.user} - {notification.title}"


def test_notification_preference_str_representation(notification_preference):
    assert str(notification_preference) == f"Preferences for {notification_preference.user}"


def test_notification_template_str_representation(notification_template):
    assert str(notification_template) == notification_template.notification_type


def test_notification_template_unique_constraint(notification_template):
    with pytest.raises(Exception):
        NotificationTemplate.objects.create(
            notification_type=notification_template.notification_type,
            title_template="Duplicate",
            message_template="Duplicate",
            email_subject_template="Duplicate",
            email_body_template="Duplicate",
        )
