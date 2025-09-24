from django.contrib import admin

from apps.account.models import (
    Role,
    User,
    HotelProfile,
    CompanyProfile,
    IndividualOwnerProfile
)


admin.site.register(User)
admin.site.register(Role)
admin.site.register(CompanyProfile)
admin.site.register(IndividualOwnerProfile)
admin.site.register(HotelProfile)
