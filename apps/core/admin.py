from django.contrib import admin
from apps.core.models import Address, CurrencyRate, Facility


admin.site.register(Facility)
admin.site.register(Address)
admin.site.register(CurrencyRate)
