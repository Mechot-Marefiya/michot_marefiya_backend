from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def has_deliverable_email(user_or_email) -> bool:
    email = getattr(user_or_email, "email", user_or_email) or ""
    email = str(email).strip().lower()
    if not email or "@" not in email:
        return False
    return not email.endswith("@phone.local")



class EmailService:    
    @staticmethod
    def send_booking_confirmation(booking):
        if not has_deliverable_email(getattr(booking, "guest_email", "")):
            return False
        
        # send confirmation email to guest after successful booking.
        try:
            context = {
                'booking_reference': booking.booking_reference,
                'guest_name': booking.guest_full_name,
                'guest_email': booking.guest_email,
                'guest_phone': booking.guest_phone,
                'check_in': getattr(booking, 'check_in_date', getattr(booking, 'start_date', None)).strftime('%B %d, %Y'),
                'check_out': getattr(booking, 'check_out_date', getattr(booking, 'end_date', None)).strftime('%B %d, %Y'),
                'total': booking.total_price,
                'currency': booking.currency,
            }
            
            subject = f"Booking Confirmed - {booking.booking_reference}"
            
            html_body = render_to_string('emails/booking_confirmation.html', context)
            
            plain_body = f"""
Dear {context['guest_name']},

Thank you for booking with Michot Marefiya. Your reservation has been successfully confirmed.

BOOKING REFERENCE: {booking.booking_reference}

Booking Details:
- Check-in Date: {context['check_in']}
- Check-out Date: {context['check_out']}
- Guest Email: {context['guest_email']}
- Guest Phone: {context['guest_phone']}
- Total Amount: {context['total']} {context['currency']}

IMPORTANT: Please save this email and your booking reference. You will need it for check-in and to manage your booking.

If you have any questions or need to modify your booking, please contact our support team or reply to this email.

We look forward to welcoming you!

Best regards,
Michot Marefiya Team

---
© 2026 Michot Marefiya. All rights reserved.
Visit us: https://michotmarefia.com
Support: support@michotmarefia.com
            """
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body.strip(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[booking.guest_email]
            )
            email.attach_alternative(html_body, "text/html")
            
            email.send(fail_silently=False)
            
            logger.info(
                f"Confirmation email sent successfully for booking {booking.booking_reference} "
                f"to {booking.guest_email}"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to send confirmation email for booking {booking.id}: {str(e)}",
                exc_info=True
            )
            # don't crash the booking flow if email fails
            # the booking is still valid even if email doesn't send
            return False

    @staticmethod
    def send_account_credentials(user, password):
        if not has_deliverable_email(user):
            return False
        try:
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com').rstrip('/')
            login_url = f"{frontend_url}/login"
            
            context = {
                'first_name': user.first_name or "User",
                'email': user.email,
                'password': password,
                'login_url': login_url
            }
            
            subject = "Welcome to Michot Marefiya - Your Account Credentials"
            
            html_body = render_to_string('emails/account_credentials.html', context)
            plain_body = render_to_string('emails/account_credentials.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email]
            )
            email.attach_alternative(html_body, "text/html")
            
            email.send(fail_silently=False)
            
            logger.info(f"Credentials email sent successfully to {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send credentials email to {user.email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_password_reset(user, reset_url):
        if not has_deliverable_email(user):
            return False
        try:
            context = {
                'first_name': user.first_name or "User",
                'reset_url': reset_url
            }
            
            subject = "Reset Your Password - Michot Marefiya"
            
            html_body = render_to_string('emails/password_reset.html', context)
            plain_body = render_to_string('emails/password_reset.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email]
            )
            email.attach_alternative(html_body, "text/html")
            
            email.send(fail_silently=False)
            
            logger.info(f"Password reset email sent successfully to {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {user.email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_verification_email(user, activation_url):
        if not has_deliverable_email(user):
            return False
        try:
            context = {
                'first_name': user.first_name or "User",
                'activation_url': activation_url
            }
            
            subject = "Activate Your Account - Michot Marefiya"
            
            html_body = render_to_string('emails/activation_email.html', context)
            plain_body = render_to_string('emails/activation_email.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email]
            )
            email.attach_alternative(html_body, "text/html")
            
            email.send(fail_silently=False)
            
            logger.info(f"Verification email sent successfully to {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {user.email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_email_change_verification(user, new_email, verification_url):
        if not has_deliverable_email(new_email):
            return False
        try:
            context = {
                'first_name': user.first_name or "User",
                'new_email': new_email,
                'verification_url': verification_url
            }
            
            subject = "Verify Your New Email Address - Michot Marefiya"
            
            html_body = render_to_string('emails/verify_email_change.html', context)
            plain_body = render_to_string('emails/verify_email_change.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[new_email]
            )
            email.attach_alternative(html_body, "text/html")
            
            email.send(fail_silently=False)
            
            logger.info(f"Email change verification sent successfully to {new_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email change verification to {new_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_email_change_notice(user, old_email, new_email):
        if not has_deliverable_email(old_email):
            return False
        try:
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://michotmarefia.com').rstrip('/')
            context = {
                'first_name': user.first_name or "User",
                'old_email': old_email,
                'new_email': new_email,
                'frontend_url': frontend_url
            }
            
            subject = "Security Alert: Email Change Request - Michot Marefiya"
            
            html_body = render_to_string('emails/email_change_notification.html', context)
            plain_body = render_to_string('emails/email_change_notification.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[old_email]  # Send to OLD email
            )
            email.attach_alternative(html_body, "text/html")
            
            email.send(fail_silently=False)
            
            logger.info(f"Security alert for email change sent to {old_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send security alert to {old_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_payment_receipt(booking, payment_transaction):
        # send payment receipt email (future implementation)
        
        # todo: implement payment receipt email
        pass
    
    @staticmethod
    def send_checkin_reminder(booking):
        # send check-in reminder email 24h before arrival (future implementation)
        
        # todo: implement check-in reminder
        # this would be called by a Celery scheduled task
        pass



    @staticmethod
    def send_notification_email(user, subject, body, html_body=None):
        if not has_deliverable_email(user):
            return False
        try:
            if html_body:
                html_content = render_to_string('emails/generic_notification.html', {
                    'body_content': html_body,
                    'title': subject
                })
            else:
                html_content = None

            email = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email]
            )
            if html_content:
                email.attach_alternative(html_content, "text/html")
            
            email.send(fail_silently=False)
            logger.info(f"Notification email sent to {user.email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send notification email to {user.email}: {str(e)}", exc_info=True)
            return False

BookingEmailService = EmailService
