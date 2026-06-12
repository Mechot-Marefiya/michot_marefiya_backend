import json
import uuid
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.views import APIView
from django.conf import settings
from django.utils import timezone
from apps.listing.models import Booking
from apps.account.enums import RoleCode
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, OpenApiExample, inline_serializer
from rest_framework import viewsets, filters
from rest_framework.throttling import ScopedRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum
from apps.account.permissions import IsAdmin, IsCompanyOwner
from .serializers import (
    PaymentInitializeSerializer, 
    PaymentTransactionSerializer, 
    PaymentInitializeResponseSerializer,
    ChapaCallbackSerializer,
    ChapaWebhookSerializer,
    OwnerPaymentTransactionSerializer,
    TransactionMonitorListSerializer,
    TransactionMonitorDetailSerializer,
    DisputeActionSerializer,
    DisputeStatusSerializer,
)
from apps.core.utils import convert_currency
from .models import PaymentTransaction
from .services import (
    ChapaPaymentService,
    get_payment_tax_breakdown,
    get_transaction_monitor_list,
    open_dispute,
    update_dispute,
    resolve_dispute,
)


NO_REFUND_POLICY_CODE = "no_refunds"
NO_REFUND_POLICY_MESSAGE = "No refunds are available for any service payment on the platform."
PENDING_CANCEL_NOTE = "Cancelling a pending payment only stops that pending transaction. It does not create a refund."


def _is_payment_owner_or_admin(user, payment_tx):
    if user.is_superuser or (
        hasattr(user, 'role') and
        user.role and
        user.role.code == RoleCode.ADMIN.value
    ):
        return True

    booking = payment_tx.resolved_booking
    if not booking:
        return False

    return getattr(booking, 'user', None) == user or getattr(booking, 'renter', None) == user


def _with_no_refund_policy(payload, *, cancellation_effect):
    response = dict(payload)
    response.update(
        {
            "refund_supported": False,
            "refund_policy": NO_REFUND_POLICY_CODE,
            "refund_message": NO_REFUND_POLICY_MESSAGE,
            "cancellation_effect": cancellation_effect,
        }
    )
    return response


@extend_schema(tags=["Payments"])
class InitiatePaymentView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'payment_init'
    
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
        Supports multiple booking types: 'booking', 'guesthouse', 'eventspace', 'carrental', 'propertyrental'.
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
            'propertyrental': ('listing', 'PropertyRentalBooking', 'renter'),
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
            payable_statuses = {
                BookingClass.BookingStatus.PENDING,
                BookingClass.BookingStatus.WALK_IN,
            }
            if booking_status not in payable_statuses:
                return Response(
                    {"error": "Booking is already processed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif booking_type in ['guesthouse', 'eventspace']:
            if booking_status not in {'pending', 'walk_in'}:
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
        elif booking_type == 'propertyrental':
            if booking_status != 'pending':
                return Response(
                    {"error": "Booking is already processed"},
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
        elif hasattr(booking, 'property_listing') and booking.property_listing:
            content_object = booking.property_listing
        
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
        # Default to booking's currency logic (USD or ETB)
        payment_currency = serializer.validated_data.get('currency') or booking.currency or 'ETB'
        
        # PRICE GUARD & RATE LOCK: Calculate and lock the correct amount on the server
        try:
            # Only convert if the payment currency differs from booking currency
            source_amount = booking.total_price
            if booking_type == 'propertyrental':
                source_amount = get_payment_tax_breakdown(booking)["grand_total"]

            if booking.currency == payment_currency:
                expected_amount = source_amount
                exchange_rate = Decimal("1.0")
            else:
                expected_amount, exchange_rate = convert_currency(
                    amount=source_amount,
                    source_currency=booking.currency or 'ETB',
                    target_currency=payment_currency,
                    return_rate=True
                )
            
            # Locked metadata for audit trail
            locked_metadata = {
                "original_amount": str(source_amount),
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
            result["original_amount"] = str(source_amount)
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
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
@csrf_exempt
def chapa_callback(request):
    """Handle Chapa callback - GET request as per Chapa documentation"""
    chapa_callback.throttle_scope = 'payment_callback'
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
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
@csrf_exempt
def chapa_webhook(request):
    chapa_webhook.throttle_scope = 'payment_webhook'
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
        try:
            payment_tx = PaymentTransaction.objects.get(tx_ref=tx_ref)
            
            if not _is_payment_owner_or_admin(request.user, payment_tx):
                return Response(
                    {"error": "You can only verify your own payments."},
                    status=status.HTTP_403_FORBIDDEN
                )

            result = ChapaPaymentService.handle_callback({"tx_ref": tx_ref})
            serializer = PaymentTransactionSerializer(payment_tx)
            response_data = serializer.data
            response_data["chapa_verification"] = result
        except PaymentTransaction.DoesNotExist:
            result = ChapaPaymentService.handle_callback({"tx_ref": tx_ref})
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
@throttle_classes([ScopedRateThrottle])
def verify_payment_public(request, tx_ref):
    verify_payment_public.throttle_scope = 'payment_verify'
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
    description=(
        "Cancel a payment transaction that is still in PENDING status. "
        "This endpoint does not issue refunds because the platform does not support refunds."
    ),
    request=None,
    responses={
        200: inline_serializer(
            name="PaymentCancelSuccessResponse",
            fields={
                "message": serializers.CharField(),
                "pending_cancel_note": serializers.CharField(),
                "refund_supported": serializers.BooleanField(),
                "refund_policy": serializers.CharField(),
                "refund_message": serializers.CharField(),
                "cancellation_effect": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            name="PaymentCancelErrorResponse",
            fields={
                "error": serializers.CharField(),
                "pending_cancel_note": serializers.CharField(required=False),
                "refund_supported": serializers.BooleanField(),
                "refund_policy": serializers.CharField(),
                "refund_message": serializers.CharField(),
                "cancellation_effect": serializers.CharField(),
            },
        ),
        403: inline_serializer(
            name="PaymentCancelForbiddenResponse",
            fields={"error": serializers.CharField()},
        ),
        404: inline_serializer(
            name="PaymentCancelNotFoundResponse",
            fields={"error": serializers.CharField()},
        ),
    }
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
        
        if not _is_payment_owner_or_admin(request.user, payment_tx):
            return Response(
                {"error": "You can only cancel your own payments."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if payment_tx.status != PaymentTransaction.PaymentStatus.PENDING:
            return Response(
                _with_no_refund_policy(
                    {
                        "error": "Only pending transactions can be cancelled. Completed service payments are non-refundable.",
                        "pending_cancel_note": PENDING_CANCEL_NOTE,
                    },
                    cancellation_effect="refund_not_available",
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = ChapaPaymentService.cancel_transaction(tx_ref)
        
        if result["success"]:
            payment_tx.status = PaymentTransaction.PaymentStatus.CANCELLED
            payment_tx.save()
            
            return Response(
                _with_no_refund_policy(
                    {
                        "message": result["message"],
                        "pending_cancel_note": PENDING_CANCEL_NOTE,
                    },
                    cancellation_effect="pending_payment_cancelled_only",
                )
            )
        else:
            return Response(
                _with_no_refund_policy(
                    {
                        "error": result["error"],
                        "pending_cancel_note": PENDING_CANCEL_NOTE,
                    },
                    cancellation_effect="pending_payment_not_cancelled",
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except PaymentTransaction.DoesNotExist:
        return Response(
            {"error": "Payment transaction not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )


@extend_schema(tags=["Finance & Ledger"])
class OwnerPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for Owners to view their financial ledger.
    Supports search by tx_ref, booking_reference, customer_name.
    Supports filtering by status and payout_status.
    """
    serializer_class = OwnerPaymentTransactionSerializer
    permission_classes = [IsCompanyOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {
        'status': ['exact'],
        'payout_status': ['exact'],
    }
    search_fields = ['tx_ref', 'booking_reference', 'customer_name']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PaymentTransaction.objects.none()

        if hasattr(user, 'role') and user.role.code == RoleCode.ADMIN.value:
            return PaymentTransaction.objects.all()

        if hasattr(user, 'company') and user.company:
            return PaymentTransaction.objects.filter(vendor_company=user.company)
        
        elif hasattr(user, 'individual_owner') and user.individual_owner:
            return PaymentTransaction.objects.filter(vendor_individual=user.individual_owner)
        
        return PaymentTransaction.objects.none()


    @extend_schema(summary="Get financial summary (Total Revenue)")
    def list(self, request, *args, **kwargs):
        filtered_queryset = self.filter_queryset(self.get_queryset())
        
        success_qs = filtered_queryset.filter(status=PaymentTransaction.PaymentStatus.SUCCESS)
        pending_payout_qs = filtered_queryset.filter(payout_status=PaymentTransaction.PayoutStatus.PENDING)
        
        # Using aggregate for performance instead of python sum
        revenue_metrics = success_qs.aggregate(
            total_revenue=Sum('amount'),
            total_payout=Sum('vendor_payout_amount'),
            total_commission=Sum('commission_amount')
        )
        
        pending_metrics = pending_payout_qs.aggregate(
            total_pending=Sum('vendor_payout_amount')
        )

        # Default to 0 if None (no records)
        total_revenue = revenue_metrics['total_revenue'] or Decimal('0.00')
        total_payout = revenue_metrics['total_payout'] or Decimal('0.00')
        total_commission = revenue_metrics['total_commission'] or Decimal('0.00')
        total_pending = pending_metrics['total_pending'] or Decimal('0.00')
        
        count = success_qs.count()

        page = self.paginate_queryset(filtered_queryset)
        summary_data = {
            "total_successful_transactions": count,
            "total_revenue_etb": total_revenue,
            "total_payout_etb": total_payout,
            "total_commission_etb": total_commission,
            "pending_payout_etb": total_pending
        }

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['summary'] = summary_data
            return response

        serializer = self.get_serializer(filtered_queryset, many=True)
        return Response({
            "results": serializer.data,
            "summary": summary_data
        })


@extend_schema(tags=["Admin Payments"])
class AdminTransactionMonitorViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdmin]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TransactionMonitorDetailSerializer
        if self.action in {"open_dispute", "update_dispute", "resolve_dispute"}:
            return DisputeStatusSerializer
        return TransactionMonitorListSerializer

    def get_queryset(self):
        return get_transaction_monitor_list(self.request.query_params)

    def get_object(self):
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        summary="Open a payment transaction dispute",
        request=DisputeActionSerializer,
        responses={200: DisputeStatusSerializer, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="dispute/open")
    def open_dispute(self, request, pk=None):
        serializer = DisputeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = open_dispute(
            self.get_object(),
            request.user,
            note=serializer.validated_data.get("note"),
        )
        return Response(DisputeStatusSerializer(transaction).data)

    @extend_schema(
        summary="Update a payment transaction dispute",
        request=DisputeActionSerializer,
        responses={200: DisputeStatusSerializer, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["patch"], url_path="dispute")
    def update_dispute(self, request, pk=None):
        serializer = DisputeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispute_status = serializer.validated_data.get("status")
        if not dispute_status:
            return Response(
                {"status": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        transaction = update_dispute(
            self.get_object(),
            request.user,
            dispute_status,
            note=serializer.validated_data.get("note"),
        )
        return Response(DisputeStatusSerializer(transaction).data)

    @extend_schema(
        summary="Resolve a payment transaction dispute",
        request=DisputeActionSerializer,
        responses={200: DisputeStatusSerializer, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="dispute/resolve")
    def resolve_dispute(self, request, pk=None):
        serializer = DisputeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = resolve_dispute(
            self.get_object(),
            request.user,
            note=serializer.validated_data.get("note"),
        )
        return Response(DisputeStatusSerializer(transaction).data)
