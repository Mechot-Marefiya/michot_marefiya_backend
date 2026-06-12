from django.contrib import admin
from apps.payment.models import PaymentTransaction
from apps.payment.services import open_dispute, resolve_dispute


@admin.action(description="Open dispute triage")
def open_dispute_triage(modeladmin, request, queryset):
    for transaction in queryset:
        if not transaction.dispute_status or transaction.dispute_status == PaymentTransaction.DisputeStatus.RESOLVED:
            open_dispute(transaction, request.user)


@admin.action(description="Resolve dispute triage")
def resolve_dispute_triage(modeladmin, request, queryset):
    for transaction in queryset.filter(dispute_status__isnull=False):
        resolve_dispute(transaction, request.user)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "tx_ref", 
        "amount", 
        "currency", 
        "status", 
        "payout_status",
        "dispute_status",
        "commission_amount",
        "vendor_payout_amount",
        "created_at"
    )
    list_filter = ("status", "payout_status", "dispute_status", "booking_type", "currency")
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
        "payout_status",
        "dispute_opened_at",
        "dispute_resolved_at",
        "dispute_handled_by",
    )
    actions = [open_dispute_triage, resolve_dispute_triage]
