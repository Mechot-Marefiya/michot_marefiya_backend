from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from apps.account.models import normalize_phone_number
from .models import Favorite, GuestFavorite
from django.db import IntegrityError
from django.utils import timezone


def _build_snapshot_for_object(ct, obj):
    # minimal, safe snapshot builder. extend per-model as needed
    snapshot = {"id": str(getattr(obj, "id", "")), "type": f"{ct.app_label}.{ct.model}"}

    # HotelProfile best-effort fields
    if ct.model == "hotelprofile":
        # try company name or object name
        company = getattr(obj, "company", None)
        title = None
        if company is not None:
            title = getattr(company, "name", None)
        if not title:
            title = getattr(obj, "name", None)
        if title:
            snapshot["title"] = str(title)

        # try to get first image url
        images = getattr(obj, "images", None)
        if images is not None:
            try:
                first = images.first()
                if first and hasattr(first, "file"):
                    url = getattr(first.file, "url", None)
                    if url:
                        snapshot["thumbnail"] = str(url)
            except Exception:
                pass

    # include currency if present on object (generic)
    try:
        if hasattr(obj, "currency") and getattr(obj, "currency"):
            snapshot["currency"] = str(getattr(obj, "currency"))
    except Exception:
        pass

    return snapshot


def _build_snapshot_for_favorite(favorite):
    """Build a best-effort snapshot from the current favorite target."""
    try:
        ct = favorite.content_type
        target = ct.model_class()._default_manager.filter(pk=favorite.object_id).first()
        if target:
            return _build_snapshot_for_object(ct, target)
    except Exception:
        pass
    return {"id": str(favorite.object_id), "type": f"{favorite.content_type.app_label}.{favorite.content_type.model}"}


class FavoriteSerializer(serializers.ModelSerializer):
    content_type = serializers.CharField(write_only=True)
    object_id = serializers.CharField()
    content_type_display = serializers.SerializerMethodField(read_only=True)
    snapshot = serializers.SerializerMethodField(read_only=True)
    object = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Favorite
        fields = ("id", "content_type", "object_id", "content_type_display", "snapshot", "object", "created_at")
        read_only_fields = ("id", "created_at", "content_type_display", "snapshot")

    def validate(self, attrs):
        ct_label = attrs.get("content_type")
        try:
            if "." in ct_label:
                app_label, model = ct_label.split(".")
                ct = ContentType.objects.get(app_label=app_label, model=model.lower())
            else:
                ct = ContentType.objects.get(pk=int(ct_label))
        except Exception:
            raise serializers.ValidationError({"content_type": "Invalid content_type"})

        attrs["content_type_obj"] = ct
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        ct = validated_data.pop("content_type_obj")
        object_id = validated_data.get("object_id")
        # build snapshot first (best-effort)
        snapshot = _build_snapshot_for_favorite(type("FavoriteStub", (), {"content_type": ct, "object_id": object_id})())
        snapshot_at = timezone.now()

        try:
            fav, created = Favorite.objects.get_or_create(
                user=user, content_type=ct, object_id=str(object_id),
                defaults={"snapshot": snapshot, "snapshot_at": snapshot_at},
            )
            # if the favorite exists but snapshot empty, try to update it
            if not created and (not fav.snapshot) and snapshot:
                fav.snapshot = snapshot
                fav.snapshot_at = snapshot_at
                fav.save(update_fields=["snapshot", "snapshot_at"])
            return fav
        except IntegrityError:
            # race: someone else created it; return existing
            return Favorite.objects.filter(user=user, content_type=ct, object_id=str(object_id)).first()

    def update(self, instance, validated_data):
        ct = validated_data.pop("content_type_obj", None)
        if ct is not None:
            instance.content_type = ct
        validated_data.pop("content_type", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        refreshed_snapshot = _build_snapshot_for_favorite(instance)
        instance.snapshot = refreshed_snapshot
        instance.snapshot_at = timezone.now()
        instance.save(update_fields=["snapshot", "snapshot_at"])
        return instance

    def get_content_type_display(self, obj):
        return f"{obj.content_type.app_label}.{obj.content_type.model}"

    def get_snapshot(self, obj):
        if obj.snapshot:
            result = dict(obj.snapshot)
            if obj.snapshot_at:
                result["snapshot_at"] = obj.snapshot_at.isoformat()
            return result
        return _build_snapshot_for_favorite(obj)

    def get_object(self, obj):
        return self.get_snapshot(obj)


class GuestFavoriteSerializer(serializers.ModelSerializer):
    content_type = serializers.CharField(write_only=True)
    object_id = serializers.CharField()
    guest_phone = serializers.CharField()
    content_type_display = serializers.SerializerMethodField(read_only=True)
    snapshot = serializers.SerializerMethodField(read_only=True)
    object = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GuestFavorite
        fields = (
            "id",
            "guest_phone",
            "content_type",
            "object_id",
            "content_type_display",
            "snapshot",
            "object",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "content_type_display", "snapshot", "object")

    def validate_guest_phone(self, value):
        normalized_phone = normalize_phone_number(value)
        if not normalized_phone:
            raise serializers.ValidationError("guest_phone is required.")
        return normalized_phone

    def validate(self, attrs):
        ct_label = attrs.get("content_type")
        try:
            if "." in ct_label:
                app_label, model = ct_label.split(".")
                ct = ContentType.objects.get(app_label=app_label, model=model.lower())
            else:
                ct = ContentType.objects.get(pk=int(ct_label))
        except Exception:
            raise serializers.ValidationError({"content_type": "Invalid content_type"})

        attrs["content_type_obj"] = ct
        return attrs

    def create(self, validated_data):
        guest_phone = validated_data["guest_phone"]
        ct = validated_data.pop("content_type_obj")
        object_id = validated_data.get("object_id")
        snapshot = _build_snapshot_for_favorite(
            type("FavoriteStub", (), {"content_type": ct, "object_id": object_id})()
        )
        snapshot_at = timezone.now()

        try:
            favorite, created = GuestFavorite.objects.get_or_create(
                guest_phone=guest_phone,
                content_type=ct,
                object_id=str(object_id),
                defaults={"snapshot": snapshot, "snapshot_at": snapshot_at},
            )
            if not created and (not favorite.snapshot) and snapshot:
                favorite.snapshot = snapshot
                favorite.snapshot_at = snapshot_at
                favorite.save(update_fields=["snapshot", "snapshot_at"])
            return favorite
        except IntegrityError:
            return GuestFavorite.objects.filter(
                guest_phone=guest_phone,
                content_type=ct,
                object_id=str(object_id),
            ).first()

    def get_content_type_display(self, obj):
        return f"{obj.content_type.app_label}.{obj.content_type.model}"

    def get_snapshot(self, obj):
        if obj.snapshot:
            result = dict(obj.snapshot)
            if obj.snapshot_at:
                result["snapshot_at"] = obj.snapshot_at.isoformat()
            return result
        return _build_snapshot_for_favorite(obj)

    def get_object(self, obj):
        return self.get_snapshot(obj)
