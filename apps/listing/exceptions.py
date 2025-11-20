from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.exceptions import APIException


class BookingConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Booking operation conflict."
    default_code = "booking_conflict"
class RatingException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "rating_error"