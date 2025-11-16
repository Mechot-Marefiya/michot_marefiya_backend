from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.exceptions import APIException


class BookingConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Booking operation conflict."
    default_code = "booking_conflict"
