from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.promotions.models import PromotionCampaign, PromotionPlacement
from apps.promotions.services import invalidate_active_placement_cache


@receiver(post_save, sender=PromotionCampaign)
@receiver(post_delete, sender=PromotionCampaign)
@receiver(post_save, sender=PromotionPlacement)
@receiver(post_delete, sender=PromotionPlacement)
def invalidate_promotion_cache_on_change(**kwargs):
    invalidate_active_placement_cache()
