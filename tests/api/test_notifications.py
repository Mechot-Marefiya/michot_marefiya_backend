# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest
from apps.notifications.models import Notification, NotificationTemplate

pytestmark = pytest.mark.django_db


def test_get_notifications_unauthenticated(api_client):
    response = api_client.get("/api/v1/notifications/")

    assert response.status_code == 401


def test_get_notifications_list_success(auth_client, notification):
    response = auth_client.get("/api/v1/notifications/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["id"] == str(notification.id)
    assert "notification_type" in data["results"][0]
    assert "priority" in data["results"][0]
    assert "notification_type_display" in data["results"][0]
    assert "priority_display" in data["results"][0]
    assert "delivered_in_app" in data["results"][0]
    assert "delivered_email" in data["results"][0]
    assert "delivered_sms" in data["results"][0]
    assert "delivered_push" in data["results"][0]


def test_get_notification_detail_success(auth_client, notification):
    response = auth_client.get(f"/api/v1/notifications/{notification.id}/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(notification.id)
    assert data["title"] == notification.title
    assert data["message"] == notification.message


def test_get_notification_detail_not_found_for_other_user(auth_client, company_user):
    other_notification = Notification.objects.create(
        user=company_user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Other user notification",
        message="Hidden from current user",
    )

    response = auth_client.get(f"/api/v1/notifications/{other_notification.id}/")

    assert response.status_code == 404


def test_delete_notification_detail_success(auth_client, notification):
    response = auth_client.delete(f"/api/v1/notifications/{notification.id}/")

    assert response.status_code == 204
    assert Notification.objects.filter(id=notification.id).exists() is False


def test_delete_notification_detail_not_found_for_other_user(auth_client, company_user):
    other_notification = Notification.objects.create(
        user=company_user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Other user notification",
        message="Hidden from current user",
    )

    response = auth_client.delete(f"/api/v1/notifications/{other_notification.id}/")

    assert response.status_code == 404
    assert Notification.objects.filter(id=other_notification.id).exists() is True


def test_patch_notification_mark_read_success(auth_client, notification):
    response = auth_client.patch(f"/api/v1/notifications/{notification.id}/mark-read/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == str(notification.id)
    notification.refresh_from_db()
    assert notification.is_read is True
    assert notification.read_at is not None


def test_patch_notification_mark_read_not_found_for_other_user(auth_client, company_user):
    other_notification = Notification.objects.create(
        user=company_user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Other user notification",
        message="Hidden from current user",
    )

    response = auth_client.patch(f"/api/v1/notifications/{other_notification.id}/mark-read/")

    assert response.status_code == 404


def test_post_notifications_mark_all_read_success(auth_client, notification, user, company_user):
    Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
        title="Second unread",
        message="Unread for authenticated user",
    )
    other_notification = Notification.objects.create(
        user=company_user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Other user unread",
        message="Should stay unread",
    )

    response = auth_client.post("/api/v1/notifications/mark-all-read/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["count"] == 2
    assert Notification.objects.filter(user=user, is_read=False).count() == 0
    other_notification.refresh_from_db()
    assert other_notification.is_read is False


def test_delete_notifications_bulk_delete_invalid_payload(auth_client):
    response = auth_client.delete("/api/v1/notifications/bulk-delete/", {}, format="json")

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False


def test_delete_notifications_bulk_delete_success_scopes_to_authenticated_user(auth_client, notification, user, company_user):
    own_second = Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
        title="Own second notification",
        message="Delete me too",
    )
    other_notification = Notification.objects.create(
        user=company_user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Other user notification",
        message="Should not be deleted",
    )

    response = auth_client.delete(
        "/api/v1/notifications/bulk-delete/",
        {"ids": [str(notification.id), str(own_second.id), str(other_notification.id)]},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["count"] == 2
    assert Notification.objects.filter(id=notification.id).exists() is False
    assert Notification.objects.filter(id=own_second.id).exists() is False
    assert Notification.objects.filter(id=other_notification.id).exists() is True


def test_get_notifications_unread_count_success(auth_client, notification):
    response = auth_client.get("/api/v1/notifications/unread-count/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["unread_count"] == 1


def test_post_notifications_mark_read_batch_invalid_payload(auth_client):
    response = auth_client.post("/api/v1/notifications/mark-read-batch/", {}, format="json")

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False


def test_post_notifications_mark_read_batch_success_scopes_to_authenticated_user(auth_client, notification, user, company_user):
    own_second = Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
        title="Own second notification",
        message="Mark me read too",
    )
    other_notification = Notification.objects.create(
        user=company_user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Other user notification",
        message="Should stay unread",
    )

    response = auth_client.post(
        "/api/v1/notifications/mark-read-batch/",
        {"ids": [str(notification.id), str(own_second.id), str(other_notification.id)]},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["count"] == 2
    notification.refresh_from_db()
    own_second.refresh_from_db()
    other_notification.refresh_from_db()
    assert notification.is_read is True
    assert own_second.is_read is True
    assert other_notification.is_read is False


def test_get_notifications_summary_success(auth_client, notification, user):
    Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
        title="Payment success",
        message="Unread payment notification",
        priority=Notification.Priority.HIGH,
    )
    Notification.objects.create(
        user=user,
        notification_type=Notification.NotificationType.BOOKING_CREATED,
        title="Already read",
        message="Read notification",
        priority=Notification.Priority.LOW,
        is_read=True,
    )

    response = auth_client.get("/api/v1/notifications/summary/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["total_unread"] == 2
    assert data["data"]["by_type"]["booking_created"] == 1
    assert data["data"]["by_type"]["payment_success"] == 1
    assert data["data"]["by_priority"]["medium"] == 1
    assert data["data"]["by_priority"]["high"] == 1


def test_get_notification_preferences_success(auth_client, notification_preference):
    response = auth_client.get("/api/v1/notifications/preferences/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "email_preferences" in data["data"]
    assert "in_app_preferences" in data["data"]
    assert "sms_preferences" in data["data"]
    assert "push_preferences" in data["data"]
    assert "email_enabled" in data["data"]
    assert "sms_enabled" in data["data"]
    assert "push_enabled" in data["data"]


def test_put_notification_preferences_success(auth_client, notification_preference):
    response = auth_client.put(
        "/api/v1/notifications/preferences/",
        {
            "email_preferences": {"booking_created": True},
            "in_app_preferences": {"booking_created": True},
            "sms_preferences": {"booking_created": True},
            "push_preferences": {"booking_created": False},
            "email_enabled": False,
            "sms_enabled": True,
            "push_enabled": False,
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email_enabled"] is False
    assert data["data"]["sms_enabled"] is True
    assert data["data"]["push_enabled"] is False
    assert data["data"]["sms_preferences"]["booking_created"] is True
    assert data["data"]["push_preferences"]["booking_created"] is False


def test_put_notification_preferences_preserves_existing_keys_on_merge(auth_client, notification_preference):
    notification_preference.email_preferences = {
        "booking_created": False,
        "payment_success": True,
    }
    notification_preference.in_app_preferences = {
        "booking_created": True,
        "payment_success": False,
    }
    notification_preference.sms_preferences = {
        "booking_created": False,
        "payment_success": True,
    }
    notification_preference.push_preferences = {
        "booking_created": True,
        "payment_success": False,
    }
    notification_preference.save(
        update_fields=[
            "email_preferences", "in_app_preferences",
            "sms_preferences", "push_preferences",
        ]
    )

    response = auth_client.put(
        "/api/v1/notifications/preferences/",
        {
            "email_preferences": {"booking_created": True},
            "in_app_preferences": {"payment_success": True},
            "sms_preferences": {"payment_success": False},
            "push_preferences": {"booking_created": False},
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["email_preferences"]["booking_created"] is True
    assert data["data"]["email_preferences"]["payment_success"] is True
    assert data["data"]["in_app_preferences"]["booking_created"] is True
    assert data["data"]["in_app_preferences"]["payment_success"] is True
    assert data["data"]["sms_preferences"]["booking_created"] is False
    assert data["data"]["sms_preferences"]["payment_success"] is False
    assert data["data"]["push_preferences"]["booking_created"] is False
    assert data["data"]["push_preferences"]["payment_success"] is False


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/notifications/"),
        ("get", "/api/v1/notifications/00000000-0000-0000-0000-000000000001/"),
        ("delete", "/api/v1/notifications/00000000-0000-0000-0000-000000000001/"),
        ("patch", "/api/v1/notifications/00000000-0000-0000-0000-000000000001/mark-read/"),
        ("post", "/api/v1/notifications/mark-all-read/"),
        ("delete", "/api/v1/notifications/bulk-delete/"),
        ("get", "/api/v1/notifications/unread-count/"),
        ("post", "/api/v1/notifications/mark-read-batch/"),
        ("get", "/api/v1/notifications/summary/"),
        ("get", "/api/v1/notifications/preferences/"),
        ("put", "/api/v1/notifications/preferences/"),
    ],
)
def test_notifications_endpoints_require_authentication(api_client, method, path):
    payload = {"ids": []} if "bulk-delete" in path or "mark-read-batch" in path else {}
    response = getattr(api_client, method)(path, payload, format="json")

    assert response.status_code == 401


def test_get_notification_templates_admin_list_success(admin_client, notification_template):
    response = admin_client.get("/api/v1/notifications/templates/")

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["results"][0]["notification_type"] == notification_template.notification_type


def test_post_notification_template_admin_create_success(admin_client):
    response = admin_client.post(
        "/api/v1/notifications/templates/",
        {
            "notification_type": "saved_listing_deleted",
            "title_template": "Saved listing removed",
            "message_template": "A listing you saved is no longer available.",
            "email_subject_template": "Saved listing removed",
            "email_body_template": "A listing you saved is no longer available.",
            "required_variables": ["listing_title"],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["notification_type"] == "saved_listing_deleted"


def test_patch_notification_template_admin_update_success(admin_client, notification_template):
    response = admin_client.patch(
        f"/api/v1/notifications/templates/{notification_template.id}/",
        {"title_template": "Updated title"},
        format="json",
    )

    assert response.status_code == 200
    notification_template.refresh_from_db()
    assert notification_template.title_template == "Updated title"


def test_delete_notification_template_admin_delete_success(admin_client, notification_template):
    response = admin_client.delete(f"/api/v1/notifications/templates/{notification_template.id}/")

    assert response.status_code == 204
    assert NotificationTemplate.objects.filter(id=notification_template.id).exists() is False


def test_notification_templates_non_admin_forbidden(auth_client):
    response = auth_client.get("/api/v1/notifications/templates/")

    assert response.status_code == 403
