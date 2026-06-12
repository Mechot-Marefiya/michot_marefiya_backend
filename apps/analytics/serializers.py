from rest_framework import serializers


class OverviewSerializer(serializers.Serializer):
    total_revenue = serializers.FloatField()
    total_bookings = serializers.IntegerField()
    confirmed_bookings = serializers.IntegerField()
    cancellations = serializers.IntegerField()
    avg_booking_value = serializers.FloatField()
    top_listings = serializers.ListField(child=serializers.DictField(), required=False)


class TimeseriesItemSerializer(serializers.Serializer):
    period = serializers.CharField()
    revenue = serializers.FloatField()


class FrontDeskStatsSerializer(serializers.Serializer):
    arrivals_today = serializers.IntegerField()
    departures_today = serializers.IntegerField()
    in_house_count = serializers.IntegerField()
    availability_percent = serializers.IntegerField()
    total_rooms = serializers.IntegerField()
    occupied_rooms = serializers.IntegerField()


class FrontDeskAvailabilityDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    available = serializers.IntegerField()
    status = serializers.CharField()
    booked = serializers.IntegerField()


class FrontDeskAvailabilityRowSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()
    room_name = serializers.CharField()
    total_units = serializers.IntegerField()
    availability = FrontDeskAvailabilityDaySerializer(many=True)


class DateRangeQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if date_from and date_to:
            if date_from > date_to:
                raise serializers.ValidationError(
                    {"date_from": "date_from must not be after date_to."}
                )
            if (date_to - date_from).days > 365:
                raise serializers.ValidationError(
                    {"date_to": "Date range must not exceed 365 days."}
                )

        return attrs


class ActiveListingMetricSerializer(serializers.Serializer):
    category = serializers.CharField()
    count = serializers.IntegerField()


class RevenuePeriodMetricSerializer(serializers.Serializer):
    date = serializers.CharField()
    amount = serializers.FloatField()


class RevenueCategoryMetricSerializer(serializers.Serializer):
    category = serializers.CharField()
    amount = serializers.FloatField()


class FailureReasonMetricSerializer(serializers.Serializer):
    reason = serializers.CharField()
    count = serializers.IntegerField()


class OverviewMetricsSerializer(serializers.Serializer):
    total_revenue = serializers.FloatField()
    total_transactions = serializers.IntegerField()
    pending_approvals = serializers.IntegerField()
    active_listings = ActiveListingMetricSerializer(many=True)
    total_users = serializers.IntegerField()
    new_users_in_range = serializers.IntegerField()


class RevenueMetricsSerializer(serializers.Serializer):
    revenue_by_period = RevenuePeriodMetricSerializer(many=True)
    revenue_by_category = RevenueCategoryMetricSerializer(many=True)
    average_transaction = serializers.FloatField()
    total_service_fees = serializers.FloatField()


class PayoutFailureMetricsSerializer(serializers.Serializer):
    total_failures = serializers.IntegerField()
    failure_rate = serializers.FloatField()
    failures_by_reason = FailureReasonMetricSerializer(many=True)
    total_failed_amount = serializers.FloatField()

