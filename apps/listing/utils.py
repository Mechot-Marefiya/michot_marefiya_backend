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
    


def is_user_staff_of_listing(user, listing) -> bool:
    if not user or not user.is_authenticated:
        return False
        
    if user.is_superuser:
        return True
        
    pass

    core_object = None
    
    if hasattr(listing, 'hotel') and listing.hotel:
        core_object = listing.hotel
    elif hasattr(listing, 'guest_house') and listing.guest_house:
        core_object = listing.guest_house
    elif hasattr(listing, 'company') or hasattr(listing, 'individual_owner'):
        core_object = listing
        
    if not core_object:
        return False

    
    if hasattr(user, 'workspace') and user.workspace:
        if user.workspace == core_object:
            return True
            
    if hasattr(user, 'company') and user.company:
        if hasattr(core_object, 'company') and core_object.company == user.company:
            return True

    if hasattr(user, 'individual_owner') and user.individual_owner:
        if hasattr(core_object, 'individual_owner') and core_object.individual_owner == user.individual_owner:
            return True
            
    return False
