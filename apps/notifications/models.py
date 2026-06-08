from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.core.models import AbstractBaseModel


class Notification(AbstractBaseModel):
    class NotificationType(models.TextChoices):
        EMAIL_VERIFIED = 'email_verified', _('Email Verified')
        PASSWORD_CHANGED = 'password_changed', _('Password Changed')
        
        BOOKING_CREATED = 'booking_created', _('Booking Created')
        BOOKING_CONFIRMED = 'booking_confirmed', _('Booking Confirmed')
        BOOKING_CANCELLED = 'booking_cancelled', _('Booking Cancelled')
        
        PAYMENT_SUCCESS = 'payment_success', _('Payment Successful')
        PAYMENT_FAILED = 'payment_failed', _('Payment Failed')
        LISTING_DELETED = 'listing_deleted', _('Listing Deleted')
        
        COMPANY_APPROVED = 'company_approved', _('Company Approved')
        COMPANY_REJECTED = 'company_rejected', _('Company Rejected')
        NEW_BOOKING_RECEIVED = 'new_booking_received', _('New Booking Received')
        PAYOUT_COMPLETED = 'payout_completed', _('Payout Completed')
        
        NEW_COMPANY_REGISTRATION = 'new_company_registration', _('New Company Registration')

    class Priority(models.TextChoices):
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        CRITICAL = 'critical', _('Critical')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('Recipient')
    )
    
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        verbose_name=_('Type')
    )
    
    title = models.CharField(max_length=255, verbose_name=_('Title'))
    message = models.TextField(verbose_name=_('Message'))
    
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_('Metadata'))
    action_url = models.URLField(null=True, blank=True, verbose_name=_('Action URL'))
    
    is_read = models.BooleanField(default=False, verbose_name=_('Read?'))
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Read At'))
    
    delivered_in_app = models.BooleanField(default=False, verbose_name=_('Delivered In-App'))
    delivered_email = models.BooleanField(default=False, verbose_name=_('Delivered Email'))
    delivered_sms = models.BooleanField(default=False, verbose_name=_('Delivered SMS'))
    delivered_push = models.BooleanField(default=False, verbose_name=_('Delivered Push'))
    
    email_sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Email Sent At'))
    sms_sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_('SMS Sent At'))
    push_sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Push Sent At'))
    
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        verbose_name=_('Priority')
    )
    
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Expires At'))

    class Meta:
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['notification_type']),
        ]

    def __str__(self):
        return f"{self.user} - {self.title}"


class NotificationPreference(AbstractBaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        verbose_name=_('User')
    )
    
    email_preferences = models.JSONField(
        default=dict, 
        blank=True,
        verbose_name=_('Email Preferences')
    )
    
    in_app_preferences = models.JSONField(
        default=dict, 
        blank=True,
        verbose_name=_('In-App Preferences')
    )

    sms_preferences = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('SMS Preferences')
    )

    push_preferences = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Push Preferences')
    )
    
    email_enabled = models.BooleanField(
        default=True,
        verbose_name=_('Enable Email Notifications')
    )

    sms_enabled = models.BooleanField(
        default=False,
        verbose_name=_('Enable SMS Notifications')
    )

    push_enabled = models.BooleanField(
        default=True,
        verbose_name=_('Enable Push Notifications')
    )

    class Meta:
        verbose_name = _('Notification Preference')
        verbose_name_plural = _('Notification Preferences')

    def __str__(self):
        return f"Preferences for {self.user}"


class NotificationTemplate(AbstractBaseModel):
    notification_type = models.CharField(
        max_length=50, 
        unique=True,
        verbose_name=_('Notification Type')
    )
    
    title_template = models.CharField(
        max_length=255,
        verbose_name=_('Title Template')
    )
    message_template = models.TextField(verbose_name=_('Message Template'))
    
    email_subject_template = models.CharField(
        max_length=255,
        verbose_name=_('Email Subject Template')
    )
    email_body_template = models.TextField(verbose_name=_('Email Body Template (Text)'))
    email_html_template = models.TextField(
        null=True, 
        blank=True,
        verbose_name=_('Email Body Template (HTML)')
    )

    sms_template = models.CharField(
        max_length=320,
        blank=True,
        verbose_name=_('SMS Template')
    )

    push_title_template = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Push Title Template')
    )

    push_body_template = models.TextField(
        blank=True,
        verbose_name=_('Push Body Template')
    )
    
    required_variables = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Required Variables')
    )

    class Meta:
        verbose_name = _('Notification Template')
        verbose_name_plural = _('Notification Templates')

    def __str__(self):
        return self.notification_type
