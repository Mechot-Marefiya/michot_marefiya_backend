from datetime import date, timedelta
from django.db.models import Count, Q, Sum
from django.utils import timezone
from apps.listing.models import (
    Booking,
    GuestHouseBooking,
    RoomListing,
    GuestHouseRoom,
    StayAvailability,
    BookingBase
)

def compute_front_desk_stats(workspace_id: str, workspace_type: str) -> dict:
    today = timezone.localtime().date()
    
    arrivals = 0
    departures = 0
    in_house = 0
    total_rooms = 0
    occupied_rooms = 0
    
    if workspace_type == "hotel":
        total_rooms = RoomListing.objects.filter(
            hotel_id=workspace_id
        ).aggregate(total=Sum('total_units'))['total'] or 0
        
        active_statuses = [
            Booking.BookingStatus.CONFIRMED,
            Booking.BookingStatus.WALK_IN
        ]
        
        bookings_qs = Booking.objects.filter(
            items__room__hotel_id=workspace_id,
            status__in=active_statuses
        ).distinct()
        
        arrivals = bookings_qs.filter(check_in_date=today).count()
        
        departures = bookings_qs.filter(check_out_date=today).count()
        
        in_house_qs = bookings_qs.filter(
            check_in_date__lte=today,
            check_out_date__gt=today
        )
        in_house = in_house_qs.count()
        
        occupied_rooms = in_house_qs.aggregate(
            total_units=Sum('items__units_booked')
        )['total_units'] or 0
            
    elif workspace_type == "guesthouse":
        total_rooms = GuestHouseRoom.objects.filter(
            guest_house_id=workspace_id
        ).aggregate(total=Sum('total_units'))['total'] or 0
        
        active_statuses = [
            GuestHouseBooking.RentStatus.CONFIRMED,
        ]
        
        bookings_qs = GuestHouseBooking.objects.filter(
            items__room__guest_house_id=workspace_id,
            status__in=active_statuses
        ).distinct()
        
        arrivals = bookings_qs.filter(start_date=today).count()
        departures = bookings_qs.filter(end_date=today).count()
        
        in_house_qs = bookings_qs.filter(
            start_date__lte=today,
            end_date__gt=today
        )
        in_house = in_house_qs.count()
        
        occupied_rooms = in_house_qs.aggregate(
            total_units=Sum('items__units_booked')
        )['total_units'] or 0
        
    availability_percent = 0
    if total_rooms > 0:
        available_rooms = max(0, total_rooms - occupied_rooms)
        display_percent = (available_rooms / total_rooms) * 100
        availability_percent = int(round(display_percent))
        
    return {
        "arrivals_today": arrivals,
        "departures_today": departures,
        "in_house_count": in_house,
        "availability_percent": availability_percent,
        "total_rooms": total_rooms,
        "occupied_rooms": occupied_rooms
    }


def get_availability_matrix(workspace_id: str, workspace_type: str, start_date: date, end_date: date) -> list:
    matrix = []
    
    delta = end_date - start_date
    date_list = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    
    if workspace_type == "hotel":
        rooms = RoomListing.objects.filter(hotel_id=workspace_id)
        
        for room in rooms:
            room_data = {
                "room_id": str(room.id),
                "room_name": room.title,
                "total_units": room.total_units,
                "availability": []
            }
            
            active_statuses = [
                Booking.BookingStatus.CONFIRMED,
                Booking.BookingStatus.WALK_IN
            ]
            
            room_bookings = Booking.objects.filter(
                items__room=room,
                status__in=active_statuses,
                check_in_date__lt=end_date + timedelta(days=1),
                check_out_date__gt=start_date
            ).values('check_in_date', 'check_out_date', 'items__units_booked')
            
            for d in date_list:
                booked_units = 0
                for b in room_bookings:
                    if b['check_in_date'] <= d < b['check_out_date']:
                        booked_units += b['items__units_booked']
                
                available = max(0, room.total_units - booked_units)
                status = "available"
                if available == 0:
                    status = "full"
                elif available < room.total_units:
                    status = "partial"
                    
                room_data["availability"].append({
                    "date": d.isoformat(),
                    "available": available,
                    "status": status,
                    "booked": booked_units
                })
            
            matrix.append(room_data)

    elif workspace_type == "guesthouse":
        rooms = GuestHouseRoom.objects.filter(guest_house_id=workspace_id)
        
        for room in rooms:
            room_data = {
                "room_id": str(room.id),
                "room_name": room.title,
                "total_units": room.total_units,
                "availability": []
            }
            
            active_statuses = [
                GuestHouseBooking.RentStatus.CONFIRMED,
            ]
            
            room_bookings = GuestHouseBooking.objects.filter(
                items__room=room,
                status__in=['confirmed', 'walk_in'],
                start_date__lte=end_date, 
                end_date__gte=start_date
            ).values('start_date', 'end_date', 'items__units_booked')
             
            for d in date_list:
                booked_units = 0
                for b in room_bookings:
                    if b['start_date'] <= d < b['end_date']:
                        booked_units += b['items__units_booked']
                                
                total = getattr(room, 'total_units', 1) 
                
                available = max(0, total - booked_units)
                status = "available"
                if available == 0:
                    status = "full"
                elif available < total:
                    status = "partial"
                    
                room_data["availability"].append({
                    "date": d.isoformat(),
                    "available": available,
                    "status": status,
                    "booked": booked_units
                })
            
            matrix.append(room_data)
            
    return matrix
