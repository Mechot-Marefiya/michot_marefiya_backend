import json
import uuid
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from django.conf import settings
from django.utils import timezone
from apps.listing.models import Booking
from apps.account.enums import RoleCode
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, OpenApiExample
from .serializers import (
    PaymentInitializeSerializer, 
    PaymentTransactionSerializer, 
    PaymentInitializeResponseSerializer,
    ChapaCallbackSerializer,
    ChapaWebhookSerializer
)
from apps.core.utils import convert_currency
from .models import PaymentTransaction
from .services import ChapaPaymentService

@extend_schema(tags=["Payments"])
class InitiatePaymentView(APIView):
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Initiate payment for a booking",
        description="""
        Initiates a payment transaction via Chapa for a specific booking.
        The server calculates and locks the exchange rate at the moment of initiation 
        to ensure price consistency throughout the payment flow.
        
        **Access Control**:
        - **Authenticated**: Users can pay for their own bookings.
        - **Guest**: Public access allowed if the booking is a 'Guest Booking' (no registered user).
        """,
        request=PaymentInitializeSerializer,
        responses={
            200: PaymentInitializeResponseSerializer,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                "Successful Initiation",
                value={
                    "success": True,
                    "message": "Payment initialized",
                    "checkout_url": "https://checkout.chapa.co/checkout/payment/...",
                    "tx_ref": "marefiya-booking-123-abc",
                    "calculated_amount": "5000.00",
                    "payment_currency": "ETB",
                    "exchange_rate": "1.0",
                    "original_amount": "5000.00",
                    "original_currency": "ETB"
                }
            )
        ]
    )
    def post(self, request):
        """
        Initiate payment for a booking.
        Supports multiple booking types: 'booking', 'guesthouse', 'eventspace', 'carrental'.
        Users can only initiate payment for their own bookings.
        Companies can initiate payment for bookings they own (as customers).
        Admin can initiate payment for any booking.
        """
        serializer = PaymentInitializeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        booking_type = serializer.validated_data.get('booking_type', 'booking')
        booking_id = serializer.validated_data['booking_id']
        
        BOOKING_MODELS = {
            'booking': ('listing', 'Booking', 'user'),
            'guesthouse': ('listing', 'GuestHouseBooking', 'renter'),
            'eventspace': ('listing', 'EventSpaceBooking', 'user'),
            'carrental': ('listing', 'CarRental', 'renter'),
        }
        
        if booking_type not in BOOKING_MODELS:
            return Response(
                {"error": f"Invalid booking_type: {booking_type}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        app_label, model_name, user_field = BOOKING_MODELS[booking_type]
        
        from django.apps import apps
        try:
            BookingModel = apps.get_model(app_label, model_name)
        except LookupError:
            return Response(
                {"error": f"Booking model {model_name} not found"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            booking = BookingModel.objects.get(id=booking_id)
        except BookingModel.DoesNotExist:
            return Response(
                {"error": f"{model_name} not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permission: user must own the booking (or be admin)
        user = request.user
        
        if user.is_authenticated:
            is_admin = user.is_superuser or (
                hasattr(user, 'role') and
                user.role and
                user.role.code == RoleCode.ADMIN.value
            )
            
            booking_user = getattr(booking, user_field, None)
            if not is_admin and booking_user != user:
                return Response(
                    {"error": "You can only initiate payment for your own bookings."},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            # GUEST FLOW VERIFICATION
            booking_user = getattr(booking, user_field, None)
            if booking_user is not None:
                return Response(
                    {"error": "This booking belongs to a registered user. Please log in to pay."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        status_field = 'status'
        booking_status = getattr(booking, status_field, None)
        
        if booking_type == 'booking':
            from apps.listing.models import Booking as BookingClass
            if booking_status != BookingClass.BookingStatus.PENDING:
                return Response(
                    {"error": "Booking is already processed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif booking_type in ['guesthouse', 'eventspace']:
            if booking_status != 'pending':
                return Response(
                    {"error": "Booking is already processed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif booking_type == 'carrental':
            from apps.listing.models import CarRental as CarRentalClass
            if booking_status != CarRentalClass.RentStatus.PENDING:
                return Response(
                    {"error": "Rental is already processed"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if booking.is_legacy:
            return Response(
                {
                    "error": "This is a legacy booking. Please contact support or re-book to accept current Terms & Conditions.",
                    "code": "LEGACY_BOOKING_NOT_PAYABLE"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.listing.services import TermsService
        
        content_object = None
        if hasattr(booking, 'items') and booking.items.exists():
            first_item = booking.items.first()
            if hasattr(first_item, 'room') and first_item.room:
                room = first_item.room
                if hasattr(room, 'hotel') and room.hotel:
                    content_object = room.hotel
                elif hasattr(room, '__class__') and room.__class__.__name__ == 'GuestHouseListing':
                    content_object = room
            elif hasattr(first_item, 'event_space') and first_item.event_space:
                content_object = first_item.event_space.hotel
        elif hasattr(booking, 'rental_items') and booking.rental_items.exists():
            first_item = booking.rental_items.first()
            if hasattr(first_item, 'car_listing') and first_item.car_listing:
                content_object = first_item.car_listing
        
        if content_object:
            active_tc = TermsService.get_active_terms(content_object)
            if active_tc and booking.terms_version != active_tc.version:
                return Response(
                    {
                        "error": "The Terms & Conditions have been updated since you booked. Please review and accept the latest version before paying.",
                        "code": "TERMS_UPDATED",
                        "current_version": active_tc.version,
                        "accepted_version": booking.terms_version
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Determine the target currency for payment
        payment_currency = serializer.validated_data.get('currency') or booking.currency or 'ETB'
        
        # PRICE GUARD & RATE LOCK: Calculate and lock the correct amount on the server
        try:
            expected_amount, exchange_rate = convert_currency(
                amount=booking.total_price,
                source_currency=booking.currency or 'ETB',
                target_currency=payment_currency,
                return_rate=True
            )
            
            # Locked metadata for audit trail
            locked_metadata = {
                "original_amount": str(booking.total_price),
                "original_currency": booking.currency or 'ETB',
                "exchange_rate_locked": str(exchange_rate),
                "locked_at": timezone.now().isoformat(),
                "triangulation_reference": "USD"
            }

            fe_amount = serializer.validated_data.get('amount')
            if fe_amount and abs(float(fe_amount) - float(expected_amount)) > 0.01:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Price Mismatch in Payment Init for {model_name} {booking.id}. "
                    f"Client sent: {fe_amount}, Server calculated: {expected_amount}"
                )
        except Exception as e:
            return Response(
                {"error": f"Currency conversion failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if request.user.is_authenticated:
            payer_email = request.user.email
            payer_first_name = request.user.first_name
            payer_last_name = request.user.last_name
        else:
            payer_email = getattr(booking, 'guest_email', 'guest@michotmarefia.com')
            payer_first_name = getattr(booking, 'guest_first_name', 'Guest')
            payer_last_name = getattr(booking, 'guest_last_name', 'User')

        result = ChapaPaymentService.initialize_payment(
            booking=booking,
            booking_type=booking_type,
            amount=expected_amount,
            currency=payment_currency,
            email=payer_email,
            first_name=payer_first_name,
            last_name=payer_last_name,
            metadata=locked_metadata
        )
        
        if result["success"]:
            # Inject audit data into response for frontend disclosure
            result["calculated_amount"] = str(expected_amount)
            result["payment_currency"] = payment_currency
            result["exchange_rate"] = str(exchange_rate)
            result["original_amount"] = str(booking.total_price)
            result["original_currency"] = booking.currency or 'ETB'
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Payments"],
    summary="Chapa Payment Callback (Internal)",
    description="Handle GET callback from Chapa after user completes payment.",
    parameters=[
        OpenApiParameter("tx_ref", OpenApiTypes.STR, description="Transaction reference"),
        OpenApiParameter("status", OpenApiTypes.STR, description="Payment status")
    ],
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT}
)
@api_view(['GET'])
@csrf_exempt
def chapa_callback(request):
    """
    Handle Chapa callback - GET request as per Chapa documentation
    """
    try:
        callback_data = {
            "tx_ref": request.GET.get("tx_ref"),
            "trx_ref": request.GET.get("trx_ref"),
            "status": request.GET.get("status"),
            "id": request.GET.get("id"),
            "ref_id": request.GET.get("ref_id")
        }
        
        callback_data = {k: v for k, v in callback_data.items() if v is not None}
        
        if not callback_data.get("tx_ref") and not callback_data.get("trx_ref"):
            return JsonResponse({"error": "Missing transaction reference"}, status=400)
        
        result = ChapaPaymentService.handle_callback(callback_data)
        
        if result["success"]:
            return JsonResponse({"message": result["message"]}, status=200)
        else:
            return JsonResponse({"error": result["message"]}, status=400)
            
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@extend_schema(
    tags=["Payments"],
    summary="Chapa Payment Webhook (Internal)",
    description="Handle POST webhook from Chapa for async payment status updates.",
    request=ChapaWebhookSerializer,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT}
)
@api_view(['POST'])
@csrf_exempt
def chapa_webhook(request):
    result = ChapaPaymentService.handle_webhook(request)
    
    if result["success"]:
        return JsonResponse({"message": result["message"]}, status=200)
    else:
        return JsonResponse({"error": result["message"]}, status=400)

@extend_schema(
    tags=["Payments"],
    summary="Verify payment status",
    description="""
    Verify the status of a payment transaction using its reference.
    Returns transaction details and Chapa verification result if found, 
    otherwise returns only the Chapa verification result.
    """,
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT,
        403: OpenApiTypes.OBJECT
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_payment(request, tx_ref):
    """
    Verify payment for authenticated user.
    Users can only verify their own payments.
    Admin can verify any payment.
    """
    try:
        result = ChapaPaymentService.handle_callback({"tx_ref": tx_ref})

        try:
            payment_tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
            
            # Check permission
            user = request.user
            is_admin = user.is_superuser or (
                hasattr(user, 'role') and
                user.role and
                user.role.code == RoleCode.ADMIN.value
            )
            
            if not is_admin and payment_tx.booking.user != user:
                return Response(
                    {"error": "You can only verify your own payments."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = PaymentTransactionSerializer(payment_tx)
            response_data = serializer.data
            response_data["chapa_verification"] = result
        except PaymentTransaction.DoesNotExist:
            response_data = {"chapa_verification": result}

        return Response(response_data)

    except Exception as e:
        return Response({"error": f"Verification failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Payments"],
    summary="Publicly verify payment status",
    description="Verify the status of a payment transaction without authentication.",
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def verify_payment_public(request, tx_ref):
    try:
        result = ChapaPaymentService.handle_callback({"tx_ref": tx_ref})

        try:
            payment_tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
            serializer = PaymentTransactionSerializer(payment_tx)
            response_data = serializer.data
            response_data["chapa_verification"] = result
        except PaymentTransaction.DoesNotExist:
            response_data = {"chapa_verification": result}

        return Response(response_data)

    except Exception as e:
        return Response({"error": f"Verification failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    tags=["Payments"],
    summary="Cancel a pending payment",
    description="Cancel a payment transaction that is still in PENDING status.",
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def cancel_payment(request, tx_ref):
    """
    Cancel payment transaction.
    Users can only cancel their own payments.
    Admin can cancel any payment.
    """
    try:
        payment_tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
        
        # Check permission
        user = request.user
        is_admin = user.is_superuser or (
            hasattr(user, 'role') and
            user.role and
            user.role.code == RoleCode.ADMIN.value
        )
        
        if not is_admin and payment_tx.booking.user != user:
            return Response(
                {"error": "You can only cancel your own payments."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if payment_tx.status != PaymentTransaction.PaymentStatus.PENDING:
            return Response(
                {"error": "Only pending transactions can be cancelled"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = ChapaPaymentService.cancel_transaction(tx_ref)
        
        if result["success"]:
            payment_tx.status = PaymentTransaction.PaymentStatus.CANCELLED
            payment_tx.save()
            
            return Response({"message": result["message"]})
        else:
            return Response(
                {"error": result["error"]},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except PaymentTransaction.DoesNotExist:
        return Response(
            {"error": "Payment transaction not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )

@extend_schema(tags=["Debug & Utils"], summary="Test Chapa Key", description="Verify if the Chapa API key is valid by initiating a test transaction.")
@api_view(['GET'])
@permission_classes([AllowAny])
def test_chapa_key(request):
    import requests
    
    # Simple test payload
    payload = {
        "amount": "100",
        "currency": "ETB",
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "tx_ref": "test-key-validation",
        "callback_url": "https://webhook.site/test",
        "return_url": "https://example.com"
    }
    
    headers = {
        'Authorization': f'Bearer {settings.CHAPA_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(
            "https://api.chapa.co/v1/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        return Response({
            "status_code": response.status_code,
            "response": response.json(),
            "api_key_prefix": settings.CHAPA_SECRET_KEY[:20] + "..."  # Show first 20 chars
        })
        
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@extend_schema(tags=["Debug & Utils"], summary="Debug Config", description="Internal configuration check.")
@api_view(['GET'])
@permission_classes([AllowAny])
def debug_config(request):
    from django.conf import settings
    return Response({
        "chapa_callback_url": getattr(settings, 'CHAPA_CALLBACK_URL', 'NOT SET'),
        "frontend_url": getattr(settings, 'FRONTEND_URL', 'NOT SET'),
        "debug": settings.DEBUG,
        "ngrok_url": "https://4a74b1285b13.ngrok-free.app"
    })

@extend_schema(tags=["Debug & Utils"], summary="Direct Chapa Test")
@api_view(['POST'])
@permission_classes([AllowAny])
def test_chapa_direct(request):
    """Direct test for Chapa API"""
    import requests
    from django.conf import settings  # IMPORT SETTINS HERE
    
    # Use working email format based on our test results
    payload = {
        "amount": "100",
        "currency": "ETB",
        "email": "user@gmail.com",  # Use working email format
        "first_name": "Test",
        "last_name": "User",
        "tx_ref": f"direct-test-{uuid.uuid4().hex[:8]}",
        "callback_url": "https://webhook.site/test",
    }
    
    headers = {
        'Authorization': f'Bearer {settings.CHAPA_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(
            "https://api.chapa.co/v1/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        return Response({
            "request_sent": payload,
            "response_status": response.status_code,
            "response_body": response.json() if response.content else {"error": "No content"},
            "api_key_prefix": settings.CHAPA_SECRET_KEY[:25] + "..." if settings.CHAPA_SECRET_KEY else "NOT SET"
        })
        
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@extend_schema(tags=["Debug & Utils"], summary="Test Email Format Acceptance")
@api_view(['POST'])
@permission_classes([AllowAny])
def test_email_format(request):
    import requests
    from django.conf import settings
    
    test_emails = [
        "test@example.com",
        "user@gmail.com", 
        "test.user@domain.com",
        "test@sub.domain.com"
    ]
    
    results = []
    
    for email in test_emails:
        payload = {
            "amount": "100",
            "currency": "ETB",
            "email": email,
            "first_name": "Test",
            "last_name": "User",
            "tx_ref": f"email-test-{uuid.uuid4().hex[:8]}",
            "callback_url": "https://webhook.site/test",
        }
        
        headers = {
            'Authorization': f'Bearer {settings.CHAPA_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                "https://api.chapa.co/v1/transaction/initialize",
                json=payload,
                headers=headers,
                timeout=10
            )
            
            results.append({
                "email": email,
                "status_code": response.status_code,
                "response": response.json() if response.content else {"error": "No content"}
            })
            
        except Exception as e:
            results.append({
                "email": email,
                "error": str(e)
            })
    
    return Response({"email_tests": results})