from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
import logging
from .models import Notification, NotificationPreference, NotificationTemplate
from apps.core.services.email_service import has_deliverable_email

logger = logging.getLogger(__name__)


def get_unread_count_cache_key(user_id):
    return f"notifications:unread_count:{user_id}"


class NotificationService:
    MANDATORY_TYPES = [
        Notification.NotificationType.BOOKING_CONFIRMED,
        Notification.NotificationType.BOOKING_CANCELLED,
        Notification.NotificationType.PAYMENT_SUCCESS,
        Notification.NotificationType.PAYMENT_FAILED,
        Notification.NotificationType.PASSWORD_CHANGED,
        Notification.NotificationType.EMAIL_VERIFIED,
        Notification.NotificationType.COMPANY_APPROVED,
        Notification.NotificationType.COMPANY_REJECTED,
        Notification.NotificationType.NEW_COMPANY_REGISTRATION,
    ]

    @staticmethod
    def _render_template(template_text, metadata):
        rendered = template_text or ""
        for key, value in metadata.items():
            placeholder = f"{{{{{key}}}}}"
            if value is not None:
                rendered = rendered.replace(placeholder, str(value))
        return rendered

    @staticmethod
    def _preference_allowed(prefs, channel, notification_type):
        enabled_field = f"{channel}_enabled"
        preferences_field = f"{channel}_preferences"
        return getattr(prefs, enabled_field, True) and getattr(prefs, preferences_field, {}).get(notification_type, True)

    @staticmethod
    def _record_delivery_error(notification, channel, error):
        if not notification:
            return

        metadata = dict(notification.metadata or {})
        delivery_errors = dict(metadata.get("delivery_errors", {}))
        delivery_errors[channel] = str(error)
        metadata["delivery_errors"] = delivery_errors
        notification.metadata = metadata
        notification.save(update_fields=["metadata"])

    @staticmethod
    def create_notification(user, notification_type, title=None, message=None, 
                          metadata=None, action_url=None, priority=Notification.Priority.MEDIUM):
        if metadata is None:
            metadata = {}

        template = None
        try:
            template = NotificationTemplate.objects.get(notification_type=notification_type)
            
            title = NotificationService._render_template(template.title_template, metadata)
            message = NotificationService._render_template(template.message_template, metadata)
            
        except NotificationTemplate.DoesNotExist:
            if not title or not message:
                raise ValueError("title and message are required when no notification template exists.")

        in_app_allowed = True
        email_allowed = has_deliverable_email(user)
        sms_allowed = bool(getattr(user, "phone", None))
        push_allowed = True
        
        try:
            prefs = NotificationPreference.objects.get(user=user)
            in_app_allowed = prefs.in_app_preferences.get(notification_type, True)
            email_allowed = NotificationService._preference_allowed(prefs, "email", notification_type)
            sms_allowed = NotificationService._preference_allowed(prefs, "sms", notification_type)
            push_allowed = NotificationService._preference_allowed(prefs, "push", notification_type)
            
            if notification_type in NotificationService.MANDATORY_TYPES:
                email_allowed = has_deliverable_email(user)
                in_app_allowed = True
                sms_allowed = bool(getattr(user, "phone", None))
                push_allowed = True
        except NotificationPreference.DoesNotExist:
            pass

        notification = None
        if in_app_allowed:
            notification = Notification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title or "Notification",
                message=message or "",
                metadata=metadata,
                action_url=action_url,
                priority=priority,
                delivered_in_app=False
            )
            cache.delete(get_unread_count_cache_key(user.id))

        if sms_allowed:
            try:
                sms_message = (
                    NotificationService._render_template(template.sms_template, metadata)
                    if template and template.sms_template
                    else message
                )

                from apps.notifications.tasks import send_notification_sms_task
                send_notification_sms_task.delay(
                    user.id,
                    sms_message,
                    str(notification.id) if notification else None,
                )

            except Exception as e:
                logger.error(f"Failed to send SMS for notification type {notification_type} to user {user.email}: {str(e)}", exc_info=True)
                NotificationService._record_delivery_error(notification, "sms", e)

        if template and email_allowed:
            try:
                email_subject = NotificationService._render_template(template.email_subject_template, metadata)
                email_body = NotificationService._render_template(template.email_body_template, metadata)
                email_html = NotificationService._render_template(template.email_html_template, metadata) if template.email_html_template else None
                
                from apps.notifications.tasks import send_notification_email_task
                send_notification_email_task.delay(
                    user.id,
                    email_subject,
                    email_body,
                    email_html,
                    str(notification.id) if notification else None,
                )

            except Exception as e:
                logger.error(f"Failed to send email for notification type {notification_type} to user {user.email}: {str(e)}", exc_info=True)
                NotificationService._record_delivery_error(notification, "email", e)

        if push_allowed:
            try:
                push_title = (
                    NotificationService._render_template(template.push_title_template, metadata)
                    if template and template.push_title_template
                    else title
                )
                push_body = (
                    NotificationService._render_template(template.push_body_template, metadata)
                    if template and template.push_body_template
                    else message
                )

                from apps.notifications.tasks import send_notification_push_task
                send_notification_push_task.delay(
                    user.id,
                    push_title,
                    push_body,
                    metadata,
                    str(notification.id) if notification else None,
                )

            except Exception as e:
                logger.error(f"Failed to queue push for notification type {notification_type} to user {user.email}: {str(e)}", exc_info=True)
                NotificationService._record_delivery_error(notification, "push", e)
        
        return notification

    @staticmethod
    def mark_as_read(notification_id, user):
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            if not notification.is_read:
                notification.is_read = True
                notification.read_at = timezone.now()
                notification.save(update_fields=['is_read', 'read_at'])
                
                cache.delete(get_unread_count_cache_key(user.id))
            return True
        except Notification.DoesNotExist:
            return False


    @staticmethod
    def mark_all_as_read(user):
        updated = Notification.objects.filter(user=user, is_read=False).update(
            is_read=True, 
            read_at=timezone.now()
        )
        if updated > 0:
            cache.delete(get_unread_count_cache_key(user.id))
        return updated


    @staticmethod
    def get_unread_count(user):
        cache_key = get_unread_count_cache_key(user.id)
        count = cache.get(cache_key)
        
        if count is None:
            count = Notification.objects.filter(user=user, is_read=False).count()
            cache.set(cache_key, count, timeout=3600)
            
        return count


    @staticmethod
    def get_user_notifications(user, limit=50):
        return Notification.objects.filter(user=user)[:limit]

    @staticmethod
    def notify_admins(notification_type, title, message, metadata=None, priority=Notification.Priority.MEDIUM):
        from django.contrib.auth import get_user_model
        from apps.account.enums import RoleCode
        User = get_user_model()
        
        admin_users = User.objects.filter(role__code=RoleCode.ADMIN.value, is_active=True)
        
        for admin in admin_users:
            try:
                NotificationService.create_notification(
                    user=admin,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    metadata=metadata,
                    priority=priority
                )
            except Exception:
                pass
        
    @staticmethod
    @transaction.atomic
    def bulk_delete(user, notification_ids):
        deleted_count, _ = Notification.objects.filter(
            user=user, 
            id__in=notification_ids
        ).delete()
        
        if deleted_count > 0:
            cache.delete(get_unread_count_cache_key(user.id))
            
        return deleted_count

    @staticmethod
    def _listing_display_title(instance):
        brand = getattr(instance, "brand", None)
        model = getattr(instance, "model", None)
        if brand:
            brand_text = str(brand)
            model_text = str(model).strip() if model else ""
            if model_text:
                return f"{brand_text} {model_text}".strip()
            return brand_text

        title_candidates = [
            getattr(instance, "title", None),
            getattr(instance, "name", None),
        ]
        company = getattr(instance, "company", None)
        if company is not None:
            title_candidates.append(getattr(company, "name", None))

        for candidate in title_candidates:
            if candidate:
                return str(candidate)

        return str(instance)

    @staticmethod
    def _listing_has_booking(instance, *, user=None, phone_candidates=None):
        from django.db.models import Q

        from apps.account.models import HotelProfile, normalize_phone_number
        from apps.listing.models import (
            Booking,
            CarListing,
            CarRental,
            EventSpaceListing,
            EventSpaceBooking,
            GuestHouseProfile,
            GuestHouseRoom,
            GuestHouseBooking,
            PropertyListing,
            RoomListing,
        )

        normalized_phones = {
            normalize_phone_number(phone)
            for phone in (phone_candidates or [])
            if normalize_phone_number(phone)
        }

        booking_filters = Q()
        if user is not None:
            if isinstance(instance, CarListing):
                booking_filters |= Q(renter=user)
            elif isinstance(instance, EventSpaceListing):
                booking_filters |= Q(user=user)
            elif isinstance(instance, GuestHouseProfile) or isinstance(instance, GuestHouseRoom):
                booking_filters |= Q(renter=user)
            elif isinstance(instance, HotelProfile) or isinstance(instance, RoomListing):
                booking_filters |= Q(user=user)

        if normalized_phones:
            booking_filters |= Q(guest_phone__in=list(normalized_phones))

        if not booking_filters.children:
            return False

        if isinstance(instance, HotelProfile):
            return Booking.objects.filter(items__room__hotel=instance).filter(booking_filters).exists()

        if isinstance(instance, GuestHouseProfile):
            return GuestHouseBooking.objects.filter(items__room__guest_house=instance).filter(booking_filters).exists()

        if isinstance(instance, GuestHouseRoom):
            return GuestHouseBooking.objects.filter(items__room=instance).filter(booking_filters).exists()

        if isinstance(instance, CarListing):
            return CarRental.objects.filter(rental_items__car_listing=instance).filter(booking_filters).exists()

        if isinstance(instance, EventSpaceListing):
            return EventSpaceBooking.objects.filter(items__event_space=instance).filter(booking_filters).exists()

        if isinstance(instance, RoomListing):
            return Booking.objects.filter(items__room=instance).filter(booking_filters).exists()

        if isinstance(instance, PropertyListing):
            return False

        return False

    @staticmethod
    def prepare_saved_listing_deletion_notifications(instance, *, deleted_by=None):
        from django.contrib.contenttypes.models import ContentType

        from apps.account.models import normalize_phone_number
        from apps.favorites.models import Favorite, GuestFavorite

        content_type = ContentType.objects.get_for_model(instance.__class__)
        listing_title = NotificationService._listing_display_title(instance)
        listing_id = str(getattr(instance, "id", ""))
        listing_type = f"{content_type.app_label}.{content_type.model}"

        plan = {
            "notification_type": Notification.NotificationType.LISTING_DELETED,
            "title": "Listing Deleted",
            "message": f"The listing '{listing_title}' you saved is no longer available on Mechot Marefiya.",
            "sms_message": f"The listing '{listing_title}' you saved is no longer available on Mechot Marefiya.",
            "metadata": {
                "listing_id": listing_id,
                "listing_type": listing_type,
                "listing_title": listing_title,
                "deleted_by_id": str(getattr(deleted_by, "id", "")) if deleted_by else None,
            },
            "users": [],
            "guest_phones": [],
        }

        user_ids = set()
        guest_phones = set()

        favorite_qs = Favorite.objects.filter(
            content_type=content_type,
            object_id=listing_id,
        ).select_related("user")

        for favorite in favorite_qs:
            user = getattr(favorite, "user", None)
            if not user or user.id in user_ids:
                continue
            phone_candidates = [getattr(user, "phone", None)]
            if NotificationService._listing_has_booking(instance, user=user, phone_candidates=phone_candidates):
                continue
            user_ids.add(user.id)
            plan["users"].append(user)

        guest_favorite_qs = GuestFavorite.objects.filter(
            content_type=content_type,
            object_id=listing_id,
        ).select_related("linked_user")

        for guest_favorite in guest_favorite_qs:
            linked_user = getattr(guest_favorite, "linked_user", None)
            if linked_user:
                if linked_user.id in user_ids:
                    continue
                phone_candidates = [guest_favorite.guest_phone, getattr(linked_user, "phone", None)]
                if NotificationService._listing_has_booking(
                    instance,
                    user=linked_user,
                    phone_candidates=phone_candidates,
                ):
                    continue
                user_ids.add(linked_user.id)
                plan["users"].append(linked_user)
                continue

            guest_phone = normalize_phone_number(guest_favorite.guest_phone)
            if not guest_phone or guest_phone in guest_phones:
                continue
            if NotificationService._listing_has_booking(instance, phone_candidates=[guest_phone]):
                continue
            guest_phones.add(guest_phone)
            plan["guest_phones"].append(guest_phone)

        return plan

    @staticmethod
    def dispatch_saved_listing_deletion_notifications(plan):
        from services.sms import send_sms

        notification_type = plan["notification_type"]
        title = plan["title"]
        message = plan["message"]
        sms_message = plan["sms_message"]
        metadata = plan["metadata"]

        for user in plan.get("users", []):
            try:
                NotificationService.create_notification(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    metadata=metadata,
                    priority=Notification.Priority.HIGH,
                )
            except Exception as exc:
                logger.error(
                    "Failed to create listing deletion notification for user %s: %s",
                    getattr(user, "id", user),
                    exc,
                    exc_info=True,
                )

        for guest_phone in plan.get("guest_phones", []):
            try:
                send_sms(guest_phone, sms_message)
            except Exception as exc:
                logger.error(
                    "Failed to send listing deletion SMS to %s: %s",
                    guest_phone,
                    exc,
                    exc_info=True,
                )

    @staticmethod
    @transaction.atomic
    def mark_read_batch(user, notification_ids):
        updated_count = Notification.objects.filter(
            user=user,
            id__in=notification_ids,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        if updated_count > 0:
            cache.delete(get_unread_count_cache_key(user.id))
            
        return updated_count


