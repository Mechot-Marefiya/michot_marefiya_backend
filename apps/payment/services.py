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
    def initialize_payment(booking, email, first_name, last_name, amount, currency="ETB"):
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
            user_email = f"no-reply+{tx_ref[:8]}@michot.local"

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
                "description": "Booking payment",
            }
        }

        with db_transaction.atomic():
            payment_tx = PaymentTransaction.objects.create(
                booking=booking,
                tx_ref=tx_ref,
                amount=amount,
                currency=currency,
                status=PaymentTransaction.PaymentStatus.PENDING
            )

            try:
                res = requests.post(
                    ChapaPaymentService.BASE_URL + "transaction/initialize",
                    headers=ChapaPaymentService._get_headers(),
                    data=json.dumps(payload),
                    timeout=15
                )
                response_data = res.json()
            except Exception as e:
                payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
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
            payment_tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
        except PaymentTransaction.DoesNotExist:
            return {"success": False, "message": "Transaction not found"}

        if payment_tx.status == PaymentTransaction.PaymentStatus.SUCCESS:
            return {"success": True, "message": "Already processed"}

        verification = ChapaPaymentService.verify_payment(tx_ref)

        if verification.get("status") != "success":
            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            payment_tx.metadata = verification
            payment_tx.save()
            return {"success": False, "message": "Verification failed"}

        chapa_data = verification["data"]

        verified_amount = Decimal(chapa_data.get("amount", "0"))
        verified_currency = chapa_data.get("currency")

        if Decimal(str(payment_tx.amount)) != verified_amount or payment_tx.currency != verified_currency:
            payment_tx.status = PaymentTransaction.PaymentStatus.FAILED
            payment_tx.metadata = {"error": "Amount/currency mismatch", "chapa": chapa_data}
            payment_tx.save()
            return {"success": False, "message": "Amount or currency mismatch"}

        payment_tx.status = PaymentTransaction.PaymentStatus.SUCCESS
        payment_tx.chapa_transaction_id = chapa_data.get("id")
        payment_tx.payment_method = chapa_data.get("payment_method", "unknown")
        payment_tx.metadata = {"verification": chapa_data}
        payment_tx.save()

        try:
            BookingService.confirm_booking(payment_tx.booking)
        except Exception as e:
            logger.exception("Booking confirmation failure: %s", e)

        return {"success": True, "message": "Payment verified and booking confirmed"}

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
