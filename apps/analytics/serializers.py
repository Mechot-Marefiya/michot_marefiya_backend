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

