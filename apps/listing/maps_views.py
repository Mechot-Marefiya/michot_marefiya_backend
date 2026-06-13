from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiTypes

from apps.listing.serializers import (
    AutocompleteResultSerializer,
    MapAutocompleteQuerySerializer,
    MapPlaceDetailRequestSerializer,
    PlaceDetailSerializer,
    ReverseGeocodeQuerySerializer,
    ReverseGeocodeSerializer,
)
from services.maps import GeocodingError, autocomplete_address, get_place_detail, reverse_geocode


@extend_schema(tags=["Maps"])
class MapsAutocompleteView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    @extend_schema(
        summary="Address autocomplete",
        parameters=[MapAutocompleteQuerySerializer],
        responses={200: AutocompleteResultSerializer(many=True), 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        serializer = MapAutocompleteQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            results = autocomplete_address(
                serializer.validated_data["input"],
                serializer.validated_data["session_token"],
            )
        except Exception:
            results = []
        return Response(AutocompleteResultSerializer(results, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["Maps"])
class MapsPlaceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Resolve Google place detail",
        request=MapPlaceDetailRequestSerializer,
        responses={200: PlaceDetailSerializer, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = MapPlaceDetailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            detail = get_place_detail(
                serializer.validated_data["place_id"],
                serializer.validated_data["session_token"],
            )
        except GeocodingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "lat": detail.get("lat"),
            "lng": detail.get("lng"),
            "formatted_address": detail.get("formatted_address"),
            "place_id": detail.get("place_id"),
            "components": detail.get("components") or {},
        }
        return Response(PlaceDetailSerializer(payload).data, status=status.HTTP_200_OK)


@extend_schema(tags=["Maps"])
class MapsReverseGeocodeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Reverse geocode coordinates",
        parameters=[ReverseGeocodeQuerySerializer],
        responses={200: ReverseGeocodeSerializer, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        serializer = ReverseGeocodeQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            detail = reverse_geocode(
                serializer.validated_data["lat"],
                serializer.validated_data["lng"],
            )
        except GeocodingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "formatted_address": detail.get("formatted_address"),
            "components": detail.get("components") or {},
        }
        return Response(ReverseGeocodeSerializer(payload).data, status=status.HTTP_200_OK)
