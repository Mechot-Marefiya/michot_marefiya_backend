from django.contrib import admin

from apps.account.models import CompanyProfile, HotelProfile, Role, User


admin.site.register(User)
admin.site.register(Role)
admin.site.register(CompanyProfile)
admin.site.register(HotelProfile)