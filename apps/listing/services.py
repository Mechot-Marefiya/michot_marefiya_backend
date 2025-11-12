from datetime import date, timedelta
from django.db import transaction
from django.db.models import Count, F
from django.shortcuts import get_object_or_404
from apps.account.models import CompanyProfile, HotelProfile
from apps.account.services import ImageCreationService
from apps.core.models import Address
from apps.listing.models import (
    Amenity,
    Booking,
    BookingItem,
    GuestHouseListing,
    PropertyListing,
    RoomListing,
    StayAvailability,
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
                    is_available=True,
                )
            )

        StayAvailability.objects.bulk_create(objs, batch_size=1000)

    # * This get_available_rooms method will be used to render our room list table.

    @staticmethod
    def get_available_rooms(hotel, check_in_date, checkout_in_date):
        """
        Return all rooms in this hotel that are fully
        available between check_in_date–checkout_in_date.
        """
        days = (checkout_in_date - check_in_date).days

        # Get all room IDs that are available for *every* day in range
        available_rooms = (
            StayAvailability.objects.filter(
                hotel=hotel,
                date__gte=check_in_date,
                date__lt=checkout_in_date,
                is_available=True,
            )
            .values("room")
            .annotate(count_days=Count("id"))
            .filter(count_days=days)
            .values_list("room", flat=True)
        )

        return RoomListing.objects.filter(id__in=available_rooms)

    @staticmethod
    def update_availability(
        hotel,
        rooms_info,  # expect a list of objs [{room: room_obj, quantity: int}]
        check_in_date,
        check_out_date,
        increment: bool = False,
    ):
        date_cursor = check_in_date
        while date_cursor < check_out_date:
            for room_info in rooms_info:
                obj = StayAvailability.objects.filter(
                    hotel=hotel, room=room_info["room"], date=date_cursor
                )
                if increment:
                    obj.update(available_rooms=F(
                        "available_rooms") + room_info["quantity"])
                else:
                    obj.update(available_rooms=F(
                        "available_rooms") - room_info["quantity"])
            date_cursor += timedelta(days=1)


class BookingService:
    @transaction.atomic()
    @staticmethod
    def create_booking(validated_data):
        items_data = validated_data.pop("items")
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
