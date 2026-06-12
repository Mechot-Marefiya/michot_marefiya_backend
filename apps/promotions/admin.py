from django.contrib import admin

from apps.promotions.models import (
    PromotionCampaign,
    PromotionClick,
    PromotionImpression,
    PromotionPlacement,
)
from apps.promotions.services import activate_campaign, deactivate_campaign


class PromotionPlacementInline(admin.TabularInline):
    model = PromotionPlacement
    extra = 0
    fields = ("slot_type", "content_type", "object_id", "target_category", "display_order", "is_active")


@admin.register(PromotionCampaign)
class PromotionCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "starts_at", "ends_at", "advertiser")
    list_filter = ("status",)
    search_fields = ("name", "advertiser__email", "advertiser__phone")
    inlines = [PromotionPlacementInline]
    actions = ["activate_selected_campaigns", "deactivate_selected_campaigns"]

    @admin.action(description="Activate selected campaigns")
    def activate_selected_campaigns(self, request, queryset):
        for campaign in queryset:
            activate_campaign(campaign)

    @admin.action(description="Expire selected campaigns")
    def deactivate_selected_campaigns(self, request, queryset):
        for campaign in queryset:
            deactivate_campaign(campaign)


@admin.register(PromotionPlacement)
class PromotionPlacementAdmin(admin.ModelAdmin):
    list_display = ("campaign", "slot_type", "content_object", "target_category", "is_active", "display_order")
    list_filter = ("slot_type", "is_active")
    search_fields = ("campaign__name", "target_category")


@admin.register(PromotionImpression)
class PromotionImpressionAdmin(admin.ModelAdmin):
    list_display = ("placement", "user", "ip_address", "recorded_at")
    list_filter = ("recorded_at",)


@admin.register(PromotionClick)
class PromotionClickAdmin(admin.ModelAdmin):
    list_display = ("placement", "user", "ip_address", "recorded_at")
    list_filter = ("recorded_at",)
