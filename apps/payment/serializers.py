from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from apps.payment.models import PaymentTransaction
from apps.payment.services import get_payment_tax_breakdown


class PaymentInitializeSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(help_text="The unique identifier (UUID) of the booking to pay for.")
    booking_type = serializers.ChoiceField(
        choices=["booking", "guesthouse", "eventspace", "carrental", "propertyrental"],
        default="booking",
        help_text="Type of booking: 'booking' (hotel room), 'guesthouse', 'eventspace', 'carrental', or 'propertyrental'"
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
        required=False,
        help_text="Payment currency (e.g., 'ETB', 'USD'). If not provided, defaults to booking currency."
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
    owner_price = serializers.CharField(required=False, allow_null=True)
    service_fee = serializers.CharField(required=False, allow_null=True)
    tax_amount = serializers.CharField(required=False, allow_null=True)
    tax_rate = serializers.CharField(required=False, allow_null=True)
    grand_total = serializers.CharField(required=False, allow_null=True)
    tax_liability_status = serializers.CharField(required=False, allow_null=True)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    owner_price = serializers.SerializerMethodField()
    service_fee = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()

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
            "owner_price",
            "service_fee",
            "tax_amount",
            "tax_rate",
            "grand_total",
            "tax_liability_status",
            "metadata",
            "created_at",
            "updated_at",
        ]

    def _breakdown(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return {
                "owner_price": None,
                "service_fee": None,
                "grand_total": obj.amount,
            }
        return get_payment_tax_breakdown(booking, amount=obj.amount)

    @extend_schema_field(OpenApiTypes.STR)
    def get_owner_price(self, obj):
        value = self._breakdown(obj)["owner_price"]
        return str(value) if value is not None else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_service_fee(self, obj):
        value = self._breakdown(obj)["service_fee"]
        return str(value) if value is not None else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_grand_total(self, obj):
        value = self._breakdown(obj)["grand_total"]
        return str(value) if value is not None else None


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
    owner_price = serializers.SerializerMethodField()
    service_fee = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()

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
            "owner_price",
            "service_fee",
            "tax_amount",
            "tax_rate",
            "grand_total",
            "tax_liability_status",
            "commission_rate",
            "commission_amount",
            "vendor_payout_amount",
            "payout_status",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_booking_reference(self, obj):
        booking = obj.resolved_booking
        return getattr(booking, 'booking_reference', 'N/A')

    def _breakdown(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return {
                "owner_price": None,
                "service_fee": None,
                "grand_total": obj.amount,
            }
        return get_payment_tax_breakdown(booking, amount=obj.amount)

    @extend_schema_field(OpenApiTypes.STR)
    def get_owner_price(self, obj):
        value = self._breakdown(obj)["owner_price"]
        return str(value) if value is not None else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_service_fee(self, obj):
        value = self._breakdown(obj)["service_fee"]
        return str(value) if value is not None else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_grand_total(self, obj):
        value = self._breakdown(obj)["grand_total"]
        return str(value) if value is not None else None

    @extend_schema_field(OpenApiTypes.STR)
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

    @extend_schema_field(OpenApiTypes.STR)
    def get_customer_name(self, obj):
        booking = obj.resolved_booking
        if hasattr(booking, 'guest_full_name'):
            return booking.guest_full_name
        return "Customer"

    @extend_schema_field(OpenApiTypes.OBJECT)
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


class TransactionMonitorListSerializer(serializers.ModelSerializer):
    listing_reference = serializers.SerializerMethodField()
    user_reference = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "tx_ref",
            "status",
            "amount",
            "currency",
            "booking_type",
            "listing_reference",
            "user_reference",
            "payout_status",
            "tax_amount",
            "grand_total",
            "dispute_status",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_listing_reference(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return None
        listing = getattr(booking, "property_listing", None)
        if not listing and hasattr(booking, "items") and booking.items.exists():
            item = booking.items.first()
            listing = (
                getattr(item, "room", None)
                or getattr(item, "guest_house_room", None)
                or getattr(item, "event_space", None)
            )
        if not listing and hasattr(booking, "rental_items") and booking.rental_items.exists():
            listing = getattr(booking.rental_items.first(), "car_listing", None)
        return {
            "id": str(getattr(listing, "id", "")) if listing else None,
            "title": getattr(listing, "title", None) or getattr(listing, "name", None),
            "type": obj.booking_type,
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_user_reference(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return None
        user = getattr(booking, "user", None) or getattr(booking, "renter", None)
        if user:
            return {
                "id": str(user.id),
                "email": user.email,
                "phone": user.phone,
                "name": user.get_full_name(),
            }
        return {
            "id": None,
            "email": getattr(booking, "guest_email", None),
            "phone": getattr(booking, "guest_phone", None),
            "name": getattr(booking, "guest_full_name", None),
        }

    @extend_schema_field(OpenApiTypes.STR)
    def get_grand_total(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return str(obj.amount)
        value = get_payment_tax_breakdown(booking, amount=obj.amount)["grand_total"]
        return str(value) if value is not None else None


class TransactionMonitorDetailSerializer(TransactionMonitorListSerializer):
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=4, read_only=True)
    tax_liability_status = serializers.CharField(read_only=True)
    service_fee = serializers.SerializerMethodField()
    owner_price = serializers.SerializerMethodField()
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=4, read_only=True)
    commission_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    vendor_payout_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    metadata = serializers.JSONField(read_only=True)
    dispute_note = serializers.CharField(read_only=True)
    dispute_opened_at = serializers.DateTimeField(read_only=True)
    dispute_resolved_at = serializers.DateTimeField(read_only=True)
    dispute_handled_by = serializers.SerializerMethodField()

    class Meta(TransactionMonitorListSerializer.Meta):
        fields = TransactionMonitorListSerializer.Meta.fields + [
            "payment_method",
            "chapa_transaction_id",
            "owner_price",
            "service_fee",
            "tax_rate",
            "tax_liability_status",
            "commission_rate",
            "commission_amount",
            "vendor_payout_amount",
            "metadata",
            "dispute_note",
            "dispute_opened_at",
            "dispute_resolved_at",
            "dispute_handled_by",
            "updated_at",
        ]
        read_only_fields = fields

    def _breakdown(self, obj):
        booking = obj.resolved_booking
        if not booking:
            return {
                "owner_price": None,
                "service_fee": None,
            }
        return get_payment_tax_breakdown(booking, amount=obj.amount)

    @extend_schema_field(OpenApiTypes.STR)
    def get_owner_price(self, obj):
        value = self._breakdown(obj)["owner_price"]
        return str(value) if value is not None else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_service_fee(self, obj):
        value = self._breakdown(obj)["service_fee"]
        return str(value) if value is not None else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_dispute_handled_by(self, obj):
        admin = obj.dispute_handled_by
        if not admin:
            return None
        return {
            "id": str(admin.id),
            "email": admin.email,
            "name": admin.get_full_name(),
        }


class DisputeActionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=PaymentTransaction.DisputeStatus.choices,
        required=False,
    )
    note = serializers.CharField(required=False, allow_blank=True)


class DisputeStatusSerializer(serializers.ModelSerializer):
    handled_by = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        fields = [
            "dispute_status",
            "dispute_note",
            "dispute_opened_at",
            "dispute_resolved_at",
            "handled_by",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_handled_by(self, obj):
        admin = obj.dispute_handled_by
        if not admin:
            return None
        return {
            "id": str(admin.id),
            "email": admin.email,
            "name": admin.get_full_name(),
        }
