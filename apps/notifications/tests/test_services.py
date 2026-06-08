from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch
from apps.notifications.models import Notification, NotificationPreference, NotificationTemplate
from apps.notifications.services import NotificationService

User = get_user_model()

class NotificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            first_name='Test',
            last_name='User'
        )
        self.template = NotificationTemplate.objects.create(
            notification_type=Notification.NotificationType.BOOKING_CONFIRMED,
            title_template='Booking {{booking_reference}} Confirmed',
            message_template='Your booking at {{hotel_name}} is confirmed.',
            email_subject_template='Booking Confirmed',
            email_body_template='Body',
            sms_template='Booking {{booking_reference}} confirmed.',
            push_title_template='Booking Confirmed',
            push_body_template='Booking {{booking_reference}} confirmed.',
            required_variables=['booking_reference', 'hotel_name']
        )

    def test_create_notification_with_template(self):
        context = {
            'booking_reference': 'BK-123',
            'hotel_name': 'Grand Hotel'
        }
        notification = NotificationService.create_notification(
            user=self.user,
            notification_type=Notification.NotificationType.BOOKING_CONFIRMED,
            metadata=context
        )
        
        self.assertEqual(notification.title, 'Booking BK-123 Confirmed')
        self.assertEqual(notification.message, 'Your booking at Grand Hotel is confirmed.')
        self.assertFalse(notification.is_read)

    def test_create_notification_without_template_raises_error(self):
        with self.assertRaises(ValueError):
            NotificationService.create_notification(
                user=self.user,
                notification_type=Notification.NotificationType.PAYMENT_FAILED
            )

    def test_mark_as_read(self):
        notification = Notification.objects.create(
            user=self.user,
            notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
            title='Test',
            message='Message'
        )
        
        success = NotificationService.mark_as_read(notification.id, self.user)
        self.assertTrue(success)
        
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_get_unread_count(self):
        Notification.objects.create(
            user=self.user,
            notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
            title='Test 1',
            message='Message 1'
        )
        Notification.objects.create(
            user=self.user,
            notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
            title='Test 2',
            message='Message 2',
            is_read=True
        )
        
        count = NotificationService.get_unread_count(self.user)
        self.assertEqual(count, 1)

    def test_mark_all_read(self):
        Notification.objects.create(user=self.user, notification_type='type1', title='1', message='1')
        Notification.objects.create(user=self.user, notification_type='type2', title='2', message='2')
        
        count = NotificationService.mark_all_as_read(self.user)
        self.assertEqual(count, 2)
        self.assertEqual(NotificationService.get_unread_count(self.user), 0)

    @patch("apps.notifications.tasks.send_notification_push_task.delay")
    @patch("apps.notifications.tasks.send_notification_sms_task.delay")
    @patch("apps.notifications.tasks.send_notification_email_task.delay")
    def test_create_notification_dispatch_respects_channel_preferences(
        self,
        mock_email_delay,
        mock_sms_delay,
        mock_push_delay,
    ):
        self.template.notification_type = Notification.NotificationType.BOOKING_CREATED
        self.template.save(update_fields=["notification_type"])
        NotificationPreference.objects.create(
            user=self.user,
            email_enabled=True,
            sms_enabled=True,
            push_enabled=True,
            email_preferences={Notification.NotificationType.BOOKING_CREATED: False},
            sms_preferences={Notification.NotificationType.BOOKING_CREATED: True},
            push_preferences={Notification.NotificationType.BOOKING_CREATED: False},
        )

        notification = NotificationService.create_notification(
            user=self.user,
            notification_type=Notification.NotificationType.BOOKING_CREATED,
            metadata={"booking_reference": "BK-124", "hotel_name": "Grand Hotel"},
        )

        self.assertIsNotNone(notification)
        mock_email_delay.assert_not_called()
        mock_sms_delay.assert_called_once()
        mock_push_delay.assert_not_called()
        notification.refresh_from_db()
        self.assertFalse(notification.delivered_sms)
        self.assertFalse(notification.delivered_email)
        self.assertFalse(notification.delivered_push)

    @patch("apps.notifications.tasks.send_notification_push_task.delay")
    @patch("apps.notifications.tasks.send_notification_sms_task.delay", side_effect=RuntimeError("SMS queue unavailable"))
    @patch("apps.notifications.tasks.send_notification_email_task.delay")
    def test_create_notification_records_delivery_failure(
        self,
        mock_email_delay,
        mock_sms_delay,
        mock_push_delay,
    ):
        self.template.notification_type = Notification.NotificationType.BOOKING_CREATED
        self.template.save(update_fields=["notification_type"])
        NotificationPreference.objects.create(
            user=self.user,
            sms_enabled=True,
            push_enabled=False,
            email_enabled=False,
            sms_preferences={Notification.NotificationType.BOOKING_CREATED: True},
        )

        notification = NotificationService.create_notification(
            user=self.user,
            notification_type=Notification.NotificationType.BOOKING_CREATED,
            metadata={"booking_reference": "BK-125", "hotel_name": "Grand Hotel"},
        )

        notification.refresh_from_db()
        self.assertIn("delivery_errors", notification.metadata)
        self.assertIn("sms", notification.metadata["delivery_errors"])
        mock_sms_delay.assert_called_once()
        mock_email_delay.assert_not_called()
        mock_push_delay.assert_not_called()
