from datetime import date
from decimal import Decimal
from typing import List, Dict, Tuple

from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

from apps.listing.models import Booking, BookingItem, BookingItemPrice, CarRental, CarRentalItem
from apps.analytics.models import CompanyDailyMetrics, ListingDailyMetrics


def _sum_decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(value)


def compute_company_overview(company_id, start_date: date, end_date: date) -> Dict:
    """
    Compute basic KPIs for a company between start_date and end_date (inclusive).
    This aggregates confirmed bookings and car rentals that belong to the company.
    """
    # Bookings revenue and counts
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

    # Car rentals revenue for company cars
    car_rental_qs = CarRental.objects.filter(
        status=CarRental.RentStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        rental_items__car_listing__company__id=company_id,
    ).distinct()

    car_agg = car_rental_qs.aggregate(total_revenue=Sum("total_price"), total_rentals=Count("id"))

    total_revenue = _sum_decimal(booking_agg.get("total_revenue")) + _sum_decimal(car_agg.get("total_revenue"))
    total_bookings = (booking_agg.get("total_bookings") or 0) + (car_agg.get("total_rentals") or 0)

    # counts by status across bookings belonging to company
    confirmed_count = Booking.objects.filter(
        status=Booking.BookingStatus.CONFIRMED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        items__room__hotel__company__id=company_id,
    ).distinct().count()

    cancelled_count = Booking.objects.filter(
        status=Booking.BookingStatus.CANCELLED,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        items__room__hotel__company__id=company_id,
    ).distinct().count()

    avg_booking_value = Decimal(0)
    if total_bookings:
        avg_booking_value = (total_revenue / Decimal(total_bookings)).quantize(Decimal('.01'))

    # Top listings by revenue (rooms)
    top_listing_qs = (
        BookingItem.objects.filter(
            booking__status=Booking.BookingStatus.CONFIRMED,
            booking__created_at__date__gte=start_date,
            booking__created_at__date__lte=end_date,
            room__hotel__company__id=company_id,
        )
        .values("room__id", "room__title")
        .annotate(revenue=Sum("price_per_unit"), bookings_count=Count("booking"))
        .order_by("-revenue")[:10]
    )

    top_listings = [
        {"listing_id": str(r["room__id"]), "title": r["room__title"], "revenue": float(r["revenue"] or 0), "bookings_count": r["bookings_count"]}
        for r in top_listing_qs
    ]

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
    granularity: day | week | month
    """
    if granularity == "month":
        trunc = TruncMonth
    elif granularity == "week":
        trunc = TruncWeek
    else:
        trunc = TruncDate

    # Room bookings
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

    for r in car_qs:
        key = r["period"].date() if hasattr(r["period"], "date") else r["period"]
        data[key] = data.get(key, 0) + float(r.get("revenue") or 0)

    # produce sorted list
    items = []
    for k in sorted(data.keys()):
        items.append({"period": k.isoformat() if hasattr(k, "isoformat") else str(k), "revenue": data[k]})

    return items
