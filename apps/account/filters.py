from django_filters import rest_framework as filters

from apps.account.models import HotelProfile


class HotelFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="company__category", lookup_expr="iexact")

    class Meta:
        model = HotelProfile
        fields = ["category"]
