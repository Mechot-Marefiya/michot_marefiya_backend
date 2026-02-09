import json
import requests
import hmac
import hashlib
import logging
from decimal import Decimal
from django.conf import settings
from django.utils.crypto import constant_time_compare
from django.db import transaction as db_transaction

from apps.payment.models import PaymentTransaction
from apps.listing.services import BookingService
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


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
    def initialize_payment(booking, booking_type, email, first_name, last_name, amount, currency="ETB", metadata=None):
        tx_ref = ChapaPaymentService.generate_tx_ref()

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
        
        vendor_obj = None
        vendor_company = None
        vendor_individual = None
        
        try:
            subaccount_id = None
            if hasattr(booking, 'items') and booking.items.exists():
                first_item = booking.items.first()
                
                # 1. Hotel Room / Event Space (via Hotel)
                if hasattr(first_item, 'room') and first_item.room and hasattr(first_item.room, 'hotel') and first_item.room.hotel:
                    vendor_obj = first_item.room.hotel.company
                elif hasattr(first_item, 'event_space') and first_item.event_space and hasattr(first_item.event_space, 'hotel') and first_item.event_space.hotel:
                    vendor_obj = first_item.event_space.hotel.company
                
                # 2. Guest House (direct Company link or Individual)
                elif hasattr(first_item, 'room') and first_item.room:
                     if hasattr(first_item.room, 'guest_house') and first_item.room.guest_house:
                        gh = first_item.room.guest_house
                        if gh.company:
                            vendor_obj = gh.company
                        elif gh.individual_owner:
                            vendor_obj = gh.individual_owner
                
                # 3. Car Rental
                elif hasattr(first_item, 'car_listing') and first_item.car_listing:
                    vendor_obj = first_item.car_listing.company
            
            if vendor_obj:
                if hasattr(vendor_obj, 'chapa_subaccount_id'):
                    subaccount_id = vendor_obj.chapa_subaccount_id
                
                from apps.account.models import CompanyProfile, IndividualOwnerProfile
                if isinstance(vendor_obj, CompanyProfile):
                    vendor_company = vendor_obj
                elif isinstance(vendor_obj, IndividualOwnerProfile):
                    vendor_individual = vendor_obj

            if subaccount_id:
                total_dec = Decimal(str(amount))
                
                # Calculate sharing using centralized rate
                fee_rate = getattr(settings, 'PLATFORM_FEE_RATE', Decimal('0.05'))
                if not isinstance(fee_rate, Decimal):
                    fee_rate = Decimal(str(fee_rate))
                
                # total = base * (1 + rate) => base = total / (1 + rate)
                divisor = Decimal('1') + fee_rate
                vendor_share = total_dec / divisor
                platform_share = total_dec - vendor_share
                
                # Round to 2 decimal places
                vendor_share_fixed = vendor_share.quantize(Decimal("0.01"))
                platform_share_fixed = platform_share.quantize(Decimal("0.01"))
                
                payload["subaccount_id"] = subaccount_id
                payload["split_type"] = "flat"
                payload["split_value"] = float(vendor_share_fixed)
                
                commission_rate = fee_rate
                commission_amount = platform_share_fixed
                vendor_payout_amount = vendor_share_fixed
                payout_status = PaymentTransaction.PayoutStatus.PENDING

                logger.info(
                    f"Split configured for {tx_ref}: Vendor receives {vendor_share_fixed} (Subaccount {subaccount_id}), "
                    f"Platform keeps {platform_share_fixed} (Rate {fee_rate})"
                )
            else:
                 # No subaccount found, so money stays in main account
                 if vendor_obj:
                     logger.warning(f"Vendor {vendor_obj} has no chapa_subaccount_id. Split failed.")
                     payout_status = PaymentTransaction.PayoutStatus.FAILED
                
        except Exception as e:
            logger.error(f"Failed to configure split payment for {tx_ref}: {e}")
            payout_status = PaymentTransaction.PayoutStatus.FAILED
            # Proceed without split (all money to main account) as fallback

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
            except Exception as e:
                payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                if isinstance(payment_tx.metadata, dict):
                    payment_tx.metadata["error"] = str(e)
                else:
                    payment_tx.metadata = {"error": str(e)}
                payment_tx.save()
                return {"success": False, "error": str(e), "tx_ref": tx_ref}

            if response_data.get("status") == "success":
                return {
                    "success": True,
                    "checkout_url": response_data["data"]["checkout_url"],
                    "tx_ref": tx_ref,
                }

            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            if isinstance(payment_tx.metadata, dict):
                payment_tx.metadata["chapa_response"] = response_data
            else:
                payment_tx.metadata = response_data
            payment_tx.save()
            return {"success": False, "error": response_data, "tx_ref": tx_ref}

    @staticmethod
    def cancel_transaction(tx_ref):
        try:
            tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
            if tx.status == PaymentTransaction.PaymentStatus.PENDING:
                tx.status = PaymentTransaction.PaymentStatus.CANCELLED
                tx.save()
                return {"success": True, "message": "Transaction cancelled successfully"}
            else:
                return {"success": False, "error": f"Cannot cancel transaction in status {tx.status}"}
        except PaymentTransaction.DoesNotExist:
            return {"success": False, "error": "Transaction not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}


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
            except Exception as e:
                payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                if isinstance(payment_tx.metadata, dict):
                    payment_tx.metadata["error"] = str(e)
                else:
                    payment_tx.metadata = {"error": str(e)}
                payment_tx.save()
                return {"success": False, "error": str(e), "tx_ref": tx_ref}

            if response_data.get("status") == "success":
                return {
                    "success": True,
                    "checkout_url": response_data["data"]["checkout_url"],
                    "tx_ref": tx_ref,
                }

            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            if isinstance(payment_tx.metadata, dict):
                payment_tx.metadata["chapa_response"] = response_data
            else:
                payment_tx.metadata = response_data
            payment_tx.save()
            return {"success": False, "error": response_data, "tx_ref": tx_ref}

    @staticmethod
    def verify_payment(tx_ref):
        url = f"{ChapaPaymentService.BASE_URL}transaction/verify/{tx_ref}"
        try:
            res = requests.get(url, headers=ChapaPaymentService._get_headers(), timeout=10)
            return res.json()
        except Exception as e:
            return {"status": "failed", "error": str(e)}

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
                
                booking_model_name = booking.__class__.__name__.lower()
                
                from apps.listing.services import (
                    BookingService, 
                    GuestHouseBookingService, 
                    EventSpaceBookingService,
                    CarRentalService
                )
                
                SERVICE_MAP = {
                    'booking': BookingService,
                    'guesthousebooking': GuestHouseBookingService,
                    'eventspacebooking': EventSpaceBookingService,
                    'carrental': CarRentalService,
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
                    return {"success": True, "message": "Already processed"}

                verification = ChapaPaymentService.verify_payment(tx_ref)

                if verification.get("status") != "success":
                    payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
                    if isinstance(payment_tx.metadata, dict):
                        payment_tx.metadata["verification_error"] = verification
                    else:
                        payment_tx.metadata = verification
                    payment_tx.save()
                    
                    NotificationService.create_notification(
                        user=booking.user,
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
                    
                    NotificationService.create_notification(
                        user=booking.user,
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

                NotificationService.create_notification(
                    user=booking.user,
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
                return {"success": False, "message": "Empty webhook body"}

            headers = {k.lower(): v for k, v in request.headers.items()}
            signature = headers.get("chapa-signature") or headers.get("x-chapa-signature")

            secret = getattr(settings, "CHAPA_WEBHOOK_SECRET", None)
            if not secret:
                return {"success": False, "message": "Webhook secret not configured"}

            if not signature:
                return {"success": False, "message": "Missing signature"}

            computed = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

            if not constant_time_compare(computed, signature):
                return {"success": False, "message": "Invalid signature"}

            data = json.loads(raw.decode("utf-8"))

            tx_ref = (
                data.get("tx_ref")
                or data.get("trx_ref")
                or data.get("reference")
                or data.get("ref_id")
            )

            if tx_ref:
                try:
                    ex = PaymentTransaction.objects.get(tx_ref=tx_ref)
                    if ex.status == PaymentTransaction.PaymentStatus.SUCCESS:
                        return {"success": True, "message": "Already processed"}
                except:
                    pass

            return ChapaPaymentService.handle_callback(data)

        except Exception as e:
            logger.exception("Webhook error: %s", e)
            return {"success": False, "message": str(e)}
