from django.contrib import admin
from apps.payment.models import PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
	list_display = ("tx_ref", "booking", "amount", "currency", "status", "created_at")
	search_fields = ("tx_ref", "chapa_transaction_id")
	list_filter = ("status", "currency")
