from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.account.models import CompanyProfile, HotelProfile
from apps.core.models import Address
from apps.listing.models import HotelListing, ListingImage


class ListingService:
    @staticmethod
    @transaction.atomic()
    def create_hotel_listing(validated_data: dict):
        user = validated_data.pop("user")
        images = validated_data.pop("images")
        # TODO: Do some way of handling the duplicate address creation
        # TODO: by maybe asking hotels to fill how many branches they have on
        # TODO: registration then avoid listing address fill form the UI and
        # TODO:  also make it optional here as well so that we can reuse the HQ address.
        address_data = validated_data.pop("address", None)
        amenitites = validated_data.pop("amenities")

        # ? I assumed this listing creation is done by the companies
        # ? themselves. But if this will be done by the Michot admin, this will mess up
        company = get_object_or_404(CompanyProfile, user=user)

        hotel_profile = get_object_or_404(HotelProfile, company=company)

        address_instance = None

        if address_data:
            address_instance = ListingService.create_address(address_data)
        else:
            address_instance = company.address

        hotel_listing_instance = HotelListing.objects.create(
            hotel=hotel_profile, address=address_instance, **validated_data
        )

        # M2M to amenities
        hotel_listing_instance.amenities.set(amenitites)

        ListingService.create_images(hotel_listing_instance, images)

        return hotel_listing_instance

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
