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
from apps.listing.models import Booking
from .services import ChapaPaymentService
from .serializers import PaymentInitializeSerializer, PaymentTransactionSerializer
from .models import PaymentTransaction

class InitiatePaymentView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = PaymentInitializeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            booking = Booking.objects.get(
                id=serializer.validated_data['booking_id'],
                user=request.user
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if booking.status != Booking.BookingStatus.PENDING:
            return Response(
                {"error": "Booking is already processed"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = ChapaPaymentService.initialize_payment(
            booking=booking,
            amount=serializer.validated_data['amount'],
            currency=serializer.validated_data.get('currency', 'ETB'),
            email=request.user.email,
            first_name=request.user.first_name,
            last_name=request.user.last_name
        )
        
        if result["success"]:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

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

@api_view(['POST'])
@csrf_exempt
def chapa_webhook(request):
    result = ChapaPaymentService.handle_webhook(request)
    
    if result["success"]:
        return JsonResponse({"message": result["message"]}, status=200)
    else:
        return JsonResponse({"error": result["message"]}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_payment(request, tx_ref):
    try:
        result = ChapaPaymentService.handle_callback({"tx_ref": tx_ref})

        try:
            payment_tx = PaymentTransaction.objects.get(
                tx_ref=tx_ref,
                booking__user=request.user
            )
            serializer = PaymentTransactionSerializer(payment_tx)
            response_data = serializer.data
            response_data["chapa_verification"] = result
        except PaymentTransaction.DoesNotExist:
            response_data = {"chapa_verification": result}

        return Response(response_data)

    except Exception as e:
        return Response({"error": f"Verification failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


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

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def cancel_payment(request, tx_ref):
    try:
        payment_tx = PaymentTransaction.objects.get(
            tx_ref=tx_ref,
            booking__user=request.user
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