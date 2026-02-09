from django.test import TestCase
from django.contrib.auth import get_user_model
from ..models import Notification, NotificationPreference, NotificationTemplate
from ..services import NotificationService

User = get_user_model()

class NotificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
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
