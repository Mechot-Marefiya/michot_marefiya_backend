import pytest
from PIL import Image
from io import BytesIO
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from apps.listing.models import (
    CarListing,
    GuestHouseProfile,
    GuestHouseRoom,
    PropertyListing,
    RoomListing,
)


def create_test_image(name="test.png", ext="PNG", size=(100, 100), color=(255, 0, 0)):
    file = BytesIO()
    image = Image.new("RGB", size=size, color=color)
    image.save(file, ext)
    file.seek(0)
    return SimpleUploadedFile(name, file.read(), content_type=f"image/{ext.lower()}")


@pytest.mark.django_db(transaction=True)
class TestRoomListingAPI:
    endpoint = "rooms-list"

    def _make_room(self, **kwargs):
        """Helper to create a RoomListing directly via the manager."""
        defaults = {
            "title": "Deluxe room",
            "description": "A very luxury room with 2 king bed",
            "base_price": 2000,
            "number_of_guests": 2,
            "total_units": 10,
            "address": kwargs["address"].id,
            "hotel": kwargs["hotel"].id,
            "bed_type": RoomListing.BedType.KING,
            "room_size_sqm": 50,
            "smoking_allowed": False,
            "children_allowed": False,
            # if your model requires FKs like `hotel_profile` or `address`,
            # you can pass them in via **overrides from the test
        }
        defaults.update(kwargs)
        return RoomListing.objects.create(**defaults)

    def test_room_listing_get(
        self, authenticated_hotel_profile_client, address, hotel_profile
    ):
        room = self._make_room(address=address, hotel=hotel_profile)
        url = reverse(self.endpoint) + f"{room.id}/"

        res = authenticated_hotel_profile_client.get(url)

        assert res.status_code == status.HTTP_200_OK
        assert res.data["id"] == str(room.id)
        assert res.data["title"] == room.title

    def test_room_listing_patch(
        self, authenticated_hotel_profile_client, address, hotel_profile
    ):
        room = self._make_room(address=address, hotel=hotel_profile)
        url = reverse(self.endpoint) + f"{room.id}/"
        payload = {"title": "Updated Deluxe Room", "total_units": 15}

        res = authenticated_hotel_profile_client.patch(url, payload, format="json")

        assert res.status_code == status.HTTP_200_OK
        assert res.data["title"] == "Updated Deluxe Room"
        room.refresh_from_db()
        assert room.total_units == 15

    def test_room_listing_creation(
        self,
        authenticated_hotel_profile_client,
        address_payload,
        images_list,
        amenities,
    ):
        data = {
            "images": images_list,
            "title": "Deluxe room",
            "description": "A very luxury room with 2 king bed",
            "base_price": "2000",
            "address": address_payload,
            "number_of_guests": 2,
            "total_units": 10,
            "amenities": amenities,
            "bed_type": RoomListing.BedType.KING,
            "room_size_sqm": 50,
            "smoking_allowed": False,
            "children_allowed": False,
        }

        res = authenticated_hotel_profile_client.post(
            reverse(self.endpoint), data, format="multipart"
        )

        # print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["title"] == "Deluxe room"
        assert res.data["bed_type"] == RoomListing.BedType.KING

    def test_room_listing_creation_fails_on_missed_data(
        self,
        authenticated_hotel_profile_client,
        amenities,
        address_payload,
        images_list,
    ):
        data = {
            "images": images_list,
            "title": "",
            "base_price": "2000",
            "address": address_payload,
            "number_of_guests": 2,
            "total_units": 10,
            "amenities": amenities,
            "bed_type": RoomListing.BedType.KING,
            "room_size_sqm": 50,
        }

        res = authenticated_hotel_profile_client.post(
            reverse(self.endpoint), data, format="multipart"
        )

        # print("RES", res.data)

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "This field may not be blank." in str(res.data)


@pytest.mark.django_db(transaction=True)
class TestGuestHouseListingAPI:
    endpoint = "guest_houses-list"

    def test_create_guest_house_with_individual_owner(
        self,
        authenticated_client,
        individual_owner_profile,
        address_payload,
        images_list,
        amenities,
    ):
        payload = {
            "title": "ABCD",
            "base_price": 12500.00,
            "amenities": amenities,
            "address": address_payload,
            "individual_owner": individual_owner_profile.id,
            "images": images_list,
        }

        res = authenticated_client.post(
            reverse(self.endpoint), payload, format="multipart"
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        # Note: Profile creation no longer returns total_rooms as it is room-level
        assert res.data["title"] == "ABCD"
        gh = GuestHouseProfile.objects.get(id=res.data["id"])
        assert gh.company is None
        assert gh.individual_owner == individual_owner_profile

    def test_create_guest_house_with_company_owner(
        self,
        authenticated_company_profile_client,
        address_payload,
        images_list,
        amenities,
    ):
        payload = {
            "title": "ABCD",
            "base_price": 12500.00,
            "amenities": amenities,
            "address": address_payload,
            "images": images_list,
        }
        res = authenticated_company_profile_client.post(
            reverse(self.endpoint), payload, format="multipart"
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["title"] == "ABCD"
        gh = GuestHouseProfile.objects.get(id=res.data["id"])
        assert gh.individual_owner is None

    def test_create_guest_house_without_owner_should_fail(
        self, authenticated_michot_admin_client, address_payload, images_list, amenities
    ):
        """Simulating if by any case the michot admin failed to send an individual owner profile.
        Assume they're registering individually owner GuestHouse buy we missed that profile.
        i.e: no individual or company owner.
        """
        payload = {
            "title": "ABCD",
            "base_price": 12500.00,
            "amenities": amenities,
            "address": address_payload,
            "images": images_list,
        }

        res = authenticated_michot_admin_client.post(
            reverse(self.endpoint), payload, format="multipart"
        )
        assert res.status_code == 400
        assert "Valid Company or individual owner must exist" in str(res.data)


@pytest.mark.django_db(transaction=True)
class TestCarListingAPI:
    endpoint = reverse("cars-list")

    def test_create_car_with_company_owner(
        self,
        authenticated_company_profile_client,
        images_list,
    ):
        payload = {
            "title": "Lamburgini",
            "base_price": 5_000_000,
            "images": images_list,
            "brand": CarListing.CarBrandChoices.BMW,
            "model": "X5",
            "year": 2020,
            "mileage": 25000,
            "fuel_type": CarListing.FuelTypeChoices.PETROL,
            "transmission": CarListing.TransmissionChoices.AUTOMATIC,
            "listing_type": CarListing.ListingTypeChoices.SELL,
            "condition": CarListing.ConditionChoices.NEW,
        }

        res = authenticated_company_profile_client.post(
            self.endpoint, payload, format="multipart"
        )
        # print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        car = CarListing.objects.get(id=res.data["id"])
        assert car.individual_owner is None
        assert str(car) == "bmw::X5::normal"

    def test_create_car_with_individual_owner(
        self,
        authenticated_company_profile_client,
        images_list,
        individual_owner_profile,
    ):
        payload = {
            "title": "Corolla",
            "base_price": 5_000_000,
            "images": images_list,
            "individual_owner": individual_owner_profile.id,
            "brand": CarListing.CarBrandChoices.TOYOTA,
            "model": "Camry",
            "year": 2018,
            "mileage": 60000,
            "fuel_type": CarListing.FuelTypeChoices.HYBRID,
            "transmission": CarListing.TransmissionChoices.MANUAL,
            "listing_type": CarListing.ListingTypeChoices.SELL,
            "condition": CarListing.ConditionChoices.NEW,
        }

        res = authenticated_company_profile_client.post(
            self.endpoint, payload, format="multipart"
        )
        # print("RES", res.data)
        assert res.status_code == status.HTTP_201_CREATED
        car = CarListing.objects.get(id=res.data["id"])
        assert car.individual_owner == individual_owner_profile
        assert car.company is None

    def test_create_car_without_owner_should_fail(
        self, authenticated_michot_admin_client, images_list
    ):
        payload = {
            "title": "Corolla",
            "base_price": 5_000_000,
            "images": images_list,
            "brand": CarListing.CarBrandChoices.AUDI,
            "model": "A4",
            "year": 2022,
            "mileage": 5000,
            "fuel_type": CarListing.FuelTypeChoices.DIESEL,
            "transmission": CarListing.TransmissionChoices.AUTOMATIC,
            "listing_type": CarListing.ListingTypeChoices.SELL,
            "condition": CarListing.ConditionChoices.NEW,
        }
        res = authenticated_michot_admin_client.post(
            self.endpoint, payload, format="multipart"
        )

        print("RES", res.data)
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Valid Company or individual owner must exist" in str(res.data)


@pytest.mark.db(transaction=True)
class TestPropertyListingAPI:
    endpoint = "properties-list"

    def test_create_property_with_company_owner(
        self, authenticated_company_profile_client, images_list, address_payload
    ):
        payload = {
            "title": "Luxury Apartment",
            "base_price": 16_000_000,
            "images": images_list,
            "address": address_payload,
            "property_type": PropertyListing.PropertyTypeChoices.APARTMENT,
            "bedrooms": 4,
            "bathrooms": 2,
            "square_meters": 120,
            "is_furnished": True,
            "listing_type": PropertyListing.ListingTypeChoices.SELL,
        }

        res = authenticated_company_profile_client.post(
            reverse(self.endpoint), payload, format="multipart"
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["title"] == payload["title"]
        property = PropertyListing.objects.get(id=res.data["id"])

        assert property.individual_owner is None

    def test_create_property_with_individual_owner(
        self,
        authenticated_client,
        individual_owner_profile,
        images_list,
        address_payload,
    ):
        payload = {
            "title": "Luxury Apartment",
            "base_price": 16_000_000,
            "individual_owner": individual_owner_profile.id,
            "images": images_list,
            "address": address_payload,
            "property_type": PropertyListing.PropertyTypeChoices.CONDO,
            "bedrooms": 4,
            "bathrooms": 2,
            "square_meters": 120,
            "listing_type": PropertyListing.ListingTypeChoices.RENT,
        }

        res = authenticated_client.post(
            reverse(self.endpoint), payload, format="multipart"
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        property = PropertyListing.objects.get(id=res.data["id"])

        assert property.company is None
        assert property.individual_owner == individual_owner_profile

    def test_create_property_without_owner_should_fail(
        self, authenticated_michot_admin_client, images_list, address_payload
    ):
        payload = {
            "title": "Luxury Apartment",
            "base_price": 16_000_000,
            "images": images_list,
            "address": address_payload,
            "property_type": PropertyListing.PropertyTypeChoices.CONDO,
            "bedrooms": 4,
            "bathrooms": 2,
            "square_meters": 120,
            "listing_type": PropertyListing.ListingTypeChoices.RENT,
        }

        res = authenticated_michot_admin_client.post(
            reverse(self.endpoint), payload, format="multipart"
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_property_with_missed_required_data_should_fail(
        self, authenticated_company_profile_client, images_list, address_payload
    ):
        payload = {
            "title": "",
            "base_price": 16_000_000,
            "images": images_list,
            "address": address_payload,
            "property_type": PropertyListing.PropertyTypeChoices.VILLA,
            "bedrooms": 4,
            "bathrooms": 2,
            "square_meters": 120,
            "listing_type": PropertyListing.ListingTypeChoices.RENT,
        }

        res = authenticated_company_profile_client.post(
            reverse(self.endpoint), payload, format="multipart"
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "title" in str(res.data)
