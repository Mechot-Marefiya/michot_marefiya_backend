from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils import timezone

from apps.promotions.models import PromotionCampaign, PromotionClick, PromotionImpression, PromotionPlacement
from apps.promotions.services import PROMOTION_CACHE_VERSION_KEY
from apps.promotions.tasks import record_click_async, record_impression_async, sync_campaign_statuses

pytestmark = pytest.mark.django_db


def _campaign(user, *, status, starts_at=None, ends_at=None):
    now = timezone.now()
    return PromotionCampaign.objects.create(
        name=f"{status} campaign",
        advertiser=user,
        status=status,
        starts_at=starts_at or now - timedelta(hours=1),
        ends_at=ends_at or now + timedelta(days=1),
    )


def _placement(campaign, car_listing, *, active=False):
    return PromotionPlacement.objects.create(
        campaign=campaign,
        slot_type=PromotionPlacement.SlotType.FEATURED_LISTING,
        content_type=ContentType.objects.get_for_model(car_listing),
        object_id=car_listing.id,
        target_category="cars",
        is_active=active,
    )


def test_sync_campaign_statuses_activates_scheduled_campaign(admin_user, car_listing):
    cache.set(PROMOTION_CACHE_VERSION_KEY, 1, timeout=None)
    campaign = _campaign(admin_user, status=PromotionCampaign.Status.SCHEDULED)
    placement = _placement(campaign, car_listing, active=False)

    result = sync_campaign_statuses()

    campaign.refresh_from_db()
    placement.refresh_from_db()
    assert result["activated"] == 1
    assert campaign.status == PromotionCampaign.Status.ACTIVE
    assert placement.is_active is True
    assert cache.get(PROMOTION_CACHE_VERSION_KEY) == 2


def test_sync_campaign_statuses_deactivates_expired_campaign(admin_user, car_listing):
    cache.set(PROMOTION_CACHE_VERSION_KEY, 1, timeout=None)
    campaign = _campaign(
        admin_user,
        status=PromotionCampaign.Status.ACTIVE,
        starts_at=timezone.now() - timedelta(days=3),
        ends_at=timezone.now() - timedelta(minutes=1),
    )
    placement = _placement(campaign, car_listing, active=True)

    result = sync_campaign_statuses()

    campaign.refresh_from_db()
    placement.refresh_from_db()
    assert result["expired"] == 1
    assert campaign.status == PromotionCampaign.Status.EXPIRED
    assert placement.is_active is False
    assert cache.get(PROMOTION_CACHE_VERSION_KEY) == 2


def test_record_impression_async_creates_row(admin_user, car_listing):
    campaign = _campaign(admin_user, status=PromotionCampaign.Status.ACTIVE)
    placement = _placement(campaign, car_listing, active=True)

    assert record_impression_async(str(placement.id), str(admin_user.id), "127.0.0.1") is True

    impression = PromotionImpression.objects.get()
    assert impression.placement == placement
    assert impression.user == admin_user
    assert impression.ip_address == "127.0.0.1"


def test_record_click_async_creates_row(admin_user, car_listing):
    campaign = _campaign(admin_user, status=PromotionCampaign.Status.ACTIVE)
    placement = _placement(campaign, car_listing, active=True)

    assert record_click_async(str(placement.id), str(admin_user.id), "127.0.0.1") is True

    click = PromotionClick.objects.get()
    assert click.placement == placement
    assert click.user == admin_user
    assert click.ip_address == "127.0.0.1"


def test_sync_campaign_statuses_beat_schedule_registered():
    schedule = settings.CELERY_BEAT_SCHEDULE["sync-promotion-campaign-statuses-every-5-minutes"]

    assert schedule["task"] == "apps.promotions.tasks.sync_campaign_statuses"
