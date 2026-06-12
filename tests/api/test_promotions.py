from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils import timezone

from apps.promotions.models import PromotionCampaign, PromotionPlacement

pytestmark = pytest.mark.django_db


def _campaign_payload(user, **overrides):
    now = timezone.now()
    payload = {
        "name": "Holiday Featured Listings",
        "advertiser": str(user.id),
        "status": PromotionCampaign.Status.SCHEDULED,
        "starts_at": (now + timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
        "budget": "5000.00",
    }
    payload.update(overrides)
    return payload


def _create_campaign(user, *, status=PromotionCampaign.Status.ACTIVE, starts_at=None, ends_at=None):
    now = timezone.now()
    return PromotionCampaign.objects.create(
        name="Promo Campaign",
        advertiser=user,
        status=status,
        starts_at=starts_at or now - timedelta(hours=1),
        ends_at=ends_at or now + timedelta(days=3),
        budget=Decimal("2500.00"),
    )


def _create_listing_placement(campaign, listing, **overrides):
    content_type = ContentType.objects.get_for_model(listing)
    defaults = {
        "campaign": campaign,
        "slot_type": PromotionPlacement.SlotType.FEATURED_LISTING,
        "content_type": content_type,
        "object_id": listing.id,
        "target_category": "cars",
        "display_order": 1,
        "is_active": True,
    }
    defaults.update(overrides)
    return PromotionPlacement.objects.create(**defaults)


def test_post_campaign_create_success(admin_client, admin_user):
    response = admin_client.post(
        "/api/v1/promotions/campaigns/",
        _campaign_payload(admin_user),
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Holiday Featured Listings"
    assert data["status"] == PromotionCampaign.Status.SCHEDULED


def test_post_campaign_placement_targeting_listing_success(admin_client, admin_user, car_listing):
    campaign = _create_campaign(admin_user)
    content_type = ContentType.objects.get_for_model(car_listing)

    response = admin_client.post(
        f"/api/v1/promotions/campaigns/{campaign.id}/placements/",
        {
            "slot_type": PromotionPlacement.SlotType.FEATURED_LISTING,
            "content_type": content_type.id,
            "object_id": str(car_listing.id),
            "target_category": "cars",
            "display_order": 1,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["object_id"] == str(car_listing.id)


def test_post_campaign_placement_targeting_category_success(admin_client, admin_user):
    campaign = _create_campaign(admin_user)

    response = admin_client.post(
        f"/api/v1/promotions/campaigns/{campaign.id}/placements/",
        {
            "slot_type": PromotionPlacement.SlotType.CATEGORY_BANNER,
            "target_category": "properties",
            "display_order": 2,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["target_category"] == "properties"


def test_get_campaigns_admin_only(admin_client, auth_client, api_client, admin_user):
    _create_campaign(admin_user)

    assert admin_client.get("/api/v1/promotions/campaigns/").status_code == 200
    assert auth_client.get("/api/v1/promotions/campaigns/").status_code == 403
    assert api_client.get("/api/v1/promotions/campaigns/").status_code == 401


def test_post_campaign_create_forbidden_for_non_admin(auth_client, user):
    response = auth_client.post(
        "/api/v1/promotions/campaigns/",
        _campaign_payload(user),
        format="json",
    )

    assert response.status_code == 403


def test_get_public_active_placements_returns_nested_listing(api_client, admin_user, car_listing):
    campaign = _create_campaign(admin_user)
    _create_listing_placement(campaign, car_listing)

    response = api_client.get("/api/v1/promotions/placements/")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    placement = data[0]
    assert placement["slot_type"] == PromotionPlacement.SlotType.FEATURED_LISTING
    assert placement["promoted_listing"]["id"] == str(car_listing.id)
    assert placement["promoted_listing"]["title"] == car_listing.title
    assert "budget" not in placement
    assert "advertiser" not in placement


@pytest.mark.parametrize(
    ("status_value", "starts_delta", "ends_delta"),
    [
        (PromotionCampaign.Status.EXPIRED, -5, -1),
        (PromotionCampaign.Status.DRAFT, -1, 5),
    ],
)
def test_get_public_placements_excludes_ineligible_campaigns(
    api_client,
    admin_user,
    car_listing,
    status_value,
    starts_delta,
    ends_delta,
):
    now = timezone.now()
    campaign = _create_campaign(
        admin_user,
        status=status_value,
        starts_at=now + timedelta(days=starts_delta),
        ends_at=now + timedelta(days=ends_delta),
    )
    _create_listing_placement(campaign, car_listing)

    response = api_client.get("/api/v1/promotions/placements/")

    assert response.status_code == 200
    assert response.json() == []


def test_get_public_placements_slot_type_filter(api_client, admin_user, car_listing):
    campaign = _create_campaign(admin_user)
    _create_listing_placement(campaign, car_listing, slot_type=PromotionPlacement.SlotType.FEATURED_LISTING)
    _create_listing_placement(
        campaign,
        car_listing,
        slot_type=PromotionPlacement.SlotType.HOME_BANNER,
        display_order=2,
    )

    response = api_client.get(
        "/api/v1/promotions/placements/",
        {"slot_type": PromotionPlacement.SlotType.HOME_BANNER},
    )

    assert response.status_code == 200
    assert [item["slot_type"] for item in response.json()] == [PromotionPlacement.SlotType.HOME_BANNER]


def test_get_public_placements_category_filter(api_client, admin_user, car_listing):
    campaign = _create_campaign(admin_user)
    _create_listing_placement(campaign, car_listing, target_category="cars")
    _create_listing_placement(campaign, car_listing, target_category="properties", display_order=2)

    response = api_client.get("/api/v1/promotions/placements/", {"category": "properties"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["promoted_category"]["id"] == "properties"


def test_get_public_placements_served_from_cache_on_second_call(api_client, admin_user, car_listing):
    cache.clear()
    campaign = _create_campaign(admin_user)
    placement = _create_listing_placement(campaign, car_listing)

    first_response = api_client.get("/api/v1/promotions/placements/")
    assert first_response.status_code == 200
    assert len(first_response.json()) == 1

    placement.is_active = False
    placement.save(update_fields=["is_active", "updated_at"])

    second_response = api_client.get("/api/v1/promotions/placements/")
    assert second_response.status_code == 200
    assert len(second_response.json()) == 1


@patch("apps.promotions.tasks.record_impression_async.delay")
def test_post_track_dispatches_impression_task(mock_delay, api_client, admin_user, car_listing):
    campaign = _create_campaign(admin_user)
    placement = _create_listing_placement(campaign, car_listing)

    response = api_client.post(
        "/api/v1/promotions/track/",
        {"placement_id": str(placement.id), "event_type": "impression"},
        format="json",
    )

    assert response.status_code == 204
    mock_delay.assert_called_once()


@patch("apps.promotions.tasks.record_click_async.delay")
def test_post_track_dispatches_click_task(mock_delay, api_client, admin_user, car_listing):
    campaign = _create_campaign(admin_user)
    placement = _create_listing_placement(campaign, car_listing)

    response = api_client.post(
        "/api/v1/promotions/track/",
        {"placement_id": str(placement.id), "event_type": "click"},
        format="json",
    )

    assert response.status_code == 204
    mock_delay.assert_called_once()
