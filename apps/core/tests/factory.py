# import factory
# from apps.listing.models import RoomListing, Address


# class AddressFactory(factory.django.DjangoModelFactory):
#     class Meta:
#         model = Address

#     street_line1 = "wollo sefer"
#     country = "Ethiopia"
#     city = "Addis Ababa"
#     sub_city = "Bole"
#     state = "Addis Ababa"
#     postal_code = "1000"
#     latitude = "45.12"
#     longitude = "23.46"


# class RoomListingFactory(factory.django.DjangoModelFactory):
#     class Meta:
#         model = RoomListing

#     title = "Deluxe Room"
#     base_price = 2000
#     total_units = 10
#     address = factory.SubFactory(AddressFactory)
