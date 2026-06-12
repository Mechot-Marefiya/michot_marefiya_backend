from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import OpenApiTypes, extend_schema_field, inline_serializer
from rest_framework import serializers

from apps.promotions.models import (
    PromotionCampaign,
    PromotionClick,
    PromotionImpression,
    PromotionPlacement,
)
from apps.promotions.services import get_promotable_content_type_ids


class PromotionPlacementSerializer(serializers.ModelSerializer):
    content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PromotionPlacement
        fields = [
            "id",
            "campaign",
            "slot_type",
            "content_type",
            "object_id",
            "target_category",
            "display_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        content_type = attrs.get("content_type", getattr(self.instance, "content_type", None))
        object_id = attrs.get("object_id", getattr(self.instance, "object_id", None))
        category = attrs.get("target_category", getattr(self.instance, "target_category", None))

        if bool(content_type) != bool(object_id):
            raise serializers.ValidationError(
                {"target": "content_type and object_id must be provided together."}
            )
        if not content_type and not category:
            raise serializers.ValidationError(
                {"target": "Provide either a promoted listing target or target_category."}
            )
        if content_type and content_type.id not in get_promotable_content_type_ids():
            raise serializers.ValidationError({"content_type": "Content type is not promotable."})
        if content_type:
            try:
                content_type.get_object_for_this_type(id=object_id)
            except content_type.model_class().DoesNotExist:
                raise serializers.ValidationError({"object_id": "Promoted listing target does not exist."})

        return attrs


class PromotionCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionCampaign
        fields = [
            "id",
            "name",
            "advertiser",
            "status",
            "starts_at",
            "ends_at",
            "budget",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "ends_at must be after starts_at."})
        return attrs


class PromotionCampaignDetailSerializer(PromotionCampaignSerializer):
    placements = PromotionPlacementSerializer(many=True, read_only=True)

    class Meta(PromotionCampaignSerializer.Meta):
        fields = PromotionCampaignSerializer.Meta.fields + ["placements"]


class PublicPlacementSerializer(serializers.ModelSerializer):
    promoted_listing = serializers.SerializerMethodField()
    promoted_category = serializers.SerializerMethodField()

    class Meta:
        model = PromotionPlacement
        fields = [
            "id",
            "slot_type",
            "display_order",
            "promoted_listing",
            "promoted_category",
        ]
        read_only_fields = fields

    def _thumbnail_url(self, listing):
        images = getattr(listing, "images", None)
        if images is None:
            return None
        image = images.order_by("-is_primary", "created_at").first()
        if not image or not getattr(image, "image", None):
            return None
        request = self.context.get("request")
        url = image.image.url
        return request.build_absolute_uri(url) if request else url

    @extend_schema_field(inline_serializer(
        name="PromotedListingSnapshot",
        fields={
            "id": serializers.UUIDField(),
            "title": serializers.CharField(),
            "thumbnail": serializers.URLField(allow_null=True),
            "category": serializers.CharField(),
            "rating": serializers.FloatField(allow_null=True),
            "price_preview": serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True),
            "currency": serializers.CharField(),
            "listing_type": serializers.CharField(),
        },
        allow_null=True,
    ))
    def get_promoted_listing(self, obj) -> dict | None:
        listing = obj.content_object
        if listing is None:
            return None

        return {
            "id": str(listing.id),
            "title": getattr(listing, "title", None) or getattr(listing, "name", ""),
            "thumbnail": self._thumbnail_url(listing),
            "category": obj.target_category or obj.content_type.model,
            "rating": getattr(listing, "rating", None),
            "price_preview": getattr(listing, "base_price", None),
            "currency": getattr(listing, "currency", "ETB"),
            "listing_type": obj.content_type.model,
        }

    @extend_schema_field(inline_serializer(
        name="PromotedCategorySnapshot",
        fields={
            "id": serializers.CharField(),
            "name": serializers.CharField(),
        },
        allow_null=True,
    ))
    def get_promoted_category(self, obj) -> dict | None:
        if not obj.target_category:
            return None
        return {
            "id": obj.target_category,
            "name": obj.target_category.replace("_", " ").title(),
        }


class TrackingEventSerializer(serializers.Serializer):
    placement_id = serializers.UUIDField()
    event_type = serializers.CharField()

    def validate_event_type(self, value):
        if value not in {"impression", "click"}:
            raise serializers.ValidationError("event_type must be impression or click.")
        return value

    def validate_placement_id(self, value):
        try:
            self.placement = PromotionPlacement.objects.get(id=value)
        except PromotionPlacement.DoesNotExist:
            raise serializers.ValidationError("Promotion placement does not exist.")
        return value
