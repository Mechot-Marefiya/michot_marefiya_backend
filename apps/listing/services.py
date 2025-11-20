from datetime import date, timedelta, datetime
from django.db import transaction
from django.db.models import Count, F, Min
from django.shortcuts import get_object_or_404
from apps.account.models import CompanyProfile, HotelProfile
from apps.account.services import ImageCreationService
from apps.core.models import Address
from apps.listing.exceptions import BookingConflict
from apps.listing.models import (
    Amenity,
    Booking,
    BookingItem,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
    StayAvailability,
    Transaction,
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

        StayAvailability.objects.bulk_create(objs, batch_size=1000)

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
                        StayAvailability.objects.bulk_create(batch, batch_size=1000)
                        created += len(batch)
                        batch = []
                cursor += timedelta(days=1)
        if batch:
            StayAvailability.objects.bulk_create(batch, batch_size=1000)
            created += len(batch)
        return created


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

        for item in items_data:
            room = item["room"]
            units = item["units_booked"]

            BookingItem.objects.create(
                booking=booking,
                room=room,
                units_booked=units,
                price_per_unit=room.base_price,
            )

            StayAvailabilityService.update_availability(
                hotel=room.hotel,
                rooms_info=[{"room": room, "quantity": units}],
                check_in_date=booking.check_in_date,
                check_out_date=booking.check_out_date,
                increment=False,
            )

        booking.total_price = sum(i.subtotal() for i in booking.items.all())
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
        booking.total_price = sum(item.subtotal() for item in booking.items.all())
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
