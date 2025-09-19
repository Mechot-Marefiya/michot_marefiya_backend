from django.contrib import admin

from apps.account.models import CompanyProfile, Role, User


admin.site.register(User)
admin.site.register(Role)
admin.site.register(CompanyProfile)
