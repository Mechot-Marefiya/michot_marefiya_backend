from django.urls import path
from .views import (
    InitiatePaymentView, 
    chapa_callback, 
    chapa_webhook, 
    verify_payment, 
    verify_payment_public,
    cancel_payment,
    OwnerPaymentViewSet
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('ledger', OwnerPaymentViewSet, basename='owner-ledger')

urlpatterns = [
    path('initiate/', InitiatePaymentView.as_view(), name='initiate-payment'),
    path('callback/chapa/', chapa_callback, name='chapa-callback'),
    path('webhook/chapa/', chapa_webhook, name='chapa-webhook'),
    path('verify/<str:tx_ref>/', verify_payment, name='verify-payment'),
    path('verify-public/<str:tx_ref>/', verify_payment_public, name='verify-payment-public'),
    path('cancel/<str:tx_ref>/', cancel_payment, name='cancel-payment'),
]

urlpatterns += router.urls