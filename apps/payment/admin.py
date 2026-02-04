from django.contrib import admin
from apps.payment.models import PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "tx_ref", 
        "amount", 
        "currency", 
        "status", 
        "payout_status",
        "commission_amount",
        "vendor_payout_amount",
        "created_at"
    )
    list_filter = ("status", "payout_status", "booking_type", "currency")
    search_fields = (
        "tx_ref", 
        "chapa_transaction_id", 
        "booking__guest_email",
        "vendor_company__name",
        "vendor_individual__first_name"
    )
    readonly_fields = (
        "created_at", 
        "updated_at", 
        "metadata", 
        "commission_rate",
        "commission_amount",
        "vendor_payout_amount",
        "payout_status"
    )
