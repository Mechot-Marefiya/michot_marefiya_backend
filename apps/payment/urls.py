from django.urls import path
from .views import (
    InitiatePaymentView, 
    chapa_callback, 
    chapa_webhook, 
    verify_payment, 
    verify_payment_public,
    cancel_payment,
    test_chapa_key,
    test_chapa_direct,
    debug_config,
    test_email_format
)

urlpatterns = [
    path('initiate/', InitiatePaymentView.as_view(), name='initiate-payment'),
    path('callback/chapa/', chapa_callback, name='chapa-callback'),
    path('webhook/chapa/', chapa_webhook, name='chapa-webhook'),
    path('verify/<str:tx_ref>/', verify_payment, name='verify-payment'),
    path('verify-public/<str:tx_ref>/', verify_payment_public, name='verify-payment-public'),
    path('cancel/<str:tx_ref>/', cancel_payment, name='cancel-payment'),
    path('test-key/', test_chapa_key, name='test-chapa-key'),
    path('test-direct/', test_chapa_direct, name='test-chapa-direct'),
    path('test-email/', test_email_format, name='test-email-format'),
    path('debug-config/', debug_config, name='debug-config'),
]