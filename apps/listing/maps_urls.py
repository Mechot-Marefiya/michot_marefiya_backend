from django.urls import path

from apps.listing.maps_views import (
    MapsAutocompleteView,
    MapsPlaceDetailView,
    MapsReverseGeocodeView,
)


urlpatterns = [
    path("autocomplete/", MapsAutocompleteView.as_view(), name="maps-autocomplete"),
    path("place-detail/", MapsPlaceDetailView.as_view(), name="maps-place-detail"),
    path("reverse-geocode/", MapsReverseGeocodeView.as_view(), name="maps-reverse-geocode"),
]
