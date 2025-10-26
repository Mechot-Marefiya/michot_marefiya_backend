from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from apps.account.models import (
    ListingImage,
    Role,
    User,
    HotelProfile,
    CompanyProfile,
    IndividualOwnerProfile,
)


class ListingImageInline(GenericTabularInline):
    model = ListingImage
    extra = 1  # how many empty slots to show
    fields = ("image", "alt_text", "is_primary")


@admin.register(HotelProfile)
class HotelProfileModelAdmin(admin.ModelAdmin):
    list_display = ["stars", "company"]
    inlines = [ListingImageInline]


admin.site.register(Role)
admin.site.register(CompanyProfile)
admin.site.register(IndividualOwnerProfile)
admin.site.register(User)
