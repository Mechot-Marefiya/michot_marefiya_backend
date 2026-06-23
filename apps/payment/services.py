import json
import requests
import hmac
import hashlib
import logging
from decimal import Decimal
from urllib.parse import quote
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.db import transaction as db_transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from apps.account.enums import RoleCode
from apps.payment.models import PaymentTransaction
from apps.listing.services import BookingService, get_effective_platform_fee_rate
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


def _is_admin_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return bool(
        getattr(user, "role", None)
        and user.role.code == RoleCode.ADMIN.value
    )


def _require_admin(user) -> None:
    if not _is_admin_user(user):
        raise PermissionDenied("Admin permission is required.")


def get_transaction_monitor_list(filters=None):
    filters = filters or {}
    queryset = PaymentTransaction.objects.select_related(
        "content_type",
        "booking",
        "booking__user",
        "vendor_company",
        "vendor_individual",
        "dispute_handled_by",
    ).all()

    status = filters.get("status")
    if status:
        queryset = queryset.filter(status=status)

    date_from = filters.get("date_from")
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)

    date_to = filters.get("date_to")
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    listing_type = filters.get("listing_type")
    if listing_type:
        queryset = queryset.filter(booking_type=listing_type)

    dispute_status = filters.get("dispute_status")
    if dispute_status:
        queryset = queryset.filter(dispute_status=dispute_status)

    has_dispute = filters.get("has_dispute")
    if has_dispute is not None:
        if str(has_dispute).lower() in {"1", "true", "yes"}:
            queryset = queryset.filter(dispute_status__isnull=False)
        elif str(has_dispute).lower() in {"0", "false", "no"}:
            queryset = queryset.filter(dispute_status__isnull=True)

    payout_failed = filters.get("payout_failed")
    if str(payout_failed).lower() in {"1", "true", "yes"}:
        queryset = queryset.filter(payout_status=PaymentTransaction.PayoutStatus.FAILED)

    return queryset


def get_transaction_monitor_detail(pk):
    try:
        return get_transaction_monitor_list().get(pk=pk)
    except PaymentTransaction.DoesNotExist as exc:
        raise Http404("Payment transaction not found.") from exc


def _append_dispute_note(transaction, note):
    if not note:
        return
    existing = transaction.dispute_note or ""
    transaction.dispute_note = f"{existing}\n{note}".strip() if existing else note


def open_dispute(transaction, admin, note=None):
    _require_admin(admin)
    if (
        transaction.dispute_status
        and transaction.dispute_status != PaymentTransaction.DisputeStatus.RESOLVED
    ):
        raise ValidationError("An active dispute already exists for this transaction.")

    now = timezone.now()
    transaction.dispute_status = PaymentTransaction.DisputeStatus.OPEN
    transaction.dispute_opened_at = now
    transaction.dispute_resolved_at = None
    transaction.dispute_handled_by = admin
    _append_dispute_note(transaction, note)
    transaction.save(
        update_fields=[
            "dispute_status",
            "dispute_note",
            "dispute_opened_at",
            "dispute_resolved_at",
            "dispute_handled_by",
            "updated_at",
        ]
    )
    return transaction


def update_dispute(transaction, admin, status, note=None):
    _require_admin(admin)
    valid_statuses = {choice.value for choice in PaymentTransaction.DisputeStatus}
    if status not in valid_statuses:
        raise ValidationError("Invalid dispute status.")
    if not transaction.dispute_status:
        raise ValidationError("Open a dispute before updating it.")
    if transaction.dispute_status == PaymentTransaction.DisputeStatus.RESOLVED and status != PaymentTransaction.DisputeStatus.RESOLVED:
        raise ValidationError("Resolved disputes cannot be reopened through this endpoint.")

    transaction.dispute_status = status
    transaction.dispute_handled_by = admin
    if status == PaymentTransaction.DisputeStatus.RESOLVED and not transaction.dispute_resolved_at:
        transaction.dispute_resolved_at = timezone.now()
    elif status != PaymentTransaction.DisputeStatus.RESOLVED:
        transaction.dispute_resolved_at = None
    _append_dispute_note(transaction, note)
    transaction.save(
        update_fields=[
            "dispute_status",
            "dispute_note",
            "dispute_resolved_at",
            "dispute_handled_by",
            "updated_at",
        ]
    )
    return transaction


def resolve_dispute(transaction, admin, note=None):
    return update_dispute(
        transaction,
        admin,
        PaymentTransaction.DisputeStatus.RESOLVED,
        note=note,
    )


class ContactRevealPaymentService:
    @staticmethod
    def _ttl_minutes():
        return getattr(settings, "CONTACT_REVEAL_REQUEST_TTL_MINUTES", 30)

    @staticmethod
    def _request_models():
        from apps.listing.models import ContactRevealRequest, PropertyContactRevealRequest

        return (ContactRevealRequest, PropertyContactRevealRequest)

    @staticmethod
    def _request_model_for_listing(listing):
        from apps.listing.models import CarSaleListing, ContactRevealRequest, PropertyContactRevealRequest, PropertySaleListing

        if isinstance(listing, CarSaleListing):
            return ContactRevealRequest
        if isinstance(listing, PropertySaleListing):
            return PropertyContactRevealRequest
        raise ValueError("Unsupported listing type for contact reveal.")

    @staticmethod
    def _contact_snapshot(listing):
        return {
            "seller_contact_name": listing.seller_contact_name,
            "seller_phone": listing.seller_phone,
            "seller_email": listing.seller_email,
            "off_platform_notice": (
                "The platform only connects buyer and seller. Any sale negotiation, "
                "inspection, transfer, or payment continues off-platform."
            ),
        }

    @staticmethod
    def expire_stale_requests(request_model=None):
        from django.utils import timezone

        total = 0
        models = (request_model,) if request_model else ContactRevealPaymentService._request_models()
        for model in models:
            stale = model.objects.filter(
                status__in=[
                    model.RevealStatus.REQUESTED,
                    model.RevealStatus.PAYMENT_INITIATED,
                ],
                expires_at__lte=timezone.now(),
            )
            total += stale.update(status=model.RevealStatus.EXPIRED)
        return total

    @staticmethod
    def create_reveal_request(*, listing, buyer=None, buyer_note="", buyer_phone=""):
        from apps.account.services import OtpService
        from django.utils import timezone

        request_model = ContactRevealPaymentService._request_model_for_listing(listing)
        ContactRevealPaymentService.expire_stale_requests(request_model=request_model)

        buyer_phone = OtpService.normalize_phone(buyer_phone)
        if buyer is None and not buyer_phone:
            raise ValidationError("Guest contact reveal requires a verified phone number.")

        filters = {
            "listing": listing,
            "status__in": [
                request_model.RevealStatus.REQUESTED,
                request_model.RevealStatus.PAYMENT_INITIATED,
                request_model.RevealStatus.PAID_REVEALED,
            ],
        }
        if buyer is not None:
            filters["buyer"] = buyer
        else:
            filters["buyer__isnull"] = True
            filters["buyer_phone"] = buyer_phone

        existing = request_model.objects.filter(**filters).order_by("-created_at").first()

        if existing:
            if existing.status == request_model.RevealStatus.PAID_REVEALED:
                return existing
            if existing.is_expired:
                existing.mark_expired()
            else:
                return existing

        expires_at = timezone.now() + timezone.timedelta(
            minutes=ContactRevealPaymentService._ttl_minutes()
        )
        return request_model.objects.create(
            listing=listing,
            buyer=buyer,
            buyer_note=buyer_note,
            buyer_phone=buyer_phone,
            amount=listing.reveal_fee,
            currency=listing.currency,
            expires_at=expires_at,
        )

    @staticmethod
    def initialize_contact_reveal_payment(reveal_request):
        from django.contrib.contenttypes.models import ContentType
        from django.utils import timezone

        request_model = reveal_request.__class__
        if reveal_request.status == request_model.RevealStatus.PAID_REVEALED:
            return {"success": False, "error": "Contact is already unlocked."}

        if reveal_request.is_expired:
            reveal_request.mark_expired()
            return {"success": False, "error": "Contact reveal request has expired."}

        tx_ref = ChapaPaymentService.generate_tx_ref(prefix="CONTACT")
        callback_url = getattr(settings, "CHAPA_CALLBACK_URL", None)
        return_base = getattr(settings, "FRONTEND_URL", None)

        if callback_url is None or return_base is None:
            return {"success": False, "error": "Callback URLs not configured", "tx_ref": tx_ref}

        buyer = reveal_request.buyer
        email = _safe_chapa_email(getattr(buyer, "email", ""), tx_ref)
        first_name = getattr(buyer, "first_name", "") or "User"
        last_name = getattr(buyer, "last_name", "") or ""
        return_url = return_base.rstrip("/") + f"/payments/complete?tx_ref={tx_ref}"

        payload = {
            "amount": str(reveal_request.amount),
            "currency": reveal_request.currency,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "tx_ref": tx_ref,
            "callback_url": callback_url,
            "return_url": return_url,
            "customization": {
                "title": "Contact Reveal",
                "description": f"Contact reveal for {reveal_request.listing.title}",
            },
            "meta": {
                "reveal_request_id": str(reveal_request.id),
                "listing_id": str(reveal_request.listing_id),
                "payment_type": "contact_reveal",
                "buyer_phone": reveal_request.buyer_phone,
            },
        }

        with db_transaction.atomic():
            content_type = ContentType.objects.get_for_model(reveal_request)
            payment_tx = PaymentTransaction.objects.create(
                content_type=content_type,
                object_id=reveal_request.id,
                booking_type="contact_reveal",
                tx_ref=tx_ref,
                amount=reveal_request.amount,
                currency=reveal_request.currency,
                status=PaymentTransaction.PaymentStatus.PENDING,
                metadata={
                    "reveal_request_id": str(reveal_request.id),
                    "listing_id": str(reveal_request.listing_id),
                    "buyer_phone": reveal_request.buyer_phone,
                    "locked_at": timezone.now().isoformat(),
                },
                payout_status=PaymentTransaction.PayoutStatus.NOT_APPLICABLE,
            )

            try:
                res = requests.post(
                    ChapaPaymentService.BASE_URL + "transaction/initialize",
                    headers=ChapaPaymentService._get_headers(),
                    data=json.dumps(payload),
                    timeout=15,
                )
                response_data = res.json()

                msg = response_data.get("message") or {}
                email_errors = msg.get("email") if isinstance(msg, dict) else None
                if email_errors and any("validation.email" in str(error) for error in email_errors):
                    fallback_email = _fallback_chapa_email(tx_ref)
                    logger.warning(
                        "Chapa rejected contact reveal email %s, retrying initialize with fallback %s",
                        payload.get("email"),
                        fallback_email,
                    )
                    payload["email"] = fallback_email
                    res = requests.post(
                        ChapaPaymentService.BASE_URL + "transaction/initialize",
                        headers=ChapaPaymentService._get_headers(),
                        data=json.dumps(payload),
                        timeout=15,
                    )
                    response_data = res.json()
            except Exception as e:
                payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                payment_tx.metadata["error"] = str(e)
                payment_tx.save(update_fields=["status", "metadata", "updated_at"])
                return {"success": False, "error": str(e), "tx_ref": tx_ref}

            if response_data.get("status") == "success":
                reveal_request.status = request_model.RevealStatus.PAYMENT_INITIATED
                reveal_request.tx_ref = tx_ref
                reveal_request.save(update_fields=["status", "tx_ref", "updated_at"])
                return {
                    "success": True,
                    "checkout_url": response_data["data"]["checkout_url"],
                    "tx_ref": tx_ref,
                    "reveal_request": reveal_request,
                }

            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            payment_tx.metadata["chapa_response"] = response_data
            payment_tx.save(update_fields=["status", "metadata", "updated_at"])
            return {
                "success": False,
                "error": _chapa_error_message(response_data),
                "provider_error": response_data,
                "tx_ref": tx_ref,
            }

    @staticmethod
    def unlock_contact_reveal(payment_tx, chapa_data):
        from django.utils import timezone

        reveal_request = payment_tx.resolved_booking
        if not isinstance(reveal_request, ContactRevealPaymentService._request_models()):
            return {"success": False, "message": "Transaction is not a contact reveal payment"}

        request_model = reveal_request.__class__
        if payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS:
            if reveal_request.status != request_model.RevealStatus.PAID_REVEALED:
                reveal_request.status = request_model.RevealStatus.PAID_REVEALED
                reveal_request.unlocked_at = timezone.now()
                reveal_request.contact_snapshot = ContactRevealPaymentService._contact_snapshot(reveal_request.listing)
                reveal_request.save(update_fields=["status", "unlocked_at", "contact_snapshot", "updated_at"])
            return {"success": True, "message": "Contact already unlocked"}

        verified_amount = Decimal(str(chapa_data.get("amount", "0")))
        verified_currency = chapa_data.get("currency")
        if Decimal(str(payment_tx.amount)) != verified_amount or payment_tx.currency != verified_currency:
            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            payment_tx.metadata["verification_error"] = {
                "error": "Amount/currency mismatch",
                "chapa_verification": chapa_data,
            }
            payment_tx.save(update_fields=["status", "metadata", "updated_at"])
            return {"success": False, "message": "Amount or currency mismatch"}

        payment_tx.status = PaymentTransaction.PaymentStatus.SUCCESS
        payment_tx.chapa_transaction_id = chapa_data.get("id") or chapa_data.get("reference")
        payment_tx.payment_method = chapa_data.get("method") or chapa_data.get("payment_method", "unknown")
        payment_tx.metadata["verification_success"] = chapa_data
        payment_tx.save()

        reveal_request.status = request_model.RevealStatus.PAID_REVEALED
        reveal_request.unlocked_at = timezone.now()
        reveal_request.contact_snapshot = ContactRevealPaymentService._contact_snapshot(reveal_request.listing)
        reveal_request.save(update_fields=["status", "unlocked_at", "contact_snapshot", "updated_at"])

        def enqueue_notification():
            from apps.listing.tasks import send_contact_reveal_unlocked_notification
            send_contact_reveal_unlocked_notification.delay(reveal_request.id)

        db_transaction.on_commit(enqueue_notification)
        return {"success": True, "message": "Payment verified and contact unlocked"}

    @staticmethod
    def get_unlocked_contact(*, listing, buyer=None, tx_ref=None):
        from rest_framework.exceptions import PermissionDenied

        request_model = ContactRevealPaymentService._request_model_for_listing(listing)
        ContactRevealPaymentService.expire_stale_requests(request_model=request_model)
        queryset = request_model.objects.filter(
            listing=listing,
            status=request_model.RevealStatus.PAID_REVEALED,
        )
        if buyer is not None:
            queryset = queryset.filter(buyer=buyer)
        elif tx_ref:
            queryset = queryset.filter(tx_ref=tx_ref)
        else:
            raise PermissionDenied("Contact details are available only after successful payment verification.")

        reveal_request = queryset.order_by("-unlocked_at").first()

        if not reveal_request:
            raise PermissionDenied("Contact details are available only after successful payment verification.")

        contact = reveal_request.contact_snapshot or ContactRevealPaymentService._contact_snapshot(listing)
        return {
            "listing_id": listing.id,
            "request_id": reveal_request.id,
            "status": reveal_request.status,
            **contact,
        }


def _money(value):
    return Decimal(str(value or "0.00")).quantize(Decimal("0.01"))


def get_chapa_receipt_url(payment_tx):
    if payment_tx.status != PaymentTransaction.PaymentStatus.SUCCESS:
        return None
    if not payment_tx.chapa_transaction_id:
        return None

    reference = quote(str(payment_tx.chapa_transaction_id), safe="")
    return f"https://chapa.link/payment-receipt/{reference}"


def verify_webhook_signature(raw_body, signature):
    secret = getattr(settings, "CHAPA_WEBHOOK_SECRET", None)
    if not secret or not raw_body or not signature:
        return False

    signature = str(signature).strip()
    if signature.startswith("sha256="):
        signature = signature.removeprefix("sha256=")

    computed = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return constant_time_compare(computed, signature)


def is_tax_applicable(booking) -> bool:
    if booking.__class__.__name__ != "PropertyRentalBooking":
        return False

    property_listing = getattr(booking, "property_listing", None)
    if not getattr(property_listing, "individual_owner_id", None):
        return False

    from apps.account.services import is_agreement_active

    return is_agreement_active(property_listing.individual_owner)


def calculate_tax(owner_price) -> Decimal:
    rate = getattr(settings, "PROPERTY_RENTAL_TAX_RATE")
    if not isinstance(rate, Decimal):
        rate = Decimal(str(rate))
    return (Decimal(str(owner_price or "0.00")) * rate).quantize(Decimal("0.01"))


def get_payment_tax_breakdown(booking, *, owner_price=None, amount=None):
    if owner_price is None:
        owner_price = ChapaPaymentService._booking_base_subtotal(booking)

    owner_price = _money(owner_price)
    fee_rate = get_effective_platform_fee_rate(booking=booking)
    service_fee = _money(owner_price * fee_rate)
    tax_amount = calculate_tax(owner_price) if is_tax_applicable(booking) else None
    grand_total = _money(owner_price + service_fee + (tax_amount or Decimal("0.00")))

    if amount is not None and booking.__class__.__name__ != "PropertyRentalBooking":
        grand_total = _money(amount)
        service_fee = _money(grand_total - owner_price)

    return {
        "owner_price": owner_price,
        "service_fee": service_fee,
        "tax_amount": tax_amount,
        "grand_total": grand_total,
        "tax_rate": getattr(settings, "PROPERTY_RENTAL_TAX_RATE") if tax_amount is not None else None,
        "tax_liability_status": (
            PaymentTransaction.TaxLiabilityStatus.APPLICABLE if tax_amount is not None else None
        ),
    }


def apply_tax_to_transaction(transaction, booking) -> None:
    if not is_tax_applicable(booking):
        return

    breakdown = get_payment_tax_breakdown(booking)
    transaction.tax_amount = breakdown["tax_amount"]
    transaction.tax_rate = breakdown["tax_rate"]
    transaction.tax_liability_status = breakdown["tax_liability_status"]
    transaction.save(update_fields=["tax_amount", "tax_rate", "tax_liability_status", "updated_at"])


def validate_split_config(split_type, split_value):
    from apps.payment.models import PaymentPlatformConfig

    normalized_type = str(split_type or "").strip().lower()
    value = Decimal(str(split_value))
    valid_types = {choice.value for choice in PaymentPlatformConfig.SplitType}

    if normalized_type not in valid_types:
        raise ValidationError("Invalid split type.")
    if value < Decimal("0.0000"):
        raise ValidationError("Split value cannot be negative.")
    if (
        normalized_type == PaymentPlatformConfig.SplitType.PERCENTAGE
        and value > Decimal("1.0000")
    ):
        raise ValidationError("Percentage split value must be between 0 and 1.")

    return {
        "split_type": normalized_type,
        "split_value": value,
    }


def get_effective_platform_split_config():
    from apps.payment.models import PaymentPlatformConfig

    config = (
        PaymentPlatformConfig.objects.filter(is_active=True)
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if config:
        return validate_split_config(
            config.default_split_type,
            config.default_split_value,
        )

    return validate_split_config(
        getattr(settings, "PLATFORM_DEFAULT_SPLIT_TYPE", "percentage"),
        getattr(settings, "PLATFORM_DEFAULT_SPLIT_VALUE", Decimal("0.02")),
    )


def get_effective_contact_reveal_fee(listing_kind: str) -> Decimal:
    from apps.payment.models import PaymentPlatformConfig

    config = (
        PaymentPlatformConfig.objects.filter(is_active=True)
        .order_by("-updated_at", "-created_at")
        .first()
    )

    if listing_kind == "car_sale":
        if config:
            return Decimal(str(config.default_car_sale_reveal_fee))
        return Decimal(str(getattr(settings, "DEFAULT_CAR_SALE_REVEAL_FEE", Decimal("100.00"))))

    if listing_kind == "property_sale":
        if config:
            return Decimal(str(config.default_property_sale_reveal_fee))
        return Decimal(
            str(getattr(settings, "DEFAULT_PROPERTY_SALE_REVEAL_FEE", Decimal("100.00")))
        )

    raise ValidationError("Unsupported reveal fee listing type.")


def resolve_payment_owner_for_split(booking):
    if booking is None:
        return None

    if booking.__class__.__name__ in {"ContactRevealRequest", "PropertyContactRevealRequest"}:
        return None

    if booking.__class__.__name__ == "PropertyRentalBooking":
        listing = getattr(booking, "property_listing", None)
        if listing:
            return getattr(listing, "company", None) or getattr(listing, "individual_owner", None)
        return None

    items = getattr(booking, "items", None)
    if items is not None and items.exists():
        first_item = items.first()

        room = getattr(first_item, "room", None)
        if room is not None:
            hotel = getattr(room, "hotel", None)
            if hotel is not None:
                return getattr(hotel, "company", None)

            guest_house = getattr(room, "guest_house", None)
            if guest_house is not None:
                return getattr(guest_house, "company", None) or getattr(
                    guest_house,
                    "individual_owner",
                    None,
                )

        event_space = getattr(first_item, "event_space", None)
        if event_space is not None:
            hotel = getattr(event_space, "hotel", None)
            if hotel is not None:
                return getattr(hotel, "company", None)
            return getattr(event_space, "company", None) or getattr(
                event_space,
                "individual_owner",
                None,
            )

    rental_items = getattr(booking, "rental_items", None)
    if rental_items is not None and rental_items.exists():
        first_item = rental_items.first()
        car_listing = getattr(first_item, "car_listing", None)
        if car_listing is not None:
            return getattr(car_listing, "company", None) or getattr(
                car_listing,
                "individual_owner",
                None,
            )

    return None


def _owner_split_config_is_complete(owner):
    return bool(
        owner
        and getattr(owner, "split_config_active", False)
        and getattr(owner, "split_type", None)
        and getattr(owner, "split_value", None) is not None
    )


def get_effective_split_config_for_owner(owner):
    if _owner_split_config_is_complete(owner):
        return validate_split_config(owner.split_type, owner.split_value)

    return get_effective_platform_split_config()


def get_effective_split_config_for_booking(booking):
    owner = resolve_payment_owner_for_split(booking)
    return get_effective_split_config_for_owner(owner)


def get_effective_chapa_subaccount_id(owner):
    stored_subaccount_id = (getattr(owner, "chapa_subaccount_id", None) or "").strip()
    sandbox_subaccount_id = (getattr(settings, "CHAPA_SANDBOX_SUBACCOUNT_ID", "") or "").strip()
    settings_module = getattr(settings, "SETTINGS_MODULE", "")
    sandbox_override_allowed = bool(
        sandbox_subaccount_id
        and (getattr(settings, "DEBUG", False) or settings_module == "config.settings.test")
    )

    if sandbox_override_allowed and (
        not stored_subaccount_id or stored_subaccount_id.startswith("demo-subaccount-")
    ):
        return sandbox_subaccount_id

    return stored_subaccount_id or None


def _is_chapa_subaccount_mismatch_response(response_data):
    if not isinstance(response_data, dict):
        return False

    message = response_data.get("message")
    if not isinstance(message, dict):
        return False

    return bool(message.get("subaccounts.id"))


def _chapa_error_message(response_data, fallback="Payment initialization failed. Please try again."):
    if not isinstance(response_data, dict):
        return str(response_data or fallback)

    message = response_data.get("message") or response_data.get("error")
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        parts = []
        for field, errors in message.items():
            if isinstance(errors, (list, tuple)):
                joined_errors = ", ".join(str(error) for error in errors)
            else:
                joined_errors = str(errors)
            parts.append(f"{field}: {joined_errors}")
        return "; ".join(parts) or fallback
    if message:
        return str(message)
    return fallback


def _fallback_chapa_email(tx_ref):
    configured = getattr(settings, "CHAPA_FALLBACK_EMAIL", None)
    if configured:
        try:
            validate_email(configured)
            return configured
        except DjangoValidationError:
            pass

    token = "".join(ch for ch in str(tx_ref).lower() if ch.isalnum())[:16]
    if not token:
        token = hashlib.sha256(str(tx_ref).encode("utf-8")).hexdigest()[:16]
    return f"no-reply+{token}@gmail.com"


def _safe_chapa_email(email, tx_ref):
    candidate = (email or "").strip()
    try:
        validate_email(candidate)
    except DjangoValidationError:
        return _fallback_chapa_email(tx_ref)
    return candidate


SPLIT_PAYMENT_CONFIGURATION_ERROR = (
    "Payment is temporarily unavailable because this listing's payout account "
    "is not configured correctly. Please contact support."
)


def _fail_split_payment(payment_tx, *, detail=None, provider_response=None):
    payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
    payment_tx.payout_status = PaymentTransaction.PayoutStatus.FAILED
    split_error = provider_response or {"detail": detail or SPLIT_PAYMENT_CONFIGURATION_ERROR}
    if isinstance(payment_tx.metadata, dict):
        payment_tx.metadata["split_error"] = split_error
    else:
        payment_tx.metadata = {"split_error": split_error}
    payment_tx.save(update_fields=["status", "payout_status", "metadata", "updated_at"])
    return {
        "success": False,
        "code": "SPLIT_PAYMENT_CONFIGURATION_ERROR",
        "error": SPLIT_PAYMENT_CONFIGURATION_ERROR,
        "tx_ref": payment_tx.tx_ref,
    }


def _chapa_transaction_status(response_data):
    if not isinstance(response_data, dict):
        return ""

    data = response_data.get("data")
    if not isinstance(data, dict):
        return ""

    return str(data.get("status") or "").strip().lower()


def _chapa_verification_is_success(response_data):
    return (
        isinstance(response_data, dict)
        and response_data.get("status") == "success"
        and _chapa_transaction_status(response_data) == "success"
    )


def _chapa_verification_is_pending(response_data):
    return (
        isinstance(response_data, dict)
        and response_data.get("status") == "success"
        and _chapa_transaction_status(response_data) in {"pending", "processing"}
    )


def _mark_payment_verification_pending(payment_tx, verification):
    if isinstance(payment_tx.metadata, dict):
        payment_tx.metadata["verification_pending"] = verification
    else:
        payment_tx.metadata = {"verification_pending": verification}
    payment_tx.save(update_fields=["metadata", "updated_at"])


def _chapa_base_url():
    return getattr(settings, "CHAPA_BASE_URL", ChapaPaymentService.BASE_URL).rstrip("/") + "/"


def _extract_chapa_subaccount_id(response_data):
    data = response_data.get("data") if isinstance(response_data, dict) else None
    if not isinstance(data, dict):
        return None

    subaccount = data.get("subaccount")
    nested_id = subaccount.get("id") if isinstance(subaccount, dict) else None
    return data.get("subaccounts[id]") or data.get("subaccount_id") or data.get("id") or nested_id


def register_chapa_subaccount(
    *,
    owner,
    bank_code,
    account_number,
    business_name,
    account_name,
    split_type=None,
    split_value=None,
    allow_overwrite=False,
):
    if owner is None:
        raise ValidationError("Unsupported owner target.")

    existing_subaccount_id = getattr(owner, "chapa_subaccount_id", None)
    if existing_subaccount_id and not allow_overwrite:
        raise ValidationError("Owner already has a Chapa subaccount.")

    if split_type is not None or split_value is not None:
        if split_type is None or split_value is None:
            raise ValidationError("Both split_type and split_value are required together.")
        split_config = validate_split_config(split_type, split_value)
        owner_split_update = True
    else:
        split_config = get_effective_split_config_for_owner(owner)
        owner_split_update = False

    payload = {
        "bank_code": bank_code,
        "account_number": account_number,
        "business_name": business_name,
        "account_name": account_name,
        "split_type": split_config["split_type"],
        "split_value": float(split_config["split_value"]),
    }

    try:
        response = requests.post(
            _chapa_base_url() + "subaccount",
            headers=ChapaPaymentService._get_headers(),
            data=json.dumps(payload),
            timeout=15,
        )
        response_data = response.json()
    except Exception as exc:
        logger.warning("Chapa subaccount registration failed before response: %s", exc)
        return {
            "success": False,
            "error": "Unable to register Chapa subaccount.",
            "status_code": 400,
        }

    if response_data.get("status") != "success":
        return {
            "success": False,
            "error": response_data.get("message") or "Unable to register Chapa subaccount.",
            "status_code": 400,
        }

    subaccount_id = _extract_chapa_subaccount_id(response_data)
    if not subaccount_id:
        logger.warning("Chapa subaccount success response did not include subaccount id.")
        return {
            "success": False,
            "error": "Chapa subaccount response did not include an ID.",
            "status_code": 400,
        }

    owner.chapa_subaccount_id = subaccount_id
    update_fields = ["chapa_subaccount_id", "updated_at"]
    if owner_split_update:
        owner.split_type = split_config["split_type"]
        owner.split_value = split_config["split_value"]
        owner.split_config_active = True
        update_fields.extend(["split_type", "split_value", "split_config_active"])
    owner.save(update_fields=update_fields)

    return {
        "success": True,
        "chapa_subaccount_id": subaccount_id,
        "split_type": owner.split_type,
        "split_value": owner.split_value,
        "split_config_active": owner.split_config_active,
    }


class ChapaPaymentService:
    BASE_URL = "https://api.chapa.co/v1/"

    @staticmethod
    def generate_tx_ref(prefix="MICHOT"):
        import time, random
        random_num = random.randint(1000, 9999)
        timestamp = int(time.time())
        return f"{prefix}-{timestamp}-{random_num}"

    @staticmethod
    def _get_headers():
        return {
            "Authorization": f"Bearer {settings.CHAPA_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _is_walk_in_booking(booking):
        return str(getattr(booking, "status", "")).lower() == "walk_in"

    @staticmethod
    def _booking_base_subtotal(booking):
        total = Decimal("0.00")

        if booking.__class__.__name__.lower() == "booking":
            use_seasonal = getattr(settings, "FEATURE_SEASONAL_PRICING", False)
            if use_seasonal:
                from apps.listing.models import BookingItemPrice
                for price in BookingItemPrice.objects.filter(booking_item__booking=booking):
                    total += Decimal(price.price_per_unit) * Decimal(price.units)
            else:
                nights = (booking.check_out_date - booking.check_in_date).days
                for item in booking.items.all():
                    total += Decimal(item.price_per_unit) * Decimal(item.units_booked) * Decimal(nights)
        elif hasattr(booking, "items"):
            for item in booking.items.all():
                if hasattr(item, "subtotal"):
                    total += Decimal(item.subtotal())
        elif hasattr(booking, "rental_items"):
            days = (booking.end_date - booking.start_date).days or 1
            for item in booking.rental_items.all():
                total += Decimal(item.subtotal(days=days))
        elif booking.__class__.__name__ == "PropertyRentalBooking":
            from apps.listing.services import PropertyRentalAvailabilityService

            price_details = PropertyRentalAvailabilityService.price_details(
                booking.property_listing,
                booking.start_date,
                booking.end_date,
                payment_currency=booking.currency,
            )
            total += sum(Decimal(str(detail["price_per_unit"])) for detail in price_details)

        return total

    @staticmethod
    def _booking_addon_subtotal(booking):
        if booking.__class__.__name__.lower() != "booking":
            return Decimal("0.00")

        from apps.listing.models import BookingAddon
        return sum(
            (Decimal(addon.price_per_unit) * Decimal(addon.quantity))
            for addon in BookingAddon.objects.filter(booking_item__booking=booking)
        )

    @staticmethod
    def _calculate_split_amounts(booking, amount):
        total_dec = Decimal(str(amount))

        if ChapaPaymentService._is_walk_in_booking(booking):
            split_config = {
                "split_type": "flat",
                "split_value": Decimal("0.0000"),
            }
            return {
                "split_type": split_config["split_type"],
                "split_value": split_config["split_value"],
                "commission_rate": None,
                "commission_amount": Decimal("0.00"),
                "vendor_payout_amount": total_dec,
                "commissionable_amount": Decimal("0.00"),
                "addon_amount": ChapaPaymentService._booking_addon_subtotal(booking),
                "walk_in": True,
            }

        split_config = get_effective_split_config_for_booking(booking)
        split_value = Decimal(str(split_config["split_value"]))
        commissionable_amount = total_dec
        addon_amount = ChapaPaymentService._booking_addon_subtotal(booking)
        if split_config["split_type"] == "percentage":
            commission_amount = commissionable_amount * split_value
            commission_rate = split_value
        else:
            commission_amount = split_value
            commission_rate = None

        if commission_amount > total_dec:
            raise ValidationError("Split commission cannot exceed payment amount.")

        vendor_payout_amount = total_dec - commission_amount

        return {
            "split_type": split_config["split_type"],
            "split_value": split_value,
            "commission_rate": commission_rate,
            "commission_amount": commission_amount,
            "vendor_payout_amount": vendor_payout_amount,
            "commissionable_amount": commissionable_amount,
            "addon_amount": addon_amount,
            "walk_in": False,
        }

    @staticmethod
    def initialize_payment(booking, email, first_name, last_name, amount, booking_type="booking", currency="ETB", metadata=None):
        tx_ref = ChapaPaymentService.generate_tx_ref()
        payment_breakdown = None
        if booking.__class__.__name__ == "PropertyRentalBooking":
            payment_breakdown = get_payment_tax_breakdown(booking)
            amount = payment_breakdown["grand_total"]

        callback_url = getattr(settings, "CHAPA_CALLBACK_URL", None)
        return_base = getattr(settings, "FRONTEND_URL", None)

        if callback_url is None or return_base is None:
            return {"success": False, "error": "Callback URLs not configured", "tx_ref": tx_ref}

        return_url = return_base.rstrip("/") + f"/payments/complete?tx_ref={tx_ref}"

        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError

        try:
            validate_email(email)
            user_email = email
        except Exception:
            user_email = f"no-reply+{tx_ref[:8]}@example.com"

        payload = {
            "amount": str(amount),
            "currency": currency,
            "email": user_email,
            "first_name": first_name or "User",
            "last_name": last_name or "",
            "tx_ref": tx_ref,
            "callback_url": callback_url,
            "return_url": return_url,
            "customization": {
                "title": "Michot Marefiya",
                "description": f"Booking payment - Terms {getattr(booking, 'terms_version', 'unknown')}",
            },
            "meta": {
                "tc_version": getattr(booking, "terms_version", "unknown"),
                "tc_accepted_at": booking.terms_accepted_at.isoformat() if hasattr(booking, "terms_accepted_at") and booking.terms_accepted_at else None,
                "booking_id": str(booking.id),
                "is_legacy": getattr(booking, "is_legacy", False),
            }
        }

        # SPLIT PAYMENT LOGIC & LEDGER PREP
        commission_rate = None
        commission_amount = None
        vendor_payout_amount = None
        payout_status = PaymentTransaction.PayoutStatus.NOT_APPLICABLE
        split_configuration_error = None
        
        vendor_obj = None
        vendor_company = None
        vendor_individual = None
        
        try:
            vendor_obj = resolve_payment_owner_for_split(booking)
            subaccount_id = None
            if vendor_obj:
                subaccount_id = get_effective_chapa_subaccount_id(vendor_obj)
                
                from apps.account.models import CompanyProfile, IndividualOwnerProfile
                if isinstance(vendor_obj, CompanyProfile):
                    vendor_company = vendor_obj
                elif isinstance(vendor_obj, IndividualOwnerProfile):
                    vendor_individual = vendor_obj

            if subaccount_id:
                split = ChapaPaymentService._calculate_split_amounts(booking, amount)
                
                # Round to 2 decimal places
                vendor_share_fixed = split["vendor_payout_amount"].quantize(Decimal("0.01"))
                platform_share_fixed = split["commission_amount"].quantize(Decimal("0.01"))
                
                payload["subaccounts"] = {
                    "id": subaccount_id,
                }
                
                commission_rate = split["commission_rate"]
                commission_amount = platform_share_fixed
                vendor_payout_amount = vendor_share_fixed
                payout_status = PaymentTransaction.PayoutStatus.PENDING

                logger.info(
                    "Split configured for %s: platform commission estimate %s, vendor payout estimate %s",
                    tx_ref,
                    platform_share_fixed,
                    vendor_share_fixed,
                )
            else:
                 # Missing payout configuration blocks checkout below.
                 split_configuration_error = "The booking owner has no Chapa payout subaccount."
                 logger.error("Split payment configuration missing for %s.", tx_ref)
                 payout_status = PaymentTransaction.PayoutStatus.FAILED
                
        except Exception as e:
            logger.error(f"Failed to configure split payment for {tx_ref}: {e}")
            payout_status = PaymentTransaction.PayoutStatus.FAILED
            split_configuration_error = str(e)

        with db_transaction.atomic():
            # Using GenericForeignKey for multi-booking-type support
            from django.contrib.contenttypes.models import ContentType
            content_type = ContentType.objects.get_for_model(booking)
            
            payment_tx = PaymentTransaction.objects.create(
                content_type=content_type,
                object_id=booking.id,
                booking_type=booking_type,
                tx_ref=tx_ref,
                amount=amount,
                currency=currency,
                status=PaymentTransaction.PaymentStatus.PENDING,
                metadata=metadata or {},
                
                commission_rate=commission_rate,
                commission_amount=commission_amount,
                vendor_payout_amount=vendor_payout_amount,
                payout_status=payout_status,
                vendor_company=vendor_company,
                vendor_individual=vendor_individual
            )

            if split_configuration_error:
                return _fail_split_payment(payment_tx, detail=split_configuration_error)

            try:
                logger.debug("Chapa initialize payload: %s", payload)
                res = requests.post(
                    ChapaPaymentService.BASE_URL + "transaction/initialize",
                    headers=ChapaPaymentService._get_headers(),
                    data=json.dumps(payload),
                    timeout=15
                )
                response_data = res.json()
                logger.debug("Chapa initialize response: %s", response_data)

                msg = response_data.get("message") or {}
                email_errors = None
                try:
                    if isinstance(msg, dict):
                        email_errors = msg.get("email")
                except Exception:
                    email_errors = None

                if email_errors and any("validation.email" in str(e) for e in email_errors):
                    fallback = getattr(settings, "CHAPA_FALLBACK_EMAIL", None) or f"no-reply+{tx_ref[:8]}@gmail.com"
                    logger.warning("Chapa rejected email %s, retrying initialize with fallback %s", user_email, fallback)
                    payload["email"] = fallback
                    try:
                        res2 = requests.post(
                            ChapaPaymentService.BASE_URL + "transaction/initialize",
                            headers=ChapaPaymentService._get_headers(),
                            data=json.dumps(payload),
                            timeout=15,
                        )
                        response_data = res2.json()
                        logger.debug("Chapa initialize response (retry): %s", response_data)
                    except Exception as e2:
                        payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                        if isinstance(payment_tx.metadata, dict):
                            payment_tx.metadata["error"] = str(e2)
                        else:
                            payment_tx.metadata = {"error": str(e2)}
                        payment_tx.save()
                        return {"success": False, "error": str(e2), "tx_ref": tx_ref}

                if payload.get("subaccounts") and _is_chapa_subaccount_mismatch_response(response_data):
                    rejected_subaccount = payload["subaccounts"].get("id")
                    logger.error(
                        "Chapa rejected payout subaccount %s for %s; checkout was blocked.",
                        rejected_subaccount,
                        tx_ref,
                    )
                    return _fail_split_payment(
                        payment_tx,
                        provider_response=response_data,
                    )
            except Exception as e:
                payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                if isinstance(payment_tx.metadata, dict):
                    payment_tx.metadata["error"] = str(e)
                else:
                    payment_tx.metadata = {"error": str(e)}
                payment_tx.save()
                return {"success": False, "error": str(e), "tx_ref": tx_ref}

            if response_data.get("status") == "success":
                if booking.__class__.__name__ == "PropertyRentalBooking":
                    apply_tax_to_transaction(payment_tx, booking)
                return {
                    "success": True,
                    "checkout_url": response_data["data"]["checkout_url"],
                    "tx_ref": tx_ref,
                    **({
                        "owner_price": str(payment_breakdown["owner_price"]),
                        "service_fee": str(payment_breakdown["service_fee"]),
                        "tax_amount": (
                            str(payment_breakdown["tax_amount"])
                            if payment_breakdown["tax_amount"] is not None else None
                        ),
                        "tax_rate": (
                            str(payment_breakdown["tax_rate"])
                            if payment_breakdown["tax_rate"] is not None else None
                        ),
                        "grand_total": str(payment_breakdown["grand_total"]),
                        "tax_liability_status": payment_breakdown["tax_liability_status"],
                    } if payment_breakdown else {}),
                }

            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            if isinstance(payment_tx.metadata, dict):
                payment_tx.metadata["chapa_response"] = response_data
            else:
                payment_tx.metadata = response_data
            payment_tx.save()
            return {"success": False, "error": response_data, "tx_ref": tx_ref}

    @staticmethod
    def initialize_car_rental_extension_payment(
        extension_request,
        *,
        email,
        first_name,
        last_name,
    ):
        from django.contrib.contenttypes.models import ContentType
        from apps.account.models import CompanyProfile, IndividualOwnerProfile

        rental = extension_request.rental
        tx_ref = ChapaPaymentService.generate_tx_ref(prefix="CEXT")
        callback_url = getattr(settings, "CHAPA_CALLBACK_URL", None)
        return_base = getattr(settings, "FRONTEND_URL", None)

        if callback_url is None or return_base is None:
            CarRentalService = __import__("apps.listing.services", fromlist=["CarRentalService"]).CarRentalService
            CarRentalService.mark_extension_request_failed(
                extension_request,
                reason="Callback URLs not configured.",
            )
            return {"success": False, "error": "Callback URLs not configured", "tx_ref": tx_ref}

        return_url = return_base.rstrip("/") + f"/payments/complete?tx_ref={tx_ref}"

        from django.core.validators import validate_email

        try:
            validate_email(email)
            user_email = email
        except Exception:
            user_email = f"no-reply+{tx_ref[:8]}@example.com"

        payload = {
            "amount": str(extension_request.amount),
            "currency": extension_request.currency,
            "email": user_email,
            "first_name": first_name or "User",
            "last_name": last_name or "",
            "tx_ref": tx_ref,
            "callback_url": callback_url,
            "return_url": return_url,
            "customization": {
                "title": "Michot Marefiya",
                "description": f"Car rental extension payment - {rental.booking_reference}",
            },
            "meta": {
                "payment_type": "carrental_extension",
                "extension_request_id": str(extension_request.id),
                "rental_id": str(rental.id),
                "booking_reference": rental.booking_reference,
                "original_end_date": extension_request.original_end_date.isoformat(),
                "requested_end_date": extension_request.requested_end_date.isoformat(),
            },
        }

        commission_rate = None
        commission_amount = None
        vendor_payout_amount = None
        payout_status = PaymentTransaction.PayoutStatus.NOT_APPLICABLE
        split_configuration_error = None
        vendor_company = None
        vendor_individual = None

        try:
            vendor_obj = resolve_payment_owner_for_split(rental)
            subaccount_id = get_effective_chapa_subaccount_id(vendor_obj) if vendor_obj else None
            if isinstance(vendor_obj, CompanyProfile):
                vendor_company = vendor_obj
            elif isinstance(vendor_obj, IndividualOwnerProfile):
                vendor_individual = vendor_obj

            if subaccount_id:
                split = ChapaPaymentService._calculate_split_amounts(rental, extension_request.amount)
                vendor_share_fixed = split["vendor_payout_amount"].quantize(Decimal("0.01"))
                platform_share_fixed = split["commission_amount"].quantize(Decimal("0.01"))
                payload["subaccounts"] = {
                    "id": subaccount_id,
                }
                commission_rate = split["commission_rate"]
                commission_amount = platform_share_fixed
                vendor_payout_amount = vendor_share_fixed
                payout_status = PaymentTransaction.PayoutStatus.PENDING
            else:
                payout_status = PaymentTransaction.PayoutStatus.FAILED
                split_configuration_error = "The booking owner has no Chapa payout subaccount."
        except Exception as exc:
            logger.error("Failed to configure extension split payment for %s: %s", tx_ref, exc)
            payout_status = PaymentTransaction.PayoutStatus.FAILED
            split_configuration_error = str(exc)

        content_type = ContentType.objects.get_for_model(extension_request)
        payment_tx = PaymentTransaction.objects.create(
            content_type=content_type,
            object_id=extension_request.id,
            booking_type="carrental_extension",
            tx_ref=tx_ref,
            amount=extension_request.amount,
            currency=extension_request.currency,
            status=PaymentTransaction.PaymentStatus.PENDING,
            metadata={
                "payment_type": "carrental_extension",
                "extension_request_id": str(extension_request.id),
                "rental_id": str(rental.id),
                "booking_reference": rental.booking_reference,
            },
            commission_rate=commission_rate,
            commission_amount=commission_amount,
            vendor_payout_amount=vendor_payout_amount,
            payout_status=payout_status,
            vendor_company=vendor_company,
            vendor_individual=vendor_individual,
        )

        if split_configuration_error:
            result = _fail_split_payment(payment_tx, detail=split_configuration_error)
            __import__("apps.listing.services", fromlist=["CarRentalService"]).CarRentalService.mark_extension_request_failed(
                extension_request,
                reason=result["error"],
            )
            return result

        try:
            res = requests.post(
                ChapaPaymentService.BASE_URL + "transaction/initialize",
                headers=ChapaPaymentService._get_headers(),
                data=json.dumps(payload),
                timeout=15,
            )
            response_data = res.json()
        except Exception as exc:
            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            if isinstance(payment_tx.metadata, dict):
                payment_tx.metadata["error"] = str(exc)
            else:
                payment_tx.metadata = {"error": str(exc)}
            payment_tx.save(update_fields=["status", "metadata", "updated_at"])
            __import__("apps.listing.services", fromlist=["CarRentalService"]).CarRentalService.mark_extension_request_failed(
                extension_request,
                reason=str(exc),
            )
            return {"success": False, "error": str(exc), "tx_ref": tx_ref}

        if response_data.get("status") == "success":
            extension_request.status = extension_request.ExtensionStatus.PAYMENT_INITIATED
            extension_request.tx_ref = tx_ref
            extension_request.save(update_fields=["status", "tx_ref", "updated_at"])
            return {
                "success": True,
                "checkout_url": response_data["data"]["checkout_url"],
                "tx_ref": tx_ref,
            }

        if payload.get("subaccounts") and _is_chapa_subaccount_mismatch_response(response_data):
            result = _fail_split_payment(payment_tx, provider_response=response_data)
            __import__("apps.listing.services", fromlist=["CarRentalService"]).CarRentalService.mark_extension_request_failed(
                extension_request,
                reason=result["error"],
            )
            return result

        payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
        if isinstance(payment_tx.metadata, dict):
            payment_tx.metadata["chapa_response"] = response_data
        else:
            payment_tx.metadata = response_data
        payment_tx.save(update_fields=["status", "metadata", "updated_at"])
        __import__("apps.listing.services", fromlist=["CarRentalService"]).CarRentalService.mark_extension_request_failed(
            extension_request,
            reason=str(response_data),
        )
        return {"success": False, "error": response_data, "tx_ref": tx_ref}

    @staticmethod
    def _release_car_rental_extension_after_failure(payment_tx, *, status):
        extension_request = payment_tx.resolved_booking
        if extension_request is None:
            return
        CarRentalService = __import__("apps.listing.services", fromlist=["CarRentalService"]).CarRentalService
        CarRentalService.mark_extension_request_failed(
            extension_request,
            status=status,
            reason=f"Extension payment moved to {status}.",
        )

    @staticmethod
    def cancel_transaction(tx_ref):
        try:
            tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
            if tx.status == PaymentTransaction.PaymentStatus.PENDING:
                try:
                    res = requests.put(
                        _chapa_base_url() + f"transaction/cancel/{tx_ref}",
                        headers=ChapaPaymentService._get_headers(),
                        timeout=10,
                    )
                    response_data = res.json()
                except Exception as exc:
                    logger.warning("Chapa cancellation failed before response for %s: %s", tx_ref, exc)
                    return {"success": False, "error": "Unable to cancel transaction with Chapa."}

                message = response_data.get("message") or "Transaction cancellation failed"
                response_status = str(response_data.get("status") or "").lower()
                already_expired = (
                    response_status == "failed"
                    and "already expired" in str(message).lower()
                )

                if response_status == "success" or already_expired:
                    metadata = tx.metadata if isinstance(tx.metadata, dict) else {}
                    metadata["chapa_cancel_response"] = response_data
                    tx.metadata = metadata
                    tx.status = PaymentTransaction.PaymentStatus.CANCELLED
                    tx.save(update_fields=["status", "metadata", "updated_at"])
                    if tx.booking_type == "carrental_extension":
                        ChapaPaymentService._release_car_rental_extension_after_failure(
                            tx,
                            status="cancelled",
                        )
                    return {"success": True, "message": message}

                metadata = tx.metadata if isinstance(tx.metadata, dict) else {}
                metadata["chapa_cancel_error"] = response_data
                tx.metadata = metadata
                tx.save(update_fields=["metadata", "updated_at"])
                return {"success": False, "error": message}
            else:
                return {"success": False, "error": f"Cannot cancel transaction in status {tx.status}"}
        except PaymentTransaction.DoesNotExist:
            return {"success": False, "error": "Transaction not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def verify_payment(tx_ref):
        url = f"{ChapaPaymentService.BASE_URL}transaction/verify/{tx_ref}"
        try:
            res = requests.get(url, headers=ChapaPaymentService._get_headers(), timeout=10)
            return res.json()
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    @staticmethod
    def _webhook_tx_ref(data):
        return (
            data.get("tx_ref")
            or data.get("trx_ref")
            or data.get("reference")
            or data.get("ref_id")
        )

    @staticmethod
    def _safe_webhook_metadata(data):
        allowed = {
            "event",
            "status",
            "reference",
            "tx_ref",
            "trx_ref",
            "ref_id",
            "amount",
            "currency",
            "charge",
            "mode",
            "type",
            "payment_method",
            "chapa_reference",
            "bank_reference",
            "created_at",
            "updated_at",
        }
        return {key: data.get(key) for key in allowed if key in data}

    @staticmethod
    def _append_webhook_metadata(payment_tx, data, *, key="webhook_events"):
        metadata = payment_tx.metadata if isinstance(payment_tx.metadata, dict) else {}
        events = metadata.get(key)
        if not isinstance(events, list):
            events = []
        event_data = ChapaPaymentService._safe_webhook_metadata(data)
        event_fingerprint = (
            event_data.get("event"),
            event_data.get("reference") or event_data.get("chapa_reference"),
            event_data.get("tx_ref") or event_data.get("trx_ref") or event_data.get("ref_id"),
        )
        for existing in events:
            existing_fingerprint = (
                existing.get("event"),
                existing.get("reference") or existing.get("chapa_reference"),
                existing.get("tx_ref") or existing.get("trx_ref") or existing.get("ref_id"),
            )
            if existing_fingerprint == event_fingerprint:
                payment_tx.metadata = metadata
                return False
        events.append(event_data)
        metadata[key] = events
        payment_tx.metadata = metadata
        return True

    @staticmethod
    def _cancel_booking_after_webhook_failure(payment_tx):
        if payment_tx.booking_type == "carrental_extension":
            ChapaPaymentService._release_car_rental_extension_after_failure(
                payment_tx,
                status="failed",
            )
            return

        booking = payment_tx.resolved_booking
        if not booking:
            return

        booking_model_name = booking.__class__.__name__.lower()
        from apps.listing.services import (
            BookingService,
            GuestHouseBookingService,
            EventSpaceBookingService,
            CarRentalService,
            PropertyRentalBookingService,
        )

        service_map = {
            "booking": BookingService,
            "guesthousebooking": GuestHouseBookingService,
            "eventspacebooking": EventSpaceBookingService,
            "carrental": CarRentalService,
            "propertyrentalbooking": PropertyRentalBookingService,
        }
        service = service_map.get(booking_model_name)
        if service and hasattr(service, "cancel_booking"):
            try:
                service.cancel_booking(booking)
            except Exception as exc:
                logger.error(
                    "Failed to release booking after failed webhook for %s %s: %s",
                    booking_model_name,
                    getattr(booking, "id", None),
                    exc,
                )

    @staticmethod
    def handle_callback(payload):
        tx_ref = (
            payload.get("tx_ref")
            or payload.get("trx_ref")
            or payload.get("reference")
            or payload.get("ref_id")
        )

        if not tx_ref:
            return {"success": False, "message": "Missing tx_ref in callback"}

        try:
            with db_transaction.atomic():
                # Use select_for_update to handle concurrent callbacks/webhooks safely
                payment_tx = PaymentTransaction.objects.select_for_update().get(tx_ref=tx_ref)
                
                booking = payment_tx.resolved_booking
                if not booking:
                    logger.error(f"PaymentTransaction {tx_ref} has no associated booking!")
                    return {" success": False, "message": "No booking associated with payment"}

                if payment_tx.booking_type == "contact_reveal":
                    if payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS:
                        result = ContactRevealPaymentService.unlock_contact_reveal(payment_tx, {})
                        return result if result["success"] else {"success": False, "message": result["message"]}

                    verification = ChapaPaymentService.verify_payment(tx_ref)

                    if not _chapa_verification_is_success(verification):
                        if _chapa_verification_is_pending(verification):
                            _mark_payment_verification_pending(payment_tx, verification)
                            return {"success": False, "message": "Payment pending", "status": "pending"}
                        payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                        if isinstance(payment_tx.metadata, dict):
                            payment_tx.metadata["verification_error"] = verification
                        else:
                            payment_tx.metadata = {"verification_error": verification}
                        payment_tx.save()
                        return {"success": False, "message": "Verification failed"}

                    result = ContactRevealPaymentService.unlock_contact_reveal(
                        payment_tx,
                        verification["data"],
                    )
                    return result if result["success"] else {"success": False, "message": result["message"]}

                if payment_tx.booking_type == "carrental_extension":
                    from apps.listing.services import CarRentalService

                    extension_request = payment_tx.resolved_booking
                    if extension_request is None:
                        return {"success": False, "message": "No extension request associated with payment"}

                    if payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS:
                        CarRentalService.apply_paid_extension(extension_request)
                        return {"success": True, "message": "Car rental extension already applied"}

                    verification = ChapaPaymentService.verify_payment(tx_ref)
                    if not _chapa_verification_is_success(verification):
                        if _chapa_verification_is_pending(verification):
                            _mark_payment_verification_pending(payment_tx, verification)
                            return {"success": False, "message": "Payment pending", "status": "pending"}
                        payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                        if isinstance(payment_tx.metadata, dict):
                            payment_tx.metadata["verification_error"] = verification
                        else:
                            payment_tx.metadata = {"verification_error": verification}
                        payment_tx.save()
                        CarRentalService.mark_extension_request_failed(
                            extension_request,
                            reason="Extension payment verification failed.",
                        )
                        return {"success": False, "message": "Verification failed"}

                    chapa_data = verification["data"]
                    verified_amount = Decimal(str(chapa_data.get("amount", "0")))
                    verified_currency = chapa_data.get("currency")

                    if Decimal(str(payment_tx.amount)) != verified_amount or payment_tx.currency != verified_currency:
                        payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                        error_info = {"error": "Amount/currency mismatch", "chapa_verification": chapa_data}
                        if isinstance(payment_tx.metadata, dict):
                            payment_tx.metadata.update(error_info)
                        else:
                            payment_tx.metadata = error_info
                        payment_tx.save()
                        CarRentalService.mark_extension_request_failed(
                            extension_request,
                            reason="Extension payment amount or currency mismatch.",
                        )
                        return {"success": False, "message": "Amount or currency mismatch"}

                    payment_tx.status = PaymentTransaction.PaymentStatus.SUCCESS
                    payment_tx.chapa_transaction_id = chapa_data.get("id") or chapa_data.get("reference")
                    payment_tx.payment_method = chapa_data.get("method") or chapa_data.get("payment_method", "unknown")
                    if isinstance(payment_tx.metadata, dict):
                        payment_tx.metadata["verification_success"] = chapa_data
                    else:
                        payment_tx.metadata = {"verification_success": chapa_data}
                    payment_tx.save()

                    CarRentalService.apply_paid_extension(extension_request)
                    return {"success": True, "message": "Payment verified and car rental extended"}
                
                booking_model_name = booking.__class__.__name__.lower()
                
                from apps.listing.services import (
                    BookingService, 
                    GuestHouseBookingService, 
                    EventSpaceBookingService,
                    CarRentalService,
                    PropertyRentalBookingService
                )
                
                SERVICE_MAP = {
                    'booking': BookingService,
                    'guesthousebooking': GuestHouseBookingService,
                    'eventspacebooking': EventSpaceBookingService,
                    'carrental': CarRentalService,
                    'propertyrentalbooking': PropertyRentalBookingService,
                }
                
                service = SERVICE_MAP.get(booking_model_name)
                if not service:
                    logger.error(f"Unknown booking type: {booking_model_name}")
                    return {"success": False, "message": f"Unsupported booking type: {booking_model_name}"}
                
                # Check for booking status even if payment is already success (idempotency recovery)
                if payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS:
                    if hasattr(booking, 'status'):
                        if booking_model_name == 'booking':
                            from apps.listing.models import Booking
                            if booking.status == Booking.BookingStatus.PENDING:
                                logger.info(f"Transaction {tx_ref} is SUCCESS but Booking {booking.id} is PENDING. Recovering...")
                                service.confirm_booking(booking)
                                return {"success": True, "message": "Booking confirmed via recovery path"}
                        elif booking_model_name in ['guesthousebooking', 'eventspacebooking']:
                            if booking.status == 'pending':
                                logger.info(f"Transaction {tx_ref} is SUCCESS but {booking_model_name} {booking.id} is PENDING. Recovering...")
                                service.confirm_booking(booking)
                                return {"success": True, "message": "Booking confirmed via recovery path"}
                        elif booking_model_name == 'carrental':
                            from apps.listing.models import CarRental as CarRentalClass
                            if booking.status == CarRentalClass.RentStatus.PENDING:
                                logger.info(f"Transaction {tx_ref} is SUCCESS but CarRental {booking.id} is PENDING. Recovering...")
                                service.confirm_booking(booking)
                                return {"success": True, "message": "Rental confirmed via recovery path"}
                        elif booking_model_name == 'propertyrentalbooking':
                            if booking.status == 'pending':
                                logger.info(f"Transaction {tx_ref} is SUCCESS but PropertyRentalBooking {booking.id} is PENDING. Recovering...")
                                service.confirm_booking(booking)
                                return {"success": True, "message": "Property rental booking confirmed via recovery path"}
                    return {"success": True, "message": "Already processed"}

                verification = ChapaPaymentService.verify_payment(tx_ref)

                if not _chapa_verification_is_success(verification):
                    if _chapa_verification_is_pending(verification):
                        _mark_payment_verification_pending(payment_tx, verification)
                        return {"success": False, "message": "Payment pending", "status": "pending"}
                    payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                    if isinstance(payment_tx.metadata, dict):
                        payment_tx.metadata["verification_error"] = verification
                    else:
                        payment_tx.metadata = verification
                    payment_tx.save()
                    
                    recipient = getattr(booking, 'user', None) or getattr(booking, 'renter', None)
                    if recipient:
                        NotificationService.create_notification(
                            user=recipient,
                            notification_type=Notification.NotificationType.PAYMENT_FAILED,
                            title="Payment Failed",
                            message=f"Payment for booking {getattr(booking, 'booking_reference', booking.id)} failed verification.",
                            metadata={
                                'booking_reference': getattr(booking, 'booking_reference', str(booking.id)),
                                'transaction_reference': tx_ref,
                                'reason': 'Verification failed'
                            },
                            priority=Notification.Priority.HIGH
                        )
                    
                    # Phase 4: Immediate release on definitive failure
                    try:
                        if hasattr(service, 'cancel_booking'):
                            service.cancel_booking(booking)
                        else:
                            logger.warning(f"{service.__name__} does not have cancel_booking method")
                    except Exception as e:
                        logger.error(f"Failed to auto-cancel {booking_model_name} {booking.id} after payment failure: {e}")
                        
                    return {"success": False, "message": "Verification failed"}

                chapa_data = verification["data"]

                # Use str() before Decimal() to prevent floating point precision issues
                verified_amount = Decimal(str(chapa_data.get("amount", "0")))
                verified_currency = chapa_data.get("currency")

                if Decimal(str(payment_tx.amount)) != verified_amount or payment_tx.currency != verified_currency:
                    payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                    error_info = {"error": "Amount/currency mismatch", "chapa_verification": chapa_data}
                    if isinstance(payment_tx.metadata, dict):
                        payment_tx.metadata.update(error_info)
                    else:
                        payment_tx.metadata = error_info
                    payment_tx.save()
                    
                    recipient = getattr(booking, 'user', None) or getattr(booking, 'renter', None)
                    if recipient:
                        NotificationService.create_notification(
                            user=recipient,
                            notification_type=Notification.NotificationType.PAYMENT_FAILED,
                            title="Payment Failed",
                            message=f"Payment for booking {getattr(booking, 'booking_reference', booking.id)} failed due to amount mismatch.",
                            metadata={
                                'booking_reference': getattr(booking, 'booking_reference', str(booking.id)),
                                'transaction_reference': tx_ref,
                                'reason': 'Amount/Currency mismatch'
                            },
                            priority=Notification.Priority.HIGH
                        )
                    
                    try:
                        if hasattr(service, 'cancel_booking'):
                            service.cancel_booking(booking)
                        else:
                            logger.warning(f"{service.__name__} does not have cancel_booking method")
                    except Exception as e:
                        logger.error(f"Failed to auto-cancel {booking_model_name} {booking.id} after mismatch: {e}")
                        
                    return {"success": False, "message": "Amount or currency mismatch"}

                # Update Transaction
                payment_tx.status = PaymentTransaction.PaymentStatus.SUCCESS
                # Map ID robustly: Chapa sometimes uses 'id' or 'reference' in the data block
                payment_tx.chapa_transaction_id = chapa_data.get("id") or chapa_data.get("reference")
                payment_tx.payment_method = chapa_data.get("method") or chapa_data.get("payment_method", "unknown")
                
                if isinstance(payment_tx.metadata, dict):
                    payment_tx.metadata["verification_success"] = chapa_data
                else:
                    payment_tx.metadata = {"verification_success": chapa_data}
                payment_tx.save()

                # Confirm Booking (Now inside the same transaction)
                service.confirm_booking(booking)

                recipient = getattr(booking, 'user', None) or getattr(booking, 'renter', None)
                if recipient:
                    NotificationService.create_notification(
                        user=recipient,
                        notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
                        title="Payment Successful",
                        message=f"Payment for booking {getattr(booking, 'booking_reference', booking.id)} was successful.",
                        metadata={
                            'booking_reference': getattr(booking, 'booking_reference', str(booking.id)),
                            'amount': str(payment_tx.amount),
                            'currency': payment_tx.currency,
                            'transaction_reference': tx_ref
                        },
                        priority=Notification.Priority.HIGH
                    )


            return {"success": True, "message": "Payment verified and booking confirmed"}

        except PaymentTransaction.DoesNotExist:
            return {"success": False, "message": f"Transaction {tx_ref} not found"}
        except Exception as e:
            logger.exception(f"Callback processing error for {tx_ref}: {e}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def handle_webhook(request):
        try:
            raw = request.body
            if not raw:
                return {"success": True, "message": "Webhook ignored"}

            headers = {k.lower(): v for k, v in request.headers.items()}
            signature = headers.get("x-chapa-signature") or headers.get("chapa-signature")

            if not verify_webhook_signature(raw, signature):
                return {"success": True, "message": "Webhook ignored"}

            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {"success": True, "message": "Webhook ignored"}

            event = str(data.get("event") or "").lower()
            tx_ref = ChapaPaymentService._webhook_tx_ref(data)

            if event.startswith("payout."):
                if tx_ref:
                    try:
                        payment_tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
                        ChapaPaymentService._append_webhook_metadata(payment_tx, data, key="payout_webhook_events")
                        payment_tx.save(update_fields=["metadata", "updated_at"])
                    except PaymentTransaction.DoesNotExist:
                        pass
                return {"success": True, "message": "Webhook processed"}

            if not tx_ref:
                return {"success": True, "message": "Webhook ignored"}

            try:
                payment_tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
            except PaymentTransaction.DoesNotExist:
                if event == "charge.success" or data.get("status") == "success":
                    return ChapaPaymentService.handle_callback(data)
                return {"success": True, "message": "Webhook ignored"}

            if not ChapaPaymentService._append_webhook_metadata(payment_tx, data):
                payment_tx.save(update_fields=["metadata", "updated_at"])
                return {"success": True, "message": "Already processed"}

            if event == "charge.success" or data.get("status") == "success":
                payment_tx.save(update_fields=["metadata", "updated_at"])
                return ChapaPaymentService.handle_callback(data)

            if event == "charge.failed/cancelled" or data.get("status") in {"failed", "cancelled"}:
                event_status = str(data.get("status") or "").lower()
                payment_tx.status = (
                    PaymentTransaction.PaymentStatus.CANCELLED
                    if event_status == "cancelled"
                    else PaymentTransaction.PaymentStatus.FAILED
                )
                payment_tx.save(update_fields=["status", "metadata", "updated_at"])
                ChapaPaymentService._cancel_booking_after_webhook_failure(payment_tx)
                return {"success": True, "message": "Webhook processed"}

            if event in {"charge.refunded", "charge.reversed"}:
                payment_tx.save(update_fields=["metadata", "updated_at"])
                return {"success": True, "message": "Webhook processed"}

            payment_tx.save(update_fields=["metadata", "updated_at"])
            return {"success": True, "message": "Webhook processed"}

        except Exception as e:
            logger.exception("Webhook error: %s", e)
            return {"success": False, "message": str(e)}
