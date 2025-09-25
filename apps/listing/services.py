from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.account.models import CompanyProfile, HotelProfile, IndividualOwnerProfile
from apps.core.models import Address
from apps.listing.models import (
    Amenity,
    GuestHouseListing,
    ListingImage,
    PropertyListing,
    RoomListing,
)


class ListingService:
    @staticmethod
    @transaction.atomic()
    def create_hotel_listing(validated_data: dict):
        hotel_id = validated_data.pop("hotel_id", None)
        images = validated_data.pop("images")
        # TODO: Do some way of handling the duplicate address creation
        # TODO: by maybe asking hotels to fill how many branches they have on
        # TODO: registration then avoid listing address fill form the UI and
        # TODO:  also make it optional here as well so that we can reuse the HQ address.
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities")

        if hotel_id:
            company = get_object_or_404(
                CompanyProfile, id=hotel_id)
        else:
            company = get_object_or_404(
                CompanyProfile, user=validated_data.pop('user'))

        hotel_profile = get_object_or_404(HotelProfile, company=company)

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

        ListingService.create_images(room_listing_instance, images)

        return room_listing_instance

    @staticmethod
    @transaction.atomic()
    def create_guest_house_listing(validated_data: dict):
        images = validated_data.pop("images")
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities")
        individual_owner_id = validated_data.pop('individual_owner')
        address_instance = ListingService.create_address(address_data)

        individual_owner = get_object_or_404(
            IndividualOwnerProfile, id=individual_owner_id)

        guest_house_listing_instance = GuestHouseListing.objects.create(
            address=address_instance,
            individual_owner=individual_owner,
            **validated_data
        )
        amenities = []
        for id in amenity_ids:
            instance = get_object_or_404(Amenity, id=id)
            amenities.append(instance)

        # M2M to amenities
        guest_house_listing_instance.amenities.set(amenities)

        ListingService.create_images(guest_house_listing_instance, images)

        return guest_house_listing_instance

    @staticmethod
    @transaction.atomic()
    def create_property_listing(validated_data: dict):
        images = validated_data.pop("images")
        address_data = validated_data.pop("address", None)

        address_instance = ListingService.create_address(address_data)
        individual_owner_id = validated_data.pop('individual_owner')

        individual_owner = get_object_or_404(
            IndividualOwnerProfile,
            id=individual_owner_id
        )

        property_listing_instance = PropertyListing.objects.create(
            address=address_instance,
            individual_owner=individual_owner,
            **validated_data
        )

        ListingService.create_images(property_listing_instance, images)

        return property_listing_instance

    @staticmethod
    def create_address(address_data) -> Address:
        return Address.objects.create(**address_data)

    @staticmethod
    def create_images(content_object, images_payload):
        # create images
        image_objs = []

        for img_file in images_payload:
            if hasattr(img_file, "is_primary"):
                is_primary = img_file.is_primary
            else:
                is_primary = False

            img_instance = ListingImage(
                content_object=content_object,
                image=img_file,
                alt_text=img_file.name,
                # TODO: Expect a metadata attached in the payload
                is_primary=is_primary,
            )
            image_objs.append(img_instance)

        images = ListingImage.objects.bulk_create(image_objs)

        print("Images Created", images)
