from datetime import date, timedelta, datetime
from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Min,Q
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple,Any,List
from rest_framework.exceptions import ValidationError
from decimal import Decimal
from apps.account.models import CompanyProfile, HotelProfile
from apps.account.services import ImageCreationService
from apps.core.models import Address,Facility
from apps.listing.exceptions import BookingConflict
from apps.listing.models import (
    Amenity,
    Booking,
    BookingItem,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
    StayAvailability,EventSpaceListing,
    Transaction,CarAvailability,EventSpaceAvailability,
    Season, SeasonalRate, BookingItemPrice, RoomInventory,
    CarListing,
    EventSpaceBooking,
    EventSpaceBookingItem,
    CarRental,
    GuestHouseAvailability,
    CarRentalItem,
    Season,
    BookingItemPrice,
    SeasonalRate,
    RoomInventory
)


class ListingService:
    @staticmethod
    @transaction.atomic()
    def create_room_listing(validated_data: dict):
        company_id = validated_data.pop("company_id")
        images = validated_data.pop("images")
        # TODO: Do some way of handling the duplicate address creation
        # TODO: by maybe asking hotels to fill how many branches they have on
        # TODO: registration then avoid listing address fill form the UI and
        # TODO:  also make it optional here as well so that we can reuse the HQ address.
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities")

        if company_id:
            company = get_object_or_404(CompanyProfile, id=company_id)
            if company.status != CompanyProfile.StatusChoice.APPROVED:
                raise ValidationError("Company profile is not approved.")

        print("------->", company)
        # else:
        #     company = get_object_or_404(
        #         CompanyProfile, user=validated_data.pop('user'))

        hotel_profile = get_object_or_404(HotelProfile, company=company_id)

        address_instance = None

        if address_data:
            address_instance = ListingService.create_address(address_data)
        else:
            address_instance = company.address

        room_listing_instance = RoomListing.objects.create(
            hotel=hotel_profile, address=address_instance, **validated_data
        )

        amenities = []
        for id in amenity_ids:
            instance = get_object_or_404(Amenity, id=id)
            amenities.append(instance)

        # M2M to amenities
        room_listing_instance.amenities.set(amenities)

        ImageCreationService.create_images(room_listing_instance, images)

        # creating availability for the room created
        StayAvailabilityService.create_availability(
            hotel_profile,
            room_listing_instance,
            room_listing_instance.total_units
        )

        return room_listing_instance

    @staticmethod
    @transaction.atomic()
    def create_guest_house_listing(validated_data: dict):
        images = validated_data.pop("images")
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities")
        facility_ids=validated_data.pop("facilities")
        # individual_owner_id = validated_data.pop('individual_owner')
        address_instance = ListingService.create_address(address_data)

        # individual_owner = get_object_or_404(
        #     IndividualOwnerProfile, id=individual_owner_id)

        guest_house_listing_instance = GuestHouseListing.objects.create(
            address=address_instance,
            # individual_owner=individual_owner,
            **validated_data,
        )
        amenities = []
        for id in amenity_ids:
            instance = get_object_or_404(Amenity, id=id)
            amenities.append(instance)
                # M2M to amenities
        guest_house_listing_instance.amenities.set(amenities)
        facilities = []
        for id in facility_ids:
            instance = get_object_or_404(Facility, id=id)
            facilities.append(instance)
        # M2M to facilities
        guest_house_listing_instance.facilities.set(facilities)
        ImageCreationService.create_images(
            guest_house_listing_instance, images)

        return guest_house_listing_instance

    @staticmethod
    @transaction.atomic()
    def create_property_listing(validated_data: dict):
        images = validated_data.pop("images")
        address_data = validated_data.pop("address", None)

        address_instance = ListingService.create_address(address_data)
        # individual_owner_id = validated_data.pop('individual_owner')

        # individual_owner = get_object_or_404(
        #     IndividualOwnerProfile,
        #     id=individual_owner_id
        # )

        property_listing_instance = PropertyListing.objects.create(
            address=address_instance,
            # individual_owner=individual_owner,
            **validated_data,
        )

        ImageCreationService.create_images(property_listing_instance, images)

        return property_listing_instance

    @staticmethod
    def create_address(address_data) -> Address:
        return Address.objects.create(**address_data)


class StayAvailabilityService:
    @staticmethod
    def create_availability(hotel, room, room_quantity, days=90):
        today = date.today()
        # rooms = RoomListing.objects.filter(hotel=hotel)

        objs = []
        for i in range(days):
            objs.append(
                StayAvailability(
                    hotel=hotel,
                    room=room,
                    available_rooms=room_quantity,
                    date=today + timedelta(days=i),
                    # is_available=True,
                )
            )

        StayAvailability.objects.bulk_create(objs, batch_size=1000,ignore_conflicts=True)

    # * This get_available_rooms method will be used to render our room list table.
    @staticmethod
    def get_available_rooms(hotel, check_in_date, check_out_date):
        required_days = (check_out_date - check_in_date).days

        qs = (
            StayAvailability.objects
            .filter(
                hotel=hotel,
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_rooms__gt=0
            )
            .values("room")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_rooms")
            )
            .filter(total_days=required_days)  # available every day
        )

        # extract room IDs
        room_ids = [row["room"] for row in qs]

        rooms = RoomListing.objects.filter(id__in=room_ids)

        # TODO: attach min_available to room instance to return to frontend

        return rooms, qs

    @staticmethod
    def validate_availability(hotel, rooms_info, check_in_date, check_out_date):
        date_cursor = check_in_date
        room_ids = [room_info["room"].id for room_info in rooms_info]
        dates = []
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)
        
        availabilities = StayAvailability.objects.select_for_update().filter(
            hotel=hotel,
            room_id__in=room_ids,
            date__in=dates
        )
        
        availability_map = {}
        for av in availabilities:
            key = (av.room_id, av.date)
            availability_map[key] = av
        
        for date_cursor in dates:
            for room_info in rooms_info:
                room = room_info["room"]
                quantity = room_info["quantity"]
                key = (room.id, date_cursor)
                availability = availability_map.get(key)
                
                if not availability:
                    raise BookingConflict(
                        f"No availability data for room {room.title} on {date_cursor}"
                    )
                
                if availability.available_rooms < quantity:
                    raise BookingConflict(
                        f"Not enough rooms available for {room.title} on {date_cursor}. "
                        f"Available: {availability.available_rooms}, Requested: {quantity}"
                    )

    @staticmethod
    def update_availability(
        hotel,
        rooms_info,
        check_in_date,
        check_out_date,
        increment: bool = False,
    ):
        date_cursor = check_in_date
        room_ids = [room_info["room"].id for room_info in rooms_info]
        dates = []
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)
        
        for date_cursor in dates:
            for room_info in rooms_info:
                room_id = room_info["room"].id
                quantity = room_info["quantity"]
                obj = StayAvailability.objects.select_for_update().filter(
                    hotel=hotel, room_id=room_id, date=date_cursor
                )
                if increment:
                    obj.update(available_rooms=F(
                        "available_rooms") + quantity)
                else:
                    obj.update(available_rooms=F(
                        "available_rooms") - quantity)

    @staticmethod
    def search_stays(city, check_in_date, check_out_date, number_of_guests):
        required_days = (check_out_date - check_in_date).days

        qs = (
            StayAvailability.objects
            .filter(
                hotel__company__address__city=city,
                room__number_of_guests__gte=number_of_guests,
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_rooms__gt=0
            )
            .values("hotel", "room")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_rooms")
            )
            .filter(total_days=required_days)
        )

        hotel_ids = list(set([row["hotel"] for row in qs]))
        hotels = HotelProfile.objects.filter(id__in=hotel_ids).select_related(
            "company", "company__address"
        ).prefetch_related("room_listings")

        availability_data = list(qs)
        
        results = []
        for hotel in hotels:
            hotel_rooms_data = [row for row in availability_data if row["hotel"] == hotel.id]
            room_ids = [row["room"] for row in hotel_rooms_data]
            rooms = RoomListing.objects.filter(id__in=room_ids).select_related("hotel", "address")
            
            room_availability_map = {
                row["room"]: {
                    "min_available": row["min_available"],
                    "total_days": row["total_days"]
                }
                for row in hotel_rooms_data
            }
            
            hotel_data = {
                "hotel": hotel,
                "rooms": []
            }
            
            for room in rooms:
                availability_info = room_availability_map.get(room.id, {})
                hotel_data["rooms"].append({
                    "room": room,
                    "available_units": availability_info.get("min_available", 0)
                })
            
            if hotel_data["rooms"]:
                results.append(hotel_data)
        
        return results

    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        start = start_date or date.today()
        end = start + timedelta(days=days_ahead)
        rooms = RoomListing.objects.select_related("hotel")
        created = 0
        batch = []
        for room in rooms:
            if not room.hotel:
                continue
            existing_dates = set(
                StayAvailability.objects.filter(
                    room=room,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )
            cursor = start
            while cursor < end:
                if cursor not in existing_dates:
                    batch.append(
                        StayAvailability(
                            hotel=room.hotel,
                            room=room,
                            date=cursor,
                            available_rooms=room.total_units
                        )
                    )
                    if len(batch) >= 1000:
                        StayAvailability.objects.bulk_create(batch, batch_size=1000,ignore_conflicts=True)
                        created += len(batch)
                        batch = []
                cursor += timedelta(days=1)
        if batch:
            StayAvailability.objects.bulk_create(batch, batch_size=1000,ignore_conflicts=True)
            created += len(batch)
        return created


class PriceService:
    @staticmethod
    def _season_matches(season: Season, when: date) -> bool:
        if not season.active:
            return False
        if season.recurring:
            start_md = (season.start_date.month, season.start_date.day)
            end_md = (season.end_date.month, season.end_date.day)
            md = (when.month, when.day)
            if start_md <= end_md:
                return start_md <= md <= end_md
            return md >= start_md or md <= end_md
        return season.start_date <= when <= season.end_date

    @staticmethod
    def resolve_price(room: RoomListing, when: date) -> Decimal:
        # 1) RoomInventory override
        inv = RoomInventory.objects.filter(room_listing=room, date=when).first()
        if inv and inv.price is not None:
            return Decimal(inv.price)

        # 2) SeasonalRate candidates
        hotel = room.hotel
        company = getattr(hotel, 'company', None) if hotel else None

        candidates = SeasonalRate.objects.filter(active=True).select_related('season')
        # narrow to possible scopes to reduce in-memory checks
        scope_q = Q(room=room) | Q(hotel=hotel)
        if company:
            scope_q |= Q(company=company)
        scope_q |= Q(room__isnull=True, hotel__isnull=True, company__isnull=True)
        candidates = candidates.filter(scope_q)

        matched = []
        for rate in candidates:
            if not PriceService._season_matches(rate.season, when):
                continue
            # days_of_week optional filter
            if rate.days_of_week:
                try:
                    if when.weekday() not in rate.days_of_week:
                        continue
                except Exception:
                    pass
            matched.append(rate)

        if matched:
            # sort by priority desc then specificity (room>hotel>company>global)
            def score(r):
                # specificity: room > hotel > company > global
                spec = 0
                if r.room:
                    spec = 3
                elif r.hotel:
                    spec = 2
                elif r.company:
                    spec = 1
                # use created_at as deterministic tie-breaker; later entries win
                return (r.priority, spec, getattr(r, 'created_at', None))

            # sort by priority desc, then specificity desc, then created_at desc
            matched.sort(key=score, reverse=True)
            chosen = matched[0]
            if chosen.price_override is not None:
                return Decimal(chosen.price_override)
            if chosen.multiplier is not None:
                base = Decimal(room.base_price)
                return (base * Decimal(chosen.multiplier)).quantize(Decimal('0.01'))

        # 3) fallback to base price
        return Decimal(room.base_price)

    @staticmethod
    def resolve_price_detail(room: RoomListing, when: date) -> dict:
        # Returns detailed info for a single date: final price and source info
        inv = RoomInventory.objects.filter(room_listing=room, date=when).first()
        if inv and inv.price is not None:
            p = Decimal(inv.price).quantize(Decimal('0.01'))
            base = Decimal(room.base_price)
            return {
                "price": p,
                "source": "inventory",
                "rate_id": None,
                "note": None,
                "is_discounted": p < base,
            }

        hotel = room.hotel
        company = getattr(hotel, 'company', None) if hotel else None

        candidates = SeasonalRate.objects.filter(active=True).select_related('season')
        scope_q = Q(room=room) | Q(hotel=hotel)
        if company:
            scope_q |= Q(company=company)
        scope_q |= Q(room__isnull=True, hotel__isnull=True, company__isnull=True)
        candidates = candidates.filter(scope_q)

        matched = []
        for rate in candidates:
            if not PriceService._season_matches(rate.season, when):
                continue
            if rate.days_of_week:
                try:
                    if when.weekday() not in rate.days_of_week:
                        continue
                except Exception:
                    pass
            matched.append(rate)

        if matched:
            def score(r):
                spec = 0
                if r.room:
                    spec = 3
                elif r.hotel:
                    spec = 2
                elif r.company:
                    spec = 1
                return (r.priority, spec, getattr(r, 'created_at', None))

            matched.sort(key=score, reverse=True)
            chosen = matched[0]
            if chosen.price_override is not None:
                p = Decimal(chosen.price_override).quantize(Decimal('0.01'))
                base = Decimal(room.base_price)
                return {
                    "price": p,
                    "source": "seasonal",
                    "rate_id": str(chosen.id),
                    "note": None,
                    "is_discounted": p < base,
                }
            if chosen.multiplier is not None:
                base = Decimal(room.base_price)
                p = (base * Decimal(chosen.multiplier)).quantize(Decimal('0.01'))
                return {
                    "price": p,
                    "source": "seasonal",
                    "rate_id": str(chosen.id),
                    "note": f"multiplier {chosen.multiplier}",
                    "is_discounted": p < base,
                }

        base = Decimal(room.base_price).quantize(Decimal('0.01'))
        return {
            "price": base,
            "source": "base",
            "rate_id": None,
            "note": None,
            "is_discounted": False,
        }


class BookingService:
    @transaction.atomic()
    @staticmethod
    def create_booking(validated_data, user=None):
        items_data = validated_data.pop("items")
        if user:
            validated_data["user"] = user
        
        check_in_date = validated_data.get("check_in_date")
        check_out_date = validated_data.get("check_out_date")
        
        rooms_info = []
        for item in items_data:
            room = item["room"]
            units = item["units_booked"]
            rooms_info.append({"room": room, "quantity": units})
        
        if rooms_info:
            hotel = rooms_info[0]["room"].hotel
            StayAvailabilityService.validate_availability(
                hotel, rooms_info, check_in_date, check_out_date
            )
        
        booking = Booking.objects.create(**validated_data)

        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)

        for item in items_data:
            room = item["room"]
            units = item["units_booked"]

            booking_item = BookingItem.objects.create(
                booking=booking,
                room=room,
                units_booked=units,
                price_per_unit=room.base_price,
            )

            # create per-night price lines if feature enabled
            if use_seasonal:
                date_cursor = booking.check_in_date
                while date_cursor < booking.check_out_date:
                    price = PriceService.resolve_price(room, date_cursor)
                    BookingItemPrice.objects.create(
                        booking_item=booking_item,
                        date=date_cursor,
                        price_per_unit=price,
                        units=units,
                    )
                    date_cursor += timedelta(days=1)

            StayAvailabilityService.update_availability(
                hotel=room.hotel,
                rooms_info=[{"room": room, "quantity": units}],
                check_in_date=booking.check_in_date,
                check_out_date=booking.check_out_date,
                increment=False,
            )

        if use_seasonal:
            # compute total from BookingItemPrice rows (per-night prices already stored)
            total_price = Decimal('0.00')
            for pip in BookingItemPrice.objects.filter(booking_item__booking=booking):
                total_price += (Decimal(pip.price_per_unit) * Decimal(pip.units))
            booking.total_price = total_price
        else:
            # Non-seasonal: price_per_unit on BookingItem is stored as per-night base price.
            # Multiply by number of nights and units booked to get the total.
            nights = (booking.check_out_date - booking.check_in_date).days
            total_price = Decimal('0.00')
            for item in booking.items.all():
                total_price += (Decimal(item.price_per_unit) * Decimal(item.units_booked) * Decimal(nights))
            booking.total_price = total_price

        booking.save()
        return booking

    @staticmethod
    def cancel_booking(booking: Booking):
        """Called when the user cancel their booking.

        Args:
            booking (Booking): Booking instance.

        Returns:
            Booking: Cancelled Booking instance.
        """
        if booking.status in [
            Booking.BookingStatus.CANCELLED,
            Booking.BookingStatus.CONFIRMED
        ]:
            raise BookingConflict(
                "Booking is already finalized and cannot be changed."
            )
        for item in booking.items.all():
            StayAvailabilityService.update_availability(
                hotel=item.room.hotel,
                rooms_info=[
                    {"room": item.room, "quantity": item.units_booked}],
                check_in_date=booking.check_in_date,
                check_out_date=booking.check_out_date,
                increment=True,
            )
        booking.status = booking.BookingStatus.CANCELLED
        booking.save()
        return booking
    #partial cancel
    @staticmethod
    @transaction.atomic
    def partial_cancel_booking(booking_item: BookingItem, units_to_cancel: int):
        booking = booking_item.booking
        if booking.status in [
            Booking.BookingStatus.CANCELLED,
            Booking.BookingStatus.CONFIRMED,
        ]:
            raise BookingConflict("Booking is already finalized and cannot be changed.")
        if units_to_cancel <= 0:
            raise BookingConflict("Units to cancel must be greater than zero.")

        if units_to_cancel > booking_item.units_booked:
            raise BookingConflict(
                f"You cannot cancel more units ({units_to_cancel}) "
                f"than booked ({booking_item.units_booked})."
            )

        # Update availability (increment=True since we release rooms)
        StayAvailabilityService.update_availability(
            hotel=booking_item.room.hotel,
            rooms_info=[
                {"room": booking_item.room, "quantity": units_to_cancel}
            ],
            check_in_date=booking.check_in_date,
            check_out_date=booking.check_out_date,
            increment=True,
        )
        booking_item.units_booked -= units_to_cancel

        # If zero, delete the booking item
        if booking_item.units_booked == 0:
            booking_item.delete()
        else:
            booking_item.save()

        # Recalculate booking total
        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        if use_seasonal:
            total_price = Decimal('0.00')
            for pip in BookingItemPrice.objects.filter(booking_item__booking=booking):
                total_price += (Decimal(pip.price_per_unit) * Decimal(pip.units))
            booking.total_price = total_price
        else:
            nights = (booking.check_out_date - booking.check_in_date).days
            total_price = Decimal('0.00')
            for item in booking.items.all():
                total_price += (Decimal(item.price_per_unit) * Decimal(item.units_booked) * Decimal(nights))
            booking.total_price = total_price
        booking.save()

        return booking

    @staticmethod
    def confirm_booking(booking: Booking):
        """Called when the user complete payment.

        Args:
            booking (Booking): Booking instance.

        Returns:
            Booking: Confirmed Booking instance.
        """
        if booking.status in [
            Booking.BookingStatus.CANCELLED,
            Booking.BookingStatus.CONFIRMED
        ]:
            raise BookingConflict(
                "Booking is already finalized and cannot be changed."
            )

        booking.status = booking.BookingStatus.CONFIRMED
        booking.save()

        return booking
    
    @staticmethod
    def get_booking_total(booking):
        """Return booking total considering seasonal pricing if enabled.

        - When `FEATURE_SEASONAL_PRICING` is enabled, sums `BookingItemPrice` rows (per-night).
        - Otherwise, multiplies booking item per-night price by nights and units.
        """
        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        if use_seasonal:
            total = Decimal('0.00')
            for pip in BookingItemPrice.objects.filter(booking_item__booking=booking):
                total += (Decimal(pip.price_per_unit) * Decimal(pip.units))
            return total

        nights = (booking.check_out_date - booking.check_in_date).days
        total = Decimal('0.00')
        for item in booking.items.all():
            total += (Decimal(item.price_per_unit) * Decimal(item.units_booked) * Decimal(nights))
        return total
class EventSpaceBookingService:
    @transaction.atomic()
    @staticmethod
    def create_booking(validated_data, user=None):
        """
        Creates a new Event Space Booking, validates availability, and decrements inventory, 
        using only the base price for calculation.
        """
        items_data = validated_data.pop("items")
        
        if user:
            validated_data["user"] = user
        
        check_in_date = validated_data.get("check_in_date")
        check_out_date = validated_data.get("check_out_date")
        
        spaces_info = []
        for item in items_data:
            event_space = item["event_space"]
            units = item["units_booked"]
            spaces_info.append({"space_listing": event_space, "quantity": units})
        
        # 1. Availability Check (and locking records)
        if spaces_info:
            EventSpaceAvailabilityService.validate_availability(
                spaces_info, check_in_date, check_out_date
            )
        
        # 2. Create the parent Booking object
        booking = EventSpaceBooking.objects.create(**validated_data)

        total_price = Decimal('0.00')
        booking_items_to_create = []
        duration = (check_out_date - check_in_date).days
        
        # 3. Create Booking Items and Calculate Price (Simplified)
        for item in items_data:
            event_space: EventSpaceListing = item["event_space"]
            units = item["units_booked"]
            
            # Price Calculation: Base Price * Duration (Days)
            # This is the price paid by the customer per unit for the entire booking period
            price_per_unit_total = event_space.base_price * duration 
            
            booking_item = EventSpaceBookingItem(
                booking=booking,
                event_space=event_space,
                units_booked=units,
                price_per_unit=price_per_unit_total, # Total price per unit for the stay
            )
            booking_items_to_create.append(booking_item)
            total_price += booking_item.subtotal()

        EventSpaceBookingItem.objects.bulk_create(booking_items_to_create)
        
        # 4. Decrement Availability
        EventSpaceAvailabilityService.update_availability(
            spaces_info=spaces_info,
            check_in_date=booking.check_in_date,
            check_out_date=booking.check_out_date,
            increment=False, # Decrement
        )

        # 5. Update Booking Total Price
        booking.total_price = total_price
        booking.save(update_fields=['total_price'])
        
        return booking

    @staticmethod
    def cancel_booking(booking: EventSpaceBooking):
        # Logic remains the same, as it only deals with status and availability update
        if booking.status in [
            booking.BookingStatus.CANCELLED,
            booking.BookingStatus.CONFIRMED 
        ]:
            raise BookingConflict(
                "Booking is already finalized and cannot be changed."
            )
        
        spaces_info = []
        for item in booking.items.all():
            spaces_info.append({
                "space_listing": item.event_space, 
                "quantity": item.units_booked
            })

        # Increment Availability
        EventSpaceAvailabilityService.update_availability(
            spaces_info=spaces_info,
            check_in_date=booking.check_in_date,
            check_out_date=booking.check_out_date,
            increment=True, 
        )
        
        booking.status = booking.BookingStatus.CANCELLED
        booking.save()
        return booking

    @staticmethod
    @transaction.atomic
    def partial_cancel_booking(booking_item: EventSpaceBookingItem, units_to_cancel: int):
        """Partially cancels units from a specific EventSpaceBookingItem."""
        booking = booking_item.booking
        # Check conflict status
        if booking.status in [
            booking.BookingStatus.CANCELLED,
            booking.BookingStatus.CONFIRMED,
        ]:
            raise BookingConflict("Booking is already finalized and cannot be changed.")
            
        if units_to_cancel <= 0:
            raise BookingConflict("Units to cancel must be greater than zero.")

        if units_to_cancel > booking_item.units_booked:
            raise BookingConflict(
                f"You cannot cancel more units ({units_to_cancel}) "
                f"than booked ({booking_item.units_booked})."
            )

        spaces_info = [
            {"space_listing": booking_item.event_space, "quantity": units_to_cancel}
        ]
        
        # Update availability (increment=True)
        EventSpaceAvailabilityService.update_availability(
            spaces_info=spaces_info,
            check_in_date=booking.check_in_date,
            check_out_date=booking.check_out_date,
            increment=True,
        )
        
        # Update item's booked quantity
        booking_item.units_booked -= units_to_cancel

        # If zero, delete the booking item
        if booking_item.units_booked == 0:
            booking_item.delete()
        else:
            booking_item.save()

        # Recalculate booking total (Simplified: sum current item subtotals)
        booking.total_price = sum(item.subtotal() for item in booking.items.all())
        booking.save()

        return booking

    @staticmethod
    def confirm_booking(booking: EventSpaceBooking):
        # Logic remains the same
        if booking.status in [
            booking.BookingStatus.CANCELLED,
            booking.BookingStatus.CONFIRMED
        ]:
            raise BookingConflict(
                "Booking is already finalized and cannot be changed."
            )

        booking.status = booking.BookingStatus.CONFIRMED
        booking.save()

        return booking
    
    @staticmethod
    def get_booking_total(booking: EventSpaceBooking):
        return sum(item.subtotal() for item in booking.items.all())

class PaymentService:
    """
    Handles payment initiation, verification, and transaction recording
    """

    @staticmethod
    def initiate_payment(booking: Booking, amount: float, provider: str):
        """
        Trigger the payment gateway
        Returns payment session info (URL / token)
        """
        # pseudo-code; replace with actual SDK/API
        payment_session_id = f"{booking.id}-{int(datetime.now().timestamp())}"
        return {
            "provider": provider,
            "session_id": payment_session_id,
            "amount": amount,
            "currency": "USD",
            "checkout_url": f"https://fakepayment.com/pay/{payment_session_id}"
        }

    @staticmethod
    def handle_webhook(provider: str, payload: dict):
        """
        Called by payment provider asynchronously
        payload must include provider_payment_id, booking_id, status, amount, etc.
        """
        booking_id = payload.get("booking_id")
        payment_status = payload.get("status")
        provider_payment_id = payload.get("provider_payment_id")
        amount = payload.get("amount")
        currency = payload.get("currency")

        booking = Booking.objects.get(id=booking_id)

        Transaction.objects.create(
            booking=booking,
            provider=provider,
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency=currency,
            status=payment_status
        )

        if payment_status == "success":
            BookingService.confirm_booking(booking)
        else:
            # TODO: Find a way to handle retry logic
            BookingService.cancel_booking(booking)
class CarAvailabilityService:

    @staticmethod
    def create_availability(car_listing, days=90):
        today = date.today()
        objs = []

        for i in range(days):
            objs.append(
                CarAvailability(
                    car_listing=car_listing,
                    date=today + timedelta(days=i),
                    available_units=car_listing.quantity,
                )
            )
        
        CarAvailability.objects.bulk_create(
            objs, 
            batch_size=1000,
            ignore_conflicts=True
        )
    @staticmethod
    def get_available_cars(check_start, check_end):
        required_days = (check_end - check_start).days

        qs = (
            CarAvailability.objects
            .filter(
                date__gte=check_start,
                date__lt=check_end,
                available_units__gt=0
            )
            .values("car_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_units")
            )
            .filter(total_days=required_days)
        )

        car_ids = [row["car_listing"] for row in qs]
        cars = CarListing.objects.filter(id__in=car_ids)

        return cars, qs
    @staticmethod
    @transaction.atomic
    def validate_availability(car_listing, quantity, start_date, end_date):
        dates = []
        d = start_date
        while d < end_date:
            dates.append(d)
            d += timedelta(days=1)

        # get rows for those dates for this car
        qs = CarAvailability.objects.select_for_update().filter(
            car_listing=car_listing,
            date__in=dates
        )

        availability_map = {av.date: av for av in qs}

        for dt in dates:
            av = availability_map.get(dt)

            if not av:
                raise BookingConflict(
                    f"No availability entry for {car_listing} on {dt}"
                )

            if av.available_units < quantity:
                raise BookingConflict(
                    f"{car_listing} not enough units on {dt}, "
                    f"Available: {av.available_units}, Requested: {quantity}"
                )
    @staticmethod
    def update_availability(car_listing, quantity, start_date, end_date, increment=False):

        dates = []
        d = start_date
        while d < end_date:
            dates.append(d)
            d += timedelta(days=1)

        for dt in dates:
            qs = CarAvailability.objects.select_for_update().filter(
                car_listing=car_listing,
                date=dt
            )
            if increment:
                qs.update(available_units=F("available_units") + quantity)
            else:
                qs.update(available_units=F("available_units") - quantity)
    @staticmethod
    def search_available_cars(
        start_date,
        end_date,
        brand=None,
        car_class=None,
        seats=None,
    ):
        required_days = (end_date - start_date).days

        qs = (
            CarAvailability.objects
            .filter(
                date__gte=start_date,
                date__lt=end_date,
                available_units__gt=0
            )
            .values("car_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_units")
            )
            .filter(total_days=required_days)
        )

        car_ids = [row["car_listing"] for row in qs]

        cars = CarListing.objects.filter(id__in=car_ids)

        if brand:
            cars = cars.filter(brand=brand)
        if car_class:
            cars = cars.filter(car_class=car_class)
        if seats:
            cars = cars.filter(seats__gte=seats)

        # Return mapped availability data
        availability_map = {
            row["car_listing"]: row["min_available"] for row in qs
        }

        result = []
        for car in cars:
            result.append({
                "car": car,
                "available_units": availability_map.get(car.id, 0)
            })

        return result
    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        start = start_date or date.today()
        end = start + timedelta(days=days_ahead)

        car_listings = CarListing.objects.all()
        created = 0
        batch = []

        for car in car_listings:
            existing_dates = set(
                CarAvailability.objects.filter(
                    car_listing=car,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )

            cursor = start
            while cursor < end:
                if cursor not in existing_dates:
                    batch.append(
                        CarAvailability(
                            car_listing=car,
                            date=cursor,
                            available_units=car.quantity,
                        )
                    )
                    if len(batch) >= 1000:
                        CarAvailability.objects.bulk_create(
                            batch,
                            batch_size=1000,
                            ignore_conflicts=True
                        )
                        created += len(batch)
                        batch = []
                cursor += timedelta(days=1)

        if batch:
            CarAvailability.objects.bulk_create(
                batch,
                batch_size=1000,
                ignore_conflicts=True
            )
            created += len(batch)

        return created

class EventSpaceAvailabilityService:
    @staticmethod
    def create_availability(space_listing, units_quantity, days=90):
        """
        Populates EventSpaceAvailability records for a new listing.
        The price comes from the listing's base_price (or other logic).
        """
        today = timezone.now().date()
        objs = []
        base_price = space_listing.base_price 
        for i in range(1, days + 1):
            objs.append(
                EventSpaceAvailability(
                    space_listing=space_listing,
                    available_eventspace=units_quantity, 
                    date=today + timedelta(days=i),
                    price=base_price,
                )
            )

        EventSpaceAvailability.objects.bulk_create(
            objs, batch_size=1000, ignore_conflicts=True
        )
        

    @staticmethod
    def get_available_listings(hotel, space_type, check_in_date, check_out_date):
        """
        Retrieves EventSpaceListings that have availability for ALL days in the range.
        """
        required_days = (check_out_date - check_in_date).days

        # Aggregate availability across the date range
        qs = (
            EventSpaceAvailability.objects
            .filter(
                space_listing__hotel=hotel,
                space_listing__space_type=space_type,
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_eventspace__gt=0 # Must have at least 1 unit available
            )
            .values("space_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_eventspace")
            )
            .filter(total_days=required_days) # Ensure availability exists for ALL days
        )

        # Extract listing IDs
        listing_ids = [row["space_listing"] for row in qs]

        listings = EventSpaceListing.objects.filter(id__in=listing_ids)

        return listings, qs

    @staticmethod
    def validate_availability(space_infos, check_in_date, check_out_date):
        """
        Validates if the requested quantity of each space is available on ALL dates.
        `space_infos` is a list of dictionaries: [{"space_listing": listing_obj, "quantity": 1}]
        """
        dates = []
        date_cursor = check_in_date
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)
        
        space_listing_ids = [info["space_listing"].id for info in space_infos]
        availabilities = EventSpaceAvailability.objects.select_for_update().filter(
            space_listing_id__in=space_listing_ids,
            date__in=dates
        )
        
        availability_map = {}
        for av in availabilities:
            key = (av.space_listing_id, av.date)
            availability_map[key] = av
        
        for date_cursor in dates:
            for info in space_infos:
                listing = info["space_listing"]
                quantity = info["quantity"]
                key = (listing.id, date_cursor)
                availability = availability_map.get(key)
                
                if not availability:
                    raise BookingConflict(
                        f"No availability data for {listing.title} on {date_cursor}"
                    )
                
                if availability.available_eventspace < quantity:
                    raise BookingConflict(
                        f"Not enough units available for {listing.title} on {date_cursor}. "
                        f"Available: {availability.available_eventspace}, Requested: {quantity}"
                    )

    @staticmethod
    def update_availability(
        space_infos,
        check_in_date,
        check_out_date,
        increment: bool = False,
    ):
        """
        Updates the available_units count. Decrements on booking, increments on cancellation.
        """
        dates = []
        date_cursor = check_in_date
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1) 
        with transaction.atomic():
            for date_cursor in dates:
                for info in space_infos:
                    listing_id = info["space_listing"].id
                    quantity = info["quantity"]
                    
                    obj = EventSpaceAvailability.objects.select_for_update().filter(
                        space_listing_id=listing_id, date=date_cursor
                    )

                    if increment:
                        obj.update(available_eventspace=F("available_eventspace") + quantity)
                    else:
                        obj.update(available_eventspace=F("available_eventspace") - quantity)
                    
    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        """
        A maintenance function to ensure all listings have availability populated for the future.
        """
        start = start_date or timezone.now().date()
        end = start + timedelta(days=days_ahead)
        
        # Select related data to avoid N+1 queries in the loop
        listings = EventSpaceListing.objects.select_related("hotel")
        created = 0
        batch = []
        
        for listing in listings:
            if not listing.hotel:
                continue
            
            # Find all dates that already have availability for this listing in the range
            existing_dates = set(
                EventSpaceAvailability.objects.filter(
                    space_listing=listing,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )
            
            cursor = start
            while cursor < end:
                if cursor not in existing_dates:
                    # Create a new availability record
                    batch.append(
                        EventSpaceAvailability(
                            space_listing=listing,
                            date=cursor,
                            available_eventspace=listing.total_units,
                            price=listing.base_price,
                        )
                    )
                    
                    if len(batch) >= 1000:
                        EventSpaceAvailability.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
                        created += len(batch)
                        batch = []
                cursor += timedelta(days=1)
                
        if batch:
            EventSpaceAvailability.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
            created += len(batch)
            
        return created
    @staticmethod
    def search_available_listings(
        check_in_date,
        check_out_date,
        required_quantity,
        address_query=None,
        max_distance_km=None,
    ):
        required_days = (check_out_date - check_in_date).days

        availability_qs = (
            EventSpaceAvailability.objects
            .filter(
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_eventspace__gte=required_quantity
            )
            .values("space_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_eventspace")
            )
            .filter(total_days=required_days)
        )

        available_listing_ids = [row["space_listing"] for row in availability_qs]

        listings_qs = EventSpaceListing.objects.filter(id__in=available_listing_ids)

        if address_query:
            listings_qs = listings_qs.filter(
        Q(address__city__icontains=address_query) |
        Q(address__sub_city__icontains=address_query) |
        Q(address__street_line1__icontains=address_query)
    )

        listing_info_map = {
            row["space_listing"]: row["min_available"]
            for row in availability_qs
        }

        final_listings = []
        for listing in listings_qs:
            listing.min_available_for_period = listing_info_map.get(listing.id)
            final_listings.append(listing)

        return final_listings
class GuestHouseAvailabilityService:

    @staticmethod
    def create_availability(guest_house, units_quantity, days=90):
        """
        Creates GuestHouseAvailability rows for the next `days` for a new listing.
        """
        today = timezone.now().date()
        objs = []

        for i in range(1, days + 1):
            objs.append(
                GuestHouseAvailability(
                    guest_house=guest_house,
                    available_rooms=units_quantity,
                    date=today + timedelta(days=i)
                )
            )

        GuestHouseAvailability.objects.bulk_create(
            objs, batch_size=1000, ignore_conflicts=True
        )

    @staticmethod
    def get_available_listings(check_in_date, check_out_date, min_units=1, address_filters=None):
        """
        Returns GuestHouseListing objects available for all days in the range.
        """
        required_days = (check_out_date - check_in_date).days

        qs = GuestHouseAvailability.objects.filter(
            date__gte=check_in_date,
            date__lt=check_out_date,
            available_rooms__gte=min_units
        )

        if address_filters:
            filter_kwargs = {}
            
            address_fields = ["city", "country", "region", "sub_city"]

            for key in address_fields:
                value = address_filters.get(key)               
                if value:
                    # Construct the full Django ORM lookup string dynamically
                    lookup_key = f"guest_house__address__{key}__icontains"
                    filter_kwargs[lookup_key] = value

            if filter_kwargs:
                qs = qs.filter(**filter_kwargs)
        aggregated = qs.values("guest_house").annotate(
            total_days=Count("date", distinct=True),
            min_available=Min("available_rooms")
        ).filter(total_days=required_days)

        listing_ids = [row["guest_house"] for row in aggregated]
        listings = GuestHouseListing.objects.filter(id__in=listing_ids, is_active=True)

        return listings, aggregated

    @staticmethod
    def validate_availability(room_infos, check_in_date, check_out_date):
        """
        Validate availability for each room in room_infos:
        room_infos = [{"guesthouse_listing": obj, "quantity": 2}, ...]
        """
        dates = [check_in_date + timedelta(days=i) for i in range((check_out_date - check_in_date).days)]
        listing_ids = [r["guesthouse_listing"].id for r in room_infos]

        availabilities = GuestHouseAvailability.objects.select_for_update().filter(
            guest_house_id__in=listing_ids,
            date__in=dates
        )

        availability_map = {(av.guest_house_id, av.date): av for av in availabilities}

        for date in dates:
            for info in room_infos:
                listing = info["guesthouse_listing"]
                qty = info["quantity"]
                key = (listing.id, date)
                av = availability_map.get(key)

                if not av:
                    raise BookingConflict(f"No availability for {listing.title} on {date}")
                if av.available_rooms < qty:
                    raise BookingConflict(f"Not enough rooms for {listing.title} on {date}. Available: {av.available_rooms}, Requested: {qty}")

    @staticmethod
    def update_availability(room_infos, check_in_date, check_out_date, increment=False):
        """
        Updates available_rooms:
        decrement if booking, increment if cancellation.
        """
        dates = [check_in_date + timedelta(days=i) for i in range((check_out_date - check_in_date).days)]

        with transaction.atomic():
            for date in dates:
                for info in room_infos:
                    listing_id = info["guesthouse_listing"].id
                    qty = info["quantity"]
                    qs = GuestHouseAvailability.objects.select_for_update().filter(
                        guest_house_id=listing_id, date=date
                    )
                    if increment:
                        qs.update(available_rooms=F("available_rooms") + qty)
                    else:
                        qs.update(available_rooms=F("available_rooms") - qty)

    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        """
        Ensure all guest houses have availability populated for the next `days_ahead`.
        """
        start = start_date or timezone.now().date()
        end = start + timedelta(days=days_ahead)
        listings = GuestHouseListing.objects.all()
        batch = []
        created = 0

        for listing in listings:
            existing_dates = set(
                GuestHouseAvailability.objects.filter(
                    guest_house=listing,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )

            for day in range((end - start).days):
                date = start + timedelta(days=day)
                if date not in existing_dates:
                    batch.append(
                        GuestHouseAvailability(
                            guest_house=listing,
                            date=date,
                            available_rooms=listing.total_rooms
                        )
                    )

                    if len(batch) >= 1000:
                        GuestHouseAvailability.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
                        created += len(batch)
                        batch = []

        if batch:
            GuestHouseAvailability.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
            created += len(batch)

        return created
