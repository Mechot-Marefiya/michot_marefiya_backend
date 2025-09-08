import pytest
import json
from PIL import Image
from io import BytesIO
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from apps.listing.models import CarListing, RoomListing


def create_test_image(name="test.png", ext="PNG", size=(100, 100), color=(255, 0, 0)):
    file = BytesIO()
    image = Image.new("RGB", size=size, color=color)
    image.save(file, ext)
    file.seek(0)
    return SimpleUploadedFile(name, file.read(), content_type=f"image/{ext.lower()}")


@pytest.mark.django_db(transaction=True)
class TestRoomListingAPI:
    endpoint = "rooms-list"

    def test_room_listing_creation(
        self,
        authenticated_hotel_profile_client,
        address_payload,
        images_list,
        amenities
    ):
        print("AM", amenities)
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
            "children_allowed": False
        }

        res = authenticated_hotel_profile_client.post(
            reverse(self.endpoint), data, format="multipart"
        )

        # print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["title"] == "Deluxe room"
        assert res.data["bed_type"] == RoomListing.BedType.KING

    # @pytest.mark.django_db
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
    endpoint = 'guest_houses-list'

    def test_create_guest_house_with_individual_owner(
        self,
        authenticated_client,
        individual_owner_profile,
        address_payload,
        images_list,
        amenities
    ):

        payload = {
            'title': 'ABCD',
            'base_price': 12500.00,
            'total_rooms': 4,
            'rating': 4,
            'amenities': amenities,
            'address': address_payload,
            'individual_owner': individual_owner_profile.id,
            'images': images_list
        }

        res = authenticated_client.post(
            reverse(self.endpoint), payload, format='multipart'
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['total_rooms'] == 4
        assert res.data['title'] == 'ABCD'

    def test_create_guest_house_with_company_owner(
        self,
        authenticated_company_profile_client,
        address_payload,
        images_list,
        amenities
    ):

        payload = {
            'title': 'ABCD',
            'base_price': 12500.00,
            'total_rooms': 4,
            'rating': 4,
            'amenities': amenities,
            'address': address_payload,
            'images': images_list
        }
        res = authenticated_company_profile_client.post(
            reverse(self.endpoint), payload, format='multipart'
        )

        print("RES", res.data)

        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['total_rooms'] == 4
        assert res.data['title'] == 'ABCD'

    def test_create_guest_house_without_owner_should_fail(
        self,
        authenticated_michot_admin_client,
        address_payload,
        images_list,
        amenities
    ):
        """Simulating if by any case the michot admin failed to send an individual owner profile.
        Assume they're registering individually owner GuestHouse buy we missed that profile.
        i.e: no individual or company owner.
        """
        payload = {
            'title': 'ABCD',
            'base_price': 12500.00,
            'total_rooms': 4,
            'rating': 4,
            'amenities': amenities,
            'address': address_payload,
            'images': images_list
        }

        res = authenticated_michot_admin_client.post(
            reverse(self.endpoint), payload, format='multipart'
        )
        assert res.status_code == 400
        assert "Valid Company or individual owner must exist" in str(res.data)


# @pytest.mark.django_db
# class TestCarListingAPI:
#     endpoint = reverse("cars-list")

#     def test_create_car_with_company_owner(
#         self,
#         authenticated_company_profile_client,
#         images_list,
#     ):
#         payload = {
#             'title': 'Lamburgini',
#             'base_price': 5_000_000,
#             'images': images_list,
#             "brand": CarListing.CarBrandChoices.BMW,
#             "model": "X5",
#             "year": 2020,
#             "mileage": 25000,
#             "fuel_type": CarListing.FuelTypeChoices.PETROL,
#             "transmission": CarListing.TransmissionChoices.AUTOMATIC,
#             "listing_type": CarListing.ListingTypeChoices.SELL
#         }

#         response = authenticated_company_profile_client.post(
#             self.endpoint, payload, format="multipart"
#         )

#         assert response.status_code == status.HTTP_201_CREATED
#         car = CarListing.objects.get(id=response.data["id"])
#         assert car.company == authenticated_company_profile_client
#         assert car.individual_owner is None
#         assert str(car) == "bmw::X5"

#     def test_create_car_with_individual_owner(
#         self,
#         authenticated_company_profile_client,
#         images_list,
#         individual_owner_profile
#     ):
#         payload = {
#             'title': 'Corolla',
#             'base_price': 5_000_000,
#             'images': images_list,
#             "individual_owner": individual_owner_profile.id,
#             "brand": CarListing.CarBrandChoices.TOYOTA,
#             "model": "Camry",
#             "year": 2018,
#             "mileage": 60000,
#             "fuel_type": CarListing.FuelTypeChoices.HYBRID,
#             "transmission": CarListing.TransmissionChoices.MANUAL,
#             "listing_type": CarListing.ListingTypeChoices.SELL
#         }

#         response = authenticated_company_profile_client.post(
#             self.endpoint, payload, format="json"
#         )
#         assert response.status_code == status.HTTP_201_CREATED
#         car = CarListing.objects.get(id=response.data["id"])
#         assert car.individual_owner == individual_owner_profile
#         assert car.company is None

#     def test_create_car_without_owner_should_fail(
#             self,
#             authenticated_company_profile_client
#     ):
#         payload = {
#             "brand": CarListing.CarBrandChoices.AUDI,
#             "model": "A4",
#             "year": 2022,
#             "mileage": 5000,
#             "fuel_type": CarListing.FuelTypeChoices.DIESEL,
#             "transmission": CarListing.TransmissionChoices.AUTOMATIC,
#             "is_for_sale": True,
#         }
#         response = authenticated_company_profile_client.post(
#             self.endpoint, payload, format="json"
#         )
#         assert response.status_code == status.HTTP_400_BAD_REQUEST

#     def test_retrieve_car_listings(
#         self, authenticated_company_profile_client, car_listing_factory
#     ):
#         car = car_listing_factory()
#         response = authenticated_company_profile_client.get(self.endpoint)
#         assert response.status_code == status.HTTP_200_OK
#         assert any(item["id"] == car.id for item in response.data)
