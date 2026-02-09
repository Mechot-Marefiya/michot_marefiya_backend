from django.core.management.base import BaseCommand
from apps.notifications.models import NotificationTemplate, Notification

class Command(BaseCommand):
    help = 'Loads initial notification templates'

    def handle(self, *args, **kwargs):
        templates = [
            {
                'notification_type': Notification.NotificationType.NEW_COMPANY_REGISTRATION,
                'title_template': 'New Company Registration: {{company_name}}',
                'message_template': 'A new company {{company_name}} has been registered by {{owner_email}}.',
                'email_subject_template': 'New Company Registration: {{company_name}}',
                'email_body_template': 'Hello Admin,\n\nA new company has been registered.\n\nName: {{company_name}}\nOwner: {{owner_email}}\n\nPlease review it in the dashboard.',
                'email_html_template': '<p>Hello Admin,</p><p>A new company has been registered.</p><p><strong>Name:</strong> {{company_name}}<br><strong>Owner:</strong> {{owner_email}}</p><p>Please review it in the dashboard.</p>',
                'required_variables': ['company_name', 'owner_email']
            },
            {
                'notification_type': Notification.NotificationType.COMPANY_APPROVED,
                'title_template': 'Company Approved',
                'message_template': 'Your company profile {{company_name}} has been approved.',
                'email_subject_template': 'Your Company Profile has been Approved!',
                'email_body_template': 'Hello,\n\nWe are pleased to inform you that your company profile "{{company_name}}" has been approved. You can now start listing your properties.\n\nWelcome to Michot Marefiya!',
                'email_html_template': '<p>Hello,</p><p>We are pleased to inform you that your company profile "<strong>{{company_name}}</strong>" has been approved.</p><p>You can now start listing your properties.</p><p>Welcome to Michot Marefiya!</p>',
                'required_variables': ['company_name']
            },
            {
                'notification_type': Notification.NotificationType.COMPANY_REJECTED,
                'title_template': 'Company Profile Rejected',
                'message_template': 'Your company profile {{company_name}} has been rejected.',
                'email_subject_template': 'Update regarding your Company Profile',
                'email_body_template': 'Hello,\n\nUnfortunately, your company profile "{{company_name}}" has been rejected.\n\nPlease contact support for more details.',
                'email_html_template': '<p>Hello,</p><p>Unfortunately, your company profile "<strong>{{company_name}}</strong>" has been rejected.</p><p>Please contact support for more details.</p>',
                'required_variables': ['company_name']
            },
            {
                'notification_type': Notification.NotificationType.PAYMENT_SUCCESS,
                'title_template': 'Payment Successful',
                'message_template': 'Your payment of {{amount}} {{currency}} for {{booking_reference}} was successful.',
                'email_subject_template': 'Payment Receipt - {{booking_reference}}',
                'email_body_template': 'Hello,\n\nWe have received your payment of {{amount}} {{currency}} for booking {{booking_reference}}.\n\nThank you!',
                'email_html_template': '<p>Hello,</p><p>We have received your payment of <strong>{{amount}} {{currency}}</strong> for booking <strong>{{booking_reference}}</strong>.</p><p>Thank you!</p>',
                'required_variables': ['amount', 'currency', 'booking_reference']
            },
            {
                'notification_type': Notification.NotificationType.PAYMENT_FAILED,
                'title_template': 'Payment Failed',
                'message_template': 'Payment for {{booking_reference}} failed.',
                'email_subject_template': 'Payment Failed - {{booking_reference}}',
                'email_body_template': 'Hello,\n\nWe were unable to process your payment for booking {{booking_reference}}.\n\nPlease try again or contact your bank.',
                'email_html_template': '<p>Hello,</p><p>We were unable to process your payment for booking <strong>{{booking_reference}}</strong>.</p><p>Please try again or contact your bank.</p>',
                'required_variables': ['booking_reference']
            },
            {
                'notification_type': Notification.NotificationType.NEW_BOOKING_RECEIVED,
                'title_template': 'New Booking Received',
                'message_template': 'You have a new booking ({{booking_reference}}).',
                'email_subject_template': 'New Booking Alert: {{booking_reference}}',
                'email_body_template': 'Hello,\n\nYou have received a new booking.\n\nReference: {{booking_reference}}\n\nPlease check your dashboard for details.',
                'email_html_template': '<p>Hello,</p><p>You have received a new booking.</p><p><strong>Reference:</strong> {{booking_reference}}</p><p>Please check your dashboard for details.</p>',
                'required_variables': ['booking_reference']
            }
        ]

        for tmpl in templates:
            obj, created = NotificationTemplate.objects.update_or_create(
                notification_type=tmpl['notification_type'],
                defaults=tmpl
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created template for {tmpl["notification_type"]}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Updated template for {tmpl["notification_type"]}'))
