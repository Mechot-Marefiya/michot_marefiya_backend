from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.account.models import HotelProfile
from apps.listing.models import (
    CarListing,
    CarSaleListing,
    EventSpaceListing,
    GuestHouseProfile,
    GuestHouseRoom,
    PropertyListing,
    PropertySaleListing,
    RoomListing,
)
from apps.promotions.models import PromotionCampaign, PromotionPlacement


PROMOTION_CACHE_VERSION_KEY = "promotions:placements:version"
PROMOTION_CACHE_TTL = 300
PROMOTABLE_MODELS = (
    HotelProfile,
    RoomListing,
    GuestHouseProfile,
    GuestHouseRoom,
    CarListing,
    CarSaleListing,
    PropertyListing,
    PropertySaleListing,
    EventSpaceListing,
)


def get_promotable_content_type_ids() -> set[int]:
    return {
        ContentType.objects.get_for_model(model).id
        for model in PROMOTABLE_MODELS
    }


def _cache_version() -> int:
    version = cache.get(PROMOTION_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(PROMOTION_CACHE_VERSION_KEY, version, timeout=None)
    return int(version)


def _cache_key(slot_type=None, category=None) -> str:
    version = _cache_version()
    if category:
        return f"promotions:v{version}:placements:category:{category}"
    if slot_type:
        return f"promotions:v{version}:placements:{slot_type}"
    return f"promotions:v{version}:placements:all"


def invalidate_active_placement_cache() -> None:
    try:
        cache.incr(PROMOTION_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(PROMOTION_CACHE_VERSION_KEY, 2, timeout=None)


def get_active_placements(slot_type=None, category=None):
    cache_key = _cache_key(slot_type=slot_type, category=category)
    cached_ids = cache.get(cache_key)
    if cached_ids is not None:
        preserved_order = {str(pk): index for index, pk in enumerate(cached_ids)}
        placements = list(
            PromotionPlacement.objects.filter(id__in=cached_ids)
            .select_related("campaign", "content_type")
            .order_by("display_order", "-created_at")
        )
        return sorted(placements, key=lambda placement: preserved_order.get(str(placement.id), 0))

    now = timezone.now()
    queryset = (
        PromotionPlacement.objects.filter(
            is_active=True,
            campaign__status=PromotionCampaign.Status.ACTIVE,
            campaign__starts_at__lte=now,
            campaign__ends_at__gte=now,
        )
        .select_related("campaign", "content_type")
        .order_by("display_order", "-created_at")
    )
    if slot_type:
        queryset = queryset.filter(slot_type=slot_type)
    if category:
        queryset = queryset.filter(target_category=category)

    placements = list(queryset)
    cache.set(cache_key, [str(placement.id) for placement in placements], timeout=PROMOTION_CACHE_TTL)
    return placements


@transaction.atomic
def activate_campaign(campaign) -> None:
    campaign.status = PromotionCampaign.Status.ACTIVE
    campaign.save(update_fields=["status", "updated_at"])
    campaign.placements.update(is_active=True)
    invalidate_active_placement_cache()


@transaction.atomic
def deactivate_campaign(campaign) -> None:
    campaign.status = PromotionCampaign.Status.EXPIRED
    campaign.save(update_fields=["status", "updated_at"])
    campaign.placements.update(is_active=False)
    invalidate_active_placement_cache()


def record_impression(placement, user, ip) -> None:
    from apps.promotions.tasks import record_impression_async

    user_id = getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None
    record_impression_async.delay(str(placement.id), str(user_id) if user_id else None, ip)


def record_click(placement, user, ip) -> None:
    from apps.promotions.tasks import record_click_async

    user_id = getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None
    record_click_async.delay(str(placement.id), str(user_id) if user_id else None, ip)
