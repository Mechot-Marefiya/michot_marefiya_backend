from io import BytesIO
import json
from PIL import Image
from django.urls import reverse
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.listing.models import Amenity


def create_test_image(name="test.png", ext="PNG", size=(100, 100), color=(255, 0, 0)):
    file = BytesIO()
    image = Image.new("RGB", size=size, color=color)
    image.save(file, ext)
    file.seek(0)
    return SimpleUploadedFile(name, file.read(), content_type=f"image/{ext.lower()}")


@pytest.mark.django_db
def test_hotel_listing_creation(authenticated_hotel_profile_client):
    images_list = []
    for i in range(1, 6):
        img_name = "img_" + str(i)
        img = create_test_image(f"{img_name}.png")
        images_list.append(img)

    address = json.dumps(
        {
            "street_line1": "wollo sefer",
            "country": "Ethiopia",
            "city": "Addis ababa",
            "sub_city": "Bole",
            "state": "Addis Ababa",
            "postal_code": "1000",
            "latitude": "45.12",
            "longitude": "23.46",
        }
    )

    amenities = [
        Amenity.objects.create(name=am).id for am in ["wifi", "pool", "balcony"]
    ]

    print(amenities)

    # json.dumps(amenities)

    data = {
        "images": images_list,
        "title": "Deluxe room",
        "description": "A very luxury room with 2 king bed",
        "price": "2000",
        "address": address,
        "capacity": 2,
        "service_type": "room",
        "amenities": amenities,
    }

    res = authenticated_hotel_profile_client.post(
        reverse("hotel_listings-list"), data, format="multipart"
    )

    print("RES", res.data)

    assert res.status_code == 201
    assert res.data["title"] == "Deluxe room"
