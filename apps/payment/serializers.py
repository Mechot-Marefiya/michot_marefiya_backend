from rest_framework import serializers
from apps.payment.models import PaymentTransaction


class PaymentInitializeSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(help_text="The unique identifier (UUID) of the booking to pay for.")
    booking_type = serializers.ChoiceField(
        choices=["booking", "guesthouse", "eventspace", "carrental"],
        default="booking",
        help_text="Type of booking: 'booking' (hotel room), 'guesthouse', 'eventspace', or 'carrental'"
    )
    email = serializers.EmailField(required=False, allow_blank=True, help_text="Email of the payer. If empty, uses the authenticated user's email.")
    first_name = serializers.CharField(required=False, allow_blank=True, help_text="First name of the payer.")
    last_name = serializers.CharField(required=False, allow_blank=True, help_text="Last name of the payer.")
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        required=False, 
        help_text="Optional: The amount you expect to pay. The server will verify this against its own calculation."
    )
    currency = serializers.CharField(
        default="ETB", 
        help_text="Payment currency (e.g., 'ETB', 'USD')."
    )


    def validate_currency(self, value):
        value = value.upper()
        supported_currencies = ["ETB", "USD"]
        if value not in supported_currencies:
            raise serializers.ValidationError(
                f"Currency '{value}' not supported. Allowed: {supported_currencies}"
            )
        return value


class PaymentInitializeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    checkout_url = serializers.URLField(required=False, allow_null=True)
    tx_ref = serializers.CharField(required=False)
    calculated_amount = serializers.CharField(required=False)
    payment_currency = serializers.CharField(required=False)
    exchange_rate = serializers.CharField(required=False)
    original_amount = serializers.CharField(required=False)
    original_currency = serializers.CharField(required=False)


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


class OwnerPaymentTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for the Owner Dashboard financial ledger.
    Flattens booking information for easier frontend consumption.
    """
    booking_reference = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    booking_dates = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "tx_ref",
            "amount",
            "currency",
            "status",
            "payment_method",
            "created_at",
            "booking_type",
            "booking_reference",
            "listing_title",
            "customer_name",
            "booking_dates",
        ]

    def get_booking_reference(self, obj):
        booking = obj.resolved_booking
        return getattr(booking, 'booking_reference', 'N/A')

    def get_listing_title(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return "N/A"
        
        # Stays
        if hasattr(booking, 'items') and booking.items.exists():
            item = booking.items.first()
            if hasattr(item, 'room') and item.room:
                return item.room.title
        
        # GuestHouseBooking
        if hasattr(booking, 'items') and obj.booking_type == 'guesthouse':
             item = booking.items.first()
             if hasattr(item, 'guest_house_room') and item.guest_house_room:
                 return item.guest_house_room.title

        # CarRental
        if hasattr(booking, 'rental_items') and booking.rental_items.exists():
            item = booking.rental_items.first()
            if hasattr(item, 'car_listing') and item.car_listing:
                return item.car_listing.title

        return "Listing"

    def get_customer_name(self, obj):
        booking = obj.resolved_booking
        if hasattr(booking, 'guest_full_name'):
            return booking.guest_full_name
        return "Customer"

    def get_booking_dates(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return None
        
        start = getattr(booking, 'check_in_date', getattr(booking, 'start_date', None))
        end = getattr(booking, 'check_out_date', getattr(booking, 'end_date', None))
        
        return {
            "start": start,
            "end": end
        }
