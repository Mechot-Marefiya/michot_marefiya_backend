from datetime import date
from decimal import Decimal
from typing import List, Dict, Tuple

from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

from apps.listing.models import (
    Booking, 
    BookingItem, 
    BookingItemPrice, 
    CarRental, 
    CarRentalItem,
    GuestHouseBooking,
    EventSpaceBooking,
    RoomListing,
    GuestHouseRoom,
)
from apps.analytics.models import CompanyDailyMetrics, ListingDailyMetrics


def _sum_decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(value)


def compute_company_overview(company_id, start_date: date, end_date: date) -> Dict:
    """
    Compute basic KPIs for a company between start_date and end_date (inclusive).
    This aggregates confirmed bookings across ALL property types:
    - Hotel Room Bookings
    - Guesthouse Bookings  
    - Event Space Bookings
    - Car Rentals
    """
    booking_qs = Booking.objects.filter(
        status=Booking.BookingStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        items__room__hotel__company__id=company_id,
    ).distinct()

    booking_agg = booking_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_bookings=Count("id"),
    )

    guesthouse_booking_qs = GuestHouseBooking.objects.filter(
        status=GuestHouseBooking.RentStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        items__room__guest_house__company__id=company_id,
    ).distinct()

    guesthouse_agg = guesthouse_booking_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_bookings=Count("id"),
    )

    eventspace_booking_qs = EventSpaceBooking.objects.filter(
        status=EventSpaceBooking.BookingStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        items__event_space__hotel__company__id=company_id,
    ).distinct()

    eventspace_agg = eventspace_booking_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_bookings=Count("id"),
    )

    # Car rentals revenue for company cars
    car_rental_qs = CarRental.objects.filter(
        status=CarRental.RentStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        rental_items__car_listing__company__id=company_id,
    ).distinct()

    car_agg = car_rental_qs.aggregate(total_revenue=Sum("total_price"), total_rentals=Count("id"))

    total_revenue = (
        _sum_decimal(booking_agg.get("total_revenue")) + 
        _sum_decimal(guesthouse_agg.get("total_revenue")) +
        _sum_decimal(eventspace_agg.get("total_revenue")) +
        _sum_decimal(car_agg.get("total_revenue"))
    )
    total_bookings = (
        (booking_agg.get("total_bookings") or 0) + 
        (guesthouse_agg.get("total_bookings") or 0) +
        (eventspace_agg.get("total_bookings") or 0) +
        (car_agg.get("total_rentals") or 0)
    )

    confirmed_count = (
        Booking.objects.filter(
            status=Booking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__hotel__company__id=company_id,
        ).distinct().count() +
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__company__id=company_id,
        ).distinct().count() +
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__hotel__company__id=company_id,
        ).distinct().count()
    )

    cancelled_count = (
        Booking.objects.filter(
            status=Booking.BookingStatus.CANCELLED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__hotel__company__id=company_id,
        ).distinct().count() +
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CANCELLED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__company__id=company_id,
        ).distinct().count() +
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CANCELLED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__hotel__company__id=company_id,
        ).distinct().count()
    )

    avg_booking_value = Decimal(0)
    if total_bookings:
        avg_booking_value = (total_revenue / Decimal(total_bookings)).quantize(Decimal('.01'))

    top_hotel_rooms = (
        BookingItem.objects.filter(
            booking__status=Booking.BookingStatus.CONFIRMED,
            booking__created_at__date__gte=start_date,
            booking__created_at__date__lte=end_date,
            room__hotel__company__id=company_id,
        )
        .values("room__id", "room__title")
        .annotate(revenue=Sum("price_per_unit"), bookings_count=Count("booking", distinct=True))
        .order_by("-revenue")
    )

    top_guesthouse_rooms = (
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__company__id=company_id,
        )
        .values("items__room__id", "items__room__title")
        .annotate(revenue=Sum("items__price_per_unit"), bookings_count=Count("id", distinct=True))
        .order_by("-revenue")
    )

    top_event_spaces = (
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__hotel__company__id=company_id,
        )
        .values("items__event_space__id", "items__event_space__title")
        .annotate(revenue=Sum("items__price_per_unit"), bookings_count=Count("id", distinct=True))
        .order_by("-revenue")
    )

    all_top_listings = []

    for r in top_hotel_rooms:
        all_top_listings.append({
            "listing_id": str(r["room__id"]), 
            "title": r["room__title"], 
            "revenue": float(r["revenue"] or 0), 
            "bookings_count": r["bookings_count"],
            "type": "hotel_room"
        })

    for r in top_guesthouse_rooms:
        all_top_listings.append({
            "listing_id": str(r["items__room__id"]), 
            "title": r["items__room__title"], 
            "revenue": float(r["revenue"] or 0), 
            "bookings_count": r["bookings_count"],
            "type": "guesthouse_room"
        })

    for r in top_event_spaces:
        all_top_listings.append({
            "listing_id": str(r["items__event_space__id"]), 
            "title": r["items__event_space__title"], 
            "revenue": float(r["revenue"] or 0), 
            "bookings_count": r["bookings_count"],
            "type": "event_space"
        })

    top_listings = sorted(all_top_listings, key=lambda x: x["revenue"], reverse=True)[:10]


    return {
        "total_revenue": float(total_revenue),
        "total_bookings": int(total_bookings),
        "confirmed_bookings": int(confirmed_count),
        "cancellations": int(cancelled_count),
        "avg_booking_value": float(avg_booking_value),
        "top_listings": top_listings,
    }


def compute_individual_owner_overview(owner_id, start_date: date, end_date: date) -> Dict:
    
    guesthouse_booking_qs = GuestHouseBooking.objects.filter(
        status=GuestHouseBooking.RentStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        items__room__guest_house__individual_owner__id=owner_id,
    ).distinct()

    guesthouse_agg = guesthouse_booking_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_bookings=Count("id"),
    )

    eventspace_booking_qs = EventSpaceBooking.objects.filter(
        status=EventSpaceBooking.BookingStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        items__event_space__individual_owner__id=owner_id,
    ).distinct()

    eventspace_agg = eventspace_booking_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_bookings=Count("id"),
    )

    total_revenue = (
        _sum_decimal(guesthouse_agg.get("total_revenue")) +
        _sum_decimal(eventspace_agg.get("total_revenue"))
    )
    total_bookings = (
        (guesthouse_agg.get("total_bookings") or 0) +
        (eventspace_agg.get("total_bookings") or 0)
    )

    confirmed_count = (
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__individual_owner__id=owner_id,
        ).distinct().count() +
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__individual_owner__id=owner_id,
        ).distinct().count()
    )

    cancelled_count = (
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CANCELLED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__individual_owner__id=owner_id,
        ).distinct().count() +
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CANCELLED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__individual_owner__id=owner_id,
        ).distinct().count()
    )

    avg_booking_value = Decimal(0)
    if total_bookings:
        avg_booking_value = (total_revenue / Decimal(total_bookings)).quantize(Decimal('.01'))

    top_guesthouse_rooms = (
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__individual_owner__id=owner_id,
        )
        .values("items__room__id", "items__room__title")
        .annotate(revenue=Sum("items__price_per_unit"), bookings_count=Count("id", distinct=True))
        .order_by("-revenue")
    )

    top_event_spaces = (
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__individual_owner__id=owner_id,
        )
        .values("items__event_space__id", "items__event_space__title")
        .annotate(revenue=Sum("items__price_per_unit"), bookings_count=Count("id", distinct=True))
        .order_by("-revenue")
    )

    all_top_listings = []

    for r in top_guesthouse_rooms:
        all_top_listings.append({
            "listing_id": str(r["items__room__id"]), 
            "title": r["items__room__title"], 
            "revenue": float(r["revenue"] or 0), 
            "bookings_count": r["bookings_count"],
            "type": "guesthouse_room"
        })

    for r in top_event_spaces:
        all_top_listings.append({
            "listing_id": str(r["items__event_space__id"]), 
            "title": r["items__event_space__title"], 
            "revenue": float(r["revenue"] or 0), 
            "bookings_count": r["bookings_count"],
            "type": "event_space"
        })

    top_listings = sorted(all_top_listings, key=lambda x: x["revenue"], reverse=True)[:10]

    return {
        "total_revenue": float(total_revenue),
        "total_bookings": int(total_bookings),
        "confirmed_bookings": int(confirmed_count),
        "cancellations": int(cancelled_count),
        "avg_booking_value": float(avg_booking_value),
        "top_listings": top_listings,
    }


def revenue_timeseries(company_id, start_date: date, end_date: date, granularity: str = "day") -> List[Dict]:
    """
    Return list of {period, revenue} between start_date and end_date with given granularity.
    Aggregates revenue from all booking types: Hotels, Guesthouses, Event Spaces, Cars.
    granularity: day | week | month
    """
    if granularity == "month":
        trunc = TruncMonth
    elif granularity == "week":
        trunc = TruncWeek
    else:
        trunc = TruncDate

    room_qs = (
        Booking.objects.filter(
            status=Booking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__hotel__company__id=company_id,
        )
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(revenue=Sum("total_price"))
        .order_by("period")
    )

    guesthouse_qs = (
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__company__id=company_id,
        )
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(revenue=Sum("total_price"))
        .order_by("period")
    )

    eventspace_qs = (
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__hotel__company__id=company_id,
        )
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(revenue=Sum("total_price"))
        .order_by("period")
    )

    # Car rentals
    car_qs = (
        CarRental.objects.filter(
            status=CarRental.RentStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            rental_items__car_listing__company__id=company_id,
        )
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(revenue=Sum("total_price"))
        .order_by("period")
    )

    data = {}
    for r in room_qs:
        key = r["period"].date() if hasattr(r["period"], "date") else r["period"]
        data[key] = data.get(key, 0) + float(r.get("revenue") or 0)

    for r in guesthouse_qs:
        key = r["period"].date() if hasattr(r["period"], "date") else r["period"]
        data[key] = data.get(key, 0) + float(r.get("revenue") or 0)

    for r in eventspace_qs:
        key = r["period"].date() if hasattr(r["period"], "date") else r["period"]
        data[key] = data.get(key, 0) + float(r.get("revenue") or 0)

    for r in car_qs:
        key = r["period"].date() if hasattr(r["period"], "date") else r["period"]
        data[key] = data.get(key, 0) + float(r.get("revenue") or 0)

    # produce sorted list
    items = []
    for k in sorted(data.keys()):
        items.append({"period": k.isoformat() if hasattr(k, "isoformat") else str(k), "revenue": data[k]})

    return items


def revenue_timeseries_individual(owner_id, start_date: date, end_date: date, granularity: str = "day") -> List[Dict]:

    if granularity == "month":
        trunc = TruncMonth
    elif granularity == "week":
        trunc = TruncWeek
    else:
        trunc = TruncDate

    guesthouse_qs = (
        GuestHouseBooking.objects.filter(
            status=GuestHouseBooking.RentStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__room__guest_house__individual_owner__id=owner_id,
        )
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(revenue=Sum("total_price"))
        .order_by("period")
    )

    eventspace_qs = (
        EventSpaceBooking.objects.filter(
            status=EventSpaceBooking.BookingStatus.CONFIRMED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            items__event_space__individual_owner__id=owner_id,
        )
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(revenue=Sum("total_price"))
        .order_by("period")
    )

    data = {}
    for r in guesthouse_qs:
        key = r["period"].date() if hasattr(r["period"], "date") else r["period"]
        data[key] = data.get(key, 0) + float(r.get("revenue") or 0)

    for r in eventspace_qs:
        key = r["period"].date() if hasattr(r["period"], "date") else r["period"]
        data[key] = data.get(key, 0) + float(r.get("revenue") or 0)

    items = []
    for k in sorted(data.keys()):
        items.append({"period": k.isoformat() if hasattr(k, "isoformat") else str(k), "revenue": data[k]})

    return items


def get_recent_activity(company_id: str, limit: int = 15) -> List[Dict]:
    """
    Fetches the most recent booking activities for a company.
    Orders by created_at descending.
    """
    activities = []

    # 1. Hotel Bookings
    hotel_qs = Booking.objects.filter(
        items__room__hotel__company__id=company_id
    ).select_related("user").distinct().order_by("-created_at")[:limit]

    for b in hotel_qs:
        user_name = f"{b.user.first_name} {b.user.last_name}" if b.user else (b.guest_email or "Guest")
        activities.append({
            "id": f"hotel-{b.id}",
            "type": "booking_created",
            "property_type": "hotel",
            "title": f"Booking #{b.booking_reference}",
            "amount": float(b.total_price or 0),
            "user_name": user_name,
            "timestamp": b.created_at,
            "status": b.status
        })

    # 2. Guesthouse Bookings
    guesthouse_qs = GuestHouseBooking.objects.filter(
        items__room__guest_house__company__id=company_id
    ).select_related("renter").distinct().order_by("-created_at")[:limit]

    for b in guesthouse_qs:
        user_name = f"{b.renter.first_name} {b.renter.last_name}" if b.renter else (b.guest_email or "Guest")
        activities.append({
            "id": f"guesthouse-{b.id}",
            "type": "booking_created",
            "property_type": "guesthouse",
            "title": f"Booking #{b.booking_reference}",
            "amount": float(b.total_price or 0),
            "user_name": user_name,
            "timestamp": b.created_at,
            "status": b.status
        })

    # 3. Event Space Bookings
    eventspace_qs = EventSpaceBooking.objects.filter(
        items__event_space__hotel__company__id=company_id
    ).select_related("user").distinct().order_by("-created_at")[:limit]

    for b in eventspace_qs:
        user_name = f"{b.user.first_name} {b.user.last_name}" if b.user else (b.guest_email or "Guest")
        activities.append({
            "id": f"eventspace-{b.id}",
            "type": "booking_created",
            "property_type": "eventspace",
            "title": f"Booking #{b.booking_reference}",
            "amount": float(b.total_price or 0),
            "user_name": user_name,
            "timestamp": b.created_at,
            "timestamp": b.created_at,
            "status": b.status
        })

    car_qs = CarRental.objects.filter(
        rental_items__car_listing__company__id=company_id
    ).select_related("user").distinct().order_by("-created_at")[:limit]

    for b in car_qs:
        user_name = f"{b.user.first_name} {b.user.last_name}" if b.user else (b.guest_email or "Guest")
        activities.append({
            "id": f"car-{b.id}",
            "type": "booking_created",
            "property_type": "car",
            "title": f"Rental #{b.booking_reference}",
            "amount": float(b.total_price or 0),
            "user_name": user_name,
            "timestamp": b.created_at,
            "status": b.status
        })

    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities[:limit]


def get_recent_activity_individual(owner_id: str, limit: int = 15) -> List[Dict]:
    
    activities = []
    guesthouse_qs = GuestHouseBooking.objects.filter(
        items__room__guest_house__individual_owner__id=owner_id
    ).select_related("renter").distinct().order_by("-created_at")[:limit]

    for b in guesthouse_qs:
        user_name = f"{b.renter.first_name} {b.renter.last_name}" if b.renter else (b.guest_email or "Guest")
        activities.append({
            "id": f"guesthouse-{b.id}",
            "type": "booking_created",
            "property_type": "guesthouse",
            "title": f"Booking #{b.booking_reference}",
            "amount": float(b.total_price or 0),
            "user_name": user_name,
            "timestamp": b.created_at,
            "status": b.status
        })

    eventspace_qs = EventSpaceBooking.objects.filter(
        items__event_space__individual_owner__id=owner_id
    ).select_related("user").distinct().order_by("-created_at")[:limit]

    for b in eventspace_qs:
        user_name = f"{b.user.first_name} {b.user.last_name}" if b.user else (b.guest_email or "Guest")
        activities.append({
            "id": f"eventspace-{b.id}",
            "type": "booking_created",
            "property_type": "eventspace",
            "title": f"Booking #{b.booking_reference}",
            "amount": float(b.total_price or 0),
            "user_name": user_name,
            "timestamp": b.created_at,
            "status": b.status
        })

    # Sort combined activities by timestamp desc and take top N
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities[:limit]


def compute_front_desk_stats(workspace_id: str, workspace_type: str) -> Dict:
    today = date.today()
    
    booking_filter = Q()
    total_units_filter = Q()
    
    is_hotel = False
    
    ws_type = str(workspace_type).lower()

    if ws_type == 'company':
        booking_filter = Q(items__room__hotel__company__id=workspace_id)
        total_units_filter = Q(hotel__company__id=workspace_id)
        is_hotel = True
        
    elif ws_type == 'hotel':
         booking_filter = Q(items__room__hotel__id=workspace_id)
         total_units_filter = Q(hotel__id=workspace_id)
         is_hotel = True

    elif ws_type == 'individual':
        booking_filter = Q(items__room__guest_house__individual_owner__id=workspace_id)
        total_units_filter = Q(guest_house__individual_owner__id=workspace_id)
        is_hotel = False
        
    elif ws_type == 'guesthouse':
        booking_filter = Q(items__room__guest_house__id=workspace_id)
        total_units_filter = Q(guest_house__id=workspace_id)
        is_hotel = False
        
    elif ws_type == 'front_desk': 
        pass

    if is_hotel:
        qs = Booking.objects.filter(booking_filter, status__in=[
            Booking.BookingStatus.CONFIRMED, 
            Booking.BookingStatus.WALK_IN
        ]).distinct()
        total_rooms = RoomListing.objects.filter(total_units_filter).aggregate(total=Sum('total_units'))['total'] or 0
    else:
        qs = GuestHouseBooking.objects.filter(booking_filter, status__in=[
            GuestHouseBooking.RentStatus.CONFIRMED,
            GuestHouseBooking.RentStatus.WALK_IN
        ]).distinct()
        total_rooms = GuestHouseRoom.objects.filter(total_units_filter).aggregate(total=Sum('total_units'))['total'] or 0
        
    if is_hotel:
        arrivals_today = qs.filter(check_in_date=today).count()
        departures_today = qs.filter(check_out_date=today).count()
        in_house_today = qs.filter(check_in_date__lte=today, check_out_date__gt=today).count()
    else:
        arrivals_today = qs.filter(start_date=today).count()
        departures_today = qs.filter(end_date=today).count()
        in_house_today = qs.filter(start_date__lte=today, end_date__gt=today).count()
        
    occupancy_rate = 0
    if total_rooms > 0:
        occupancy_rate = (in_house_today / total_rooms) * 100
        
    return {
        "arrivals_today": arrivals_today,
        "departures_today": departures_today,
        "in_house_today": in_house_today,
        "total_rooms": total_rooms,
        "occupancy_rate": round(occupancy_rate, 1),
        "available_units": max(0, total_rooms - in_house_today)
    }
