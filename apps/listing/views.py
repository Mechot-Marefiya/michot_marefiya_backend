
from django.utils.dateparse import parse_date
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from datetime import date
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import uuid
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status,filters
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework import serializers
from rest_framework.response import Response
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.throttling import ScopedRateThrottle
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from apps.account.serializers import HotelProfileResponseSerializer, ListingImageSerializer
from apps.core.serializers import FacilityResponseSerializer
from django.contrib.contenttypes.models import ContentType
from apps.favorites.services import get_favorite_object_ids
from apps.listing.docs.schema import search_schema
from apps.core.views import AbstractModelViewSet
from apps.core.utils import get_display_currency
from apps.notifications.services import NotificationService
from rest_framework import mixins, viewsets
from apps.listing.utils import ParseDatesAndQuantity
from apps.listing.filters import PropertyFilter, RoomFilter, BookingFilter,EventSpaceFilter,EventSpaceBookingFilter
from apps.core.pagination import StandardResultsSetPagination
from apps.account.permissions import (
    IsAuthenticatedOrReadOnly,
    IsCompanyOwner,
    IsPublicReadOnly,
    IsAdmin,
    IsListingOwner,
    IsBookingOwner,
    IsCarRentalOwner,
    CanModifyBooking,
    ORPermission,
    IsCompanyOrFrontDesk,
)
from apps.account.enums import RoleCode
from apps.listing.models import (
    Amenity,
    CarListing,
    CarSaleListing,
    ContactRevealRequest,
    GuestHouseProfile, GuestHouseRoom,
    PropertyListing,
    PropertyRentalBooking,
    PropertySaleListing,
    PropertyContactRevealRequest,
    RoomListing,
    Booking,StayAvailability,
    BookingItem,
    CarRentalItem,
    EventSpaceListing,
    CarAvailability,
    EventSpaceBooking,
    CarRental,
    GuestHouseBooking,
    GuestHouseBookingItem,
    AddonOffering,
    Season, SeasonalRate,
)
from apps.account.models import(CompanyProfile,IndividualOwnerProfile,HotelProfile)
from apps.listing.serializers import (
    DISCOVERY_LISTING_TYPE_CHOICES,
    AmenityResponseSSerializer,
    BookingPreviewSerializer,
    BookingSerializer,BookingResponseSerializer,
    CarListingResponseSerializer,
    CarListingSerializer,
    CarSaleContactSerializer,
    CarSaleListingResponseSerializer,
    CarSaleListingSerializer,
    ContactRevealRequestResponseSerializer,
    ContactRevealRequestSerializer,
    PropertyContactRevealRequestResponseSerializer,
    PropertyRentalBookingPreviewSerializer,
    PropertyRentalBookingResponseSerializer,
    PropertyRentalBookingSerializer,
    PropertySaleListingResponseSerializer,
    PropertySaleListingSerializer,
    BookingRatingSerializer,
    
    CarAvailabilityUpdateSerializer,
    EventSpaceBookingPreviewSerializer,
    GuestHouseBookingPreviewSerializer,
    GuestHouseBookingPreviewSerializer,
    GuestHouseProfileResponseSerializer, GuestHouseRoomResponseSerializer,
    GuestHouseProfileSerializer, GuestHouseRoomSerializer,
    PricePreviewResponseSerializer,
    PropertyListingResponseSerializer,
    PropertyListingSerializer,
    RoomListingResponseSerializer,
    EventSpaceListingSerializer,
    EventSpaceListingResponseSerializer,
    RoomListingSerializer,PartialCancelSerializer,
    SearchResultSerializer,StayAvailabilityUpdateSerializer,
    CarAvailabilitySerializer,
    AvailabilityCheckSerializer,
    CarSearchSerializer,
    CarRentalPreviewSerializer,
    CarRentalSerializer,
    CarRentalExtensionInitiateResponseSerializer,
    CarRentalExtensionInitiateSerializer,
    CarRentalExtensionPreviewResponseSerializer,
    CarRentalExtensionPreviewSerializer,
    CarRentalRescheduleSerializer,
    EventSpaceBookingResponseSerializer,
    EventSpaceBookingSerializer,
    GuestHouseBookingSerializer,
    AddonOfferingSerializer,
    AddonOfferingListSerializer,
    BookingLookupSerializer,
    GuestCarRentalHistoryAccessSerializer,
    GuestCarRentalLookupSerializer,
    GuestCarRentalCancellationSerializer,
    GuestCancellationSerializer,
    GuestBookingOtpRequestSerializer,
    GuestContactRevealOtpRequestSerializer,
    VerifyActionSerializer,
    SeasonSerializer, SeasonalRateSerializer,
    DiscoveryListingSerializer,
    ListingSearchResultSerializer,
    ProximityListingSerializer,
    MapPinSerializer,
    SearchSuggestionSerializer,
)
from apps.listing.services import (
    StayAvailabilityService, BookingService, CarAvailabilityService, 
    PriceService, GuestHouseAvailabilityService, EventSpaceAvailabilityService,
    PriceCalculationService, CarRentalService, PropertyRentalAvailabilityService,
    PropertyRentalBookingService, get_effective_platform_fee_rate, GuestBookingOtpError,
    GuestContactRevealOtpService, _phone_variants,
    verify_listing, unverify_listing,
)
from apps.payment.services import ChapaPaymentService, ContactRevealPaymentService
from apps.listing.exceptions import BookingConflict
from rest_framework.exceptions import PermissionDenied
from services.maps import build_map_pin, calculate_distance_km, find_listings_near, get_bounding_box

NO_REFUND_POLICY_CODE = "no_refunds"
NO_REFUND_POLICY_MESSAGE = "No refunds are available for any service payment on the platform."
BOOKING_CANCEL_NOTE = "Cancelling a booking does not create a refund for any completed service payment."

DISCOVERY_FILTER_CHOICES = [("all", "All"), *DISCOVERY_LISTING_TYPE_CHOICES]
DISCOVERY_LISTING_TYPE_ENUM = [choice for choice, _label in DISCOVERY_FILTER_CHOICES]
DISCOVERY_LISTING_TYPE_MAP = {
    "hotel": HotelProfile,
    "guesthouse": GuestHouseProfile,
    "event_space": EventSpaceListing,
    "property_rental": PropertyListing,
    "property_sales": PropertySaleListing,
    "car_rental": CarListing,
    "car_sales": CarSaleListing,
}
DISCOVERY_CACHE_TTL = getattr(settings, "PROXIMITY_CACHE_TTL", 300)
MAP_PINS_CACHE_TTL = getattr(settings, "MAP_PINS_CACHE_TTL", 180)


class NearbyListingsQuerySerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    radius_km = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        default=Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))),
        min_value=Decimal("0"),
    )
    listing_type = serializers.CharField(required=False, default="all")
    page = serializers.IntegerField(required=False, min_value=1)

    def validate_listing_type(self, value):
        allowed = {choice for choice, _ in DISCOVERY_FILTER_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("Invalid listing_type.")
        return value

    def validate(self, attrs):
        radius_km = Decimal(str(attrs.get("radius_km", getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))))
        max_radius = Decimal(str(getattr(settings, "MAX_PROXIMITY_RADIUS_KM", 100)))
        if radius_km > max_radius:
            raise serializers.ValidationError({"radius_km": f"radius_km cannot exceed {max_radius}."})
        return attrs


class BoundsListingsQuerySerializer(serializers.Serializer):
    north = serializers.DecimalField(max_digits=9, decimal_places=6)
    south = serializers.DecimalField(max_digits=9, decimal_places=6)
    east = serializers.DecimalField(max_digits=9, decimal_places=6)
    west = serializers.DecimalField(max_digits=9, decimal_places=6)
    listing_type = serializers.CharField(required=False, default="all")
    page = serializers.IntegerField(required=False, min_value=1)

    def validate_listing_type(self, value):
        allowed = {choice for choice, _ in DISCOVERY_FILTER_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("Invalid listing_type.")
        return value


class MapPinsQuerySerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    radius_km = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        default=Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))),
        min_value=Decimal("0"),
    )
    north = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    south = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    east = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    west = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    listing_type = serializers.CharField(required=False, default="all")

    def validate(self, attrs):
        has_lat_lng = attrs.get("lat") is not None and attrs.get("lng") is not None
        has_bounds = all(attrs.get(key) is not None for key in ("north", "south", "east", "west"))
        if not has_lat_lng and not has_bounds:
            raise serializers.ValidationError(
                "Provide either lat and lng with radius_km or north, south, east, and west."
            )
        allowed = {choice for choice, _ in DISCOVERY_FILTER_CHOICES}
        listing_type = attrs.get("listing_type", "all")
        if listing_type not in allowed:
            raise serializers.ValidationError({"listing_type": "Invalid listing_type."})
        return attrs


class FeedListingsQuerySerializer(serializers.Serializer):
    listing_type = serializers.CharField(required=False, default="all")
    page = serializers.IntegerField(required=False, min_value=1)

    def validate_listing_type(self, value):
        allowed = {choice for choice, _ in DISCOVERY_FILTER_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("Invalid listing_type.")
        return value


class ListingSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    radius_km = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        default=Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))),
        min_value=Decimal("0"),
    )
    sort_by = serializers.ChoiceField(
        choices=["distance", "price", "rating", "newest", "relevance"],
        required=False,
    )
    listing_type = serializers.CharField(required=False, default="all")
    page = serializers.IntegerField(required=False, min_value=1)

    def validate_listing_type(self, value):
        allowed = {choice for choice, _ in DISCOVERY_FILTER_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("Invalid listing_type.")
        return value

    def validate(self, attrs):
        has_lat = attrs.get("lat") is not None
        has_lng = attrs.get("lng") is not None
        if has_lat != has_lng:
            raise serializers.ValidationError({"detail": "Both lat and lng are required together."})

        radius_km = Decimal(str(attrs.get("radius_km", getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))))
        max_radius = Decimal(str(getattr(settings, "MAX_PROXIMITY_RADIUS_KM", 100)))
        if radius_km > max_radius:
            raise serializers.ValidationError({"radius_km": f"radius_km cannot exceed {max_radius}."})
        return attrs


class SearchSuggestionsQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=True, min_length=2)
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=10, default=5)
    listing_type = serializers.CharField(required=False, default="all")

    def validate_listing_type(self, value):
        allowed = {choice for choice, _ in DISCOVERY_FILTER_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("Invalid listing_type.")
        return value

    def validate(self, attrs):
        has_lat = attrs.get("lat") is not None
        has_lng = attrs.get("lng") is not None
        if has_lat != has_lng:
            raise serializers.ValidationError({"detail": "Both lat and lng are required together."})
        return attrs


def _rounded_cache_value(value) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP):.3f}"


def _discovery_querysets(listing_type: str):
    source_map = {
        "hotel": HotelProfile.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False).select_related("company", "address").prefetch_related("images", "room_listings"),
        "guesthouse": GuestHouseProfile.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False).select_related("company", "address").prefetch_related(
            "images",
            "rooms",
            "facility",
            "amenities",
        ),
        "event_space": EventSpaceListing.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False).select_related("hotel", "address").prefetch_related("images", "amenities"),
        "property_rental": PropertyListing.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False).select_related("company", "individual_owner", "address").prefetch_related("images"),
        "property_sales": PropertySaleListing.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False).select_related("company", "individual_owner", "address").prefetch_related("images"),
        "car_rental": CarListing.objects.filter(is_active=True, listing_type=CarListing.ListingTypeChoices.RENT, latitude__isnull=False, longitude__isnull=False).select_related("company", "individual_owner").prefetch_related("images"),
        "car_sales": CarSaleListing.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False).select_related("company", "individual_owner").prefetch_related("images"),
    }
    if listing_type == "all":
        return list(source_map.items())
    return [(listing_type, source_map[listing_type])]


def _search_querysets(listing_type: str):
    source_map = {
        "hotel": HotelProfile.objects.filter(is_active=True).select_related("company", "address").prefetch_related("images", "room_listings"),
        "guesthouse": GuestHouseProfile.objects.filter(is_active=True).select_related("company", "address").prefetch_related(
            "images",
            "rooms",
            "facility",
            "amenities",
        ),
        "event_space": EventSpaceListing.objects.filter(is_active=True).select_related("hotel", "address").prefetch_related("images", "amenities"),
        "property_rental": PropertyListing.objects.filter(is_active=True).select_related("company", "individual_owner", "address").prefetch_related("images"),
        "property_sales": PropertySaleListing.objects.filter(is_active=True).select_related("company", "individual_owner", "address").prefetch_related("images"),
        "car_rental": CarListing.objects.filter(is_active=True, listing_type=CarListing.ListingTypeChoices.RENT).select_related("company", "individual_owner").prefetch_related("images"),
        "car_sales": CarSaleListing.objects.filter(is_active=True).select_related("company", "individual_owner").prefetch_related("images"),
    }
    if listing_type == "all":
        return list(source_map.items())
    return [(listing_type, source_map[listing_type])]


def _listing_title(listing, listing_type: str) -> str:
    if listing_type == "hotel":
        return getattr(listing, "name", "") or getattr(listing, "title", "")
    if listing_type in {"car_rental", "car_sales"}:
        return getattr(listing, "title", "") or f"{getattr(listing, 'brand', '')} {getattr(listing, 'model', '')}".strip()
    return getattr(listing, "title", "") or getattr(listing, "name", "")


def _listing_thumbnail_url(listing) -> str | None:
    images = getattr(listing, "images", None)
    if images is not None:
        try:
            image = images.filter(is_primary=True).first() or images.first()
            if image and getattr(image, "image", None):
                return image.image.url
        except Exception:
            pass

    logo = getattr(listing, "logo", None)
    if logo:
        try:
            return logo.url
        except Exception:
            return None
    return None


def _listing_rating(listing, listing_type: str):
    if listing_type == "hotel":
        return getattr(listing, "stars", None)
    if listing_type == "guesthouse":
        return getattr(listing, "rating", None)
    return None


def _listing_price_preview(listing, listing_type: str):
    base_price = getattr(listing, "base_price", None)
    if base_price is not None:
        return Decimal(str(base_price))

    related_name = None
    if listing_type == "hotel":
        related_name = "room_listings"
    elif listing_type == "guesthouse":
        related_name = "rooms"

    if related_name:
        related_manager = getattr(listing, related_name, None)
        if related_manager is not None:
            try:
                prices = [
                    Decimal(str(item.base_price))
                    for item in related_manager.all()
                    if getattr(item, "base_price", None) is not None
                ]
                if prices:
                    return min(prices)
            except Exception:
                return None
    return None


def _normalize_discovery_listing(listing, listing_type: str, *, distance_km=None) -> dict:
    payload = {
        "id": listing.id,
        "listing_type": listing_type,
        "title": _listing_title(listing, listing_type),
        "description": getattr(listing, "description", "") or "",
        "latitude": getattr(listing, "latitude", None),
        "longitude": getattr(listing, "longitude", None),
        "formatted_address": getattr(listing, "formatted_address", None),
        "place_id": getattr(listing, "place_id", None),
        "price_preview": _listing_price_preview(listing, listing_type),
        "currency": getattr(listing, "currency", "ETB") or "ETB",
        "thumbnail_url": _listing_thumbnail_url(listing),
        "rating": _listing_rating(listing, listing_type),
        "is_verified": getattr(listing, "is_verified", False),
        "_created_at": getattr(listing, "created_at", timezone.now()),
    }
    if distance_km is not None:
        payload["distance_km"] = float(distance_km)
    return payload


def _search_text_fields(listing, listing_type: str, payload: dict) -> list[str]:
    address = getattr(listing, "address", None)
    values = [
        payload.get("title") or "",
        payload.get("description") or "",
        payload.get("formatted_address") or "",
        getattr(listing, "name", "") or "",
    ]

    if listing_type == "hotel":
        values.append(getattr(getattr(listing, "company", None), "name", "") or "")
    if listing_type in {"car_rental", "car_sales"}:
        values.append(getattr(listing, "brand", "") or "")
        values.append(getattr(listing, "model", "") or "")

    if address is not None:
        values.extend(
            [
                getattr(address, "city", "") or "",
                getattr(address, "sub_city", "") or "",
                getattr(address, "street_line1", "") or "",
                getattr(address, "state", "") or "",
            ]
        )
    return values


def _relevance_score(query: str, values: list[str]) -> int:
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return 0

    score = 0
    for raw_value in values:
        value = (raw_value or "").strip().lower()
        if not value:
            continue
        if value == normalized_query:
            score += 120
        elif value.startswith(normalized_query):
            score += 80
        elif normalized_query in value:
            score += 40
    return score


def _distance_sort_value(item: dict) -> float:
    distance = item.get("distance_km")
    return float(distance) if distance is not None else float("inf")


def _price_sort_value(item: dict) -> Decimal:
    price = item.get("price_preview")
    if price is None:
        return Decimal("Infinity")
    return Decimal(str(price))


def _rating_sort_value(item: dict) -> float:
    rating = item.get("rating")
    return float(rating) if rating is not None else -1.0


def _apply_search_sort(listings: list[dict], sort_by: str, *, has_location: bool) -> list[dict]:
    if sort_by == "price":
        return sorted(listings, key=_price_sort_value)
    if sort_by == "rating":
        return sorted(listings, key=lambda item: (_rating_sort_value(item), item.get("_relevance_score", 0)), reverse=True)
    if sort_by == "newest":
        return sorted(listings, key=lambda item: item.get("_created_at", timezone.now()), reverse=True)
    if sort_by == "relevance":
        return sorted(
            listings,
            key=lambda item: (item.get("_relevance_score", 0), item.get("_created_at", timezone.now())),
            reverse=True,
        )

    if has_location:
        return sorted(
            listings,
            key=lambda item: (_distance_sort_value(item), -item.get("_relevance_score", 0), item.get("_created_at", timezone.now())),
        )
    return sorted(
        listings,
        key=lambda item: (item.get("_relevance_score", 0), item.get("_created_at", timezone.now())),
        reverse=True,
    )


def _filter_search_payload(listing_type: str, query: str) -> list[dict]:
    normalized_query = (query or "").strip()
    listings = []

    for current_type, queryset in _search_querysets(listing_type):
        for listing in queryset:
            payload = _normalize_discovery_listing(listing, current_type, distance_km=None)
            values = _search_text_fields(listing, current_type, payload)
            payload["_relevance_score"] = _relevance_score(normalized_query, values)
            if normalized_query and payload["_relevance_score"] <= 0:
                continue
            listings.append(payload)
    return listings


def _apply_radius_to_payload(listings: list[dict], lat: Decimal, lng: Decimal, radius_km: Decimal) -> list[dict]:
    bounds = get_bounding_box(float(lat), float(lng), float(radius_km))
    filtered = []

    for item in listings:
        item_lat = item.get("latitude")
        item_lng = item.get("longitude")
        if item_lat is None or item_lng is None:
            continue
        if not (
            bounds["lat_min"] <= float(item_lat) <= bounds["lat_max"]
            and bounds["lng_min"] <= float(item_lng) <= bounds["lng_max"]
        ):
            continue

        distance_km = calculate_distance_km(float(lat), float(lng), float(item_lat), float(item_lng))
        if distance_km <= float(radius_km):
            next_item = dict(item)
            next_item["distance_km"] = distance_km
            filtered.append(next_item)

    return filtered


def _search_response_schema(name: str):
    return inline_serializer(
        name=name,
        fields={
            "count": serializers.IntegerField(),
            "total_pages": serializers.IntegerField(),
            "current_page": serializers.IntegerField(),
            "page_size": serializers.IntegerField(),
            "next": serializers.CharField(allow_null=True, required=False),
            "previous": serializers.CharField(allow_null=True, required=False),
            "results": ListingSearchResultSerializer(many=True),
            "search_center": inline_serializer(
                name=f"{name}Center",
                fields={
                    "lat": serializers.DecimalField(max_digits=9, decimal_places=6),
                    "lng": serializers.DecimalField(max_digits=9, decimal_places=6),
                },
            ),
            "applied_radius_km": serializers.FloatField(required=False),
        },
    )


def _attach_search_context(response: Response, *, lat=None, lng=None, radius_km=None) -> Response:
    if lat is not None and lng is not None:
        response.data["search_center"] = {"lat": lat, "lng": lng}
        response.data["applied_radius_km"] = float(radius_km)
    return response


def _cache_key_for_map_pins(query_params) -> str:
    normalized_items = sorted((key, str(value)) for key, value in query_params.items())
    key_payload = "&".join(f"{key}={value}" for key, value in normalized_items)
    return f"listing:pins:{hashlib.sha256(key_payload.encode('utf-8')).hexdigest()}"


def _build_discovery_payload(listing_type: str, *, lat=None, lng=None, radius_km=None, bounds=None, mode="standard"):
    listings = []
    for current_type, queryset in _discovery_querysets(listing_type):
        if mode == "nearby":
            near_items = find_listings_near(float(lat), float(lng), float(radius_km), queryset)
            if not near_items:
                continue
            ids = [uuid.UUID(item["id"]) for item in near_items]
            object_map = queryset.in_bulk(ids)
            for item in near_items:
                obj = object_map.get(uuid.UUID(item["id"]))
                if obj is None:
                    continue
                listings.append(
                    _normalize_discovery_listing(
                        obj,
                        current_type,
                        distance_km=item["distance_km"],
                    )
                )
            continue

        filtered_queryset = queryset
        if bounds is not None:
            filtered_queryset = filtered_queryset.filter(
                latitude__gte=bounds["south"],
                latitude__lte=bounds["north"],
                longitude__gte=bounds["west"],
                longitude__lte=bounds["east"],
            )
        else:
            filtered_queryset = filtered_queryset.filter(latitude__isnull=False, longitude__isnull=False)

        for listing in filtered_queryset:
            listings.append(_normalize_discovery_listing(listing, current_type))

    return listings


def _paginate_discovery_listings(request, listings, serializer_class):
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(listings, request)
    serializer = serializer_class(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)


def _top_pin_candidates(listings):
    return listings[:200]


def _build_feed_response(request, listing_type: str, page=None):
    user = request.user
    has_location = (
        user
        and user.is_authenticated
        and getattr(user, "location_permission_granted", False)
        and getattr(user, "last_known_lat", None) is not None
        and getattr(user, "last_known_lng", None) is not None
    )

    if has_location:
        cache_key = _normalized_discovery_cache_key(
            "listing:feed:proximity",
            {
                "user_id": user.id,
                "lat": _rounded_cache_value(user.last_known_lat),
                "lng": _rounded_cache_value(user.last_known_lng),
                "radius_km": Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))),
                "listing_type": listing_type,
                "page": page or request.query_params.get("page", 1),
            },
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        listings = _build_discovery_payload(
            listing_type,
            lat=user.last_known_lat,
            lng=user.last_known_lng,
            radius_km=Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))),
            mode="nearby",
        )
        listings.sort(key=lambda item: item["distance_km"])
        response = _paginate_discovery_listings(request, listings, ProximityListingSerializer)
        cache.set(cache_key, response.data, DISCOVERY_CACHE_TTL)
        return response

    cache_key = _normalized_discovery_cache_key(
        "listing:feed:standard",
        {
            "listing_type": listing_type,
            "page": page or request.query_params.get("page", 1),
        },
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    listings = _build_discovery_payload(listing_type, mode="standard")
    listings.sort(key=lambda item: item["_created_at"], reverse=True)
    response = _paginate_discovery_listings(request, listings, DiscoveryListingSerializer)
    cache.set(cache_key, response.data, MAP_PINS_CACHE_TTL)
    return response


def _with_booking_no_refund_policy(payload, *, cancellation_effect="booking_cancelled"):
    response = dict(payload)
    response.update(
        {
            "refund_supported": False,
            "refund_policy": NO_REFUND_POLICY_CODE,
            "refund_message": NO_REFUND_POLICY_MESSAGE,
            "pending_cancel_note": BOOKING_CANCEL_NOTE,
            "cancellation_effect": cancellation_effect,
        }
    )
    return response


def _request_guest_booking_otp(request, *, booking_type):
    serializer = GuestBookingOtpRequestSerializer(
        data=request.data,
        context={"booking_type": booking_type},
    )
    serializer.is_valid(raise_exception=True)
    challenge = serializer.save()
    return Response(
        {
            "success": True,
            "challenge_id": challenge.challenge_id,
            "challenge_token": challenge.challenge_id,
            "purpose": "guest_booking",
            "booking_type": challenge.booking_type,
            "expires_at": challenge.expires_at,
            "cooldown_seconds": int(getattr(settings, "OTP_COOLDOWN_SECONDS", 60)),
            "phone": challenge.phone,
        },
        status=status.HTTP_201_CREATED,
    )


def _assert_guest_rental_phone_matches(rental, guest_phone):
    rental_variants = set(_phone_variants(getattr(rental, "guest_phone", "")))
    request_variants = set(_phone_variants(guest_phone))
    if not rental_variants or not request_variants or rental_variants.isdisjoint(request_variants):
        raise PermissionDenied("Verified phone does not match this rental.")


def _request_guest_contact_reveal_otp(request, *, reveal_type):
    serializer = GuestContactRevealOtpRequestSerializer(
        data=request.data,
        context={"reveal_type": reveal_type},
    )
    serializer.is_valid(raise_exception=True)
    challenge = serializer.save()
    return Response(
        {
            "success": True,
            "challenge_id": challenge.challenge_id,
            "challenge_token": challenge.challenge_id,
            "purpose": "guest_contact_reveal",
            "reveal_type": challenge.booking_type,
            "expires_at": challenge.expires_at,
            "cooldown_seconds": int(getattr(settings, "OTP_COOLDOWN_SECONDS", 60)),
            "phone": challenge.phone,
        },
        status=status.HTTP_201_CREATED,
    )


def _verify_guest_contact_reveal_request(serializer, *, reveal_type):
    buyer_phone = serializer.validated_data.get("buyer_phone")
    guest_verification_token = serializer.validated_data.get("guest_verification_token")

    if not buyer_phone:
        raise GuestBookingOtpError("Guest contact reveal requires buyer_phone.")

    if guest_verification_token:
        GuestContactRevealOtpService.verify_guest_token(
            token=guest_verification_token,
            phone=buyer_phone,
        )
        return guest_verification_token

    otp_challenge_id = serializer.validated_data.get("otp_challenge_id")
    otp_code = serializer.validated_data.get("otp_code")
    if not otp_challenge_id or not otp_code:
        raise GuestBookingOtpError(
            "Guest contact reveal requires buyer_phone and either guest_verification_token or otp_challenge_id with otp_code."
        )

    return GuestContactRevealOtpService.verify_challenge(
        challenge_id=otp_challenge_id,
        code=otp_code,
        phone=buyer_phone,
        reveal_type=reveal_type,
    )


class SavedListingDeletionNotificationMixin:
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        notification_plan = NotificationService.prepare_saved_listing_deletion_notifications(
            instance,
            deleted_by=request.user,
        )
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == status.HTTP_204_NO_CONTENT:
            NotificationService.dispatch_saved_listing_deletion_notifications(notification_plan)
        return response


@extend_schema(tags=["Accommodations"])
class RoomListingViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    serializer_class = RoomListingSerializer
    queryset = RoomListing.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = RoomFilter


    def get_permissions(self):
        """
        - CREATE: Company users can create rooms for their hotels, admin can create all
        - READ: Public (all can read)
        - UPDATE/DELETE: Company can modify own rooms, admin can modify all
        """
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        elif self.action in ['list', 'retrieve', 'price_preview']:
            return [AllowAny()]
        else:
            return [IsListingOwner()]

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'hotel', 
            'address'
        ).prefetch_related(
            'images', 
            'amenities'
        )
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        # Admin sees all
        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset

        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(hotel__company=company)
            if individual_owner:
                pass
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    @extend_schema(
        summary="Price Preview for specific dates",
        description=(
            "**DEPRECATED**: This endpoint is deprecated and will be removed in a future version. "
            "Use the main room detail endpoint with check_in/check_out query parameters instead: "
            "`GET /rooms/{id}/?check_in=YYYY-MM-DD&check_out=YYYY-MM-DD`. "
            "The response will include a complete `price_quote` field with platform fee and currency conversion."
        ),
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=True, description="Arrival date"),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=True, description="Departure date"),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        deprecated=True
    )
    @action(detail=True, methods=['get'], url_path='price-preview')
    def price_preview(self, request, pk=None):
        """
        DEPRECATED: Use room detail endpoint with check_in/check_out params instead.
        This endpoint does NOT include the 5% platform fee and lacks currency conversion.
        """
        room = self.get_object()
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        if not check_in or not check_out:
            return Response({"detail": "check_in and check_out are required"}, status=400)
        try:
            check_in_date = parse_date(check_in)
            check_out_date = parse_date(check_out)
        except Exception:
            return Response({"detail": "invalid date format"}, status=400)
        if check_in_date >= check_out_date:
            return Response({"detail": "check_out must be after check_in"}, status=400)

        lines = PriceService.resolve_price_details_batch(room, check_in_date, check_out_date)
        total = sum(Decimal(str(l['price_per_unit'])) for l in lines)
        has_discount = any(l.get('is_discounted') for l in lines)

        response = Response({
            'lines': lines,
            'total': f"{total:.2f}",
            'has_discount': bool(has_discount),
            'warning': (
                'DEPRECATED: This endpoint does not include platform fees. '
                'Use GET /rooms/{id}/?check_in=X&check_out=Y for accurate pricing.'
            )
        })
        
        response['Warning'] = (
            '299 - "Deprecated: Use ?check_in&check_out on main room endpoint instead. '
            'This endpoint will be removed in v2.0"'
        )
        return response

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: RoomListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        room = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            room,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = RoomListingResponseSerializer(room, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: RoomListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        room = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(room, request.user)
        serializer = RoomListingResponseSerializer(room, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_serializer_context(self):
        context = super().get_serializer_context()

        request = self.request

        # Support both `check_in_date`/`check_out_date` (used by hotel availability)
        # and `check_in`/`check_out` (used elsewhere)
        check_in = request.query_params.get("check_in_date") or request.query_params.get("check_in")
        check_out = request.query_params.get("check_out_date") or request.query_params.get("check_out")
        hotel_id = request.query_params.get("hotel")

        if check_in and check_out and hotel_id:
            try:
                check_in_date = parse_date(check_in)
                check_out_date = parse_date(check_out)
            except Exception:
                check_in_date = None
                check_out_date = None

            if check_in_date and check_out_date and check_out_date > check_in_date:
                try:
                    hotel = get_object_or_404(HotelProfile, id=hotel_id)
                    _, availability_qs = StayAvailabilityService.get_available_rooms(
                        hotel, check_in_date, check_out_date
                    )
                    # availability_qs is a queryset of dicts with 'room' and 'min_available'
                    availability_map = {row['room']: row['min_available'] for row in availability_qs}
                    context['availability_map'] = availability_map
                except Exception:
                    # On any error, do not attach availability to avoid breaking existing responses
                    pass

        context["request"] = request
        context["display_currency"] = get_display_currency(request)

        return context

    @extend_schema(
        summary="Retrieve room details with accurate pricing",
        description="""
        Returns detailed information about a room listing. 
        Highly recommended: Provide `check_in` and `check_out` query parameters to receive a 
        comprehensive `price_quote` object including platform fees and daily breakdowns.
        """,
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=False, description="Arrival date (YYYY-MM-DD)"),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=False, description="Departure date (YYYY-MM-DD)"),
        ]
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = RoomListingResponseSerializer(instance, context=self.get_serializer_context())
        data = serializer.data

        quote = data.get('price_quote')
        if quote:
            prices = [Decimal(str(line['price_per_unit'])) for line in quote['breakdown']]
            if prices:
                preview_min = min(prices)
                data['preview_min_price'] = f"{preview_min:.2f}"
                data['preview_total'] = str(quote['items_subtotal'])
                data['preview_has_discount'] = quote['has_discount']
                data['display_price'] = f"{preview_min:.2f}" if quote['has_discount'] else f"{Decimal(str(data.get('base_price'))):.2f}"
        else:
            data['display_price'] = f"{Decimal(str(data.get('base_price'))):.2f}"

        return Response(data)

    @extend_schema(
        summary="List rooms with optional date-based pricing",
        description="""
        Returns a list of room listings. Provides `price_quote` and seasonal details 
        if `check_in` and `check_out` parameters are supplied.
        """,
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=False, description="Arrival date (YYYY-MM-DD)"),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=False, description="Departure date (YYYY-MM-DD)"),
            OpenApiParameter("hotel", OpenApiTypes.STR, required=False, description="Filter rooms by Hotel UUID"),
        ]
    )
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        rooms = page if page is not None else list(qs)

        serialized = []
        for room in rooms:
            serializer = RoomListingResponseSerializer(room, context=self.get_serializer_context())
            data = serializer.data
            
            quote = data.get('price_quote')
            if quote:
                prices = [Decimal(str(line['price_per_unit'])) for line in quote['breakdown']]
                if prices:
                    preview_min = min(prices)
                    data['preview_min_price'] = f"{preview_min:.2f}"
                    data['preview_total'] = str(quote['items_subtotal'])
                    data['preview_has_discount'] = quote['has_discount']
                    data['display_price'] = f"{preview_min:.2f}" if quote['has_discount'] else f"{Decimal(str(data.get('base_price'))):.2f}"
            else:
                data['display_price'] = f"{Decimal(str(data.get('base_price'))):.2f}"

            serialized.append(data)

        if page is not None:
            return self.get_paginated_response(serialized)
        return Response(serialized)

    @action(detail=False, methods=['get'], url_path='availability-matrix')
    def availability_matrix(self, request):
        workspace_id = request.query_params.get("workspace")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not workspace_id or not start_date_str or not end_date_str:
             return Response({"detail": "workspace, start_date, end_date required"}, status=400)
             
        try:
             start_date = date.fromisoformat(start_date_str)
             end_date = date.fromisoformat(end_date_str)
        except:
             return Response({"detail": "Invalid date format"}, status=400)
             
        room_qs = RoomListing.objects.filter(
            Q(hotel__id=workspace_id) | Q(hotel__company__id=workspace_id)
        ).select_related('hotel')
        
        if not room_qs.exists():
             return Response([])

        hotel_ids = room_qs.values_list('hotel_id', flat=True).distinct()
        
        full_matrix = {}
        for h_id in hotel_ids:
             matrix = StayAvailabilityService.get_availability_matrix(h_id, start_date, end_date)
             full_matrix.update(matrix)
             
        date_cursor = start_date
        dates = []
        while date_cursor <= end_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)

        results = []
        for room in room_qs:
            r_id = str(room.id)
            avail_map = full_matrix.get(r_id, {})
            
            availability_list = []
            for d in dates:
                d_str = d.isoformat()
                available_count = avail_map.get(d_str, room.total_units) 
                
                status_val = 'available'
                if available_count == 0:
                    status_val = 'full'
                elif available_count < room.total_units:
                    status_val = 'partial'
                
                availability_list.append({
                    "date": d_str,
                    "available": available_count,
                    "status": status_val
                })
            
            results.append({
                "room_id": r_id,
                "room_name": room.title,
                "total_units": room.total_units,
                "availability": availability_list
            })
            
        return Response(results)



@extend_schema(tags=["Guest House Rooms"])
class GuestHouseRoomViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    serializer_class = GuestHouseRoomSerializer
    queryset = GuestHouseRoom.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["guest_house", "total_units", "number_of_guests"]

    def get_serializer_class(self):
        if self.action in ["list", "retrieve", "price_preview"]:
            return GuestHouseRoomResponseSerializer
        return GuestHouseRoomSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        elif self.action in ['list', 'retrieve', 'price_preview']:
            return [AllowAny()]
        else:
            return [IsListingOwner()]

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "guest_house", "guest_house__address"
        ).prefetch_related(
            "images", "amenities"
        )
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset

        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

            q = Q()
            if company:
                q |= Q(guest_house__company=company)
            if individual_owner:
                q |= Q(guest_house__individual_owner=individual_owner)
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True, guest_house__is_active=True).order_by("-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        request = self.request
        context["request"] = request
        context["display_currency"] = get_display_currency(request)
        
        check_in = request.query_params.get("check_in")
        check_out = request.query_params.get("check_out")
        
        if check_in and check_out:
             try:
                check_in_date = parse_date(check_in)
                check_out_date = parse_date(check_out)
                pass 
             except Exception:
                 pass
        return context

    @extend_schema(
        summary="Retrieve room details with accurate pricing",
        parameters=[
            OpenApiParameter("check_in", OpenApiTypes.DATE, required=False),
            OpenApiParameter("check_out", OpenApiTypes.DATE, required=False),
        ]
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = GuestHouseRoomResponseSerializer(instance, context=self.get_serializer_context())
        return Response(serializer.data)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: GuestHouseRoomResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        room = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            room,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = GuestHouseRoomResponseSerializer(room, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: GuestHouseRoomResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        room = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(room, request.user)
        serializer = GuestHouseRoomResponseSerializer(room, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='availability-matrix')
    def availability_matrix(self, request):
        workspace_id = request.query_params.get("workspace")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not workspace_id or not start_date_str or not end_date_str:
             return Response({"detail": "workspace, start_date, end_date required"}, status=400)
             
        try:
             start_date = date.fromisoformat(start_date_str)
             end_date = date.fromisoformat(end_date_str)
        except:
             return Response({"detail": "Invalid date format"}, status=400)
             
        room_qs = GuestHouseRoom.objects.filter(
            Q(guest_house__id=workspace_id) | 
            Q(guest_house__company__id=workspace_id) | 
            Q(guest_house__individual_owner__id=workspace_id)
        )
        
        if not room_qs.exists():
             return Response([])
             
        gh_ids = room_qs.values_list('guest_house_id', flat=True).distinct()
        
        full_matrix = {}
        for gh_id in gh_ids:
             matrix = GuestHouseAvailabilityService.get_availability_matrix(gh_id, start_date, end_date)
             full_matrix.update(matrix)
             
        date_cursor = start_date
        dates = []
        while date_cursor <= end_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)

        results = []
        for room in room_qs:
            r_id = str(room.id)
            avail_map = full_matrix.get(r_id, {})
            
            availability_list = []
            for d in dates:
                d_str = d.isoformat()
                available_count = avail_map.get(d_str, room.total_units)
                
                status_val = 'available'
                if available_count == 0:
                     status_val = 'full'
                elif available_count < room.total_units:
                     status_val = 'partial'
                     
                availability_list.append({
                    "date": d_str,
                    "available": available_count,
                    "status": status_val
                })
            results.append({
                "room_id": r_id,
                "room_name": room.title,
                "total_units": room.total_units,
                "availability": availability_list
            })
            
        return Response(results)


@extend_schema(tags=["Accommodations"])
class GuestHouseProfileViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    serializer_class = GuestHouseProfileSerializer
    queryset = GuestHouseProfile.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['title', 'description', 'address__city', 'address__sub_city']
    throttle_scope = None

    def get_permissions(self):
        """
        - CREATE: Company users can create guest houses, admin can create all
        - READ: Public (all can read)
        - UPDATE/DELETE: Company can modify own guest houses, admin can modify all
        """
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve', 'check_availability']:
            return [AllowAny()]
        elif self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        else:
            return [IsListingOwner()]

    def get_serializer_class(self):
        if self.action in ["list", "retrieve", "check_availability"]:
            return GuestHouseProfileResponseSerializer
        return GuestHouseProfileSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'company',
            'individual_owner'
        ).prefetch_related(
            'images',
            'amenities',
            'facility',
            'rooms'
        )
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset

        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(company=company)
            if individual_owner:
                q |= Q(individual_owner=individual_owner)
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        
        # resolve favorites
        try:
            ct = ContentType.objects.get(app_label="listing", model="guesthouseprofile")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(self.request.user, ct) if ct is not None else set()

        context["favorite_object_ids"] = fav_ids
        context["display_currency"] = get_display_currency(self.request)
        
        return context

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
            parameters=[
                OpenApiParameter("check_in", OpenApiTypes.DATE, required=True),
                OpenApiParameter("check_out", OpenApiTypes.DATE, required=True),
                OpenApiParameter("units", OpenApiTypes.INT, required=False),
                OpenApiParameter("city", OpenApiTypes.STR, required=False),
                OpenApiParameter("country", OpenApiTypes.STR, required=False),
                OpenApiParameter("region", OpenApiTypes.STR, required=False),
                OpenApiParameter("sub_city", OpenApiTypes.STR, required=False),
                OpenApiParameter("guesthouse_id", OpenApiTypes.UUID, required=False),
            ],
            responses=GuestHouseProfileResponseSerializer(many=True)
        )
    @action(
        detail=False, 
        methods=["get"], 
        url_path="check-availability",
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def check_availability(self, request):
            """
            Check availability across all guesthouses or a specific one.
            Returns PROFILES that have at least one room type meeting criteria.
            """
            try:
                check_in = datetime.strptime(request.query_params.get("check_in"), "%Y-%m-%d").date()
                check_out = datetime.strptime(request.query_params.get("check_out"), "%Y-%m-%d").date()
            except:
                return Response({"error": "Invalid check_in/check_out format (YYYY-MM-DD required)."},
                                status=status.HTTP_400_BAD_REQUEST)

            if check_in >= check_out:
                return Response({"error": "check_out must be after check_in."},
                                status=status.HTTP_400_BAD_REQUEST)

            units = int(request.query_params.get("units", 1))

            address_filters = {
                "city": request.query_params.get("city"),
                "country": request.query_params.get("country"),
                "region": request.query_params.get("region"),
                "sub_city": request.query_params.get("sub_city"),
            }

            guesthouse_id = request.query_params.get("guesthouse_id")

            if guesthouse_id:
                profile = GuestHouseProfile.objects.filter(id=guesthouse_id, is_active=True).first()
                if not profile:
                    return Response({"error": "Guest house not found."}, status=404)

                qs, meta = GuestHouseAvailabilityService.get_available_listings(
                    check_in, check_out, units, address_filters
                )
                qs = qs.filter(id=guesthouse_id)
            else:
                qs, meta = GuestHouseAvailabilityService.get_available_listings(
                    check_in, check_out, units, address_filters
                )
            
            context = self.get_serializer_context()
            availability_map = {row["guest_house_room"]: row["min_available"] for row in meta}
            context["availability_map"] = availability_map
            
            serializer = GuestHouseProfileResponseSerializer(qs, many=True, context=context)
            return Response({
                "count": qs.count(),
                "results": serializer.data
            })

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: GuestHouseProfileResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        guest_house = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            guest_house,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = GuestHouseProfileResponseSerializer(guest_house, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: GuestHouseProfileResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        guest_house = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(guest_house, request.user)
        serializer = GuestHouseProfileResponseSerializer(guest_house, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

@extend_schema(tags=["Accommodations"])
class GuestHouseBookingViewSet(AbstractModelViewSet):
    """
    ViewSet for GuestHouse Bookings with full CRUD operations.
    """
    serializer_class = GuestHouseBookingSerializer
    queryset = GuestHouseBooking.objects.all()
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = {
        'status': ['exact'],
        'start_date': ['gte', 'lte'],
        'end_date': ['gte', 'lte']
    }
    ordering_fields = ['start_date', 'end_date', 'total_price', 'created_at']
    ordering = ['-created_at']
    search_fields = [
        'booking_reference',
        'renter__email',
        'renter__first_name',
        'renter__last_name',
        'guest_email',
        'guest_first_name',
        'guest_last_name',
        'guest_phone'
    ]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        context["request"] = self.request
        return context

    def get_permissions(self):
        """
        - CREATE: Authenticated users can create bookings
        - READ: Authenticated users (see own + companies see their guesthouses)
        - UPDATE/DELETE: Booking owner or guesthouse owner
        """
        if self.action in ['create', 'lookup', 'price_preview', 'guest_otp']:
            return [AllowAny()]
        elif self.action in ['list', 'retrieve', 'my_bookings']:
            return [IsAuthenticated()]
        else:
            # For update/delete/cancel, require ownership
            from apps.account.permissions import IsGuestHouseBookingOwner
            return [IsGuestHouseBookingOwner()]

    def get_throttles(self):
        if self.action in ['create', 'guest_otp']:
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()
    
    def get_queryset(self):
        """
        Filter queryset based on user role:
        - Admin: sees all bookings
        - Company (mode='host'): sees bookings for their guesthouses
        - User/Default: sees only own bookings as a guest
        """
        user = self.request.user
        if not user.is_authenticated:
            return GuestHouseBooking.objects.none()
            
        queryset = super().get_queryset()
        
        # Admin sees all
        if user.is_superuser or (
            hasattr(user, 'role') and 
            user.role and 
            user.role.code == RoleCode.ADMIN.value
        ):
            return queryset

        # Check for mode parameter
        mode = self.request.query_params.get('mode')

        # CASE 1: Host Mode (Extranet)
        if mode == 'host':
            # Company sees bookings for their guesthouses
            if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
                # Filter by company user
                return queryset.filter(items__room__guest_house__company__user=user).distinct()
            # Individual owner logic could go here if needed, but for now enforcing company/role check
             # If individual owner logic is needed:
            if hasattr(user, 'individual_owner') and user.individual_owner:
                 return queryset.filter(items__room__guest_house__individual_owner=user.individual_owner).distinct()

            return queryset.none()
        
        
        # Check for mode parameter (Feature branch logic)
        mode = self.request.query_params.get('mode')
        if mode == 'host':
            if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
                return queryset.filter(items__room__guest_house__company__user=user).distinct()
            if hasattr(user, 'individual_owner') and user.individual_owner:
                 return queryset.filter(items__room__guest_house__individual_owner=user.individual_owner).distinct()
            return queryset.none()

        # Base filter: User sees own bookings as renter
        query = Q(renter=user)
        
        if self.request.query_params.get('as_guest') == 'true':
            return queryset.filter(query).distinct()
        
        # Company sees bookings for their guesthouses
        if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
            query |= Q(items__room__guest_house__company__user=user)
        
        return queryset.filter(query).distinct()

    @extend_schema(
        summary="Lookup guest house booking status (Guest)",
        description="Retrieve booking details using reference and guest email. No login required.",
        parameters=[
            OpenApiParameter("reference", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("email", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: GuestHouseBookingSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = BookingLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        reference = serializer.validated_data['reference']
        email = serializer.validated_data['email']
        
        booking = get_object_or_404(
            GuestHouseBooking.objects.prefetch_related("items", "items__room"),
            booking_reference=reference,
            guest_email=email
        )
        
        response_serializer = GuestHouseBookingSerializer(booking, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @action(detail=False, methods=['get'], url_path='workspace-bookings')
    def workspace_bookings(self, request):
        user = request.user
        
        if not user.workspace:
             return Response(
                {"detail": "No workspace assigned to this user."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        workspace = user.workspace
        queryset = self.get_queryset()
        
        if hasattr(workspace, 'is_guesthouse') or workspace.__class__.__name__ == 'GuestHouseProfile':
            queryset = queryset.filter(items__room__guest_house=workspace).distinct()
        else:
             return Response([])

        return Response(GuestHouseBookingPreviewSerializer(queryset, many=True, context=self.get_serializer_context()).data)

    @extend_schema(request=GuestHouseBookingSerializer, responses=GuestHouseBookingSerializer)
    @action(detail=False, methods=['post'], url_path='walk-in', permission_classes=[IsAuthenticated])
    def walk_in(self, request, *args, **kwargs):
        """
        Create a walk-in booking. 
        Passes is_walk_in=True via context to trigger staff privileges check.
        Requires authentication.
        """
        # Default currency to ETB for walk-ins if not specified
        data = request.data.copy()
        if 'payment_currency' not in data:
            data['payment_currency'] = 'ETB'
        
        # Pass is_walk_in via context, not data
        context = {**self.get_serializer_context(), 'is_walk_in': True}
        serializer = self.get_serializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @extend_schema(
        summary="Request guesthouse booking phone OTP",
        description="Issue a phone OTP challenge before creating a guesthouse booking as a guest.",
        request=GuestBookingOtpRequestSerializer,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="guest-otp/request", permission_classes=[AllowAny])
    def guest_otp(self, request):
        return _request_guest_booking_otp(request, booking_type="guesthouse")

    @extend_schema(
        summary="Create a new guesthouse booking (supports guest checkout)",
        description="""
        Initiates a booking for one or more rooms in a guest house.
        - Supports both authenticated users and guest checkout.
        - Required guest fields: `guest_email`, `guest_phone`, `guest_first_name`, `guest_last_name`.
        - Guest checkout now requires a prior `guest-otp/request/` call and both `otp_challenge_id` and `otp_code` on create.
        - `terms_accepted` and `terms_version` are mandatory.
        - Returns a pending booking with a `booking_reference` (prefix 'G').
        """,
        request=GuestHouseBookingSerializer,
        responses={201: GuestHouseBookingSerializer}
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a new booking.
        Serializer handles validation, availability checks, and T&C snapshot.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Serializer.create() calls GuestHouseBookingService.create_booking()
        booking = serializer.save()

        return Response(
            self.get_serializer(booking).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Cancel a guesthouse booking",
        description=(
            "Cancel a pending or confirmed booking and restore availability. "
            "Booking cancellation does not create a refund because the platform does not support refunds."
        ),
        responses={200: GuestHouseBookingSerializer}
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a booking and restore availability.
        """
        booking = self.get_object()
        
        # Use service to cancel
        from apps.listing.services import GuestHouseBookingService
        try:
            GuestHouseBookingService.cancel_booking(booking)
        except Exception as e:
            return Response(
                _with_booking_no_refund_policy(
                    {"error": str(e)},
                    cancellation_effect="booking_not_cancelled",
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            _with_booking_no_refund_policy(self.get_serializer(booking).data)
        )
    
    @extend_schema(
        summary="Get my guesthouse bookings",
        description="Retrieve all bookings made by the authenticated user.",
        responses={200: GuestHouseBookingSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def my_bookings(self, request):
        """
        Get all bookings for the authenticated user.
        """
        bookings = GuestHouseBooking.objects.filter(renter=request.user).order_by('-created_at')
        
        page = self.paginate_queryset(bookings)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(bookings, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Price Preview for guesthouse selection",
        description="Get a consolidated price quote for a selection of guesthouses/rooms before booking.",
        request=GuestHouseBookingPreviewSerializer,
        parameters=[
            OpenApiParameter(
                name="display_currency",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional: Request price preview in a specific currency (e.g., USD) using triangulation."
            )
        ],
        responses={
            200: PricePreviewResponseSerializer,
            400: OpenApiTypes.OBJECT
        }
    )
    @action(
        detail=False, 
        methods=['post'], 
        url_path='price-preview',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def price_preview(self, request):
        serializer = GuestHouseBookingPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        start_date = data['start_date']
        end_date = data['end_date']
        items = data['items']
        preview_phone = data.get('guest_phone') or (request.user.phone if request.user.is_authenticated else None)
        
        # Validate availability (lock=False for previews)
        room_infos = [
            {"guesthouse_room": item["room"], "quantity": item["units_booked"]}
            for item in items
        ]
        try:
            GuestHouseAvailabilityService.validate_availability(room_infos, start_date, end_date, lock=False)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
            
        # Calculate totals
        nights = (end_date - start_date).days
        total_items = []
        item_subtotals = []
        
        currencies = {item["room"].currency for item in items}
        if len(currencies) > 1:
            return Response({"detail": "All selected items must have the same currency."}, status=400)
        currency = list(currencies)[0] if currencies else "ETB"
        display_currency = get_display_currency(request)
        
        for item in items:
            room = item["room"]
            units = item["units_booked"]
            
            price_details = PriceService.resolve_price_details_batch(room, start_date, end_date)
            item_base_total = sum(Decimal(str(d['price_per_unit'])) for d in price_details) * units
            
            item_subtotals.append(item_base_total)
            
            total_items.append({
                "id": str(room.id),
                "title": room.title,
                "units": units,
                "price_per_unit": f"{room.base_price:.2f}",
                "subtotal": f"{item_base_total:.2f}",
                "breakdown": price_details
            })
            
        return Response({
            "nights": nights,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(
                item_subtotals,
                currency,
                display_currency,
                items=total_items,
                fee_rate=get_effective_platform_fee_rate(phone=preview_phone),
            )
        })

# Car Listing ViewSet
@extend_schema(tags=["Car Rentals"])
class CarListingViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    serializer_class = CarListingSerializer
    queryset = CarListing.objects.all()
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['brand', 'car_class', 'fuel_type', 'transmission', 'condition', 'listing_type', 'is_active']
    search_fields = ['title', 'description', 'brand', 'model']
    ordering_fields = ['base_price', 'year', 'mileage', 'created_at']
    ordering = ['-created_at']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        # 'list' is the action for GET /api/v1/listing/cars/
        elif self.action in ['list', 'retrieve', 'check_availability', 'available_for_rent', 'search']:
            return [AllowAny()]
        elif self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        elif self.action == 'my_listings':
            return [IsAuthenticated()]
        else:
            return [IsListingOwner()]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CarListingSerializer
        return CarListingResponseSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'company',
            'individual_owner'
        ).prefetch_related(
            'images',
            'daily_availabilities'
        )
        user = self.request.user

        # Admin sees all
        if user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) and user.role.code == RoleCode.ADMIN.value):
            pass
        # Company sees all
        elif user.is_authenticated and getattr(user, 'role', None) and user.role.code == RoleCode.COMPANY.value:
            pass
        # Others see only active
        else:
            queryset = queryset.filter(is_active=True)

        # --- Apply extra filters from query params ---
        min_year = self.request.query_params.get('min_year')
        max_year = self.request.query_params.get('max_year')
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        max_mileage = self.request.query_params.get('max_mileage')

        if min_year: queryset = queryset.filter(year__gte=int(min_year))
        if max_year: queryset = queryset.filter(year__lte=int(max_year))
        if min_price: queryset = queryset.filter(base_price__gte=float(min_price))
        if max_price: queryset = queryset.filter(base_price__lte=float(max_price))
        if max_mileage: queryset = queryset.filter(mileage__lte=int(max_mileage))

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        if not serializer.validated_data.get('company') and not serializer.validated_data.get('individual_owner'):
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            if individual_owner:
                serializer.save(individual_owner=individual_owner)
                return

            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            if company:
                if company.status != CompanyProfile.StatusChoice.APPROVED:
                    raise PermissionDenied("Company profile is not approved.")
                serializer.save(company=company)
                return

            serializer.save()
        else:
            serializer.save()
    @extend_schema(responses=CarListingResponseSerializer)
    def list(self, request):
        """
        Handles GET /api/v1/listing/cars/ - the default endpoint.
        Applies queryset logic (active/all) and then filters/paginates.
        """
        queryset = self.get_queryset()
        
        # Apply DRF's default filtering/searching/ordering (from filter_backends)
        queryset = self.filter_queryset(queryset)
        
        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        # No pagination
        serializer = CarListingResponseSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: CarListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        car_listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            car_listing,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = CarListingResponseSerializer(car_listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: CarListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        car_listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(car_listing, request.user)
        serializer = CarListingResponseSerializer(car_listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    # --- Availability Actions ---
    @extend_schema(request=AvailabilityCheckSerializer)
    @action(
        detail=True, 
        methods=['post'], 
        serializer_class=AvailabilityCheckSerializer,
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def check_availability(self, request, pk=None):
        car_listing = self.get_object()
        serializer = AvailabilityCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        availability = CarAvailabilityService.validate_availability(
            car_listing,
            serializer.validated_data['quantity'],
            serializer.validated_data['start_date'],
            serializer.validated_data['end_date'],
        )
        
        return Response(availability)

    @extend_schema(parameters=[
        OpenApiParameter('start_date', OpenApiTypes.DATE),
        OpenApiParameter('end_date', OpenApiTypes.DATE),
        OpenApiParameter('brand', OpenApiTypes.STR),
        OpenApiParameter('car_class', OpenApiTypes.STR),
        OpenApiParameter('max_daily_price', OpenApiTypes.FLOAT),
    ])
    @action(
        detail=False, 
        methods=['get'], 
        serializer_class=CarSearchSerializer,
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def available_for_rent(self, request):
        serializer = CarSearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        cars = CarAvailabilityService.search_available_cars(
            start_date=serializer.validated_data['start_date'],
            end_date=serializer.validated_data['end_date'],
            brand=serializer.validated_data.get('brand'),
            car_class=serializer.validated_data.get('car_class')
        )

        # Filter max_daily_price
        max_price = serializer.validated_data.get('max_daily_price')
        if max_price:
            cars = [c for c in cars if c.base_price <= max_price]

        page = self.paginate_queryset(cars)
        if page is not None:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = CarListingResponseSerializer(cars, many=True, context={'request': request})
        return Response({'count': len(cars), 'results': serializer.data})

    @extend_schema(responses=CarListingResponseSerializer)
    @action(detail=False, methods=['get'])
    def my_listings(self, request):
        user = request.user
        if user.is_authenticated:
            if user.is_superuser or getattr(user, 'role', None) and user.role.code == RoleCode.ADMIN.value:
                # The get_queryset method handles filtering by role/active status already
                queryset = self.get_queryset() 
            else:
                # Fetch only listings belonging to the user's company/profile
                # NOTE: Depending on your model relationships, you might need to adjust this filter
                queryset = CarListing.objects.filter(company__user=user).distinct()
        else:
            return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        page = self.paginate_queryset(queryset)
        if page:
            serializer = CarListingResponseSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = CarListingResponseSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


@extend_schema(tags=["Car Sales"])
class CarSaleListingViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    queryset = CarSaleListing.objects.all()
    serializer_class = CarSaleListingSerializer
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["brand", "car_class", "fuel_type", "transmission", "condition", "is_active"]
    search_fields = ["title", "description", "brand", "model"]
    ordering_fields = ["base_price", "year", "mileage", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        if self.action in ["request_contact", "contact", "guest_otp"]:
            return [AllowAny()]
        if self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        return [IsListingOwner()]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return CarSaleListingSerializer
        return CarSaleListingResponseSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "company",
            "individual_owner",
        ).prefetch_related("images", "contact_reveal_requests")
        user = self.request.user

        if user.is_authenticated and (
            user.is_superuser or getattr(user, "role", None) and user.role.code == RoleCode.ADMIN.value
        ):
            return queryset

        managed_only = self.request.query_params.get("managed") == "true"
        if managed_only and user.is_authenticated:
            company = getattr(user, "company", None) or getattr(user, "profile", None)
            individual_owner = getattr(user, "individual_owner", None) or getattr(user, "individual_owner_profile", None)
            q = Q()
            if company:
                q |= Q(company=company)
            if individual_owner:
                q |= Q(individual_owner=individual_owner)
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        if not serializer.validated_data.get("company") and not serializer.validated_data.get("individual_owner"):
            individual_owner = getattr(user, "individual_owner", None) or getattr(user, "individual_owner_profile", None)
            if individual_owner:
                serializer.save(individual_owner=individual_owner)
                return

            company = getattr(user, "company", None) or getattr(user, "profile", None)
            if company:
                if company.status != CompanyProfile.StatusChoice.APPROVED:
                    raise PermissionDenied("Company profile is not approved.")
                serializer.save(company=company)
                return

        serializer.save()

    def _is_listing_owner(self, listing):
        user = self.request.user
        if user.is_superuser or getattr(user, "role", None) and user.role.code == RoleCode.ADMIN.value:
            return True
        company = getattr(user, "company", None) or getattr(user, "profile", None)
        individual_owner = getattr(user, "individual_owner", None) or getattr(user, "individual_owner_profile", None)
        return (company and listing.company_id == company.id) or (
            individual_owner and listing.individual_owner_id == individual_owner.id
        )

    @extend_schema(
        request=ContactRevealRequestSerializer,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="request-contact")
    def request_contact(self, request, pk=None):
        listing = self.get_object()
        if request.user.is_authenticated and self._is_listing_owner(listing):
            return Response(
                {"detail": "Listing owners cannot request their own seller contact."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ContactRevealRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        buyer = request.user if request.user.is_authenticated else None
        tx_ref = request.query_params.get("tx_ref") or serializer.validated_data.get("tx_ref")
        guest_verification_token = None

        if buyer is None:
            try:
                guest_verification_token = _verify_guest_contact_reveal_request(
                    serializer,
                    reveal_type="car_sale_reveal",
                )
            except GuestBookingOtpError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        reveal_request = ContactRevealPaymentService.create_reveal_request(
            listing=listing,
            buyer=buyer,
            buyer_note=serializer.validated_data.get("buyer_note", ""),
            buyer_phone=serializer.validated_data.get("buyer_phone", ""),
        )

        if reveal_request.status == ContactRevealRequest.RevealStatus.PAID_REVEALED:
            contact_kwargs = {"listing": listing}
            if buyer is not None:
                contact_kwargs["buyer"] = buyer
            else:
                contact_kwargs["tx_ref"] = tx_ref or reveal_request.tx_ref
            return Response(
                {
                    "success": True,
                    "contact_unlocked": True,
                    "reveal_request": ContactRevealRequestResponseSerializer(reveal_request).data,
                    "contact": ContactRevealPaymentService.get_unlocked_contact(**contact_kwargs),
                    "guest_verification_token": guest_verification_token,
                },
                status=status.HTTP_200_OK,
            )

        result = ContactRevealPaymentService.initialize_contact_reveal_payment(reveal_request)
        if not result.get("success"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        reveal_request = result["reveal_request"]
        return Response(
            {
                "success": True,
                "checkout_url": result["checkout_url"],
                "tx_ref": result["tx_ref"],
                "reveal_request": ContactRevealRequestResponseSerializer(reveal_request).data,
                "guest_verification_token": guest_verification_token,
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Request guest car-sale contact reveal phone OTP",
        request=GuestContactRevealOtpRequestSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="guest-otp")
    def guest_otp(self, request):
        return _request_guest_contact_reveal_otp(request, reveal_type="car_sale_reveal")

    @extend_schema(responses={200: CarSaleContactSerializer, 403: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"], url_path="contact")
    def contact(self, request, pk=None):
        listing = self.get_object()
        if request.user.is_authenticated:
            contact = ContactRevealPaymentService.get_unlocked_contact(
                listing=listing,
                buyer=request.user,
            )
        else:
            tx_ref = request.query_params.get("tx_ref")
            contact = ContactRevealPaymentService.get_unlocked_contact(
                listing=listing,
                tx_ref=tx_ref,
            )
        serializer = CarSaleContactSerializer(contact)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: CarSaleListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        sale_listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            sale_listing,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = CarSaleListingResponseSerializer(sale_listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: CarSaleListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        sale_listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(sale_listing, request.user)
        serializer = CarSaleListingResponseSerializer(sale_listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["Property Sales"])
class PropertySaleListingViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    http_method_names = ["get", "post"]
    queryset = PropertySaleListing.objects.all()
    serializer_class = PropertySaleListingSerializer
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["property_type", "is_furnished", "is_active"]
    search_fields = ["title", "description", "address__city", "address__sub_city"]
    ordering_fields = ["base_price", "square_meters", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        if self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        if self.action in ["request_contact", "contact", "guest_otp"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "create":
            return PropertySaleListingSerializer
        return PropertySaleListingResponseSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "company",
            "individual_owner",
            "address",
        ).prefetch_related("images", "contact_reveal_requests")
        user = self.request.user

        if user.is_authenticated and (
            user.is_superuser or getattr(user, "role", None) and user.role.code == RoleCode.ADMIN.value
        ):
            return queryset

        managed_only = self.request.query_params.get("managed") == "true"
        if managed_only and user.is_authenticated:
            company = getattr(user, "company", None) or getattr(user, "profile", None)
            individual_owner = getattr(user, "individual_owner", None) or getattr(user, "individual_owner_profile", None)
            q = Q()
            if company:
                q |= Q(company=company)
            if individual_owner:
                q |= Q(individual_owner=individual_owner)
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    def _is_admin(self, user):
        return user.is_superuser or getattr(user, "role", None) and user.role.code == RoleCode.ADMIN.value

    def _current_owner_paths(self):
        user = self.request.user
        company = getattr(user, "company", None) or getattr(user, "profile", None)
        individual_owner = getattr(user, "individual_owner", None) or getattr(user, "individual_owner_profile", None)
        return company, individual_owner

    def create(self, request, *args, **kwargs):
        company, individual_owner = self._current_owner_paths()
        if not self._is_admin(request.user) and not company and not individual_owner:
            return Response(
                {"detail": "Only approved companies, individual owners, or admins can create property sale listings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = self.request.user
        if not serializer.validated_data.get("company") and not serializer.validated_data.get("individual_owner"):
            company, individual_owner = self._current_owner_paths()
            if individual_owner:
                serializer.save(individual_owner=individual_owner)
                return
            if company:
                if company.status != CompanyProfile.StatusChoice.APPROVED:
                    raise PermissionDenied("Company profile is not approved.")
                serializer.save(company=company)
                return

        if not self._is_admin(user):
            company, individual_owner = self._current_owner_paths()
            requested_company = serializer.validated_data.get("company")
            requested_individual_owner = serializer.validated_data.get("individual_owner")
            if requested_company and (not company or requested_company.id != company.id):
                raise PermissionDenied("Cannot create property sale listings for another company.")
            if requested_individual_owner and (
                not individual_owner or requested_individual_owner.id != individual_owner.id
            ):
                raise PermissionDenied("Cannot create property sale listings for another individual owner.")

        serializer.save()

    def _is_listing_owner(self, listing):
        user = self.request.user
        if self._is_admin(user):
            return True
        company, individual_owner = self._current_owner_paths()
        return (company and listing.company_id == company.id) or (
            individual_owner and listing.individual_owner_id == individual_owner.id
        )

    @extend_schema(
        request=ContactRevealRequestSerializer,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="request-contact")
    def request_contact(self, request, pk=None):
        listing = self.get_object()
        if request.user.is_authenticated and self._is_listing_owner(listing):
            return Response(
                {"detail": "Listing owners cannot request their own seller contact."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ContactRevealRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        buyer = request.user if request.user.is_authenticated else None
        guest_verification_token = None

        if buyer is None:
            try:
                guest_verification_token = _verify_guest_contact_reveal_request(
                    serializer,
                    reveal_type="property_sale_reveal",
                )
            except GuestBookingOtpError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        reveal_request = ContactRevealPaymentService.create_reveal_request(
            listing=listing,
            buyer=buyer,
            buyer_note=serializer.validated_data.get("buyer_note", ""),
            buyer_phone=serializer.validated_data.get("buyer_phone", ""),
        )

        if reveal_request.status == PropertyContactRevealRequest.RevealStatus.PAID_REVEALED:
            contact_kwargs = {"listing": listing}
            if buyer is not None:
                contact_kwargs["buyer"] = buyer
            else:
                contact_kwargs["tx_ref"] = reveal_request.tx_ref
            contact = ContactRevealPaymentService.get_unlocked_contact(**contact_kwargs)
            return Response(
                {
                    "success": True,
                    "contact_unlocked": True,
                    "reveal_request": PropertyContactRevealRequestResponseSerializer(reveal_request).data,
                    "contact": contact,
                    "guest_verification_token": guest_verification_token,
                },
                status=status.HTTP_200_OK,
            )

        result = ContactRevealPaymentService.initialize_contact_reveal_payment(reveal_request)
        if not result.get("success"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        reveal_request = result["reveal_request"]
        return Response(
            {
                "success": True,
                "checkout_url": result["checkout_url"],
                "tx_ref": result["tx_ref"],
                "reveal_request": PropertyContactRevealRequestResponseSerializer(reveal_request).data,
                "guest_verification_token": guest_verification_token,
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Request guest property-sale contact reveal phone OTP",
        request=GuestContactRevealOtpRequestSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="guest-otp")
    def guest_otp(self, request):
        return _request_guest_contact_reveal_otp(request, reveal_type="property_sale_reveal")

    @extend_schema(responses={200: CarSaleContactSerializer, 403: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"], url_path="contact")
    def contact(self, request, pk=None):
        listing = self.get_object()
        if request.user.is_authenticated:
            contact = ContactRevealPaymentService.get_unlocked_contact(
                listing=listing,
                buyer=request.user,
            )
        else:
            contact = ContactRevealPaymentService.get_unlocked_contact(
                listing=listing,
                tx_ref=request.query_params.get("tx_ref"),
            )
        serializer = CarSaleContactSerializer(contact)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: PropertySaleListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            listing,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = PropertySaleListingResponseSerializer(listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: PropertySaleListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(listing, request.user)
        serializer = PropertySaleListingResponseSerializer(listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)
# Car Rental ViewSet
@extend_schema(tags=["Car Rentals"])
class CarRentalViewSet(AbstractModelViewSet):
    serializer_class = CarRentalSerializer
    queryset = CarRental.objects.all()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['start_date', 'end_date', 'total_price', 'created_at']
    ordering = ['-created_at']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        if self.action in ['create', 'lookup', 'guest_otp', 'guest_rentals', 'price_preview', 'extension_price_preview', 'request_extension']:
            return [AllowAny()]
        elif self.action in ['list', 'retrieve', 'my_rentals', 'rental_stats']:
            return [IsAuthenticated()]
        else:
            return [IsCarRentalOwner()]

    def get_throttles(self):
        if self.action in ['create', 'guest_otp']:
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        if self.action == 'price_preview':
            self.throttle_scope = 'availability_check'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return CarRental.objects.none()
        queryset = super().get_queryset()

        # Admin sees all
        if user.is_superuser or getattr(user, 'role', None) and user.role.code == RoleCode.ADMIN.value:
            return queryset

        # User sees own rentals
        user_rentals = queryset.filter(renter=user)

        # Company sees rentals for their cars + own rentals
        if getattr(user, 'role', None) and user.role.code == RoleCode.COMPANY.value:
            company_rentals = queryset.filter(rental_items__car_listing__company=user.profile).distinct()
            return (user_rentals.distinct() | company_rentals).distinct()

        return user_rentals

    @extend_schema(
        summary="Request car rental guest phone OTP",
        description="Issue a phone OTP challenge before creating a car rental as a guest.",
        request=GuestBookingOtpRequestSerializer,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="guest-otp/request", permission_classes=[AllowAny])
    def guest_otp(self, request):
        return _request_guest_booking_otp(request, booking_type="car_rental")

    @extend_schema(
        summary="Lookup car rental status (Guest)",
        description=(
            "Retrieve guest car rental details using a verified guest phone session. "
            "A legacy email compatibility bridge remains available temporarily."
        ),
        parameters=[GuestCarRentalLookupSerializer],
        responses={200: CarRentalSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = GuestCarRentalLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        reference = serializer.validated_data['reference']
        queryset = CarRental.objects.prefetch_related("rental_items", "rental_items__car_listing")
        email = serializer.validated_data.get("email")

        if email:
            rental = get_object_or_404(
                queryset,
                booking_reference=reference,
                guest_email__iexact=email,
            )
        else:
            rental = get_object_or_404(
                queryset,
                booking_reference=reference,
                renter__isnull=True,
            )
            _assert_guest_rental_phone_matches(rental, serializer.validated_data["guest_phone"])

        response_serializer = CarRentalSerializer(rental, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @transaction.atomic
    @extend_schema(
        summary="Create a new car rental booking (supports guest checkout)",
        description="""
        Initiates a rental booking for one or more vehicles.
        - Supports both authenticated users and guest checkout.
        - If guest, provide renter details in `guest_*` fields.
        - Guest checkout now requires a prior `guest-otp/request/` call and both `otp_challenge_id` and `otp_code` on create.
        - Checks vehicle availability across the requested date range.
        - Returns a pending booking with a `booking_reference` (prefix 'C').
        """,
        request=CarRentalSerializer,
        responses={201: CarRentalSerializer}
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rental_items_data = request.data.get('rental_items', [])

        # --- Check availability for all rental items ---
        for item_data in rental_items_data:
            car_listing = CarListing.objects.get(id=item_data['car_listing'])
            availability = CarAvailabilityService.check_daily_availability(
                car_listing=car_listing,
                start_date=serializer.validated_data['start_date'],
                end_date=serializer.validated_data['end_date'],
                quantity=item_data.get('units_rent', 1),
            )
            if not availability.get('available'):
                return Response({"error": availability.get('reason')}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user if request.user.is_authenticated else None
        rental = serializer.save(renter=user)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Price preview for car rental selection",
        description="Get a consolidated price quote for one or more cars before creating the rental or starting payment.",
        request=CarRentalPreviewSerializer,
        parameters=[
            OpenApiParameter(
                name="display_currency",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional: Request price preview in a specific currency (e.g., USD) using triangulation.",
            )
        ],
        responses={200: PricePreviewResponseSerializer, 400: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['post'], url_path='price-preview')
    def price_preview(self, request):
        serializer = CarRentalPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        preview_phone = data.get('guest_phone') or (request.user.phone if request.user.is_authenticated else None)

        try:
            payload = CarRentalService.calculate_price_preview(
                start_date=data['start_date'],
                end_date=data['end_date'],
                items=data['items'],
                display_currency=get_display_currency(request),
                guest_phone=preview_phone,
            )
        except BookingConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        rental = self.get_object()
        if rental.status != CarRental.RentStatus.PENDING:
            return Response({"error": "Only pending rentals can be confirmed."}, status=status.HTTP_400_BAD_REQUEST)

        # Check daily availability again
        for item in rental.rental_items.all():
            try:
                CarAvailabilityService.validate_availability(
                    item.car_listing, item.units_rent, rental.start_date, rental.end_date
                )
            except Exception as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        rental.status = CarRental.RentStatus.CONFIRMED
        rental.save()
        return Response(self.get_serializer(rental).data)

    @extend_schema(
        summary="Cancel a car rental",
        description=(
            "Cancel a car rental and restore availability. "
            "Authenticated owners keep the existing flow, while guest rentals can be cancelled "
            "with a verified guest phone session. "
            "Booking cancellation does not create a refund because the platform does not support refunds."
        ),
        request=GuestCarRentalCancellationSerializer,
        responses={200: CarRentalSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=['post'], permission_classes=[AllowAny])
    def cancel(self, request, pk=None):
        rental = get_object_or_404(
            CarRental.objects.prefetch_related("rental_items", "rental_items__car_listing"),
            pk=pk,
        )
        if rental.status == CarRental.RentStatus.CANCELLED:
            return Response(
                _with_booking_no_refund_policy(
                    {"error": "Rental is already cancelled."},
                    cancellation_effect="booking_not_cancelled",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.is_authenticated:
            if not IsCarRentalOwner().has_object_permission(request, self, rental):
                return Response(
                    {"detail": "You do not have permission to cancel this rental."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            if rental.renter_id:
                return Response(
                    {"detail": "This rental belongs to a registered user. Please sign in to cancel."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = GuestCarRentalCancellationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            _assert_guest_rental_phone_matches(rental, serializer.validated_data["guest_phone"])

        rental = CarRentalService.cancel_booking(rental)
        return Response(
            _with_booking_no_refund_policy(self.get_serializer(rental).data)
        )

    @extend_schema(
        summary="Reschedule car rental dates",
        description=(
            "Change the start and end dates for an existing car rental when the target inventory "
            "is available. Preserves the existing booking and recalculates totals."
        ),
        request=CarRentalRescheduleSerializer,
        responses={200: CarRentalSerializer, 400: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        rental = self.get_object()
        serializer = CarRentalRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            rental = CarRentalService.reschedule_booking(
                rental,
                start_date=serializer.validated_data["start_date"],
                end_date=serializer.validated_data["end_date"],
            )
        except BookingConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        response_serializer = self.get_serializer(rental)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Preview car rental extension price",
        description="Validate extra-day availability and calculate the extension payment before initiating payment.",
        request=CarRentalExtensionPreviewSerializer,
        responses={200: CarRentalExtensionPreviewResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="extension-price-preview", permission_classes=[AllowAny])
    def extension_price_preview(self, request, pk=None):
        rental = get_object_or_404(
            CarRental.objects.prefetch_related("rental_items", "rental_items__car_listing"),
            pk=pk,
        )
        serializer = CarRentalExtensionPreviewSerializer(
            data=request.data,
            context={"request": request, "rental": rental},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        if user.is_authenticated:
            is_admin = user.is_superuser or (
                getattr(user, "role", None) and user.role.code == RoleCode.ADMIN.value
            )
            if not is_admin and rental.renter != user:
                return Response(
                    {"detail": "You can only extend your own car rental."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            _assert_guest_rental_phone_matches(rental, serializer.validated_data["guest_phone"])

        try:
            preview = CarRentalService.calculate_extension_preview(
                rental,
                new_end_date=serializer.validated_data["new_end_date"],
                payment_currency=serializer.validated_data.get("payment_currency"),
            )
        except BookingConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        payload = {
            "booking_reference": rental.booking_reference,
            "current_end_date": rental.end_date,
            "new_end_date": preview["new_end_date"],
            "extra_days": preview["extra_days"],
            "extension_subtotal": preview["extension_subtotal"],
            "platform_fee": preview["platform_fee"],
            "original_amount": preview["original_amount"],
            "original_currency": preview["original_currency"],
            "amount": preview["amount"],
            "currency": preview["currency"],
            "exchange_rate": preview["exchange_rate"],
        }
        token = serializer.validated_data.get("guest_verification_token") or serializer.context.get(
            "guest_verification_token"
        )
        if token:
            payload["guest_verification_token"] = token
        return Response(payload, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Initiate a car rental extension payment",
        description="Hold the requested extra days, create an extension request, and initialize a dedicated Chapa payment.",
        request=CarRentalExtensionInitiateSerializer,
        responses={200: CarRentalExtensionInitiateResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="request-extension", permission_classes=[AllowAny])
    def request_extension(self, request, pk=None):
        rental = get_object_or_404(
            CarRental.objects.prefetch_related("rental_items", "rental_items__car_listing"),
            pk=pk,
        )
        serializer = CarRentalExtensionInitiateSerializer(
            data=request.data,
            context={"request": request, "rental": rental},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        if user.is_authenticated:
            is_admin = user.is_superuser or (
                getattr(user, "role", None) and user.role.code == RoleCode.ADMIN.value
            )
            if not is_admin and rental.renter != user:
                return Response(
                    {"detail": "You can only extend your own car rental."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            _assert_guest_rental_phone_matches(rental, serializer.validated_data["guest_phone"])

        try:
            extension_request, preview = CarRentalService.create_extension_request(
                rental,
                new_end_date=serializer.validated_data["new_end_date"],
                requested_by=user if user.is_authenticated else None,
                payment_currency=serializer.validated_data.get("payment_currency"),
            )
        except BookingConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        if user.is_authenticated:
            payer_email = user.email
            payer_first_name = user.first_name
            payer_last_name = user.last_name
        else:
            payer_email = getattr(rental, "guest_email", None) or "guest@michotmarefia.com"
            payer_first_name = getattr(rental, "guest_first_name", None) or "Guest"
            payer_last_name = getattr(rental, "guest_last_name", None) or "User"

        result = ChapaPaymentService.initialize_car_rental_extension_payment(
            extension_request,
            email=payer_email,
            first_name=payer_first_name,
            last_name=payer_last_name,
        )
        if not result["success"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "booking_reference": rental.booking_reference,
            "current_end_date": rental.end_date,
            "new_end_date": preview["new_end_date"],
            "extra_days": preview["extra_days"],
            "extension_subtotal": preview["extension_subtotal"],
            "platform_fee": preview["platform_fee"],
            "original_amount": preview["original_amount"],
            "original_currency": preview["original_currency"],
            "amount": preview["amount"],
            "currency": preview["currency"],
            "exchange_rate": preview["exchange_rate"],
            "extension_request_id": extension_request.id,
            "status": extension_request.ExtensionStatus.PAYMENT_INITIATED,
            "tx_ref": result["tx_ref"],
            "checkout_url": result["checkout_url"],
        }
        token = serializer.validated_data.get("guest_verification_token") or serializer.context.get(
            "guest_verification_token"
        )
        if token:
            payload["guest_verification_token"] = token
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def my_rentals(self, request):
        rentals = self.get_queryset().filter(renter=request.user).order_by("-created_at")
        page = self.paginate_queryset(rentals)
        if page:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(rentals, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="List guest car rentals by verified phone",
        description=(
            "Retrieve guest-created car rentals tied to a verified phone number. "
            "Registered-user rentals are excluded from this guest self-service view."
        ),
        parameters=[GuestCarRentalHistoryAccessSerializer],
        responses={200: CarRentalSerializer(many=True), 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="guest-rentals", permission_classes=[AllowAny])
    def guest_rentals(self, request):
        serializer = GuestCarRentalHistoryAccessSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        verified_phone = serializer.validated_data["verified_phone"]
        guest_verification_token = serializer.validated_data.get("guest_verification_token")
        rentals = (
            CarRental.objects.prefetch_related("rental_items", "rental_items__car_listing")
            .filter(renter__isnull=True, guest_phone__in=_phone_variants(verified_phone))
            .order_by("-created_at")
        )

        page = self.paginate_queryset(rentals)
        if page is not None:
            response = self.get_paginated_response(self.get_serializer(page, many=True).data)
            if guest_verification_token:
                response.data["guest_verification_token"] = guest_verification_token
            return response

        data = self.get_serializer(rentals, many=True).data
        payload = {"results": data, "count": len(data)}
        if guest_verification_token:
            payload["guest_verification_token"] = guest_verification_token
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def rental_stats(self, request):
        user = request.user
        queryset = CarRental.objects.filter(renter=user)
        total_spent = queryset.filter(status=CarRental.RentStatus.CONFIRMED).aggregate(total=Sum('total_price'))['total'] or 0
        return Response({
            "total_rentals": queryset.count(),
            "confirmed_rentals": queryset.filter(status=CarRental.RentStatus.CONFIRMED).count(),
            "pending_rentals": queryset.filter(status=CarRental.RentStatus.PENDING).count(),
            "cancelled_rentals": queryset.filter(status=CarRental.RentStatus.CANCELLED).count(),
            "total_spent": float(total_spent)
        })

# Availability APIViews
class CarAvailabilitySearchView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

    @extend_schema(responses=CarAvailabilitySerializer)
    def get(self, request):
        car_listing_id, start_date, end_date, quantity_or_resp = ParseDatesAndQuantity.parse_dates_and_quantity(request, require_car=True)
        if isinstance(quantity_or_resp, Response):
            return quantity_or_resp
        car_listing = CarListing.objects.get(id=car_listing_id)
        availability = CarAvailabilityService.validate_availability(car_listing, start_date, end_date, quantity_or_resp)
        return Response({
            "car_listing": {
                "id": car_listing.id, "title": car_listing.title, "brand": car_listing.brand,
                "model": car_listing.model, "base_price": str(car_listing.base_price)
            },
            "search_period": {"start_date": start_date, "end_date": end_date},
            "quantity_requested": quantity_or_resp,
            "availability": availability
        })

class CarAvailabilityByDateRangeView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

    @extend_schema(
        summary="Search all available cars in a date range",
        responses=inline_serializer(
            name="CarAvailabilityByDateRangeResponse",
            fields={
                "search_period": inline_serializer(
                    name="CarAvailabilityByDateRangeSearchPeriod",
                    fields={
                        "start_date": serializers.DateField(),
                        "end_date": serializers.DateField(),
                    },
                ),
                "quantity_requested": serializers.IntegerField(),
                "available_cars_count": serializers.IntegerField(),
                "available_cars": inline_serializer(
                    name="CarAvailabilityByDateRangeCar",
                    fields={
                        "car_listing_id": serializers.UUIDField(),
                        "title": serializers.CharField(),
                        "brand": serializers.CharField(),
                        "model": serializers.CharField(),
                        "base_price": serializers.CharField(),
                        "availability": serializers.JSONField(allow_null=True),
                    },
                    many=True,
                ),
            },
        ),
    )
    def get(self, request):
        _, start_date, end_date, quantity_or_resp = ParseDatesAndQuantity.parse_dates_and_quantity(request)
        if isinstance(quantity_or_resp, Response):
            return quantity_or_resp

        results = []
        for car in CarListing.objects.all():
            availability = CarAvailabilityService.get_available_cars(car, start_date, end_date, quantity_or_resp)
            if availability.get("is_available"):
                results.append({
                    "car_listing_id": car.id,
                    "title": car.title,
                    "brand": car.brand,
                    "model": car.model,
                    "base_price": str(car.base_price),
                    "availability": availability
                })
        return Response({
            "search_period": {"start_date": start_date, "end_date": end_date},
            "quantity_requested": quantity_or_resp,
            "available_cars_count": len(results),
            "available_cars": results
        })

class CarAvailabilityByCarAndDateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

    @extend_schema(
        summary="Get availability for a specific car listing within a date range",
        responses=inline_serializer(
            name="CarAvailabilityByCarAndDateResponse",
            fields={
                "car_listing": inline_serializer(
                    name="CarAvailabilityByCarAndDateCarListing",
                    fields={
                        "id": serializers.UUIDField(),
                        "title": serializers.CharField(),
                        "brand": serializers.CharField(),
                        "model": serializers.CharField(),
                        "base_price": serializers.CharField(),
                    },
                ),
                "search_period": inline_serializer(
                    name="CarAvailabilityByCarAndDateSearchPeriod",
                    fields={
                        "start_date": serializers.DateField(),
                        "end_date": serializers.DateField(),
                    },
                ),
                "quantity_requested": serializers.IntegerField(),
                "availability": serializers.JSONField(allow_null=True),
            },
        ),
    )
    def get(self, request):
        car_listing_id, start_date, end_date, quantity_or_resp = ParseDatesAndQuantity.parse_dates_and_quantity(request, require_car=True)
        if isinstance(quantity_or_resp, Response):
            return quantity_or_resp
        car_listing = CarListing.objects.get(id=car_listing_id)
        availability = CarAvailabilityService.validate_availability(car_listing, start_date, end_date, quantity_or_resp)
        return Response({
            "car_listing": {
                "id": car_listing.id, "title": car_listing.title, "brand": car_listing.brand,
                "model": car_listing.model, "base_price": str(car_listing.base_price)
            },
            "search_period": {"start_date": start_date, "end_date": end_date},
            "quantity_requested": quantity_or_resp,
            "availability": availability
        })

@extend_schema(responses=PropertyListingResponseSerializer)
class PropertyListingViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    serializer_class = PropertyListingSerializer
    queryset = PropertyListing.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = PropertyFilter
    search_fields = ['title', 'name', 'description', 'address']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        """
        - CREATE: Company users can create properties, admin can create all
        - READ: Public (all can read)
        - UPDATE/DELETE: Company can modify own properties, admin can modify all
        """
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve']:
            return [AllowAny()]
        elif self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        else:
            return [IsListingOwner()]

    def get_queryset(self):
        """Filter queryset - show all active to public, managed only to owners/admin."""
        queryset = super().get_queryset()
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset
        
        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(company=company)
            if individual_owner:
                q |= Q(individual_owner=individual_owner)
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: PropertyListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        property_listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            property_listing,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = PropertyListingResponseSerializer(property_listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: PropertyListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        property_listing = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(property_listing, request.user)
        serializer = PropertyListingResponseSerializer(property_listing, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["Property Rental Bookings"])
class PropertyRentalBookingViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PropertyRentalBookingSerializer
    queryset = PropertyRentalBooking.objects.all()
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = {
        "status": ["exact"],
        "start_date": ["gte", "lte"],
        "end_date": ["gte", "lte"],
    }
    ordering_fields = ["start_date", "end_date", "total_price", "created_at"]
    ordering = ["-created_at"]
    search_fields = [
        "booking_reference",
        "renter__email",
        "renter__first_name",
        "renter__last_name",
        "guest_email",
        "guest_first_name",
        "guest_last_name",
        "guest_phone",
    ]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        context["request"] = self.request
        return context

    def get_serializer_class(self):
        if self.action in ["retrieve", "cancel"]:
            return PropertyRentalBookingResponseSerializer
        return PropertyRentalBookingSerializer

    def get_permissions(self):
        if self.action in ["create", "price_preview", "guest_otp"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_throttles(self):
        if self.action in ["create", "guest_otp"]:
            self.throttle_scope = "booking_create"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        return super().get_queryset().select_related(
            "renter",
            "property_listing",
            "property_listing__company",
            "property_listing__individual_owner",
            "property_listing__address",
        ).prefetch_related("property_listing__images")

    def _is_admin(self, user):
        return user.is_superuser or getattr(user, "role", None) and user.role.code == RoleCode.ADMIN.value

    def _can_access_booking(self, booking):
        user = self.request.user
        if self._is_admin(user):
            return True
        if booking.renter_id and booking.renter_id == user.id:
            return True
        company = getattr(user, "company", None) or getattr(user, "profile", None)
        individual_owner = getattr(user, "individual_owner", None) or getattr(user, "individual_owner_profile", None)
        listing = booking.property_listing
        return (company and listing.company_id == company.id) or (
            individual_owner and listing.individual_owner_id == individual_owner.id
        )

    @extend_schema(
        request=PropertyRentalBookingSerializer,
        responses={201: PropertyRentalBookingResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response(
            PropertyRentalBookingResponseSerializer(booking, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={200: PropertyRentalBookingResponseSerializer, 403: OpenApiTypes.OBJECT})
    def retrieve(self, request, *args, **kwargs):
        booking = self.get_object()
        if not self._can_access_booking(booking):
            return Response({"detail": "You do not have permission to view this booking."}, status=status.HTTP_403_FORBIDDEN)
        serializer = PropertyRentalBookingResponseSerializer(booking, context=self.get_serializer_context())
        return Response(serializer.data)

    @extend_schema(
        responses={200: PropertyRentalBookingResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT}
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if not self._can_access_booking(booking):
            return Response({"detail": "You do not have permission to cancel this booking."}, status=status.HTTP_403_FORBIDDEN)
        try:
            cancelled = PropertyRentalBookingService.cancel_booking(booking)
        except Exception as exc:
            return Response(
                _with_booking_no_refund_policy(
                    {"detail": str(exc)},
                    cancellation_effect="booking_not_cancelled",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            _with_booking_no_refund_policy(
                PropertyRentalBookingResponseSerializer(cancelled, context=self.get_serializer_context()).data
            )
        )

    @extend_schema(
        request=PropertyRentalBookingPreviewSerializer,
        responses={200: PricePreviewResponseSerializer, 400: OpenApiTypes.OBJECT},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="price-preview",
        throttle_classes=[ScopedRateThrottle],
        throttle_scope="availability_check",
    )
    def price_preview(self, request):
        serializer = PropertyRentalBookingPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        listing = data["property_listing"]
        start = data["start_date"]
        end = data["end_date"]
        try:
            PropertyRentalAvailabilityService.validate_availability(listing, start, end, lock=False)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        preview_phone = data.get("guest_phone") or (request.user.phone if request.user.is_authenticated else None)
        return Response(
            PropertyRentalBookingService.calculate_price_preview(
                listing,
                start,
                end,
                payment_currency=listing.currency,
                guest_phone=preview_phone,
                display_currency=get_display_currency(request),
            )
        )

    @extend_schema(
        summary="Request property rental booking guest phone OTP",
        description="Issue a phone OTP challenge before creating a property rental booking as a guest.",
        request=GuestBookingOtpRequestSerializer,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="guest-otp/request", permission_classes=[AllowAny])
    def guest_otp(self, request):
        return _request_guest_booking_otp(request, booking_type="property_rental")


class AmenityViewSet(AbstractModelViewSet):
    serializer_class = AmenityResponseSSerializer
    queryset = Amenity.objects.all()

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        return [IsAdmin()]


class BookingViewSet(AbstractModelViewSet):
    http_method_names = ["get", "post"]
    serializer_class = BookingSerializer
    queryset = Booking.objects.all()
    throttle_scope = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = BookingFilter
    ordering = ['-created_at']
    
    @extend_schema(request=BookingSerializer, responses=BookingSerializer)
    @action(detail=False, methods=['post'], url_path='walk-in', permission_classes=[IsAuthenticated])
    def walk_in(self, request, *args, **kwargs):
        """
        Create a walk-in booking. 
        Passes is_walk_in=True via context to trigger staff privileges check.
        Requires authentication.
        """
        # Default currency to ETB for walk-ins if not specified
        data = request.data.copy()
        if 'payment_currency' not in data:
            data['payment_currency'] = 'ETB'
        
        # Pass is_walk_in via context, not data
        context = {**self.get_serializer_context(), 'is_walk_in': True}
        serializer = self.get_serializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    search_fields = [
        'booking_reference',
        'user__email',
        'user__first_name',
        'user__last_name',
        'guest_email',
        'guest_first_name',
        'guest_last_name',
        'guest_phone'
    ]

    @extend_schema(
        summary="Create a new room booking (supports guest checkout)",
        description="""
        Initiates a booking for one or more hotel rooms. 
        - Supports both authenticated users and guest checkout.
        - If not logged in, `guest_email`, `guest_phone`, `guest_first_name`, and `guest_last_name` are required.
        - Guest checkout now requires a prior `guest-otp/request/` call and both `otp_challenge_id` and `otp_code` on create.
        - `terms_accepted` must be true.
        - `terms_version` must match the hotel's latest active T&C version.
        - Returns a pending booking with a human-readable `booking_reference` (e.g., H-X7Y2Z9).
        """,
        request=BookingSerializer,
        responses={201: BookingResponseSerializer}
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_permissions(self):
        """
        - CREATE/LOOKUP: Allow anyone (guests)
        - READ: Users see own bookings, companies see bookings for their listings, admin sees all
        - Special actions: partial_cancel, rate require ownership
        """
        if self.action in ['create', 'lookup', 'cancel', 'price_preview', 'guest_otp']:
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['partial_cancel', 'rate_booking']:
            return [IsBookingOwner()]
        else:
            return [IsAuthenticated()]

    def get_throttles(self):
        if self.action in ['create', 'guest_otp']:
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        """
        Filter bookings based on user role:
        - Admin: See all bookings
        - Company (mode='host'): See bookings for their listings
        - User/Default: See only their own bookings
        """
        if not self.request.user or not self.request.user.is_authenticated:
            return Booking.objects.none()
        
        queryset = Booking.objects.prefetch_related("items", "items__room")
        
        # Admin sees all
        if self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and
            self.request.user.role and
            self.request.user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        # Check for mode parameter (Feature branch logic)
        mode = self.request.query_params.get('mode')
        if mode == 'host':
            if hasattr(self.request.user, 'role') and self.request.user.role:
                if self.request.user.role.code == RoleCode.COMPANY.value:
                    if hasattr(self.request.user, 'profile') and self.request.user.profile:
                        # Ensure HotelProfile is imported if needed, usually available via models
                        company = self.request.user.profile
                        try:
                            hotel = HotelProfile.objects.get(company=company)
                            return queryset.filter(
                                items__room__hotel=hotel
                            ).distinct()
                        except HotelProfile.DoesNotExist:
                            pass
            return queryset.none()

        # Users see only their own bookings
        user_bookings = queryset.filter(user=self.request.user).distinct()

        if self.request.query_params.get('as_guest') == 'true':
            return user_bookings

        # Company sees bookings for their hotels (Development branch logic)
        if hasattr(self.request.user, 'role') and self.request.user.role and self.request.user.role.code == RoleCode.COMPANY.value:
             if hasattr(self.request.user, 'profile') and self.request.user.profile:
                  company = self.request.user.profile
                  try:
                      hotel = HotelProfile.objects.get(company=company)
                      hotel_bookings = queryset.filter(items__room__hotel=hotel).distinct()
                      return (user_bookings | hotel_bookings).distinct()
                  except HotelProfile.DoesNotExist:
                      pass
        
        return user_bookings
    
    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)

    @extend_schema(
        summary="Request hotel booking guest phone OTP",
        description="Issue a phone OTP challenge before creating a hotel room booking as a guest.",
        request=GuestBookingOtpRequestSerializer,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="guest-otp/request", permission_classes=[AllowAny])
    def guest_otp(self, request):
        return _request_guest_booking_otp(request, booking_type="hotel")

    @extend_schema(
        summary="Lookup room booking status (Guest)",
        description="Retrieve booking details using reference and guest email. No login required.",
        parameters=[
            OpenApiParameter("reference", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("email", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: BookingResponseSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = BookingLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        reference = serializer.validated_data['reference']
        email = serializer.validated_data['email']
        
        booking = get_object_or_404(
            Booking.objects.prefetch_related("items", "items__room"),
            booking_reference=reference,
            guest_email=email
        )
        
        response_serializer = BookingResponseSerializer(booking, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @extend_schema(
        summary="Price Preview for room selection",
        description="Get a consolidated price quote for a selection of hotel rooms before booking.",
        request=BookingPreviewSerializer,
        parameters=[
            OpenApiParameter(
                name="display_currency",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional: Request price preview in a specific currency (e.g., USD) using triangulation."
            )
        ],
        responses={
            200: PricePreviewResponseSerializer,
            400: OpenApiTypes.OBJECT
        }
    )
    @action(
        detail=False, 
        methods=['post'], 
        url_path='price-preview',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='availability_check'
    )
    def price_preview(self, request):
        serializer = BookingPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        check_in = data['check_in_date']
        check_out = data['check_out_date']
        items = data['items']
        preview_phone = data.get('guest_phone') or (request.user.phone if request.user.is_authenticated else None)
        
        # Validate availability (lock=False for previews)
        rooms_info = [{"room": item["room"], "quantity": item["units_booked"]} for item in items]
        hotel = items[0]["room"].hotel
        try:
            StayAvailabilityService.validate_availability(hotel, rooms_info, check_in, check_out, lock=False)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
            
        total_items = []
        item_subtotals = []
        
        currencies = {item["room"].currency for item in items}
        if len(currencies) > 1:
            return Response({"detail": "All selected items must have the same currency."}, status=400)
        currency = list(currencies)[0] if currencies else "ETB"
        display_currency = get_display_currency(request)
        
        for item in items:
            room = item["room"]
            units = item["units_booked"]
            
            price_details = PriceService.resolve_price_details_batch(room, check_in, check_out)
            item_base_total = sum(Decimal(str(d['price_per_unit'])) for d in price_details) * units
            
            item_subtotals.append(item_base_total)
            total_items.append({
                "id": str(room.id),
                "title": room.title,
                "units": units,
                "price_per_unit": str(price_details[0]['price_per_unit']) if price_details else str(room.base_price),
                "subtotal": str(item_base_total.quantize(Decimal('0.01'))),
                "breakdown": price_details
            })
            
        nights = (check_out - check_in).days
        return Response({
            "nights": nights,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(
                item_subtotals,
                currency,
                display_currency,
                items=total_items,
                fee_rate=get_effective_platform_fee_rate(phone=preview_phone),
            )
        })
    @extend_schema(
        summary="Cancel a booking (User or Guest)",
        description="""
        Cancel a booking.
        - **Authenticated**: User cancels their own booking.
        - **Guest**: Must provide `guest_email` matching the booking to verify ownership.
        - Cancellation does not create a refund because the platform does not support refunds.
        """,
        request=GuestCancellationSerializer,
        responses={200: BookingResponseSerializer}
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Allows an authenticated user or verified guest to cancel their booking."""
        booking = self.get_object()
        
        # 1. Authenticated User Check
        if request.user.is_authenticated:
            pass # Permission class IsBookingOwner handles this? No, we might need manual check if permission is relaxed
            # If strictly using IsBookingOwner in get_permissions, this block is safe.
            # BUT: We are relaxing get_permissions to allow guests!
        
        # 2. Guest Verification Logic
        if not request.user.is_authenticated:
            if booking.user is not None:
                return Response(
                    {"detail": "This booking belongs to a registered user. Please log in to cancel."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = GuestCancellationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            email_input = serializer.validated_data['guest_email']
            if email_input.lower().strip() != booking.guest_email.lower().strip():
                return Response(
                    {"detail": "Email does not match the booking record."},
                    status=status.HTTP_403_FORBIDDEN
                )

        try:
            cancelled_booking = BookingService.cancel_booking(booking)
        except BookingConflict as e:
            return Response(
                _with_booking_no_refund_policy(
                    {"detail": str(e)},
                    cancellation_effect="booking_not_cancelled",
                ),
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            _with_booking_no_refund_policy(
                BookingResponseSerializer(
                    cancelled_booking, context=self.get_serializer_context()
                ).data
            ),
            status=status.HTTP_200_OK
        )
    @action(detail=True, methods=["post"],serializer_class=PartialCancelSerializer, url_path="partial-cancel")
    def partial_cancel(self, request, pk=None):
        serializer = PartialCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item_id = serializer.validated_data["item_id"]
        units_to_cancel = serializer.validated_data["units_to_cancel"]

        booking = self.get_object()

        try:
            booking_item = booking.items.get(id=item_id)
        except BookingItem.DoesNotExist:
            raise NotFound("Booking item not found")

        updated_booking = BookingService.partial_cancel_booking(
            booking_item,
            units_to_cancel
        )

        return Response(
            BookingResponseSerializer(
                updated_booking, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_path='workspace-bookings')
    def workspace_bookings(self, request):
        user = request.user
        
        if not user.workspace:
             return Response(
                {"detail": "No workspace assigned to this user."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        workspace = user.workspace
        queryset = self.get_queryset()
        
        if hasattr(workspace, 'is_hotel') or workspace.__class__.__name__ == 'HotelProfile':
            queryset = queryset.filter(items__room__hotel=workspace).distinct()
            
        elif hasattr(workspace, 'is_guesthouse') or workspace.__class__.__name__ == 'GuestHouseProfile':
             return Response([])
             
        return Response(
            BookingResponseSerializer(queryset, many=True).data
        )


@search_schema
class StaySearchView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'availability_check'

    def get(self, request):
        city = request.query_params.get("city")
        check_in_date = request.query_params.get("check_in_date")
        check_out_date = request.query_params.get("check_out_date")
        guests = request.query_params.get("guests")

        if not all([city, check_in_date, check_out_date, guests]):
            return Response({"detail": "Missing required parameters."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            guests_int = int(guests)
            if guests_int < 1:
                return Response({"detail": "Guest count must be at least 1."},
                                status=status.HTTP_400_BAD_REQUEST)
            if guests_int > 50:
                return Response({"detail": "Guest count cannot exceed 50."},
                                status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"detail": "Guest count must be a valid integer."},
                            status=status.HTTP_400_BAD_REQUEST)

        check_in_date = parse_date(check_in_date)
        check_out_date = parse_date(check_out_date)

        if not check_in_date or not check_out_date:
            return Response({"detail": "Invalid date format."},
                            status=status.HTTP_400_BAD_REQUEST)

        if check_out_date <= check_in_date:
            return Response(
                {"detail": "Check-out date must be after check-in date."},
                status=status.HTTP_400_BAD_REQUEST
            )

        stays = StayAvailabilityService.search_stays(
            city,
            check_in_date,
            check_out_date,
            number_of_guests=int(guests),
        )

        results = []
        for stay_data in stays:
            hotel = stay_data["hotel"]
            hotel_result = {
                "hotel_id": hotel.id,
                "hotel_name": hotel.company.name,
                "city": hotel.company.address.city,
                "stars": hotel.stars,
                "featured": hotel.featured,
                "images": hotel.images.all(),
                "facilities": hotel.facilities.all(),
                "rooms": []
            }
            
            duration = (check_out_date - check_in_date).days or 1
            for room_data in stay_data["rooms"]:
                room = room_data["room"]
                base_price = room.base_price
                
                preview_total = base_price * duration
                preview_min = base_price
                preview_has_discount = False
                display_price = base_price
                
                use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
                if use_seasonal:
                    room_lines = PriceService.resolve_price_details_batch(room, check_in_date, check_out_date)
                    room_prices = [Decimal(str(line['price_per_unit'])) for line in room_lines]

                    if room_prices:
                        preview_total = sum(room_prices)
                        preview_min = min(room_prices)
                        preview_has_discount = any(p < base_price for p in room_prices)
                        display_price = preview_min if preview_has_discount else base_price

                hotel_result["rooms"].append({
                    "id": room.id,
                    "title": room.title,
                    "description": room.description or "",
                    "base_price": base_price,
                    "display_price": display_price,
                    "preview_min_price": preview_min,
                    "preview_total": preview_total,
                    "preview_has_discount": preview_has_discount,
                    "nights": duration,
                    "number_of_guests": room.number_of_guests,
                    "bed_type": room.bed_type,
                    "room_size_sqm": room.room_size_sqm,
                    "available_units": room_data["available_units"]
                })
            
            # Use the stay total for the cheapest room as the hotel-level total
            if hotel_result["rooms"]:
                hotel_result["total_price"] = min(r["preview_total"] for r in hotel_result["rooms"])
                hotel_result["base_price"] = min(r["display_price"] for r in hotel_result["rooms"])
                first_room = stay_data["rooms"][0]["room"]
                hotel_result["currency"] = getattr(first_room, "currency", "ETB")
            
            results.append(hotel_result)

        paginator = StandardResultsSetPagination()
        paginated_results = paginator.paginate_queryset(results, request)
        
        # Resolve favorites once per request for hotel search results
        try:
            ct = ContentType.objects.get(app_label="account", model="hotelprofile")
        except Exception:
            ct = None

        fav_ids = get_favorite_object_ids(request.user, ct) if ct is not None else set()

        display_currency = get_display_currency(request)
        serializer = SearchResultSerializer(
            paginated_results, 
            many=True, 
            context={
                "request": request, 
                "favorite_object_ids": fav_ids,
                "display_currency": display_currency
            }
        )
        return paginator.get_paginated_response(serializer.data)
class StayAvailabilityUpdateView(APIView):
    serializer_class = StayAvailabilityUpdateSerializer

    def get_permissions(self):
        """
        Only company owners of the hotel or admin can update availability.
        """
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Inventory Management"],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def put(self, request, pk):
        """
        Update a StayAvailability instance.
        Only the hotel owner (company) or admin can update.
        """
        stay_availability = get_object_or_404(StayAvailability, pk=pk)
        
        # Check if user has permission to update this availability
        user = request.user
        
        # Admin can always update
        is_admin = user.is_superuser or (
            hasattr(user, 'role') and
            user.role and
            user.role.code == RoleCode.ADMIN.value
        )
        
        if not is_admin:
            # Check if user owns the hotel
            hotel = stay_availability.hotel
            if hasattr(hotel, 'company') and hotel.company:
                if not (hasattr(hotel.company, 'user') and hotel.company.user == user):
                    return Response(
                        {"detail": "You do not have permission to update this availability."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                return Response(
                    {"detail": "You do not have permission to update this availability."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        serializer = StayAvailabilityUpdateSerializer(
            instance=stay_availability,
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "id": str(stay_availability.id),
                **serializer.data,
                "detail": "Stay availability updated successfully."
            },
            status=status.HTTP_200_OK
        )
class CarAvailabilityUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CarAvailabilityUpdateSerializer

    def _can_update_availability(self, user, availability):
        if user.is_superuser or (
            hasattr(user, 'role') and
            user.role and
            user.role.code == RoleCode.ADMIN.value
        ):
            return True

        car = availability.car_listing
        company = getattr(car, 'company', None)
        if company:
            if getattr(company, 'user', None) == user:
                return True
            if getattr(user, 'company', None) == company:
                return True

        individual_owner = getattr(car, 'individual_owner', None)
        if individual_owner and getattr(user, 'individual_owner', None) == individual_owner:
            return True

        return False

    @extend_schema(
        request=CarAvailabilityUpdateSerializer,
        responses={
            200: CarAvailabilityUpdateSerializer,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
    )
    def patch(self, request, pk, format=None):
        """Update a CarAvailability instance (partial update)."""
        availability = get_object_or_404(
            CarAvailability.objects.select_related(
                'car_listing',
                'car_listing__company',
                'car_listing__individual_owner',
            ),
            pk=pk,
        )
        if not self._can_update_availability(request.user, availability):
            return Response(
                {"detail": "You do not have permission to update this availability."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Set partial=True to allow missing fields
        serializer = CarAvailabilityUpdateSerializer(availability, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
@extend_schema(responses=EventSpaceListingResponseSerializer)
class EventSpaceListingViewSet(SavedListingDeletionNotificationMixin, AbstractModelViewSet):
    """
    ViewSet for viewing and managing Event Space Listings, including 
    handling seasonal pricing display.
    """
    serializer_class = EventSpaceListingSerializer
    # Pre-fetch related data for efficient retrieval
    queryset = EventSpaceListing.objects.all().select_related(
        "hotel", "address"
    ).prefetch_related(
        "images", "amenities", "availability" 
    )
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = EventSpaceFilter # Use the dedicated filter class
    search_fields = ['title', 'description', 'address__city', 'address__sub_city']

    # --- Permission Logic ---
    def get_permissions(self):
        """
        Applies access control based on the action and user role.
        """
        if self.action == 'create':
            # Only authenticated users (Company/Admin) can create listings
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve', 'search']:
            # Public access for reading listings
            return [AllowAny()]
        elif self.action in ["verify", "unverify"]:
            return [IsAdmin()]
        else:
            # Update/Delete requires the user to own the listing
            return [IsListingOwner()]

    # --- Queryset Logic ---
    def get_queryset(self):
        queryset = super().get_queryset()
        
        user = self.request.user
        managed_only = self.request.query_params.get('managed') == 'true'

        # Admin sees all
        if user and (user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value)):
            return queryset

        if managed_only and user and user.is_authenticated:
            company = getattr(user, 'company', None) or getattr(user, 'profile', None)
            individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
            
            q = Q()
            if company:
                q |= Q(hotel__company=company)
            if individual_owner:
                 q |= Q(hotel__individual_owner=individual_owner) # Adjusting based on RoomListing pattern
            return queryset.filter(q).order_by("-created_at")

        return queryset.filter(is_active=True).order_by("-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        context["display_currency"] = get_display_currency(self.request)
        return context

    # --- Retrieve (Detail) Action ---
    def retrieve(self, request, *args, **kwargs):
        """
        Return event space detail with optional seasonal display price 
        when date query params are provided.
        """
        instance = self.get_object()
        serializer = EventSpaceListingResponseSerializer(instance, context=self.get_serializer_context())
        data = serializer.data

        # Hydrate legacy pricing fields from price_quote for backward compatibility
        quote = data.get('price_quote')
        if quote:
            data['preview_min_price'] = quote['min_nightly_price']
            data['preview_total'] = quote['base_total']
            data['preview_has_discount'] = quote['has_discount']
            data['display_price'] = quote['min_nightly_price'] if quote['has_discount'] else data.get('base_price')
        else:
            data['display_price'] = data.get('base_price')

        return Response(data)

    # --- List Action ---
    def list(self, request, *args, **kwargs):
        """
        List event spaces; computes display_price and preview fields for each 
        listing if date params are provided.
        """
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        listings = page if page is not None else list(qs)

        serialized = []
        for listing in listings:
            serializer = EventSpaceListingResponseSerializer(listing, context=self.get_serializer_context())
            data = serializer.data
            
            # Hydrate legacy pricing fields from price_quote for backward compatibility
            quote = data.get('price_quote')
            if quote:
                data['preview_min_price'] = quote['min_nightly_price']
                data['preview_total'] = quote['base_total']
                data['preview_has_discount'] = quote['has_discount']
                data['display_price'] = quote['min_nightly_price'] if quote['has_discount'] else data.get('base_price')
            else:
                data['display_price'] = data.get('base_price')

            serialized.append(data)

        if page is not None:
            return self.get_paginated_response(serialized)

        return Response(serialized)
    @extend_schema(
    summary="Search available event spaces",
    description="Searches available event spaces by date, quantity, and optional address.",
    parameters=[
        OpenApiParameter(
            name="quantity",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Required number of units"
        ),
        OpenApiParameter(
            name="check_in",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Check-in date (YYYY-MM-DD)"
        ),
        OpenApiParameter(
            name="check_out",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Check-out date (YYYY-MM-DD)"
        ),
        OpenApiParameter(
            name="address",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Optional address search term"
        ),
    ],
    responses={200: EventSpaceListingSerializer(many=True)}
)
    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Searches available event spaces by date, quantity, and address.
        """
        try:
            quantity_str = request.query_params.get('quantity')
            check_in_str = request.query_params.get('check_in')
            check_out_str = request.query_params.get('check_out')
            address_query = request.query_params.get('address')

            if not all([quantity_str, check_in_str, check_out_str]):
                return Response(
                    {"error": "Missing required query parameters: quantity, check_in, check_out."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            required_quantity = int(quantity_str)
            check_in_date = date.fromisoformat(check_in_str)
            check_out_date = date.fromisoformat(check_out_str)

        except (ValueError, TypeError) as e:
            return Response(
                {"error": f"Invalid parameter format: {e}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        available_listings = EventSpaceAvailabilityService.search_available_listings(
            check_in_date,
            check_out_date,
            required_quantity,
            address_query=address_query,
        )

        serializer = self.get_serializer(available_listings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: EventSpaceListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAdmin])
    def verify(self, request, pk=None):
        event_space = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        verify_listing(
            event_space,
            request.user,
            verification_note=action_serializer.validated_data.get("verification_note"),
        )
        serializer = EventSpaceListingResponseSerializer(event_space, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=VerifyActionSerializer,
        responses={200: EventSpaceListingResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unverify", permission_classes=[IsAdmin])
    def unverify(self, request, pk=None):
        event_space = self.get_object()
        action_serializer = VerifyActionSerializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        unverify_listing(event_space, request.user)
        serializer = EventSpaceListingResponseSerializer(event_space, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

@extend_schema(
    responses=EventSpaceBookingResponseSerializer,
)
@extend_schema(
    methods=['post'],
    summary="Create a new event space booking (supports guest checkout)",
    description="""
    Initiates a booking for an event space.
    - Supports both authenticated users and guest checkout.
    - If not logged in, guest details must be provided.
    - Guest checkout now requires a prior `guest-otp/request/` call and both `otp_challenge_id` and `otp_code` on create.
    - Captures additional fields for `event_type`.
    - Returns a pending booking with a `booking_reference`.
    """,
    request=EventSpaceBookingSerializer,
    responses={201: EventSpaceBookingResponseSerializer}
)
class EventSpaceBookingViewSet(AbstractModelViewSet):
    """
    ViewSet for viewing and managing Event Space Bookings (Create/List/Retrieve only).
    """
    # Only allow GET (list/retrieve) and POST (create)
    http_method_names = ["get", "post"] 
    serializer_class = EventSpaceBookingSerializer
    throttle_scope = None
    ordering = ['-created_at']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context
    
    # Prefetch related data for efficiency
    queryset = EventSpaceBooking.objects.prefetch_related(
        "items", 
        "items__event_space"
    )
    filter_backends = [DjangoFilterBackend]
    # Use the dedicated filter class (must be implemented)
    filterset_class = EventSpaceBookingFilter 

    # --- Permissions ---
    def get_permissions(self):
        """
        Applies access control based on the action and user role.
        """
        if self.action in ['create', 'lookup', 'price_preview', 'guest_otp']:
            # Allow guests to create and lookup bookings
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            # All authenticated users can see their permitted list/detail
            return [IsAuthenticated()]
        # Removed: partial_cancel and rate_booking actions
        else:
            return [IsAuthenticated()]

    def get_throttles(self):
        if self.action in ['create', 'guest_otp']:
            self.throttle_scope = 'booking_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    # --- Queryset Filtering ---
    def get_queryset(self):
        """
        Filter bookings based on user role: User, Company, or Admin.
        
        Default: Returns only user's PERSONAL bookings (where they are the guest).
        Mode='host': Returns bookings for the user's PROPERTIES (where they are the host).
        """
        user = self.request.user
        if not user or not user.is_authenticated:
            return EventSpaceBooking.objects.none()
        
        queryset = super().get_queryset() # Starts with the prefetched queryset
        
        # Admin sees all
        if user.is_superuser or (
            hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value
        ):
            return queryset
        
        
        # Check for mode parameter (Feature branch logic)
        mode = self.request.query_params.get('mode')
        if mode == 'host':
            if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
                if hasattr(user, 'profile') and user.profile:
                    company = user.profile
                    try:
                        hotel = HotelProfile.objects.get(company=company)
                        
                        return queryset.filter(
                            items__event_space__hotel=hotel
                        ).distinct()
                    except HotelProfile.DoesNotExist:
                        return queryset.none()
            return queryset.none()

        # Users see only their own bookings
        user_bookings = queryset.filter(user=user).distinct()
        
        if self.request.query_params.get('as_guest') == 'true':
            return user_bookings
        
        # Company sees bookings for their hotels (Development branch logic)
        if hasattr(user, 'role') and user.role and user.role.code == RoleCode.COMPANY.value:
            if hasattr(user, 'profile') and user.profile:
                company = user.profile
                try:
                    hotel = HotelProfile.objects.get(company=company)
                    
                    hotel_bookings = queryset.filter(
                        items__event_space__hotel=hotel
                    ).distinct()
                    
                    return (user_bookings | hotel_bookings).distinct()
                except HotelProfile.DoesNotExist:
                    pass
        
        # Default: Return only the user's own bookings
        return user_bookings

    def perform_create(self, serializer):
        """Passes the request user to the serializer's create method."""
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)

    @extend_schema(
        summary="Request event-space booking guest phone OTP",
        description="Issue a phone OTP challenge before creating an event-space booking as a guest.",
        request=GuestBookingOtpRequestSerializer,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="guest-otp/request", permission_classes=[AllowAny])
    def guest_otp(self, request):
        return _request_guest_booking_otp(request, booking_type="eventspace")

    @extend_schema(request=EventSpaceBookingSerializer, responses=EventSpaceBookingSerializer)
    @action(detail=False, methods=['post'], url_path='walk-in', permission_classes=[IsAuthenticated])
    def walk_in(self, request, *args, **kwargs):
        """
        Create a walk-in booking. 
        Passes is_walk_in=True via context to trigger staff privileges check.
        Requires authentication.
        """
        # Default currency to ETB for walk-ins if not specified
        data = request.data.copy()
        if 'payment_currency' not in data:
            data['payment_currency'] = 'ETB'
        
        # Pass is_walk_in via context, not data
        context = {**self.get_serializer_context(), 'is_walk_in': True}
        serializer = self.get_serializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(
        summary="Lookup event space booking status (Guest)",
        description="Retrieve event space booking details using reference and guest email. No login required.",
        parameters=[
            OpenApiParameter("reference", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter("email", OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: EventSpaceBookingResponseSerializer, 404: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='lookup', permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = BookingLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        reference = serializer.validated_data['reference']
        email = serializer.validated_data['email']
        
        booking = get_object_or_404(
            EventSpaceBooking.objects.prefetch_related("items", "items__event_space"),
            booking_reference=reference,
            guest_email=email
        )
        
        response_serializer = EventSpaceBookingResponseSerializer(booking, context=self.get_serializer_context())
        return Response(response_serializer.data)

    @extend_schema(
        summary="Price Preview for event space selection",
        description="Get a consolidated price quote for a selection of event spaces before booking.",
        request=EventSpaceBookingPreviewSerializer,
        parameters=[
            OpenApiParameter(
                name="display_currency",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional: Request price preview in a specific currency (e.g., USD) using triangulation."
            )
        ],
        responses={
            200: PricePreviewResponseSerializer,
            400: OpenApiTypes.OBJECT
        }
    )
    @action(detail=False, methods=['post'], url_path='price-preview')
    def price_preview(self, request):
        serializer = EventSpaceBookingPreviewSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        check_in = data['check_in_date']
        check_out = data['check_out_date']
        items = data['items']
        preview_phone = data.get('guest_phone') or (request.user.phone if request.user.is_authenticated else None)
        
        # validate availability (lock=False for previews)
        spaces_info = [{"space_listing": item["event_space"], "quantity": item["units_booked"]} for item in items]
        try:
            EventSpaceAvailabilityService.validate_availability(spaces_info, check_in, check_out, lock=False)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
            
        nights = (check_out - check_in).days
        total_items = []
        item_subtotals = []
        
        currencies = {item["event_space"].currency for item in items}
        if len(currencies) > 1:
            return Response({"detail": "All selected items must have the same currency."}, status=400)
        currency = list(currencies)[0] if currencies else "ETB"
        display_currency = get_display_currency(request)
        
        for item in items:
            space = item["event_space"]
            units = item["units_booked"]
            
            price_details = PriceService.resolve_price_details_batch(space, check_in, check_out)
            item_base_total = sum(Decimal(str(d['price_per_unit'])) for d in price_details) * units
            
            item_subtotals.append(item_base_total)
            
            total_items.append({
                "id": str(space.id),
                "title": space.title,
                "units": units,
                "price_per_unit": f"{(price_details[0]['price_per_unit'] if price_details else space.base_price):.2f}",
                "subtotal": f"{item_base_total:.2f}",
                "breakdown": price_details
            })
            
        return Response({
            "nights": nights,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(
                item_subtotals,
                currency,
                display_currency,
                items=total_items,
                fee_rate=get_effective_platform_fee_rate(phone=preview_phone),
            )
        })


@extend_schema(tags=["Terms & Conditions"])
class TermsAndConditionsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for retrieving Terms & Conditions.
    
    - list: Get all T&C (admin only)
    - retrieve: Get specific T&C by ID  
    - hotel/{hotel_id}: Get active T&C for a hotel
    """
    from apps.listing.serializers import TermsAndConditionsSerializer
    from apps.listing.models import TermsAndConditions
    
    serializer_class = TermsAndConditionsSerializer
    permission_classes = [AllowAny]
    queryset = TermsAndConditions.objects.filter(is_active=True)
    
    @extend_schema(
        summary="Get active Terms & Conditions for a hotel",
        description="Retrieve the currently active T&C for a specific hotel",
        parameters=[
            OpenApiParameter(
                "hotel_id",
                OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: TermsAndConditionsSerializer, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='hotel/(?P<hotel_id>[^/.]+)')
    def hotel_terms(self, request, hotel_id=None):
        """Get active T&C for a hotel"""
        from apps.account.models import HotelProfile
        from apps.listing.services import TermsService
        
        hotel = get_object_or_404(HotelProfile, id=hotel_id)
        terms = TermsService.get_active_terms(content_object=hotel)
        
        if not terms:
            return Response(
                {"detail": "No terms and conditions available for this hotel."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.serializer_class(terms)
        return Response(serializer.data)

    @extend_schema(
        summary="Get active Terms & Conditions for a guest house",
        description="Retrieve the currently active T&C for a specific guest house profile",
        parameters=[
            OpenApiParameter("gh_id", OpenApiTypes.UUID, location=OpenApiParameter.PATH),
        ],
        responses={200: TermsAndConditionsSerializer, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='guesthouse/(?P<gh_id>[^/.]+)')
    def guesthouse_terms(self, request, gh_id=None):
        """Get active T&C for a guest house"""
        from apps.listing.models import GuestHouseProfile
        from apps.listing.services import TermsService
        
        gh = get_object_or_404(GuestHouseProfile, id=gh_id)
        terms = TermsService.get_active_terms(content_object=gh)
        
        if not terms:
            return Response(
                {"detail": "No terms and conditions available for this guest house."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.serializer_class(terms)
        return Response(serializer.data)

    @extend_schema(
        summary="Get active Terms & Conditions for a company (Car Rental)",
        description="Retrieve the currently active T&C for a specific company (Car Rental, etc.)",
        parameters=[
            OpenApiParameter("company_id", OpenApiTypes.UUID, location=OpenApiParameter.PATH),
        ],
        responses={200: TermsAndConditionsSerializer, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='company/(?P<company_id>[^/.]+)')
    def company_terms(self, request, company_id=None):
        """Get active T&C for a company"""
        from apps.account.models import CompanyProfile
        from apps.listing.services import TermsService
        
        company = get_object_or_404(CompanyProfile, id=company_id)
        terms = TermsService.get_active_terms(content_object=company)
        
        if not terms:
            return Response(
                {"detail": "No terms and conditions available for this company."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.serializer_class(terms)
        return Response(serializer.data)


@extend_schema(tags=["Accommodations"])
class AddonOfferingViewSet(AbstractModelViewSet):
    queryset = AddonOffering.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['hotel', 'category', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['display_order', 'price_per_unit', 'name']
    ordering = ['display_order', 'name']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["display_currency"] = get_display_currency(self.request)
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if user.is_authenticated and (user.is_superuser or (
            hasattr(user, 'role') and user.role and user.role.code == RoleCode.ADMIN.value
        )):
            return queryset

        if user.is_authenticated and hasattr(user, 'role') and user.role:
            if user.role.code == RoleCode.COMPANY.value:
                return queryset.filter(hotel__company__user=user)

        return queryset.filter(is_active=True)

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return AddonOfferingListSerializer
        return AddonOfferingSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsListingOwner()]

    def perform_create(self, serializer):
        hotel = serializer.validated_data.get('hotel')
        
        is_admin = self.request.user.is_superuser or (
            hasattr(self.request.user, 'role') and 
            self.request.user.role and 
            self.request.user.role.code == RoleCode.ADMIN.value
        )
        
        if not is_admin:
            if not hotel.company or not hotel.company.user == self.request.user:
                raise PermissionDenied("You can only create addons for your own hotel.")
        
        serializer.save()

    @extend_schema(
        summary="List addons for a specific hotel",
        description="Filter offerings by hotel ID. Returns public-facing addon details.",
        parameters=[
            OpenApiParameter("hotel", OpenApiTypes.UUID, OpenApiParameter.QUERY, description="Filter by Hotel UUID"),
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Filter by Category"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


@extend_schema(tags=["Season Management"])
class SeasonViewSet(viewsets.ModelViewSet):
    """
    API for Owners to manage Seasons (e.g., Summer, Christmas).
    """
    serializer_class = SeasonSerializer
    permission_classes = [IsCompanyOwner]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Season.objects.none()

        if user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            return Season.objects.all()

        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        from django.db.models import Q
        q = Q(company=None, individual_owner=None) # Global seasons

        if company:
            q |= Q(company=company)
        if individual_owner:
            q |= Q(individual_owner=individual_owner)
            
        return Season.objects.filter(q).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
        
        # Only admins can create global seasons (both null)
        # For owners/staff, we MUST assign their profile
        kwargs = {}
        if not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            if company:
                kwargs['company'] = company
            if individual_owner:
                kwargs['individual_owner'] = individual_owner
                
        serializer.save(**kwargs)


@extend_schema(tags=["Season Management"])
class SeasonalRateViewSet(viewsets.ModelViewSet):
    """
    API for Owners to manage Rates associated with Seasons.
    """
    serializer_class = SeasonalRateSerializer
    permission_classes = [IsCompanyOwner]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return SeasonalRate.objects.none()

        if user.is_superuser or (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            return SeasonalRate.objects.all()

        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)

        from django.db.models import Q
        q = Q(company=None, individual_owner=None)

        if company:
            q |= Q(company=company)
        if individual_owner:
            q |= Q(individual_owner=individual_owner)
            
        return SeasonalRate.objects.filter(q).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        company = getattr(user, 'company', None) or getattr(user, 'profile', None)
        individual_owner = getattr(user, 'individual_owner', None) or getattr(user, 'individual_owner_profile', None)
        
        kwargs = {}
        if not user.is_superuser and not (hasattr(user, 'role') and user.role and user.role.code == 'admin'):
            if company:
                kwargs['company'] = company
            if individual_owner:
                kwargs['individual_owner'] = individual_owner
                
        serializer.save(**kwargs)


class InventoryGridView(APIView):
    """
    Unified endpoint for the Owner Dashboard availability grid.
    Returns 30 days of availability and pricing for all units in a property.
    """
    permission_classes = [IsAuthenticated, IsListingOwner]

    @extend_schema(
        tags=["Inventory Management"],
        summary="Get 30-day availability and pricing grid",
        parameters=[
            OpenApiParameter("property_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("property_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True, enum=['hotel', 'guesthouse', 'eventspace']),
            OpenApiParameter("start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Default is today"),
            OpenApiParameter("days", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, default=30),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        property_id = request.query_params.get('property_id')
        property_type = request.query_params.get('property_type')
        start_date_str = request.query_params.get('start_date')
        days = int(request.query_params.get('days', 30))

        if not property_id or not property_type:
            return Response({"error": "property_id and property_type are required."}, status=400)

        from django.apps import apps
        try:
            if property_type == 'hotel':
                model = apps.get_model('account', 'HotelProfile')
            elif property_type == 'eventspace':
                 model = apps.get_model('listing', 'EventSpaceListing')
            elif property_type == 'guesthouse':
                model = apps.get_model('listing', 'GuestHouseProfile')
            else:
                return Response({"error": "Invalid property_type"}, status=400)
            
            prop_obj = model.objects.get(id=property_id)
            self.check_object_permissions(request, prop_obj)
        except Exception as e:
            return Response({"error": f"Access Denied or Property Not Found: {str(e)}"}, status=403)

        if start_date_str:
            start_date = parse_date(start_date_str)
        else:
            start_date = date.today()

        from apps.listing.services import InventoryGridService
        try:
            grid_data = InventoryGridService.get_availability_grid(
                property_id=property_id,
                property_type=property_type,
                start_date=start_date,
                days=days
            )
            return Response(grid_data)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


def _paginated_discovery_response_schema(name: str, result_serializer):
    return inline_serializer(
        name=name,
        fields={
            "count": serializers.IntegerField(),
            "total_pages": serializers.IntegerField(),
            "current_page": serializers.IntegerField(),
            "page_size": serializers.IntegerField(),
            "next": serializers.CharField(allow_null=True, required=False),
            "previous": serializers.CharField(allow_null=True, required=False),
            "results": result_serializer(many=True),
        },
    )


def _normalized_discovery_cache_key(prefix: str, payload: dict) -> str:
    normalized = []
    for key in sorted(payload.keys()):
        value = payload[key]
        if isinstance(value, Decimal):
            value = f"{value}"
        normalized.append(f"{key}:{value}")
    digest = hashlib.sha256("|".join(normalized).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


class NearbyListingsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Listings"],
        summary="Find listings nearby",
        parameters=[
            OpenApiParameter("lat", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("lng", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("radius_km", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("listing_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=DISCOVERY_LISTING_TYPE_ENUM),
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: _paginated_discovery_response_schema("NearbyListingsResponse", ProximityListingSerializer), 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        query_serializer = NearbyListingsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        cache_key = _normalized_discovery_cache_key(
            "listing:nearby",
            {
                "lat": _rounded_cache_value(params["lat"]),
                "lng": _rounded_cache_value(params["lng"]),
                "radius_km": params.get("radius_km", Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10)))),
                "listing_type": params.get("listing_type", "all"),
                "page": params.get("page") or request.query_params.get("page", 1),
            },
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        listings = _build_discovery_payload(
            params.get("listing_type", "all"),
            lat=params["lat"],
            lng=params["lng"],
            radius_km=params.get("radius_km", Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10)))),
            mode="nearby",
        )
        listings.sort(key=lambda item: item["distance_km"])
        response = _paginate_discovery_listings(request, listings, ProximityListingSerializer)
        cache.set(cache_key, response.data, DISCOVERY_CACHE_TTL)
        return response


class WithinBoundsListingsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Listings"],
        summary="Find listings within viewport bounds",
        parameters=[
            OpenApiParameter("north", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("south", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("east", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("west", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("listing_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=DISCOVERY_LISTING_TYPE_ENUM),
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: _paginated_discovery_response_schema("WithinBoundsListingsResponse", DiscoveryListingSerializer), 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        query_serializer = BoundsListingsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data
        bounds = {
            "north": params["north"],
            "south": params["south"],
            "east": params["east"],
            "west": params["west"],
        }

        cache_key = _normalized_discovery_cache_key(
            "listing:bounds",
            {
                "north": _rounded_cache_value(bounds["north"]),
                "south": _rounded_cache_value(bounds["south"]),
                "east": _rounded_cache_value(bounds["east"]),
                "west": _rounded_cache_value(bounds["west"]),
                "listing_type": params.get("listing_type", "all"),
                "page": params.get("page") or request.query_params.get("page", 1),
            },
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        listings = _build_discovery_payload(
            params.get("listing_type", "all"),
            bounds=bounds,
            mode="standard",
        )
        listings.sort(key=lambda item: item["_created_at"], reverse=True)
        response = _paginate_discovery_listings(request, listings, DiscoveryListingSerializer)
        cache.set(cache_key, response.data, MAP_PINS_CACHE_TTL)
        return response


class MapPinsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Listings"],
        summary="Get lightweight map pins",
        parameters=[
            OpenApiParameter("lat", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("lng", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("radius_km", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("north", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("south", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("east", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("west", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("listing_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=DISCOVERY_LISTING_TYPE_ENUM),
        ],
        responses={200: MapPinSerializer(many=True), 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        query_serializer = MapPinsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data
        has_lat_lng = params.get("lat") is not None and params.get("lng") is not None

        cache_key = _normalized_discovery_cache_key(
            "listing:pins",
            {
                "mode": "nearby" if has_lat_lng else "bounds",
                "lat": _rounded_cache_value(params["lat"]) if has_lat_lng else "",
                "lng": _rounded_cache_value(params["lng"]) if has_lat_lng else "",
                "radius_km": params.get("radius_km", Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10)))) if has_lat_lng else "",
                "north": _rounded_cache_value(params["north"]) if not has_lat_lng else "",
                "south": _rounded_cache_value(params["south"]) if not has_lat_lng else "",
                "east": _rounded_cache_value(params["east"]) if not has_lat_lng else "",
                "west": _rounded_cache_value(params["west"]) if not has_lat_lng else "",
                "listing_type": params.get("listing_type", "all"),
            },
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        if has_lat_lng:
            listings = _build_discovery_payload(
                params.get("listing_type", "all"),
                lat=params["lat"],
                lng=params["lng"],
                radius_km=params.get("radius_km", Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10)))),
                mode="nearby",
            )
            listings.sort(key=lambda item: item["distance_km"])
        else:
            bounds = {
                "north": params["north"],
                "south": params["south"],
                "east": params["east"],
                "west": params["west"],
            }
            listings = _build_discovery_payload(
                params.get("listing_type", "all"),
                bounds=bounds,
                mode="standard",
            )
            listings.sort(key=lambda item: item["_created_at"], reverse=True)

        pins = [
            build_map_pin(listing, listing["listing_type"])
            for listing in _top_pin_candidates(listings)
        ]
        response = Response(MapPinSerializer(pins, many=True, context={"request": request}).data)
        cache.set(cache_key, response.data, MAP_PINS_CACHE_TTL)
        return response


class FeedListingsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Listings"],
        summary="Get standard or proximity feed",
        parameters=[
            OpenApiParameter("listing_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=DISCOVERY_LISTING_TYPE_ENUM),
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200: _paginated_discovery_response_schema("FeedListingsResponse", ProximityListingSerializer),
            400: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request):
        query_serializer = FeedListingsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data
        return _build_feed_response(
            request,
            params.get("listing_type", "all"),
            page=params.get("page"),
        )


class ListingSearchView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Listings"],
        summary="Search listings with optional radius context",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("lat", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("lng", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("radius_km", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("sort_by", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=["distance", "price", "rating", "newest", "relevance"]),
            OpenApiParameter("listing_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=DISCOVERY_LISTING_TYPE_ENUM),
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: _search_response_schema("ListingSearchResponse"), 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        query_serializer = ListingSearchQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        query = (params.get("q") or "").strip()
        lat = params.get("lat")
        lng = params.get("lng")
        radius_km = params.get("radius_km", Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))))
        listing_type = params.get("listing_type", "all")
        has_location = lat is not None and lng is not None

        if not query and not has_location:
            return _build_feed_response(request, listing_type, page=params.get("page"))

        if query:
            listings = _filter_search_payload(listing_type, query)
        else:
            listings = _build_discovery_payload(
                listing_type,
                lat=lat,
                lng=lng,
                radius_km=radius_km,
                mode="nearby",
            )

        if has_location and query:
            listings = _apply_radius_to_payload(listings, lat, lng, radius_km)

        sort_by = params.get("sort_by") or ("distance" if has_location else "relevance")
        listings = _apply_search_sort(listings, sort_by, has_location=has_location)
        response = _paginate_discovery_listings(request, listings, ListingSearchResultSerializer)
        return _attach_search_context(response, lat=lat, lng=lng, radius_km=radius_km) if has_location else response


class ListingSearchSuggestionsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Listings"],
        summary="Search suggestions for listing discovery",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("lat", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("lng", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("listing_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=DISCOVERY_LISTING_TYPE_ENUM),
        ],
        responses={200: SearchSuggestionSerializer(many=True), 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        query_serializer = SearchSuggestionsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        query = params["q"].strip()
        lat = params.get("lat")
        lng = params.get("lng")
        limit = params.get("limit", 5)
        listing_type = params.get("listing_type", "all")

        cache_key = _normalized_discovery_cache_key(
            "search:suggestions",
            {
                "q": query.lower(),
                "lat": _rounded_cache_value(lat) if lat is not None else "",
                "lng": _rounded_cache_value(lng) if lng is not None else "",
                "limit": limit,
                "listing_type": listing_type,
            },
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        suggestions = _filter_search_payload(listing_type, query)
        if lat is not None and lng is not None:
            suggestions = _apply_radius_to_payload(
                suggestions,
                lat,
                lng,
                Decimal(str(getattr(settings, "DEFAULT_PROXIMITY_RADIUS_KM", 10))),
            )

        suggestions = _apply_search_sort(
            suggestions,
            "distance" if lat is not None and lng is not None else "relevance",
            has_location=lat is not None and lng is not None,
        )[:limit]

        payload = SearchSuggestionSerializer(suggestions, many=True, context={"request": request}).data
        cache.set(cache_key, payload, 60)
        return Response(payload)


    
