from datetime import datetime
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework import filters, status

class ParseDatesAndQuantity:
    def parse_dates_and_quantity(request, require_car=False):
        car_listing_id = request.query_params.get("car_listing") if require_car else None
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        quantity = int(request.query_params.get("quantity", 1))
        
        if require_car and not car_listing_id:
            return None, None, None, Response(
                {"detail": "car_listing is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not start_date or not end_date:
            return None, None, None, Response(
                {"detail": "start_date and end_date are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        start_date_obj = parse_date(start_date)
        end_date_obj = parse_date(end_date)
        if not start_date_obj or not end_date_obj:
            return None, None, None, Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if end_date_obj <= start_date_obj:
            return None, None, None, Response(
                {"detail": "end_date must be after start_date."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return car_listing_id, start_date_obj, end_date_obj, quantity


import random
import string


def generate_booking_reference(prefix='H', model_class=None):

    if model_class is None:
        from apps.listing.models import Booking
        model_class = Booking
    
    max_attempts = 50
    
    for _ in range(max_attempts):
        code_part = ''.join(random.choices(
            string.ascii_uppercase + string.digits,
            k=6
        ))
        reference = f"{prefix}-{code_part}"
        
        if not model_class.objects.filter(booking_reference=reference).exists():
            return reference
    
    raise ValueError(
        f"Failed to generate unique booking reference after {max_attempts} attempts. "
        "This is extremely rare and may indicate a database issue."
    )
