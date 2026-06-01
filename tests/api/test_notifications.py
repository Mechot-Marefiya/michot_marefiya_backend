# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: yes
# Last updated: 2026-06-01

import pytest

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


def test_patch_notification_mark_read_success(auth_client, notification):
    response = auth_client.patch(f"/api/v1/notifications/{notification.id}/mark-read/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == str(notification.id)


def test_post_notifications_mark_all_read_success(auth_client, notification):
    response = auth_client.post("/api/v1/notifications/mark-all-read/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "count" in data["data"]


def test_delete_notifications_bulk_delete_invalid_payload(auth_client):
    response = auth_client.delete("/api/v1/notifications/bulk-delete/", {}, format="json")

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False


def test_get_notifications_unread_count_success(auth_client, notification):
    response = auth_client.get("/api/v1/notifications/unread-count/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "unread_count" in data["data"]


def test_post_notifications_mark_read_batch_invalid_payload(auth_client):
    response = auth_client.post("/api/v1/notifications/mark-read-batch/", {}, format="json")

    assert response.status_code == 400


def test_get_notifications_summary_success(auth_client, notification):
    response = auth_client.get("/api/v1/notifications/summary/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "total_unread" in data["data"]
    assert "by_type" in data["data"]
    assert "by_priority" in data["data"]


def test_get_notification_preferences_success(auth_client, notification_preference):
    response = auth_client.get("/api/v1/notifications/preferences/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "email_preferences" in data["data"]
    assert "in_app_preferences" in data["data"]
    assert "email_enabled" in data["data"]


def test_put_notification_preferences_success(auth_client, notification_preference):
    response = auth_client.put(
        "/api/v1/notifications/preferences/",
        {"email_preferences": {"booking_created": True}, "in_app_preferences": {"booking_created": True}, "email_enabled": False},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email_enabled"] is False
