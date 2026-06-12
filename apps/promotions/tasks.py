from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.promotions.models import PromotionCampaign, PromotionClick, PromotionImpression, PromotionPlacement
from apps.promotions.services import activate_campaign, deactivate_campaign


@shared_task
def sync_campaign_statuses():
    now = timezone.now()
    activated = 0
    expired = 0

    for campaign in PromotionCampaign.objects.filter(
        status=PromotionCampaign.Status.SCHEDULED,
        starts_at__lte=now,
        ends_at__gte=now,
    ):
        activate_campaign(campaign)
        activated += 1

    for campaign in PromotionCampaign.objects.filter(
        status=PromotionCampaign.Status.ACTIVE,
        ends_at__lt=now,
    ):
        deactivate_campaign(campaign)
        expired += 1

    return {"activated": activated, "expired": expired}


def _resolve_user(user_id):
    if not user_id:
        return None
    User = get_user_model()
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None


@shared_task
def record_impression_async(placement_id, user_id=None, ip=None):
    try:
        placement = PromotionPlacement.objects.get(id=placement_id)
    except PromotionPlacement.DoesNotExist:
        return False

    PromotionImpression.objects.create(
        placement=placement,
        user=_resolve_user(user_id),
        ip_address=ip or None,
    )
    return True


@shared_task
def record_click_async(placement_id, user_id=None, ip=None):
    try:
        placement = PromotionPlacement.objects.get(id=placement_id)
    except PromotionPlacement.DoesNotExist:
        return False

    PromotionClick.objects.create(
        placement=placement,
        user=_resolve_user(user_id),
        ip_address=ip or None,
    )
    return True
