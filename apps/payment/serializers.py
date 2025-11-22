from rest_framework import serializers
from apps.payment.models import PaymentTransaction


class PaymentInitializeSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(default="ETB")

    def validate_currency(self, value):
        value = value.upper()
        supported_currencies = ["ETB", "USD"]
        if value not in supported_currencies:
            raise serializers.ValidationError(
                f"Currency '{value}' not supported. Allowed: {supported_currencies}"
            )
        return value


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "tx_ref",
            "booking",
            "amount",
            "currency",
            "status",
            "payment_method",
            "chapa_transaction_id",
            "metadata",
            "created_at",
            "updated_at",
        ]


class ChapaCallbackSerializer(serializers.Serializer):
    tx_ref = serializers.CharField(required=False)
    trx_ref = serializers.CharField(required=False)
    reference = serializers.CharField(required=False)
    ref_id = serializers.CharField(required=False)

    def get_tx_ref(self):
        return (
            self.validated_data.get("tx_ref")
            or self.validated_data.get("trx_ref")
            or self.validated_data.get("reference")
            or self.validated_data.get("ref_id")
        )

    def validate(self, data):
        tx = (
            data.get("tx_ref")
            or data.get("trx_ref")
            or data.get("reference")
            or data.get("ref_id")
        )
        if not tx:
            raise serializers.ValidationError("Transaction reference missing in callback.")
        return data


class ChapaWebhookSerializer(serializers.Serializer):
    tx_ref = serializers.CharField(required=False)
    trx_ref = serializers.CharField(required=False)
    reference = serializers.CharField(required=False)
    ref_id = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    signature = serializers.CharField(required=False)

    def get_tx_ref(self):
        return (
            self.validated_data.get("tx_ref")
            or self.validated_data.get("trx_ref")
            or self.validated_data.get("reference")
            or self.validated_data.get("ref_id")
        )

    def validate(self, data):
        tx = (
            data.get("tx_ref")
            or data.get("trx_ref")
            or data.get("reference")
            or data.get("ref_id")
        )
        if not tx:
            raise serializers.ValidationError("Transaction reference missing in webhook.")
        return data
